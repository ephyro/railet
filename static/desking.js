/* SPDX-License-Identifier: MPL-2.0 */
(() => {
 const form=document.querySelector('[data-desk-form]');if(!form)return;
 form.noValidate=false;
 const value=name=>form.querySelector(`[name="${name}"]`)?.value||'';
 const checked=name=>Boolean(form.querySelector(`[name="${name}"]`)?.checked);
 const set=(selector,text)=>form.querySelectorAll(selector).forEach(node=>{node.textContent=text});
 const money=raw=>{const match=/^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(String(raw));if(!match)return '—';const whole=BigInt(match[2]);return `${match[1]?'−':''}$${whole.toLocaleString('en-US')}.${(match[3]||'').padEnd(2,'0')}`;};
 const show=(selector,visible)=>form.querySelectorAll(selector).forEach(node=>{node.hidden=!visible});
 let timer,controller,sequence=0;
 function modes(){
  const auto=value('tax_mode')==='fl';const readOnly=form.querySelector('[name="tax_mode"]')?.disabled;
  show('[data-tax-auto]',auto);show('[data-tax-manual]',!auto);
  show('[data-tax-trade]',auto&&Number(value('trade_allowance'))>0);
  show('[data-tax-title]',auto&&Number(value('title_registration'))>0);
  const tax=form.querySelector('[name="tax"]');if(tax&&!tax.disabled)tax.readOnly=auto;
  form.querySelectorAll('[data-desk-finance]').forEach(section=>{
   const active=section.dataset.deskFinance===value('deal_type');section.hidden=!active;
   section.querySelectorAll('input,select,textarea').forEach(field=>{field.disabled=!active});
  });
  // Keep each method's meaning explicit; a precomputed charge is not an add-on rate.
  form.querySelectorAll('[name$="-illustration_finance_charge"]').forEach(field=>{
   const prefix=field.name.replace('-illustration_finance_charge','');const method=value(`${prefix}-interest_method`);
   const wrapper=field.closest('.field');if(wrapper)wrapper.hidden=method!=='precomputed';
   const rateField=form.querySelector(`[name="${prefix}-annual_contract_rate"]`);if(rateField)rateField.closest('.field').hidden=method!=='simple';
  });
  show('[data-payment-illustration]',form.dataset.estimateEnabled!=='false'&&['bhph','outside'].includes(value('deal_type')));
 }
 async function update(){
  const current=++sequence;controller?.abort();controller=new AbortController();modes();
  if(form.dataset.estimateEnabled==='false'){set('[data-desk-feedback]','Save the draft to see its validated totals.');return;}
  const data=new URLSearchParams();
  for(const name of ['deal_type','sale_price','tax','dealer_fee','title_registration','trade_allowance','trade_payoff','down_payment','tax_mode','tax_county','tax_date','tax_reason'])data.set(name,value(name));
  if(value('tax_mode')==='manual'&&!value('tax_reason')&&form.dataset.legacyTax==='true')data.delete('tax_mode');
  for(const name of ['tax_trade_confirmed','tax_title_confirmed'])if(checked(name))data.set(name,'on');
  for(const prefix of ['bhph','outside'])for(const name of ['interest_method','payment_frequency','payment_count','annual_contract_rate','first_payment_date','creditor_name','illustration_finance_charge'])data.set(`${prefix}-${name}`,value(`${prefix}-${name}`));
  try{
   const response=await fetch(form.dataset.estimateUrl,{method:'POST',headers:{'X-CSRFToken':value('csrfmiddlewaretoken')},body:data,credentials:'same-origin',signal:controller.signal});
   const result=await response.json();if(current!==sequence)return;
   if(!result.ok){
    set('[data-desk-feedback]',result.errors[0]||'Check the draft details.');set('[data-tax-breakdown]',result.errors[0]||'Check the tax details.');
    set('[data-desk-balance],[data-desk-payment],[data-summary]', '—');show('[data-desk-payment-details]',false);
    if(value('tax_mode')==='fl'){const field=form.querySelector('[name="tax"]');if(field)field.value='';}return;
   }
   const totals=result.totals;
   if(result.tax.mode==='fl'){
    const field=form.querySelector('[name="tax"]');if(field)field.value=result.tax.total;
    const rounding=result.tax.rounding_adjustment!=='0.00'?` · Invoice rounding ${money(result.tax.rounding_adjustment)}`:'';
    set('[data-tax-breakdown]',`State 6%: ${money(result.tax.state_tax)} · ${result.tax.county} county: ${money(result.tax.county_tax)} (first $5,000 maximum)${rounding}. Draft estimate for ${result.tax.date}.`);
   }else set('[data-tax-breakdown]','Manually entered tax. Review the recorded reason before paperwork.');
   for(const [selector,key] of [['price','price'],['fees','fees'],['trade','trade_adjustment'],['down','down_payment'],['balance','balance']])set(`[data-desk-${selector}]`,money(totals[key]));
   form.querySelectorAll('[data-summary]').forEach(node=>{
    const name=node.dataset.summary;const subtract=!node.hasAttribute('data-summary-unsigned')&&['trade_allowance','down_payment'].includes(name)&&Number(totals[name])!==0;
    node.textContent=(subtract?'−':'')+money(totals[name]);
   });
   set('[data-desk-feedback]','Draft estimate only. Saving does not receive money or create a loan.');
   const illustration=result.illustration;
   if(illustration?.available){
    set('[data-desk-payment]',money(illustration.payment));set('[data-desk-charge]',money(illustration.finance_charge));set('[data-desk-total]',money(illustration.total_payments));set('[data-desk-final]',money(illustration.final_payment));set('[data-desk-note]',illustration.note);show('[data-desk-payment-details]',true);
   }else{set('[data-desk-payment]','—');set('[data-desk-note]',illustration?.message||'Choose financing terms to see an illustration.');show('[data-desk-payment-details]',false);}
  }catch(error){if(error.name!=='AbortError'&&current===sequence){set('[data-desk-feedback]','The preview could not refresh. Your entries are kept; saving will validate them.');}}
 }
 const schedule=()=>{modes();sequence++;controller?.abort();clearTimeout(timer);if(value('tax_mode')==='fl'){set('[data-desk-balance],[data-desk-payment]','—');set('[data-desk-feedback]','Updating estimate…');}timer=setTimeout(update,220);};
 form.addEventListener('input',event=>{if(event.target.matches('[data-money-field], [name^="tax_"], [name^="bhph-"], [name^="outside-"]'))schedule()});
 form.addEventListener('change',event=>{if(!event.target.name.startsWith('new-')&&!event.target.name.startsWith('newvehicle-'))schedule()});
 modes();update();
})();
