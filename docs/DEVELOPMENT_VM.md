# Optional QEMU development VM

Docker Compose can run directly on your workstation. A separate Linux VM is useful when the host's Docker/kernel configuration makes that inconvenient. VM images and local SSH keys belong under ignored `.local/`; they must never be committed.

## Create your own VM

Install QEMU and obtain an Ubuntu Server installer from Ubuntu. `dev/vm/start.sh --install` creates a 30 GiB disk under `.local/railet-vm/` and boots the installer. Set `RAILET_VM_ISO` to your ISO path; the script otherwise looks in your Downloads directory. It uses KVM when available and forwards only host loopback port 2223 to guest SSH port 22. After installation, `dev/vm/start.sh` boots the disk. Run only one VM process per disk.

The optional sync script assumes a guest account named `dev`, project path `~/railet`, and a dedicated key at `.local/vm-access/id_ed25519`. Create and authorize your own key, verify the guest host key, and adjust the script if your configuration differs. No credentials, private keys, VM images, or preconfigured accounts are distributed with this repository.

```sh
./dev/vm/sync.sh
ssh -F /dev/null -p 2223 -i .local/vm-access/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes dev@127.0.0.1
```

The explicit sync allowlist copies source without deleting guest files or transferring local credentials. In the guest, install Docker/Compose, create your own `.env`, and follow the README from `~/railet`. Use your configured privilege elevation for Docker. Apply migrations explicitly and rebuild for dependency changes.

## Open the application from the host

The Compose service binds guest loopback port 8000. Open a local SSH tunnel in a separate terminal:

```sh
ssh -F /dev/null -p 2223 -i .local/vm-access/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -N -L 127.0.0.1:8001:127.0.0.1:8000 dev@127.0.0.1
```

Then visit http://localhost:8001. Seed a fresh synthetic demo yourself; no demo password is published. Keep the VM, ports, and data private. This setup does not make the application production ready.

## Verification evidence

On October 24, 2026, the maintained development VM passed 153 PostgreSQL tests and system/migration checks. Private photos and supporting PDFs persisted after web-container recreation. Container persistence is not a backup restore drill. Staging remains a separate undeployed rehearsal configuration. See [DEVELOPMENT.md](DEVELOPMENT.md) and module documentation for scope and remaining gates.
