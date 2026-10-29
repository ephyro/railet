# SPDX-License-Identifier: MPL-2.0
"""Bounded discovery over the existing simulation; never posted delinquency."""
from .models import DemoBook
from .queries import search_accounts,with_account_activity
from .servicing_services import attach_list_status
from .services import LedgerError

MAX_ACCOUNTS=500


def select_worklist(*,books,dealership_id,state):
    """Caller holds a transaction. Filter and sort globally before pagination."""
    ids=list(books.values_list('pk',flat=True)[:MAX_ACCOUNTS+1])
    if len(ids)>MAX_ACCOUNTS:
        raise LedgerError(f'Status searches cover up to {MAX_ACCOUNTS} matching accounts. Narrow the customer or vehicle search; no partial results are shown.')
    list(DemoBook.objects.filter(pk__in=ids,dealership_id=dealership_id).order_by('pk').select_for_update())
    refreshed=state.apply(search_accounts(dealership_id=dealership_id,query=state.query).filter(pk__in=ids))
    if state.extra.get('scope'):refreshed=refreshed.filter(has_context=state.extra['scope']=='linked')
    selected=list(with_account_activity(refreshed))
    attach_list_status(selected,strict=True)
    status=state.extra.get('status')
    def matches(book):
        simulation=book.simulation
        if status=='uncalculated':return simulation is None
        if simulation is None:return False
        return simulation['status'] in ('current','covered') if status=='current' else simulation['status']==status
    if status:selected=[book for book in selected if matches(book)]
    if state.sort=='oldest_due':
        def rank(book):
            simulation=book.simulation
            if not simulation:return (4,'9999-12-31',book.pk)
            return ({'past_due':0,'due_today':1,'current':2,'covered':3}[simulation['status']],simulation['next_unpaid_on'] or '9999-12-31',book.pk)
        selected.sort(key=rank)
    return selected
