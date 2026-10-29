// SPDX-License-Identifier: MPL-2.0
(() => {
  const form = document.querySelector('[data-deal-workspace]');
  if (!form) return;
  const fields = [...form.querySelectorAll('[data-money-field]')];
  const summary = form.querySelector('.deal-summary');
  const help = form.querySelector('[data-summary-help]');
  const tabs = [...form.querySelectorAll('[data-deal-tab]')];
  const panels = [...form.querySelectorAll('[data-deal-panel]')];
  const activeSection = form.querySelector('[data-active-section]');
  form.querySelector('[data-deal-tabs]').setAttribute('role', 'tablist');
  const activate = (id, focus = false) => {
    if (!panels.some(panel => panel.id === id)) id = 'deal-structure';
    panels.forEach(panel => {
      panel.hidden = panel.id !== id;
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', `${panel.id}-tab`);
    });
    tabs.forEach(tab => {
      const selected = tab.hash === `#${id}`;
      tab.id = `${tab.hash.slice(1)}-tab`;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', tab.hash.slice(1));
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    });
    activeSection.value = id.replace('deal-', '');
    window.history.replaceState(null, '', `#${id}`);
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', event => { event.preventDefault(); activate(tab.hash.slice(1)); });
    tab.addEventListener('keydown', event => {
      const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
        : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
      if (next !== null) { event.preventDefault(); activate(tabs[next].hash.slice(1), true); }
    });
  });
  const dealType = form.querySelector('[data-deal-type]');
  const proposals = [...form.querySelectorAll('[data-finance-proposal]')];
  const updateType = () => {
    proposals.forEach(proposal => {
      const active = proposal.dataset.financeProposal === dealType.value;
      proposal.hidden = !active && proposal.dataset.hasErrors !== 'true';
      proposal.querySelector('[data-inactive-proposal]').hidden = active;
    });
    form.querySelector('[data-type-summary]').textContent = dealType.selectedOptions[0]?.textContent || 'Not chosen';
  };
  dealType.addEventListener('change', () => {
    updateType();
    const selected = proposals.find(proposal => proposal.dataset.financeProposal === dealType.value);
    if (selected) selected.open = true;
  });
  updateType();
  const reveal = field => {
    const proposal = field.closest('[data-finance-proposal]');
    if (proposal) proposal.hidden = false;
    const panel = field.closest('[data-deal-panel]');
    if (panel) activate(panel.id);
    for (let parent = field.parentElement; parent && parent !== form; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
  };
  form.addEventListener('focusin', event => {
    const field = event.target;
    if (!field.matches('input:not([type="hidden"]), select, textarea')) return;
    const heading = form.querySelector('.deal-heading');
    if (field.getBoundingClientRect().top < heading.getBoundingClientRect().bottom + 8) {
      field.scrollIntoView({block: 'center'});
    }
  });
  const invalid = form.querySelector('[aria-invalid="true"]');
  const errorPanel = invalid?.closest('[data-deal-panel]')?.id || (form.querySelector('.deal-errors') ? 'deal-structure' : null);
  activate(errorPanel || window.location.hash.slice(1) || `deal-${activeSection.value}`);
  form.addEventListener('invalid', event => reveal(event.target), true);
  form.querySelectorAll('.deal-errors a[href^="#"]').forEach(link => link.addEventListener('click', event => {
    const field = document.getElementById(link.hash.slice(1));
    if (field) { event.preventDefault(); reveal(field); field.focus(); }
  }));

  // Keep the draft preview in integer cents. The server validates and saves it.
  const cents = value => {
    const match = /^(\d*)(?:\.(\d{0,2}))?$/.exec(value.trim());
    if (!match || (!match[1] && !match[2])) return null;
    return BigInt(match[1] || '0') * 100n + BigInt((match[2] || '').padEnd(2, '0'));
  };
  const money = value => {
    const absolute = value < 0n ? -value : value;
    return `${value < 0n ? '−' : ''}$${(absolute / 100n).toLocaleString('en-US')}.${(absolute % 100n).toString().padStart(2, '0')}`;
  };
  const update = () => {
    const values = Object.fromEntries(fields.map(field => [field.dataset.moneyField, cents(field.value)]));
    const valid = Object.values(values).every(value => value !== null);
    if (!valid) {
      form.querySelectorAll('[data-summary]').forEach(output => { output.textContent = '—'; });
      summary.dataset.negative = 'false';
      help.textContent = 'Enter valid amounts to update the estimate.';
      return;
    }
    const totals = {
      price: values.sale_price,
      fees: values.tax + values.title_registration + values.dealer_fee,
      trade_allowance: values.trade_allowance,
      trade_payoff: values.trade_payoff,
      down_payment: values.down_payment,
    };
    totals.balance = totals.price + totals.fees + totals.trade_payoff - totals.trade_allowance - totals.down_payment;
    totals.trade_adjustment = totals.trade_payoff - totals.trade_allowance;
    form.querySelectorAll('[data-summary]').forEach(output => {
      const name = output.dataset.summary;
      const subtract = !output.hasAttribute('data-summary-unsigned') && ['trade_allowance', 'down_payment'].includes(name) && totals[name] !== 0n;
      output.textContent = (subtract ? '−' : '') + money(totals[name]);
    });
    form.querySelectorAll('[data-summary-row]').forEach(row => { row.hidden = totals[row.dataset.summaryRow] === 0n; });
    summary.dataset.negative = String(totals.balance < 0n);
    help.textContent = totals.balance < 0n ? 'Check the amounts. The draft balance is below zero.' : 'Draft estimate. Review taxes and fees before paperwork.';
  };
  fields.forEach(field => field.addEventListener('input', update));
  update();
})();
