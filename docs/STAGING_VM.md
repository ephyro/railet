# Debian staging VM

Status: configuration prepared; no VM has been created or deployed by the agent. Synthetic data only. This is a rehearsal environment, not approval for production use. MFA, encryption-at-rest/key management, operational recovery tests, and legal release gates remain outstanding.

## VM configuration

Use Debian stable from an official installation image, with 2 vCPUs, 4 GB RAM, and 30 GB disk as a starting development allocation. These are planning estimates, not measured requirements. Install a minimal server with OpenSSH, a non-root operator account, and security updates. Use NAT networking, not a public address or router port forwarding. Keep SSH limited to the host/private network; don't expose PostgreSQL or Gunicorn.

The tool environment has QEMU but no accessible /dev/kvm or libvirt tools. Create the VM through your Gentoo desktop VM manager; hardware virtualization availability must be verified on the host. Don't rebuild the host kernel blindly. A snapshot before deployment is useful, but doesn't replace a database backup.

Install Docker Engine and the Compose plugin inside Debian following the official instructions: https://docs.docker.com/engine/install/debian/ . Use sudo for Docker unless deliberately configuring rootless operation. Don't add the operator to the root-equivalent Docker group by default.

Copy the project to ~/railet inside the VM using an explicit allowlist (application directories, migrations, templates, static, manage.py, requirements*.txt, compose.staging.yaml and deploy/staging). Do not copy .env files, .git history, the private DealerCenter capture, or host databases. Generate fresh staging secrets there.

## Initial deployment (inside VM)

From ~/railet:

```sh
python3 deploy/staging/init_env.py
sudo docker compose --env-file .env.staging -f compose.staging.yaml build
sudo docker compose --env-file .env.staging -f compose.staging.yaml up -d db
sudo docker compose --env-file .env.staging -f compose.staging.yaml run --rm web python manage.py migrate
```

Create synthetic demo data using a one-off development-settings process. This does not start an HTTP server or change the running staging configuration:

```sh
sudo docker compose --env-file .env.staging -f compose.staging.yaml run --rm -e DJANGO_SETTINGS_MODULE=railet.settings -e RAILET_DEBUG=1 web python manage.py seed_demo
sudo docker compose --env-file .env.staging -f compose.staging.yaml up -d
```

The demo command still requires a 12-character password and interactive terminal input. A VM does not fix that prompt; if input fails, diagnose separately. Never put passwords in command arguments or shared transcripts.

Only the proxy publishes a port, on the VM's loopback. The stack uses separate database, private-photo, and Caddy volumes and a separate Compose project from development. Private photos are mounted at /app/private-media and are served only through authorized application routes. Gunicorn serves the app; WhiteNoise serves collected static files; Caddy terminates local HTTPS. Debug stays disabled. Application code is baked into the image; deploy code changes with a rebuild.

## Access from Gentoo

Keep the SSH session running (replace operator and VM_IP with your actual values):

```sh
ssh -N -L 8443:127.0.0.1:8443 operator@VM_IP
```

Open https://localhost:8443 on Gentoo. Caddy uses a private staging CA, so browsers won't trust its certificate initially. On the VM export ONLY its public root certificate:

```sh
sudo docker compose --env-file .env.staging -f compose.staging.yaml cp proxy:/data/caddy/pki/authorities/local/root.crt ./staging-root.crt
openssl x509 -in staging-root.crt -noout -fingerprint -sha256
```

Copy staging-root.crt over the same authenticated SSH connection, verify its fingerprint, and import it into a dedicated staging browser profile's certificate-authority store. Do not copy the CA private key or disable TLS verification globally. Verify HTTPS with the exported certificate:

```sh
curl --cacert staging-root.crt -I https://localhost:8443/accounts/login/
```

Confirm the login screen, CSS, POST login, inventory pages and logout all work over HTTPS. This setup uses localhost deliberately; it requires no railet.com DNS changes.

## Checks and recovery rehearsal

```sh
sudo docker compose --env-file .env.staging -f compose.staging.yaml run --rm web python manage.py check
sudo docker compose --env-file .env.staging -f compose.staging.yaml run --rm web python manage.py check --deploy
sudo docker compose --env-file .env.staging -f compose.staging.yaml run --rm web python manage.py makemigrations --check --dry-run
sudo docker compose --env-file .env.staging -f compose.staging.yaml run --rm -e DJANGO_SETTINGS_MODULE=railet.settings -e RAILET_DEBUG=1 web python manage.py test
sudo docker compose --env-file .env.staging -f compose.staging.yaml logs --tail=80 web proxy
```

Tests run against an isolated test database using base settings; manually verify staging HTTPS/cookies separately. PostgreSQL's application role currently initializes the database and has elevated development privileges; restrict roles before production. check --deploy will report HSTS warnings: long-lived HSTS is deliberately disabled for localhost to avoid affecting unrelated local services. Review every warning; this is not a clean production-security bill of health.

Create a restricted synthetic staging database backup inside the VM:

```sh
mkdir -p backups
chmod 700 backups
(umask 077; sudo docker compose --env-file .env.staging -f compose.staging.yaml exec -T db pg_dump -U railet -d railet -Fc > backups/staging.dump)
```

Restore into a separate scratch database, never overwrite the active database for a test:

```sh
sudo docker compose --env-file .env.staging -f compose.staging.yaml exec -T db createdb -U railet railet_restore_check
sudo docker compose --env-file .env.staging -f compose.staging.yaml exec -T db pg_restore -U railet -d railet_restore_check --exit-on-error < backups/staging.dump
```

The database dump above does not contain uploaded photos. A complete backup must capture the database and staging_media volume consistently while application writes are stopped, protect both as private data, and restore both before checking authenticated photo downloads. A database-only restore is not a complete photo restore.

Verify vehicle, membership, and audit counts against the source using read-only queries, then drop the scratch database deliberately. Rehearse VM reboot and container restart, login persistence, and an upgrade with a pre-upgrade backup. Migration rollback requires an explicit plan; a stale VM snapshot alone can lose later writes. Avoid docker compose down -v: it deletes volumes, including CA material, the database, and uploaded photos.

## Remaining verification

Config validation and Python syntax can be checked without deploying. Actual image builds, Gunicorn startup, certificate provisioning, proxy behavior, migrations, login, static assets, test suite and restore rehearsal must be recorded after execution inside the VM. Dependencies and base images currently use version ranges/tags; lock tested versions/digests before a release. Nothing here deploys public production infrastructure.
