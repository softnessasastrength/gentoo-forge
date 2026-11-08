# QEMU in Crostini

Run `bash setup-dev.sh` from the repository root to install Debian development
packages and pinned Python dependencies. The script uses sudo only for apt;
the TUI and QEMU run as your ordinary account. Package installation remains
interactive. `bash setup-dev.sh --python-only` skips system packages.

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m tui.qemu
# Explicit slower fallback where KVM cannot initialize:
.venv/bin/python -m tui.qemu --accel tcg
```

The smoke test starts a single-vCPU, 256 MiB Q35 VM with OVMF, its own copied
firmware variables and a newly created temporary 64 MiB qcow2 disk. QMP checks
the actual accelerator, expected block attachments and running state. A brief
run is followed by supervised shutdown and temporary-directory cleanup. KVM
failure is an error, not a silent fallback to software emulation. Duration is
bounded to 1–10 seconds. No host block device, network, shared directory or guest
agent is attached, and arbitrary QEMU arguments are not accepted.

`passed` means the configured VM started and remained running. Firmware boot,
Gentoo boot, installed-system boot and installation are explicitly unverified.
There is no ISO or operating system in this test. It does not authorize disk
erasure or qualify hibernation/rollback. QEMU is an additional boundary, not a
guarantee against hypervisor vulnerabilities.

Observed on this Crostini instance on 2026-11-08: QEMU 10.0.13 successfully
initialized KVM (`enabled: true`), and the OVMF process smoke test passed.
The container exposed 6.3 GiB RAM, about 1.8 GiB available before setup, and
22 GiB free disk. These are transient container observations, not Chromebook
physical capacity. They do not support the full 16 GiB Gentoo/Plasma target.
Increase Linux storage and available memory before a full source build; sparse
virtual capacity is not a substitute for actual host free space. A disposable
64 MiB fixture cannot fit the target's 20 GiB swap partition.

The next integration milestone is a verified Gentoo installation ISO in a
separate disposable VM, followed by a narrowly scoped installer helper and
explicit target authorization. Physical installer scripts remain locked.

QEMU flags follow the [official invocation reference](https://www.qemu.org/docs/master/system/invocation.html).
