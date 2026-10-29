# SPDX-License-Identifier: MPL-2.0
"""Bounded 2026 Florida single-vehicle draft estimate; not a tax return."""
from datetime import date
from decimal import Decimal,ROUND_HALF_UP
from django.core.exceptions import ValidationError
VERSION='fl-single-vehicle-2026-v1'
TABLE='DR-15DSS-2026-R11-25'
SOURCE='https://floridarevenue.com/Forms_library/current/dr15dss_26.pdf'
# Basis points, transcribed from the 2026 DOR table (not the 2025 current/ alias).
COUNTIES={
'Alachua':150,'Baker':100,'Bay':100,'Bradford':100,'Brevard':100,'Broward':100,
'Calhoun':150,'Charlotte':100,'Citrus':0,'Clay':150,'Collier':0,'Columbia':150,
'DeSoto':150,'Dixie':100,'Duval':150,'Escambia':150,'Flagler':100,'Franklin':150,
'Gadsden':150,'Gilchrist':100,'Glades':100,'Gulf':100,'Hamilton':200,'Hardee':100,
'Hendry':150,'Hernando':50,'Highlands':150,'Hillsborough':150,'Holmes':150,
'Indian River':100,'Jackson':150,'Jefferson':100,'Lafayette':100,'Lake':100,
'Lee':50,'Leon':150,'Levy':100,'Liberty':150,'Madison':150,'Manatee':100,
'Marion':150,'Martin':50,'Miami-Dade':100,'Monroe':150,'Nassau':100,
'Okaloosa':100,'Okeechobee':100,'Orange':50,'Osceola':150,'Palm Beach':50,
'Pasco':100,'Pinellas':100,'Polk':100,'Putnam':100,'St. Johns':50,'St. Lucie':100,
'Santa Rosa':100,'Sarasota':100,'Seminole':100,'Sumter':100,'Suwannee':100,
'Taylor':100,'Union':100,'Volusia':50,'Wakulla':150,'Walton':100,'Washington':150}
CENT=Decimal('.01')

def amount(value):
    if isinstance(value,(float,bool)):raise ValidationError('Use exact decimal money.')
    try:v=Decimal(value)
    except Exception:raise ValidationError('Enter a valid amount.')
    if not v.is_finite() or v<0 or v>Decimal('9999999999.99') or v!=v.quantize(CENT):raise ValidationError('Enter nonnegative money with at most two decimals.')
    return v


def estimate(*,county,on,sale_price,dealer_fee,trade_allowance,title_registration,trade_confirmed=False,title_confirmed=False):
    if type(on) is not date or on.year!=2026:raise ValidationError('Automatic Florida estimates currently cover 2026 only. Use manual review for another date.')
    if county not in COUNTIES:raise ValidationError('Choose the purchaser’s Florida registration county.')
    price,fee,trade,title=map(amount,(sale_price,dealer_fee,trade_allowance,title_registration))
    if trade and trade_confirmed is not True:raise ValidationError('Confirm the same-transaction trade is accepted for resale before applying a tax credit.')
    if title and title_confirmed is not True:raise ValidationError('Confirm title/tag amounts are separately stated government fees, or move service charges to Dealer fee.')
    base=max(Decimal(0),price+fee-trade);capped=min(base,Decimal(5000))
    state_raw=base*Decimal('.06');county_raw=capped*Decimal(COUNTIES[county])/10000
    state=state_raw.quantize(CENT,rounding=ROUND_HALF_UP);local=county_raw.quantize(CENT,rounding=ROUND_HALF_UP)
    total=(state_raw+county_raw).quantize(CENT,rounding=ROUND_HALF_UP)
    return {'mode':'fl','version':VERSION,'table':TABLE,'source':SOURCE,'county':county,'date':on.isoformat(),
            'state_basis_points':600,'county_basis_points':COUNTIES[county],
            'trade_confirmed':trade_confirmed,'title_confirmed':title_confirmed,
            'inputs':{'sale_price':str(price),'dealer_fee':str(fee),'trade_allowance':str(trade),'title_registration':str(title)},
            'taxable_base':str(base),'county_base':str(capped),'state_tax':str(state),'county_tax':str(local),
            'rounding_adjustment':str(total-state-local),'total':str(total),'development_only':True}


def refresh(deal):
    context=deal.tax_context
    if not isinstance(context,dict):raise ValidationError('Saved tax information could not be verified. Contact your administrator before changing this draft.')
    if context.get('mode')!='fl':return
    from django.conf import settings
    if not getattr(settings,'FL_TAX_ESTIMATES_ENABLED',False):raise ValidationError('Automatic draft tax estimates are unavailable. Use manual review before saving these numbers.')
    try:on=date.fromisoformat(context['date'])
    except (KeyError,TypeError,ValueError):raise ValidationError('Review the saved Florida tax date before saving.')
    if context.get('version')!=VERSION or context.get('table')!=TABLE:raise ValidationError('Review the saved tax profile before recalculating.')
    deal.tax_context=estimate(county=context.get('county'),on=on,sale_price=deal.sale_price,dealer_fee=deal.dealer_fee,
        trade_allowance=deal.trade_allowance,title_registration=deal.title_registration,
        trade_confirmed=context.get('trade_confirmed',False),title_confirmed=context.get('title_confirmed',False))
    deal.tax=Decimal(deal.tax_context['total'])
