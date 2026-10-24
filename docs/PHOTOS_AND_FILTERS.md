# Vehicle identity, photos, and shared filters

Development implementation, October 23, 2026. Use synthetic data while the product's production gates remain open.

## Vehicle identity and photos

Inventory and draft lists show a thumbnail with year/make/model and stock number. Inventory also shows the recorded VIN; draft rows show its final six characters. Vehicle choices include stock number and VIN suffix so identical models remain distinguishable. The deal header uses the inventory cover photo rather than a separate deal copy.

`inventory.VehiclePhoto` belongs to a protected vehicle record. Owners/staff can upload, choose a cover, hide, and restore photos. Viewers can download active photos but cannot manage them; hidden photos remain available only to editors. Downloads always resolve the photo through the requesting user's dealership. There is no public media route. Responses use JPEG content type, a fixed inline filename, `nosniff`, and private/no-store caching. Private storage deliberately does not expose `.url`.

Uploads accept JPEG, PNG, and WebP based on decoded contents, not supplied filenames or MIME type. Each request accepts up to eight files, each at most 8 MB and 40 megapixels. Animations are rejected. All files are validated before any are stored. The server applies EXIF orientation, reduces the display image to at most 1920 × 1920, and creates a 320 × 220 thumbnail. Fresh RGB JPEG output strips EXIF/location, XMP, ICC profiles, comments, and the original filename. Originals are not retained. HEIC, SVG, PDF, and other formats are not supported.

Each vehicle has at most 24 active photos. A parent-vehicle row lock serializes uploads and cover changes; a conditional database constraint permits one active cover. Hiding a cover selects another active photo. Hiding is reversible and retains the private file; physical deletion/retention and storage quotas require a reviewed operational policy before production. There is no universal age-based deletion rule.

Photo records and actor audit events commit together. Handled upload failures remove files written by that operation. Filesystem and database writes are not one atomic transaction: process termination or storage faults may leave orphan files, so reconciliation/cleanup and backup restoration remain operational release work.

Pillow is a new runtime dependency for decoding and normalization. The verified development version is 13.0.0, with MIT-CMU license metadata; retain its notices and the bundled codec notices in distributed artifacts. Sources checked October 23: [Pillow 13.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html), [security guidance](https://pillow.readthedocs.io/en/stable/handbook/security.html), and [license information](https://pillow.readthedocs.io/en/stable/about.html#license). The byte/pixel/batch limits above are Railet engineering limits, not statutory requirements.

## Shared filtering

`core.filtering` defines the typed filter engine. Each module owns a `FilterSchema` in its own `filters.py`; `railet.filtersets` is the explicit composition registry. A schema specifies logical field names, permitted comparisons, input types/choices, and allowed sort orders. The client receives display metadata, never arbitrary ORM lookup access. The engine only filters a queryset the caller has already authorized and scoped. ANY rules are grouped inside that scope, with basic search and quick filters still applied using AND.

The same component is used for inventory, customers, and draft deals. Supported rules include text comparisons, empty/nonempty text, enum/boolean values, integer/decimal/date bounds, and inclusive ranges. Dates use YYYY-MM-DD. Users can match all or any of up to ten flat rules; nested boolean groups are not implemented. Invalid fields, comparisons, values, or ordering hide results and show errors rather than silently widening the search. Sorts have stable tie breakers.

Basic search and inventory quick views remain visible. Applied rules appear as removable labels, and the detailed builder stays collapsed until opened or an error needs correction. Native form controls and labels support keyboard use; JavaScript adds/removes rows and supplies the appropriate value input. One rule can be used without JavaScript. The partial accepts an optional `filter_instance` identifier for multiple builders of the same resource on one page. Module query code and the shared pagination preserve all applied criteria; inventory no longer drops matches after 200 rows.

`core.SavedView` stores a named live query, not a copy of matching records. Views are private to their owner, dealership, and resource, including read and delete operations. Viewers may save their own display preferences without receiving record-write permission. Saving submits the current filter form, including edits that have not yet been applied. Names are limited to 60 characters; each user can keep 50 views per resource. Unsupported stored definitions fail closed and require rebuilding. Filter URLs continue to require normal application authorization; saved view IDs cannot be used by another member. Search values can contain private information, so they must not be copied into public feedback or diagnostics.

## Storage and deployment

Development uses the `private_media` named volume at `/app/private-media`; staging has a separate `staging_media` volume. The image creates this directory for the unprivileged application user. Source sync excludes uploaded files, and private media is ignored by both Git and Docker builds. Local Python uses `private-media/` or `RAILET_PRIVATE_MEDIA_ROOT`.

Database and private media must both be included in a consistent backup and restore plan. Recreating a web container is only a persistence check, not a backup-restoration drill. No staging or production deployment was authorized or performed for this change.

## Verification

Final PostgreSQL verification: all 78 tests passed, including forced simultaneous photo uploads obeying the 24-photo limit, private downloads, tenant isolation, metadata removal, file cleanup on audit failure, filter validation, saved-view privacy, pagination, and rule-removal links. System and migration drift checks passed. The earlier full local SQLite run passed 77 tests with two PostgreSQL concurrency cases skipped; subsequent focused photo/filter and core checks also passed. A streaming-response test cleanup issue found on PostgreSQL was corrected before the final successful runs.

Firefox exercised multi-photo upload/display, cover/hide/restore, SVG rejection, the shared deal cover, range rules, saving unapplied filters, restoring a saved view, and filtering in all three modules. A final pass verified compact applied-rule controls, per-rule removal, long saved names, keyboard-scrolling tables, and exact 1440px, 390px, and 320px layouts without horizontal page overflow. Images were awaited until decoding completed before final screenshots were inspected. Both photos and the deal cover remained available after force-recreating the web container; saved views also persisted. This is a volume persistence check, not a backup restore drill.

The demo uses clearly labeled generated test illustrations, not real vehicle photos. Saved review view #1 and two illustrations on stock DEMO-004 remain available. Staff usability feedback, production security review, retention/quotas, orphan reconciliation, and backup restore verification remain outstanding.
