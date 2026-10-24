# Security

Railet is an early development prototype. Use synthetic data only. No released version is currently supported for production or real customer information. Current development receives fixes as capacity permits; there is no response-time commitment.

## Report privately

Use GitHub's [Report a vulnerability](https://github.com/ephyro/railet/security/advisories/new) feature under the repository's Security tab. This is the private channel for maintainers to triage reports. Include the affected revision, impact, and minimal reproduction using invented records. If the form is unavailable, open a public issue saying only that a private reporting channel is needed; omit the vulnerability details.

Do not post exploit details, secrets, customer information, account data, contracts, or private screenshots to public issues or Discussions. Do not send secrets in a report even when reporting privately. No railet.com email address is advertised as a disclosure channel.

## Current limitations

Production security review, MFA, encryption/key management review, backup restoration drills, incident procedures, deployment hardening, and workflow-specific legal/financial review remain outstanding. Uploaded PDFs are not malware-scanned or verified and must remain synthetic. Do not expose the development server publicly or use this build for live transactions. See [the plan](docs/RAILET_PLAN.md) and module documentation for implemented controls and unresolved gates.
