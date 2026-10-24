// SPDX-License-Identifier: MPL-2.0
document.querySelectorAll('[data-filter-builder]').forEach(form => {
  const schema = JSON.parse(form.querySelector('script[type="application/json"]').textContent);
  const rules = form.querySelector('[data-filter-rules]');
  const add = form.querySelector('[data-add-rule]');
  const template = rules.firstElementChild.cloneNode(true);
  const option = (value, label) => new Option(label, value);
  const configure = (row, preserve = false) => {
    const field = row.querySelector('[data-rule-field]');
    const operator = row.querySelector('[data-rule-op]');
    const spec = schema.find(item => item.key === field.value);
    const priorOperator = operator.value;
    const priorValue = row.querySelector('[name="filter_value"]').value;
    operator.replaceChildren(...(spec?.operators || [['eq', 'is']]).map(([key, label]) => option(key, label)));
    if (preserve && [...operator.options].some(item => item.value === priorOperator)) operator.value = priorOperator;
    let input;
    if (spec?.choices.length) {
      input = document.createElement('select');
      input.append(option('', 'Choose a value'), ...spec.choices.map(([key, label]) => option(key, label)));
    } else {
      input = document.createElement('input');
      input.type = spec?.kind === 'date' ? 'date' : 'text';
      input.maxLength = 200;
      if (['integer', 'decimal'].includes(spec?.kind)) input.inputMode = 'decimal';
    }
    input.name = 'filter_value';
    if (preserve) input.value = priorValue;
    row.querySelector('[data-rule-value]').replaceChildren(input);
    const upper = row.querySelector('[name="filter_to"]');
    upper.type = spec?.kind === 'date' ? 'date' : 'text';
    if (!preserve) upper.value = '';
    updateOperator(row);
  };
  const updateOperator = row => {
    const op = row.querySelector('[data-rule-op]').value;
    row.querySelector('[data-rule-upper-label]').hidden = op !== 'between';
    row.querySelector('[data-rule-value-label]').hidden = ['empty', 'not_empty'].includes(op);
  };
  const updateLimit = () => { add.disabled = rules.children.length >= 10; };
  const bind = row => {
    row.querySelector('[data-rule-field]').addEventListener('change', () => configure(row));
    row.querySelector('[data-rule-op]').addEventListener('change', () => updateOperator(row));
    const remove = row.querySelector('[data-remove-rule]');
    remove.hidden = false;
    remove.addEventListener('click', () => { row.remove(); updateLimit(); add.focus(); });
    configure(row, true);
  };
  [...rules.children].forEach(bind);
  add.hidden = false;
  add.addEventListener('click', () => {
    if (rules.children.length >= 10) return;
    const row = template.cloneNode(true);
    row.querySelector('[data-rule-field]').value = '';
    row.querySelector('[name="filter_value"]').value = '';
    row.querySelector('[name="filter_to"]').value = '';
    rules.append(row);
    bind(row);
    updateLimit();
    row.querySelector('[data-rule-field]').focus();
  });
  updateLimit();
});
