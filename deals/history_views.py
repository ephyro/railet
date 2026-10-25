# SPDX-License-Identifier: MPL-2.0
"""Read-only access to retained draft event snapshots, never reconstructed history."""
from decimal import Decimal, InvalidOperation
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from core.access import context, member_view
from .models import DraftDeal, MONEY_FIELDS
from .review import money_text

ACTION_LABELS = {
    'draft_saved': 'Draft saved', 'trade_saved': 'Trade saved',
    'trade_removed': 'Trade removed', 'trade_intake': 'Trade added to inventory',
    'draft_archived': 'Draft archived', 'draft_restored': 'Draft restored',
}
MONEY_LABELS = dict(zip(MONEY_FIELDS, ('Vehicle price','Sales tax entered','Title / registration fees','Dealer fee','Trade allowance','Estimated trade payoff','Planned down payment')))


def event_rows(event):
    snapshot = event.snapshot if isinstance(event.snapshot, dict) else {}
    rows = []
    for name, label in MONEY_LABELS.items():
        raw = snapshot.get(name)
        try:
            value = Decimal(str(raw))
            if not value.is_finite() or abs(value) > Decimal('999999999999.99'):
                raise InvalidOperation
            display = money_text(value)
        except (InvalidOperation, ValueError, TypeError):
            display = 'Not recorded in this version'
        rows.append((label, display))
    return {'event':event, 'label':ACTION_LABELS.get(snapshot.get('action'), 'Draft started' if snapshot.get('revision') == 1 else 'Draft updated'),
            'saved':snapshot, 'amounts':rows}


@never_cache
@member_view
@require_GET
def deal_history(request, pk):
    deal = get_object_or_404(DraftDeal.objects.filter(dealership=request.member.dealership), pk=pk)
    page = Paginator(deal.events.select_related('actor'), 25).get_page(request.GET.get('page'))
    return render(request,'deals/history.html',context(request,deal=deal,page=page,rows=[event_rows(event) for event in page]))
