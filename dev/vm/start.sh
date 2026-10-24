#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
vm_dir="$project_dir/.local/railet-vm"
vm_disk="$vm_dir/railet-dev.qcow2"
installer="${RAILET_VM_ISO:-$HOME/Downloads/ubuntu-26.04.1-live-server-amd64.iso}"
mkdir -p "$vm_dir"
chmod 700 "$vm_dir"
if [[ ! -f "$vm_disk" ]]; then
    qemu-img create -f qcow2 "$vm_disk" 30G
fi
accel=(-accel tcg -cpu max)
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
    accel=(-accel kvm -cpu host)
else
    echo 'KVM unavailable; using slower software emulation.' >&2
fi
boot=()
case "${1:-}" in
    --install)
        [[ -f "$installer" ]] || { echo "Installer not found: $installer" >&2; exit 1; }
        boot=(-cdrom "$installer" -boot once=d)
        ;;
    '') ;;
    *) echo "Usage: $0 [--install]" >&2; exit 1 ;;
esac
exec qemu-system-x86_64 \
    -name railet-dev \
    "${accel[@]}" -smp 2 -m 4096 \
    -drive "file=$vm_disk,format=qcow2,if=virtio" \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2223-:22 \
    -display gtk \
    "${boot[@]}"
