# SPDX-License-Identifier: MPL-2.0
"""Offline invented account-summary comparison; never a migration or ledger.

Inputs are explicitly supplied, synthetic-only examples. The source is the
comparison reference, not proof of authoritative records; the target is a
candidate. No database, files, provider, posting or cutover is touched.
"""
from collections import Counter, defaultdict
from datetime import date
import re

from django.conf import settings
from django.core.exceptions import PermissionDenied

FORMAT_VERSION = 'synthetic-account-reconciliation-v2'
MAX_RECORDS = 10000
MAX_ABS_CENTS = 999999999999
AMOUNTS = ('principal_cents', 'interest_cents', 'fees_cents', 'unapplied_cents')


class ReconciliationInputError(ValueError):
    """Invalid input; no comparison or partial output is returned."""


def _identifier(value, kind):
    if not isinstance(value, str) or re.fullmatch(r'SYNTH-' + kind + r'-[A-Z]{1,20}', value) is None:
        raise ReconciliationInputError('Use the required invented identifier format.')
    return value


def _rows(value, kind):
    if type(value) is not list or len(value) > MAX_RECORDS:
        raise ReconciliationInputError('Provide a bounded list of synthetic summaries.')
    required = {'record_id', 'match_id', *AMOUNTS}
    output = []
    for item in value:
        if type(item) is not dict or set(item) != required:
            raise ReconciliationInputError('Each summary must contain exactly the specified fields.')
        _identifier(item['record_id'], kind)
        if item['match_id'] is not None:
            _identifier(item['match_id'], 'MAP')
        for field in AMOUNTS:
            if item[field] is not None and (type(item[field]) is not int or abs(item[field]) > MAX_ABS_CENTS):
                raise ReconciliationInputError('Amounts must be bounded signed integer cents.')
        output.append(dict(item))
    return output


def compare_synthetic(*, source, target, source_provenance, target_provenance, as_of, synthetic_only):
    """Compare two invented lists; return all exceptions or reject invalid input.

    `match_id=None` explicitly records an unresolved mapping. Duplicate record
    or mapping identifiers are exceptions, never arbitrarily paired. Aggregate
    totals are unavailable if mappings are ambiguous or unresolved; otherwise
    each side is summed independently, including uniquely mapped missing rows.
    """
    if not (getattr(settings, 'DEBUG', False) and getattr(settings, 'DEMO_LEDGER_ENABLED', False)
            and getattr(settings, 'SYNTHETIC_RECONCILIATION_ENABLED', False) and synthetic_only is True):
        raise PermissionDenied('Offline synthetic reconciliation is disabled.')
    _identifier(source_provenance, 'PROV')
    _identifier(target_provenance, 'PROV')
    if source_provenance == target_provenance:
        raise ReconciliationInputError('Source and target provenance must be distinct.')
    if type(as_of) is not str:
        raise ReconciliationInputError('Provide a common ISO date for both summaries.')
    try:
        parsed = date.fromisoformat(as_of)
    except ValueError as error:
        raise ReconciliationInputError('Provide a common ISO date for both summaries.') from error
    if parsed.isoformat() != as_of:
        raise ReconciliationInputError('Provide a common ISO date for both summaries.')
    source = _rows(source, 'SRC')
    target = _rows(target, 'TGT')
    if not source and not target:
        raise ReconciliationInputError('Provide at least one synthetic account summary.')
    exceptions = []
    groups = {}
    unsafe = set()
    unresolved = False
    for side, rows in (('source', source), ('target', target)):
        counts = Counter(row['record_id'] for row in rows)
        by_match = defaultdict(list)
        for row in rows:
            for field in AMOUNTS:
                if row[field] is None:
                    exceptions.append({'kind': 'unknown_amount', 'side': side, 'record_id': row['record_id'],
                                       'match_id': row['match_id'], 'field': field})
            if row['match_id'] is None:
                exceptions.append({'kind': 'unresolved_mapping', 'side': side, 'record_id': row['record_id']})
                unresolved = True
            else:
                by_match[row['match_id']].append(row)
                if counts[row['record_id']] > 1:
                    unsafe.add(row['match_id'])
        for record_id, count in sorted(counts.items()):
            if count > 1:
                exceptions.append({'kind': 'duplicate_record_id', 'side': side, 'record_id': record_id, 'count': count})
                unresolved = True
        for match_id, items in sorted(by_match.items()):
            if len(items) > 1:
                exceptions.append({'kind': 'duplicate_mapping', 'side': side, 'match_id': match_id,
                                   'record_ids': sorted(row['record_id'] for row in items)})
                unsafe.add(match_id)
                unresolved = True
        groups[side] = by_match
    accounts = []
    for match_id in sorted(set(groups['source']) | set(groups['target'])):
        if match_id in unsafe:
            continue
        left = groups['source'].get(match_id, [])
        right = groups['target'].get(match_id, [])
        if not left or not right:
            side = 'source' if not left else 'target'
            exceptions.append({'kind': 'missing_account', 'missing_side': side, 'match_id': match_id})
            accounts.append({'match_id': match_id, 'status': 'missing_' + side,
                             'source_record_id': left[0]['record_id'] if left else None,
                             'target_record_id': right[0]['record_id'] if right else None,
                             'source_cents': {field: left[0][field] for field in AMOUNTS} if left else None,
                             'target_cents': {field: right[0][field] for field in AMOUNTS} if right else None})
            continue
        left, right = left[0], right[0]
        unknown = any(left[field] is None or right[field] is None for field in AMOUNTS)
        differences = {field: right[field] - left[field] for field in AMOUNTS
                       if left[field] is not None and right[field] is not None and right[field] != left[field]}
        if differences:
            exceptions.append({'kind': 'amount_mismatch', 'match_id': match_id, 'target_minus_source_cents': differences})
        accounts.append({'match_id': match_id, 'status': 'mismatch' if differences else 'incomplete' if unknown else 'match',
                         'source_record_id': left['record_id'], 'target_record_id': right['record_id'],
                         'source_cents': {field: left[field] for field in AMOUNTS},
                         'target_cents': {field: right[field] for field in AMOUNTS}})
    aggregate = None
    if unresolved:
        exceptions.append({'kind': 'aggregate_unavailable', 'reason': 'duplicate_or_unresolved_mapping'})
    else:
        left = {field: None if any(row[field] is None for row in source) else sum(row[field] for row in source) for field in AMOUNTS}
        right = {field: None if any(row[field] is None for row in target) else sum(row[field] for row in target) for field in AMOUNTS}
        delta = {field: None if left[field] is None or right[field] is None else right[field] - left[field] for field in AMOUNTS}
        aggregate = {'source_cents': left, 'target_cents': right, 'target_minus_source_cents': delta}
        if any(value is not None and value != 0 for value in delta.values()):
            exceptions.append({'kind': 'aggregate_mismatch', 'target_minus_source_cents': delta})
    exceptions.sort(key=lambda item: (item['kind'], item.get('side', item.get('missing_side', '')),
                                      item.get('match_id') or '', item.get('record_id', ''), item.get('field', '')))
    return {'format': FORMAT_VERSION, 'synthetic_only': True, 'as_of': as_of,
            'source_provenance': source_provenance, 'target_provenance': target_provenance,
            'source_role': 'comparison_reference', 'target_role': 'candidate',
            'source_count': len(source), 'target_count': len(target), 'accounts': accounts,
            'aggregate': aggregate, 'exceptions': exceptions, 'has_exceptions': bool(exceptions),
            'comparison_complete': not unresolved and not any(item['kind'] in ('missing_account', 'unknown_amount') for item in exceptions),
            'reconciled': not exceptions}
