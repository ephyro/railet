# SPDX-License-Identifier: MPL-2.0
"""Portable exports of existing demo packets, never a full dealership backup."""
import hashlib
import io
import json
import zipfile
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from core.access import member_view
from .models import DemoDealPacket, DemoPacketExportEvent
from .packet_views import private_packet
from .packets import digest, source_digest

MAX_PART_BYTES = 8 * 1024 * 1024


class PacketExportError(Exception):
    pass


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def build_bundle(packet):
    if digest(packet.html) != packet.artifact_sha256:
        raise PacketExportError('Stored demo HTML failed its integrity check. Contact your administrator.')
    if source_digest(packet.snapshot) != packet.source_sha256:
        raise PacketExportError('Stored snapshot data failed its integrity check. Contact your administrator.')
    files = {
        'DEMO-summary.html': packet.html.encode('utf-8'),
        'snapshot.json': json_bytes({
            'format': 'railet-demo-packet', 'format_version': 1,
            'packet_id': packet.pk, 'deal_id': packet.deal_id,
            'created_by_account_id': packet.created_by_id,
            'captured_at': packet.created_at.isoformat(),
            'template_version': packet.template_version,
            'source_sha256': packet.source_sha256, 'snapshot': packet.snapshot,
        }),
        'README.txt': (
            'RAILET DEMONSTRATION PACKET\n\n'
            'Synthetic evaluation only. Not a contract, receipt, loan, signature or proof of legal compliance.\n'
            'DEMO-summary.html is the exact retained HTML. Open it locally in a browser.\n'
            'snapshot.json contains the captured facts and stable record/provenance identifiers.\n'
            'manifest.json lists the byte lengths and SHA-256 hashes of these files.\n'
            'Hashes detect accidental changes; they are not digital signatures or proof of authorship.\n\n'
            'This is one packet only, not a complete deal export or database/media backup.\n'
            'Uploads, signed documents, photos, complete audit history and later changes are excluded.\n'
            'Treat exported files as private. There is no export encryption or import/restore function.\n'
        ).encode('utf-8'),
    }
    if any(len(content) > MAX_PART_BYTES for content in files.values()):
        raise PacketExportError('This packet exceeds the export size limit. Contact your administrator; its saved records were not changed.')
    files['manifest.json'] = json_bytes({
        'format': 'railet-demo-packet-manifest', 'format_version': 1,
        'demonstration_only': True,
        'files': {name:{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()} for name,content in files.items()},
    })
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


@private_packet
@member_view
@require_http_methods(['GET','HEAD'])
def packet_export(request, pk, packet_pk):
    with transaction.atomic():
        packet = get_object_or_404(DemoDealPacket.objects.select_for_update(of=('self',)), pk=packet_pk, deal_id=pk, deal__dealership_id=request.member.dealership_id)
        try:
            bundle = build_bundle(packet)
        except PacketExportError as error:
            return HttpResponse(str(error), status=409, content_type='text/plain; charset=utf-8')
        if request.method == 'GET':
            # Records preparation of an authorized response, not proof of receipt.
            DemoPacketExportEvent.objects.create(packet=packet,actor=request.user,bundle_sha256=hashlib.sha256(bundle).hexdigest())
    response = HttpResponse(bundle if request.method=='GET' else b'',content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="DEMO-deal-{pk}-packet-{packet_pk}.zip"'
    response['Content-Length'] = str(len(bundle))
    response['Content-Security-Policy'] = 'sandbox'
    return response
