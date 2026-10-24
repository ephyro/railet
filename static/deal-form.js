// SPDX-License-Identifier: MPL-2.0
(() => {
  const form = document.querySelector('[data-unsaved-form]');
  if (!form) return;
  const existing = form.querySelector('[data-customer-existing]');
  const added = form.querySelector('[data-customer-new]');
  const update = () => {
    const isNew = form.querySelector('[name="customer_mode"]:checked')?.value === 'new';
    existing.hidden = isNew;
    added.hidden = !isNew;
    // Avoid invisible HTML-required errors; the server validates the selected path.
    added.querySelectorAll('input').forEach(input => { input.disabled = !isNew; });
    existing.querySelectorAll('select').forEach(input => { input.disabled = isNew; });
  };
  form.querySelectorAll('[name="customer_mode"]').forEach(input => input.addEventListener('change', update));
  form.querySelectorAll('[data-use-customer]').forEach(button => button.addEventListener('click', () => {
    form.querySelector('[name="buyer"]').value = button.dataset.useCustomer;
    form.querySelector('[name="customer_mode"][value="existing"]').checked = true;
    update();
    form.querySelector('[name="buyer"]').focus();
    form.dispatchEvent(new Event('change', { bubbles: true }));
  }));
  update();
})();
