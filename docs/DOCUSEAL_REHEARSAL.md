# DocuSeal integration research and offline rehearsal

Research date: November 2, 2026. Scope: synthetic data only.

DocuSeal documents its template submission endpoint as `POST /submissions`,
authenticated using `X-Auth-Token`. It documents `send_email` as enabled by
default and `send_sms` as optional; the offline request builder explicitly sets
both false at the submission and signer level and does not set `completed`.
The builder permits only invented `@example.invalid` identities. It has no network
transport, stores no credentials, invokes no provider and creates no provider document or
signature. The external ID is correlation data; provider-side idempotency has not
been established. See https://www.docuseal.com/docs/api (reviewed November 2,
2026; actual deployment/version behavior still requires local verification).

DocuSeal's repository says its server is AGPLv3 with additional section 7(b)
interactive attribution terms. See https://github.com/docusealco/docuseal and
https://github.com/docusealco/docuseal/blob/master/LICENSE_ADDITIONAL_TERMS.
The Railet adapter remains separate MPL-2.0 code and does not bundle DocuSeal.
Review deployment and distribution obligations for the chosen integration before
shipping; a short branding note alone does not resolve all licensing questions.

Before connecting even a test instance, define an isolated local environment,
fixture template and synthetic PDF, explicit egress/notification controls,
credential storage, authenticated event ingestion, event replay/idempotency and
artifact integrity/retention. Verify the deployed version's webhook authentication,
retries, status semantics and whether the submission endpoint is idempotent; do
not assume a correlation identifier prevents duplicates. Ensure lost/late events
cannot incorrectly mark a signing complete. Retain original and signed artifacts,
consent and delivery evidence only after approved design and legal review.

Federal E-SIGN, Florida UETA, document-specific title/odometer acceptance and
Florida contract requirements remain as recorded in RAILET_PLAN.md. Applicability,
effective-date review, consent, form rights, security, provider configuration,
reviewed documents and legal approval remain unresolved production gates. No
live e-signing or email is enabled by this prototype.

## November 2026 local mock-transport rehearsal

No isolated DocuSeal server is running in the local environment. `documents/signing/docuseal.py`
includes pre-connection and payload checks plus an in-memory `LocalMockDocuSealTransport`
that explicitly marks its results `mock_only=True`:

- `validate_loopback_sandbox` restricts any future test endpoint to loopback
  (`127.0.0.1`, `localhost`, or `::1`) without embedded credentials and requires
  an explicit expected provider version.
- `verify_submission_payload` enforces `send_email=False`, `send_sms=False`, no
  `completed` flag, UUID `external_id`, and `@example.invalid` signer emails.
  It accepts exactly the offline builder's single-signer fields; extra fields
  such as BCC, redirects, phone numbers, or 2FA options are rejected. This
  allowlist is a local precondition, not proof of provider notification behavior.
- `verify_webhook_event` exercises a **mock** callback contract using an invented
  shared-secret header (`X-DocuSeal-Webhook-Secret`), an assumed JSON event
  schema, `@example.invalid` signer checks, and an optional in-memory
  `seen_event_keys` set. **Security limits:** this header name, payload schema,
  and in-memory set are local test assumptions only—they do not establish actual
  DocuSeal webhook authentication or durable database-backed replay protection
  across processes or restarts.
- `LocalMockDocuSealTransport` deduplicates by `external_id` in memory for local
  test exercises; this is a mock assumption and does **not** establish that a
  real DocuSeal server enforces `external_id` idempotency on `POST /submissions`.
- `verify_test_pdf_artifact` checks bounded `%PDF-` bytes against an expected
  SHA-256 digest.

These checks exercise the local mock contract in memory (`documents.test_docuseal_rehearsal`);
a live isolated DocuSeal container/server, verified provider webhook authentication,
durable replay storage, and end-to-end signing flow remain unconfigured.

## November 9, 2026 availability check and fixture

The Docker CLI exists, but both sandboxed and escalated read-only `docker version`
checks returned permission denied on `/var/run/docker.sock`; image availability
could not be inspected. No accessible Ruby/Bundler or Podman executable was found,
and `/dev/kvm` was absent. No container, image, provider connection or notification
was created. These observations do not rule out a different isolated environment.
The provider's actual version, egress isolation, notification suppression, template
creation, signing, artifact retrieval, webhook authentication and retry semantics
therefore remain **unverified**. A loopback URL or the mock's `egress_disabled`
boolean is not an operating-system network control.

As a bounded offline preparation, `make_synthetic_pdf_fixture` makes a one-page,
visibly marked invented PDF in memory using the already-declared Pillow dependency;
the mock now returns that PDF rather than PDF-like text. It contains no real data,
fillable fields or signature and is not evidence of a provider-generated artifact.
When available, the focused test uses `pdfinfo` to independently parse it. The
official [DocuSeal API reference](https://www.docuseal.com/docs/api) was checked
on 2026-11-09: the request fields document notification flags and additional
options, but documentation alone does not establish deployed behavior, isolation,
webhook authenticity or idempotency. The mock stays offline and remains explicitly
mock-only; no network transport or production signing path is enabled.
