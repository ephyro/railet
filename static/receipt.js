/* SPDX-License-Identifier: MPL-2.0 */
(() => {
  const button = document.querySelector('[data-print-receipt]');
  const help = document.querySelector('[data-print-help]');
  if (!button || typeof window.print !== 'function') return;
  button.hidden = false;
  button.addEventListener('click', () => {
    try { window.print(); }
    catch (_) {
      help.hidden = false;
      help.textContent = 'Open your browser’s Print menu to print this receipt or save it as a PDF.';
    }
  });
})();
