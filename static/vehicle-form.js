// SPDX-License-Identifier: MPL-2.0
(() => {
  const form = document.querySelector('[data-unsaved-form]');
  if (!form) return;
  const status = form.querySelector('[data-save-status]');
  const submitButton = form.querySelector('button[type="submit"], button:not([type])');
  const buttonLabel = submitButton?.textContent;
  const buttonDisabled = submitButton?.disabled;
  const fields = [...form.elements].filter(field => field.name && field.type !== 'hidden' && field.type !== 'submit');
  const snapshot = () => JSON.stringify(fields.map(field => [field.name, ['checkbox', 'radio'].includes(field.type) ? field.checked : field.value]));
  const initial = snapshot();
  const hadRejectedSubmission = form.dataset.bound === 'true';
  let submitting = false;
  const dirty = () => hadRejectedSubmission || snapshot() !== initial;
  const update = () => {
    if (status) status.textContent = submitting ? 'Saving…' : dirty() ? 'Unsaved changes' : (form.dataset.cleanStatus || '');
  };
  const reveal = field => {
    for (let parent = field.parentElement; parent && parent !== form; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
  };
  form.addEventListener('focusin', event => {
    const actions = form.querySelector('.entry-actions');
    if (!actions || actions.contains(event.target)) return;
    requestAnimationFrame(() => {
      const field = event.target.getBoundingClientRect();
      const bar = actions.getBoundingClientRect();
      if (field.bottom > bar.top && field.top < bar.bottom) {
        event.target.scrollIntoView({block: 'center'});
      }
    });
  });
  form.addEventListener('invalid', event => { reveal(event.target); }, true);
  form.querySelectorAll('[data-error-summary] a[href^="#"]').forEach(link => {
    link.addEventListener('click', event => {
      const field = document.getElementById(link.hash.slice(1));
      if (field && form.contains(field)) {
        event.preventDefault(); reveal(field); field.focus();
      }
    });
  });
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  form.addEventListener('submit', () => {
    submitting = true;
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = form.dataset.submitLabel || 'Saving…';
    }
    update();
  });
  window.addEventListener('pageshow', () => {
    submitting = false;
    if (submitButton) {
      submitButton.disabled = buttonDisabled;
      submitButton.textContent = buttonLabel;
    }
    update();
  });
  window.addEventListener('beforeunload', event => {
    if (!submitting && dirty()) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  document.querySelector('[data-error-summary]')?.focus();
  update();
})();
