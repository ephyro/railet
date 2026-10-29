# SPDX-License-Identifier: MPL-2.0
"""Monthly, equal-period draft illustrations only. No APR or posted accrual."""
from decimal import Decimal,ROUND_HALF_UP,localcontext
from django.core.exceptions import ValidationError
VERSION='draft-monthly-illustration-v1'
CENT=Decimal('.01')

def illustrate(*,balance,method,frequency,count,rate=None,finance_charge=None):
    principal=Decimal(balance)
    if not principal.is_finite() or principal<=0:return None
    if frequency!='monthly':return {'available':False,'message':'Monthly payment illustrations require Monthly frequency. Other schedules need a separate reviewed illustration.'}
    if type(count) is not int or not 1<=count<=600:return {'available':False,'message':'Enter 1–600 payments to see a monthly illustration.'}
    with localcontext() as ctx:
        ctx.prec=60
        if method=='precomputed':
            if finance_charge is None:return {'available':False,'message':'Enter the proposed total finance charge for a precomputed illustration.'}
            charge=Decimal(finance_charge)
            if not charge.is_finite() or charge<0 or charge>Decimal('9999999999.99'):raise ValidationError('Enter a valid nonnegative finance charge.')
            total=principal+charge;payment=(total/count).quantize(CENT,rounding=ROUND_HALF_UP);final=total-payment*(count-1)
            if final<=0:raise ValidationError('The amount is too small for this number of payments.')
            note='Supplied total finance charge, divided across monthly payments. No earned-interest or APR calculation.'
        elif method=='simple':
            if rate is None:return {'available':False,'message':'Enter the annual contract rate for a monthly illustration.'}
            annual=Decimal(rate)
            if not annual.is_finite() or annual<0 or annual>100:raise ValidationError('This illustration supports rates from 0% through 100%; this is a calculation limit, not a legal rate limit.')
            periodic=annual/1200
            exact=principal/count if not periodic else principal*periodic/(1-(1+periodic)**(-count))
            payment=exact.quantize(CENT,rounding=ROUND_HALF_UP);remaining=principal;total=Decimal(0)
            for index in range(count):
                interest=(remaining*periodic).quantize(CENT,rounding=ROUND_HALF_UP)
                paid=payment if index<count-1 else remaining+interest
                if paid<=interest or (index<count-1 and paid>=remaining+interest):raise ValidationError('Use a shorter term or a larger amount for this illustration.')
                remaining=remaining+interest-paid;total+=paid
            final=paid;charge=total-principal
            note='Equal monthly periods at annual rate ÷ 12. Actual daily-interest contracts can differ. Not APR or a contract schedule.'
        else:return {'available':False,'message':'Choose an interest method to see the illustration.'}
    return {'available':True,'version':VERSION,'payment':str(payment),'final_payment':str(final),'finance_charge':str(charge),'total_payments':str(total),'note':note}
