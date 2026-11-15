<!-- SPDX-License-Identifier: MPL-2.0 -->
# Private vehicle acquisition attachments — development design

Acquisition attachments (`VehicleAcquisitionFile` and `VehicleAcquisitionFileEvent`)
belong to the `documents` module and reference a dealership-scoped `Vehicle`.
They let staff attach and retrieve private synthetic PDFs—such as invented
auction bills of sale or title-intake rehearsal sheets—with an explicit title
and optional description.

## Scope and boundaries

- **Unverified staff attachments only:** Uploading or retaining an acquisition
  attachment does **not** verify vehicle ownership, set or alter `acquired_on`,
  `sold_on`, `title_received`, or `title_brand`, change `vehicle.status`, or
  establish legal readiness for sale under Florida Chapter 319/320.
- **Private storage and bounded PDF screening:** Files are stored in
  `PrivateMediaStorage` under `vehicle-acquisition/` with random UUID names.
  Uploads enforce the 8 MiB per-file limit, `%PDF-` header and `%%EOF` trailer
  checks, and per-vehicle quotas (100 retained files or 100 MiB, including
  archived files). This is minimal format screening, not a PDF parser,
  antivirus scan, or authenticity check.
- **Role and dealership isolation:** Gated by `DEAL_FILES_DEMO_ENABLED`
  (derived from `DEBUG`). Owners and inventory staff can upload, archive (with a
  required reason), restore, and download active or archived attachments.
  Read-only (`viewer`) members can view and download active attachments only.
  Downloads verify the stored byte size and SHA-256 digest before returning
  bytes with `private, no-store`, `nosniff`, and `Content-Security-Policy: sandbox`
  headers.
- **Immutable file metadata and event history:** Database triggers on SQLite and
  PostgreSQL block deleting `VehicleAcquisitionFile` rows, mutating immutable
  file columns (`vehicle_id`, `title`, `description`, `blob`, `sha256`,
  `byte_size`, `upload_key`, `created_by_id`, `created_at`), or updating/deleting
  `VehicleAcquisitionFileEvent` rows. Only `archived_at` may change through
  audited archive/restore actions.
- **Export inclusion:** `documents/export.py` and `core/dealership_export.py`
  include active and archived `vehicle_acquisition_files`,
  `vehicle_acquisition_file_events`, and verified `vehicle-acquisition/<id>.pdf`
  bytes in the owner-only synthetic export package.
