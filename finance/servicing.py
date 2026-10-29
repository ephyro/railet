# SPDX-License-Identifier: MPL-2.0
"""Versioned installment coverage simulation; never ledger allocation or payoff."""
from datetime import date, datetime
from .services import LedgerError
from .schedules import valid_date

POLICY = 'monthly-oldest-first-v1'
MAX_POSTINGS = 10000


def exact_positive(value):
    if type(value) is not int or not 0 < value <= 1999999999998:
        raise LedgerError('Invalid integer-cent servicing input.')
    return value


def project(*, rows, postings, as_of, recorded_through):
    valid_date(as_of)
    if not isinstance(recorded_through, datetime) or recorded_through.tzinfo is None:
        raise LedgerError('A timezone-aware record capture timestamp is required.')
    if not 1 <= len(rows) <= 600 or len(postings) > MAX_POSTINGS:
        raise LedgerError('The demo servicing record limit was exceeded.')
    installments=[]; previous=None
    for index, row in enumerate(rows):
        try: due=valid_date(date.fromisoformat(row['due_on']))
        except (ValueError, TypeError, KeyError):raise LedgerError('Invalid saved installment date.')
        if (previous and due <= previous) or row.get('number') != index+1:
            raise LedgerError('Saved installments are not in order.')
        amount=exact_positive(row['payment_cents'])
        installments.append({'number':index+1,'due_on':due.isoformat(),'scheduled_cents':amount,'covered_cents':0,'remaining_cents':amount})
        previous=due
    captured=[p for p in postings if p['entered_at'] <= recorded_through]
    receipts={}; corrections={}
    for posting in captured:
        if posting['kind']=='opening':continue
        exact_positive(posting['amount_cents']);valid_date(posting['effective_on'])
        if posting['kind']=='receipt':
            if posting['id'] in receipts:raise LedgerError('Duplicate receipt in servicing inputs.')
            receipts[posting['id']]=posting
        elif posting['kind']=='reversal':
            original=posting['reverses_id']
            if original in corrections:raise LedgerError('Duplicate correction in servicing inputs.')
            corrections[original]=posting
        else:raise LedgerError('Unsupported posting in servicing inputs.')
    for original, correction in corrections.items():
        receipt=receipts.get(original)
        if not receipt or receipt['amount_cents']!=correction['amount_cents'] or correction['effective_on']<receipt['effective_on']:
            raise LedgerError('A correction does not match its retained receipt.')
    eligible=[p for pk,p in receipts.items() if p['effective_on']<=as_of and not (pk in corrections and corrections[pk]['effective_on']<=as_of)]
    eligible.sort(key=lambda p:(p['effective_on'],p['entered_at'],p['id']))
    allocations=[]; excess=0;cursor=0
    for receipt in eligible:
        available=receipt['amount_cents']
        while available and cursor<len(installments):
            row=installments[cursor];applied=min(available,row['remaining_cents'])
            row['covered_cents']+=applied;row['remaining_cents']-=applied;available-=applied
            allocations.append({'receipt_id':receipt['id'],'installment':row['number'],'coverage_cents':applied})
            if not row['remaining_cents']:cursor+=1
        excess+=available
    due=sum(r['remaining_cents'] for r in installments if r['due_on']<=as_of.isoformat())
    past=[r for r in installments if r['remaining_cents'] and r['due_on']<as_of.isoformat()]
    remaining=sum(r['remaining_cents'] for r in installments)
    oldest=next((r for r in installments if r['remaining_cents']),None)
    status='past_due' if past else 'due_today' if due else 'covered' if not remaining else 'current'
    return {'policy':POLICY,'as_of':as_of.isoformat(),'recorded_through':recorded_through.isoformat(),
            'amount_due_cents':due,'past_due_cents':sum(r['remaining_cents'] for r in past),
            'days_past_due':(as_of-date.fromisoformat(past[0]['due_on'])).days if past else 0,
            'remaining_scheduled_cents':remaining,'net_receipts_cents':sum(p['amount_cents'] for p in eligible),
            'excess_cents':excess,'covered_cents':sum(r['covered_cents'] for r in installments),
            'next_unpaid_on':oldest['due_on'] if oldest else None,'status':status,'rows':installments,'coverage':allocations}
