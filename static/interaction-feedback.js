// SPDX-License-Identifier: MPL-2.0
(() => {
  const revealAnchor = () => {
    document.querySelectorAll('details[data-open-for-anchor]').forEach(details => {
      if (location.hash === '#' + details.dataset.openForAnchor) {
        details.open = true;
        requestAnimationFrame(() => document.getElementById(details.dataset.openForAnchor)?.scrollIntoView({block: 'start'}));
      }
    });
  };
  revealAnchor();
  window.addEventListener('hashchange', revealAnchor);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const effects = new Set();
  document.querySelectorAll('details').forEach(details => {
    // Keep menus instant; only reveal content following a deliberate summary click.
    if (details.matches('.user-menu, .deal-more, .record-views')) return;
    const summary = details.querySelector(':scope > summary');
    if (!summary) return;
    let activated = false;
    summary.addEventListener('click', () => { activated = true; });
    details.addEventListener('toggle', () => {
      const shouldAnimate = activated && details.open && !reduced.matches;
      activated = false;
      if (!shouldAnimate) return;
      [...details.children].filter(child => child !== summary && child.tagName !== 'SCRIPT').forEach(child => {
        if (!child.animate) return;
        const effect = child.animate([{opacity: 0, transform: 'translateY(-2px)'}, {opacity: 1, transform: 'translateY(0)'}], {duration: 150, easing: 'ease-out'});
        effects.add(effect);
        effect.onfinish = effect.oncancel = () => effects.delete(effect);
      });
    });
  });
  reduced.addEventListener('change', () => {
    if (reduced.matches) effects.forEach(effect => effect.cancel());
  });
  const pending = new Map();
  document.addEventListener('submit', event => {
    const form = event.target;
    if (event.defaultPrevented || !form.matches('form[data-unsaved-form], form[data-pending-label]')) return;
    const button = event.submitter;
    if (!button || pending.has(form)) return;
    const original = button.textContent;
    // Edit also submits a confirmation form: never describe it as posting money.
    const label = button.value === 'edit' ? 'Returning to edit…' : form.dataset.pendingLabel;
    pending.set(form, {button, original});
    form.setAttribute('aria-busy', 'true');
    button.setAttribute('aria-busy', 'true');
    button.classList.add('is-pending');
    if (label) button.textContent = label;
    // Preserve the enabled submitter's name/value for action=open/post/edit.
  });
  window.addEventListener('pageshow', () => {
    pending.forEach(({button, original}, form) => {
      form.removeAttribute('aria-busy');
      button.removeAttribute('aria-busy');
      button.classList.remove('is-pending');
      if (form.dataset.pendingLabel) button.textContent = original;
    });
    pending.clear();
  });
})();
