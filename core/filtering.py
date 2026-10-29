# SPDX-License-Identifier: MPL-2.0
"""Typed, allowlisted filters applied only to a caller's authorized queryset."""
from dataclasses import dataclass, field
from functools import reduce
from operator import and_, or_
from urllib.parse import urlencode, quote

from django import forms
from django.db.models import Q

OPERATORS = {
    "eq": "is", "ne": "is not", "contains": "contains", "not_contains": "does not contain",
    "starts": "starts with", "gte": "is at least", "lte": "is at most",
    "between": "between", "empty": "is empty", "not_empty": "is not empty",
}
KINDS = {
    "text": ("contains", "not_contains", "eq", "ne", "starts", "empty", "not_empty"),
    "choice": ("eq", "ne"), "boolean": ("eq",),
    "integer": ("eq", "ne", "gte", "lte", "between"),
    "decimal": ("eq", "ne", "gte", "lte", "between"),
    "date": ("eq", "gte", "lte", "between"),
}


@dataclass(frozen=True)
class FilterField:
    key: str
    label: str
    lookup: str
    kind: str = "text"
    choices: tuple = ()

    def convert(self, value):
        validators = {
            "text": forms.CharField(max_length=200),
            "integer": forms.IntegerField(min_value=-2147483648, max_value=2147483647),
            "decimal": forms.DecimalField(max_digits=14, decimal_places=2),
            "date": forms.DateField(input_formats=["%Y-%m-%d"]),
            "choice": forms.ChoiceField(choices=self.choices),
            "boolean": forms.ChoiceField(choices=[("true", "Yes"), ("false", "No")]),
        }
        result = validators[self.kind].clean(value)
        return result == "true" if self.kind == "boolean" else result

    @property
    def metadata(self):
        labels = {**OPERATORS, **({"eq": "is on", "gte": "is on or after", "lte": "is on or before"} if self.kind == "date" else {})}
        return {"key": self.key, "label": self.label, "kind": self.kind, "choices": list(self.choices) if self.kind != "boolean" else [("true", "Yes"), ("false", "No")], "operators": [(key, labels[key]) for key in KINDS[self.kind]]}


@dataclass(frozen=True)
class FilterSchema:
    resource: str
    title: str
    route: str
    fields: tuple
    sorts: dict
    default_sort: str = "recent"
    search_hint: str = "Search"
    extras: dict = field(default_factory=dict)
    enabled_setting: str | None = None


class FilterState:
    max_rules = 10

    def __init__(self, schema, parameters):
        self.schema = schema
        self.errors, self.rows, self.conditions = [], [], []
        self.query = parameters.get("q", "").strip()[:200]
        try:
            self.query = forms.CharField(required=False, max_length=200).clean(self.query)
        except forms.ValidationError:
            self.errors.append("Remove unsupported characters from the search text.")
        self.match = parameters.get("match", "all")
        self.sort = parameters.get("sort", schema.default_sort)
        if self.match not in ("all", "any"):
            self.errors.append("Choose whether to match all or any rules.")
        if self.sort not in schema.sorts:
            self.errors.append("Choose an available sort order.")
        self.extra = {}
        for key, choices in schema.extras.items():
            value = parameters.get(key, "")
            if value and value not in choices:
                self.errors.append(f"Choose an available {key} filter.")
            self.extra[key] = value[:200]
        columns = [parameters.getlist(key) for key in ("filter_field", "filter_op", "filter_value", "filter_to")]
        count = max(map(len, columns), default=0)
        if count > self.max_rules:
            self.errors.append(f"Use up to {self.max_rules} rules per view.")
        fields = {item.key: item for item in schema.fields}
        for index in range(min(count, self.max_rules)):
            key, operator, value, upper = [column[index] if index < len(column) else "" for column in columns]
            if not key and not value and not upper:
                continue
            spec = fields.get(key)
            row = {"field": key, "op": operator, "value": value[:200], "upper": upper[:200], "spec": spec, "operators": spec.metadata["operators"] if spec else [("eq", "is")], "choices": spec.metadata["choices"] if spec else []}
            self.rows.append(row)
            labels = dict(row["choices"])
            display = labels.get(value, value)
            row["summary"] = f"{spec.label if spec else 'Field'} {dict(row['operators']).get(operator, 'comparison')} {display}" + (f" – {upper}" if operator == "between" else "")
            try:
                if not spec or operator not in KINDS[spec.kind]:
                    raise forms.ValidationError("Choose an available field and comparison.")
                if len(value) > 200 or len(upper) > 200:
                    raise forms.ValidationError("Keep each filter value under 200 characters.")
                if operator in ("empty", "not_empty"):
                    condition = Q(**{spec.lookup: ""}) | Q(**{spec.lookup + "__isnull": True})
                    if operator == "not_empty":
                        condition = ~condition
                else:
                    converted = spec.convert(value)
                    if operator == "between":
                        end = spec.convert(upper)
                        if converted > end:
                            raise forms.ValidationError("The first value must not be greater than the second.")
                        condition = Q(**{spec.lookup + "__range": (converted, end)})
                    else:
                        lookup = {"eq": "exact", "ne": "exact", "contains": "icontains", "not_contains": "icontains", "starts": "istartswith", "gte": "gte", "lte": "lte"}[operator]
                        condition = Q(**{spec.lookup + "__" + lookup: converted})
                        if operator in ("ne", "not_contains"):
                            condition = ~condition
                self.conditions.append(condition)
            except forms.ValidationError as error:
                row["error"] = " ".join(error.messages)
                self.errors.append(f"Rule {index + 1}: {row['error']}")
        self.parameters = {"q": [self.query], "sort": [self.sort], "match": [self.match], **{key: [value] for key, value in self.extra.items() if value}}
        for key, column in (("filter_field", "field"), ("filter_op", "op"), ("filter_value", "value"), ("filter_to", "upper")):
            self.parameters[key] = [row[column] for row in self.rows]
        self.querystring = urlencode(self.parameters, doseq=True, quote_via=quote)
        for index, row in enumerate(self.rows):
            reduced = {key: list(values) for key, values in self.parameters.items()}
            for key in ("filter_field", "filter_op", "filter_value", "filter_to"):
                reduced[key].pop(index)
            row["remove_query"] = urlencode(reduced, doseq=True, quote_via=quote)
        self.metadata = [item.metadata for item in schema.fields]
        self.sort_label = schema.sorts.get(self.sort, ("Choose a sort order", ()))[0]

    def apply(self, queryset):
        if self.errors:
            return queryset.none()
        if self.conditions:
            queryset = queryset.filter(reduce(and_ if self.match == "all" else or_, self.conditions))
        return queryset.order_by(*self.schema.sorts[self.sort][1])

    @property
    def render_rows(self):
        return self.rows or [{"field": "", "op": "eq", "value": "", "upper": "", "spec": None, "operators": [("eq", "is")], "choices": []}]
