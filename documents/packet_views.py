# SPDX-License-Identifier: MPL-2.0
import uuid
from functools import wraps
from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_GET
from core.access import context, member_view, require_editor
from deals.models import DraftDeal
from .models import DemoDealPacket
from .packets import PacketChanged, check_gate, create_packet, digest, packet_source, source_digest

SALT = 'railet.demo-packet.preview.v1'


def private_packet(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            check_gate()
            response = view(request, *args, **kwargs)
        except Http404:
            response = HttpResponse(status=404)
        except PermissionDenied:
            response = HttpResponse(status=403)
        response['Cache-Control'] = 'private, no-store'
        response['Pragma'] = 'no-cache'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    return wrapped


@private_packet
@member_view
@require_http_methods(['GET', 'POST'])
def packet_list(request, pk):
    deal = get_object_or_404(DraftDeal, pk=pk, dealership_id=request.member.dealership_id)
    error = None
    status = 200
    if request.method == 'POST':
        require_editor(request)
        try:
            payload = signing.loads(request.POST.get('preview_token', ''), salt=SALT, max_age=1800)
        except signing.BadSignature:
            error, status = 'This preview expired or is invalid. Review the fresh preview below before saving.', 400
        else:
            if payload.get('actor') != request.user.pk or payload.get('dealer') != request.member.dealership_id or payload.get('deal') != deal.pk:
                raise PermissionDenied
            try:
                key = uuid.UUID(payload['key'])
                packet, _ = create_packet(dealership_id=request.member.dealership_id, deal_id=deal.pk, actor=request.user, creation_key=key, expected_source=payload['source'])
            except PacketChanged as exception:
                error, status = str(exception), 409
            else:
                return redirect('demo_packet_detail', pk=deal.pk, packet_pk=packet.pk)
    snapshot = packet_source(dealership_id=request.member.dealership_id, deal_id=deal.pk)
    token = signing.dumps({'actor':request.user.pk,'dealer':request.member.dealership_id,'deal':deal.pk,'key':str(uuid.uuid4()),'source':source_digest(snapshot)}, salt=SALT)
    packets = deal.demo_packets.select_related('created_by')
    from django.core.paginator import Paginator
    page = Paginator(packets, 20).get_page(request.GET.get('page'))
    return render(request, 'documents/demo_packet_list.html', context(request, deal=deal, snapshot=snapshot, token=token, page=page, packet_error=error), status=status)


@private_packet
@member_view
@require_GET
def packet_detail(request, pk, packet_pk):
    packet = get_object_or_404(DemoDealPacket.objects.select_related('created_by'), pk=packet_pk, deal_id=pk, deal__dealership_id=request.member.dealership_id)
    return render(request, 'documents/demo_packet_detail.html', context(request, packet=packet))


@private_packet
@member_view
@require_http_methods(['GET', 'HEAD'])
def packet_artifact(request, pk, packet_pk):
    packet = get_object_or_404(DemoDealPacket, pk=packet_pk, deal_id=pk, deal__dealership_id=request.member.dealership_id)
    if digest(packet.html) != packet.artifact_sha256:
        return HttpResponse('Stored demo artifact integrity check failed. Contact your administrator.', status=409, content_type='text/plain')
    response = HttpResponse(packet.html if request.method == 'GET' else '', content_type='text/html; charset=utf-8')
    response['Content-Security-Policy'] = "sandbox; default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    response['Content-Disposition'] = f'inline; filename="DEMO-deal-{pk}-packet-{packet.pk}.html"'
    return response
