# SPDX-License-Identifier: MPL-2.0
"""Internal orchestration of synthetic module exports, not coordinated recovery."""
import hashlib
import io
import json
import re
import zipfile
from django.conf import settings
from django.core.exceptions import PermissionDenied
from .export import authorize_foundation_export, export_foundation
from customers.export import export_customers
from inventory.export import export_inventory
from deals.export import export_deals
from documents.export import export_documents
from finance.export import export_finance
from feedback.export import export_feedback

FORMAT_VERSION = 'railet-synthetic-dealership-v1'
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 20010
PHOTO_PATH = re.compile(r'photos/photo-[1-9][0-9]*-(?:image|thumbnail)\.jpg\Z')
DOC_PATH = re.compile(r'(?:deal-files/[1-9][0-9]*\.pdf|vehicle-invoices/[1-9][0-9]*\.pdf|vehicle-acquisition/[1-9][0-9]*\.pdf|packets/[1-9][0-9]*\.html|metadata\.json)\Z')


class PackageError(Exception):
    pass


def authorize_package(*, dealership_id, actor):
    flags = ('DEBUG', 'CUSTOMER_ACTIVITY_DEMO_ENABLED', 'RECON_DEMO_ENABLED', 'DEMO_COMPLETION_ENABLED',
             'DEMO_PACKETS_ENABLED', 'DEAL_FILES_DEMO_ENABLED', 'DEMO_LEDGER_ENABLED', 'DEMO_SERVICING_ENABLED')
    if not all(getattr(settings, flag, False) for flag in flags):
        raise PermissionDenied('Synthetic dealership export is disabled.')
    return authorize_foundation_export(dealership_id=dealership_id, actor=actor)


def _json(data):
    try:
        return (json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    except (TypeError, ValueError) as error:
        raise PackageError('A component is not valid JSON; no package prepared.') from error


def _verify_documents(payload, dealership_id, actor_id):
    if not isinstance(payload, bytes) or len(payload) > MAX_MEMBER_BYTES:
        raise PackageError('Documents component exceeds its size limit.')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            names = [entry.filename for entry in infos]
            if len(names) > MAX_MEMBERS or len(names) != len(set(names)) or 'manifest.json' not in names:
                raise PackageError('Invalid documents archive.')
            if any(not DOC_PATH.fullmatch(n) for n in names if n != 'manifest.json'):
                raise PackageError('Unsafe documents artifact name.')
            if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES or any(i.file_size > MAX_MEMBER_BYTES for i in infos):
                raise PackageError('Documents archive exceeds its size limit.')
            manifest = json.loads(archive.read('manifest.json'))
            if not isinstance(manifest, dict) or manifest.get('dealership_id') != dealership_id or not manifest.get('synthetic_only'):
                raise PackageError('Documents archive has invalid scope.')
            expected = manifest['files']
            if not isinstance(expected, dict) or set(expected) != set(names) - {'manifest.json'} or 'metadata.json' not in expected:
                raise PackageError('Documents manifest does not match artifacts.')
            for name, entry in expected.items():
                content = archive.read(name)
                if entry.get('bytes') != len(content) or entry.get('sha256') != hashlib.sha256(content).hexdigest():
                    raise PackageError('Documents artifact failed integrity verification.')
            metadata = json.loads(archive.read('metadata.json'))
            if (not isinstance(metadata, dict) or metadata.get('dealership_id') != dealership_id
                    or metadata.get('exported_by_user_id') != actor_id or not metadata.get('synthetic_only')):
                raise PackageError('Documents metadata has invalid scope.')
            artifact_names = set()
            for group, prefix, extension, hash_field in (
                ('deal_files', 'deal-files', 'pdf', 'sha256'),
                ('vehicle_invoices', 'vehicle-invoices', 'pdf', 'sha256'),
                ('vehicle_acquisition_files', 'vehicle-acquisition', 'pdf', 'sha256'),
                ('packets', 'packets', 'html', 'artifact_sha256'),
            ):
                for row in metadata[group]:
                    name = f'{prefix}/{row["id"]}.{extension}'
                    if (row['artifact'] != name or name in artifact_names or name not in expected
                            or expected[name]['sha256'] != row[hash_field]):
                        raise PackageError('Documents artifact metadata does not match its manifest.')
                    artifact_names.add(name)
            if artifact_names != set(expected) - {'metadata.json'}:
                raise PackageError('Documents metadata omits an artifact.')
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, UnicodeDecodeError, RuntimeError, AttributeError) as error:
        raise PackageError('Documents component could not be verified.') from error


def build_package(*, dealership_id, actor):
    """Caller must own an atomic transaction and audit before returning bytes."""
    authorize_package(dealership_id=dealership_id, actor=actor)
    parts = {}
    total = 0
    def add(name, payload):
        nonlocal total
        if name in parts or not isinstance(payload, bytes):
            raise PackageError('Invalid or duplicate package component.')
        total += len(payload)
        if len(parts) >= MAX_MEMBERS or len(payload) > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
            raise PackageError('Dealership package exceeds its size limit; no partial package prepared.')
        parts[name] = payload
    def scoped(name, result):
        if (not isinstance(result, dict) or result.get('dealership_id') != dealership_id
                or result.get('exported_by_user_id') != actor.pk or not result.get('synthetic_only')):
            raise PackageError('A component has invalid dealership scope.')
        add(name, _json(result))
    kwargs = {'dealership_id': dealership_id, 'actor': actor}
    scoped('foundation.json', export_foundation(**kwargs))
    scoped('customers.json', export_customers(**kwargs))
    inventory = export_inventory(**kwargs)
    if (not isinstance(inventory, dict) or inventory.get('dealership_id') != dealership_id
            or inventory.get('exported_by_user_id') != actor.pk or not inventory.get('synthetic_only')):
        raise PackageError('Inventory component has invalid dealership scope.')
    inventory = dict(inventory)
    photos = inventory.pop('photo_artifacts', None)
    if not isinstance(photos, dict) or not isinstance(inventory.get('photos'), list):
        raise PackageError('Inventory photo component is invalid.')
    expected = {}
    for row in inventory['photos']:
        for kind in ('image', 'thumbnail'):
            name = row.get(f'{kind}_artifact_id')
            if (not isinstance(name, str) or not PHOTO_PATH.fullmatch(name) or name in expected
                    or name != f'photos/photo-{row.get("id")}-{kind}.jpg'):
                raise PackageError('Invalid or duplicate photo artifact name.')
            expected[name] = (row.get(f'{kind}_bytes'), row.get(f'{kind}_sha256'))
    if set(expected) != set(photos):
        raise PackageError('Photo metadata and artifacts do not match.')
    for name, (length, digest) in expected.items():
        content = photos[name]
        if not isinstance(content, bytes) or len(content) != length or hashlib.sha256(content).hexdigest() != digest:
            raise PackageError('Photo artifact failed integrity verification.')
        add('inventory/' + name, content)
    scoped('inventory.json', inventory)
    scoped('deals.json', export_deals(**kwargs))
    documents = export_documents(**kwargs)
    _verify_documents(documents, dealership_id, actor.pk)
    add('documents.zip', documents)
    scoped('finance.json', export_finance(**kwargs))
    scoped('feedback.json', export_feedback(**kwargs))
    manifest = {'format': FORMAT_VERSION, 'synthetic_only': True, 'dealership_id': dealership_id,
                'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in parts.items()}}
    add('manifest.json', _json(manifest))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    if buffer.tell() > MAX_TOTAL_BYTES:
        raise PackageError('Dealership package exceeds its size limit; no partial package prepared.')
    return buffer.getvalue()
