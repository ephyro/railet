# SPDX-License-Identifier: MPL-2.0
"""Explicit synthetic illustration profiles; never legal payoff or live allocation."""
from calendar import monthrange
from datetime import date,timedelta
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP,localcontext
from .services import LedgerError,cents

VERSION='schedule-illustration-v1'
METHODS=(('precomputed','Precomputed — supplied finance charge'),('simple_daily','Daily simple — fixed 365 illustration'))
FREQUENCIES=(('weekly','Weekly'),('biweekly','Every two weeks'),('monthly','Monthly'),('semimonthly','Twice a month'))


def valid_date(value):
    if not isinstance(value,date) or hasattr(value,'hour') or not 1900<=value.year<=2100:
        raise LedgerError('Use a date between 1900 and 2100 for this illustration.')
    return value


def due_dates(*,start_on,first_due_on,count,frequency,first_day=None,second_day=None):
    valid_date(start_on);valid_date(first_due_on)
    if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=600:
        raise LedgerError('Use 1 through 600 installments for this illustration.')
    if first_due_on<=start_on:raise LedgerError('First payment must follow the starting date.')
    if frequency not in dict(FREQUENCIES):raise LedgerError('Choose an available payment frequency.')
    if frequency=='semimonthly':
        if any(isinstance(x,bool) or not isinstance(x,int) for x in (first_day,second_day)) or not 1<=first_day<second_day<=28:
            raise LedgerError('Twice-monthly dates need two distinct ordered days between 1 and 28.')
        if first_due_on.day not in (first_day,second_day):raise LedgerError('First due date must match one of the twice-monthly day anchors.')
    elif first_day is not None or second_day is not None:
        raise LedgerError('Day anchors apply only to twice-monthly schedules.')
    dates=[]
    current=first_due_on
    for index in range(count):
        if frequency in ('weekly','biweekly'):current=first_due_on+timedelta(days=index*(7 if frequency=='weekly' else 14))
        elif frequency=='monthly':
            offset=first_due_on.year*12+first_due_on.month-1+index;year,month=divmod(offset,12);month+=1
            current=date(year,month,min(first_due_on.day,monthrange(year,month)[1]))
        elif index:
            if current.day==first_day:current=current.replace(day=second_day)
            else:
                year=current.year+(current.month==12);month=1 if current.month==12 else current.month+1
                current=date(year,month,first_day)
        valid_date(current);dates.append(current)
    return dates


def nonnegative_cents(value):
    if not isinstance(value,(float,bool)):
        try:
            amount=Decimal(value)
            if amount.is_finite() and amount==0:return 0
        except (InvalidOperation,ValueError,TypeError):pass
    return cents(value)


def annual_rate(value):
    if isinstance(value,(float,bool)):raise LedgerError('Use an exact decimal annual contract rate.')
    try:rate=Decimal(value)
    except (InvalidOperation,TypeError,ValueError):raise LedgerError('Enter a valid annual contract rate.')
    if not rate.is_finite() or not 0<=rate<=1000:raise LedgerError('Illustration rate must be between 0 and 1000 percent; this is not a legal rate limit.')
    if rate.as_tuple().exponent < -4:raise LedgerError('Use at most four decimal places for the illustration rate.')
    return rate


def calculate(*,principal_cents,method,start_on,first_due_on,count,frequency,finance_charge=None,contract_rate=None,regular_payment=None,first_day=None,second_day=None):
    if isinstance(principal_cents,bool) or not isinstance(principal_cents,int) or not 1<=principal_cents<=999999999999:
        raise LedgerError('Use a positive, bounded integer-cent principal.')
    dates=due_dates(start_on=start_on,first_due_on=first_due_on,count=count,frequency=frequency,first_day=first_day,second_day=second_day)
    rows=[]
    with localcontext() as ctx:
        ctx.prec=50
        if method=='precomputed':
            if finance_charge is None or contract_rate is not None or regular_payment is not None:
                raise LedgerError('Precomputed illustrations need a supplied finance charge only, not a rate or scheduled payment.')
            charge=nonnegative_cents(finance_charge);total=principal_cents+charge
            regular=int((Decimal(total)/count).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            final=total-regular*(count-1)
            if regular<=0 or final<=0:raise LedgerError('The total is too small for that many rounded payments.')
            remaining=total
            for index,due in enumerate(dates):
                payment=final if index==count-1 else regular;remaining-=payment
                rows.append({'number':index+1,'due_on':due.isoformat(),'payment_cents':payment,'remaining_scheduled_cents':remaining})
            return {'calculation_version':VERSION,'method':method,'principal_cents':principal_cents,'finance_charge_cents':charge,'total_payments_cents':total,'rows':rows,'assumptions':['Finance charge supplied, not derived or legally validated.','No APR, earnings allocation, rebate or early payoff is calculated.','Regular installments rounded HALF_UP; exact residual in final payment.']}
        if method!='simple_daily':raise LedgerError('Choose precomputed or daily simple interest explicitly.')
        if finance_charge is not None or contract_rate is None or regular_payment is None:
            raise LedgerError('Daily simple illustrations need a rate and regular payment, not a supplied finance charge.')
        rate=annual_rate(contract_rate);regular=cents(regular_payment);balance=principal_cents;previous=start_on;interest_total=0;payment_total=0
        for index,due in enumerate(dates):
            days=(due-previous).days
            interest=int((Decimal(balance)*rate*days/Decimal('36500')).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            owed=balance+interest
            if index==count-1:
                if owed>regular:raise LedgerError('The regular payment does not clear principal in the requested count; this profile does not create a larger final balloon.')
                payment=owed
            else:payment=min(regular,owed)
            if payment<=interest:raise LedgerError('The assumed payment does not reduce principal; negative-amortizing illustrations are not supported.')
            principal=payment-interest;balance-=principal;interest_total+=interest;payment_total+=payment
            rows.append({'number':index+1,'due_on':due.isoformat(),'days':days,'payment_cents':payment,'interest_cents':interest,'principal_cents':principal,'remaining_principal_cents':balance})
            if balance==0 and index<count-1:raise LedgerError('This payment clears principal before the requested final installment. Adjust the count or payment instead of silently changing the schedule.')
            previous=due
        return {'calculation_version':VERSION,'method':method,'principal_cents':principal_cents,'contract_rate_pct':str(rate),'finance_charge_cents':interest_total,'total_payments_cents':payment_total,'day_basis':365,'rows':rows,'assumptions':['Every installment assumed paid exactly on its due date.','Actual elapsed days / fixed 365, including leap years.','Interest rounded HALF_UP once per interval, not per day.','No fees, late, partial, extra payments or live receipt allocation.','Contract rate is not an APR disclosure; no payoff quote.']}
