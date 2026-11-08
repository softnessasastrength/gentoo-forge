# gentoo-forge

A safety-first, reproducible Gentoo Linux workstation installer for AMD Ryzen 5 4500 and Radeon RX 6600 XT.

> **Status: experimental.** No disk modifications are performed by the initial scripts. Review the Gentoo Handbook before installing.

The initial implementation is developed on a feature branch and reviewed before merging.

FORGEWORTH now provides asynchronous read-only inspection, optional Codex chat,
mode/intensity controls and headless UI tests. Start with the
[TUI guide](docs/FORGEWORTH-TUI.md). Read the [architecture](docs/ARCHITECTURE.md)
and [target qualification plan](docs/INSTALLATION-TARGET.md) for explicit limits.

For a disposable VirtualBox trial, run `python -m tui.app --virtualbox` or press F4.
The [VirtualBox guide](docs/VIRTUALBOX.md) covers host resource checks, ISO setup,
read-only diagnostics, explicit disk validation and JSON/text report export.
This guided milestone does not claim a completed installation.

## Development on Debian / Crostini

Run `bash setup-dev.sh` from the repository root. See [QEMU smoke testing](docs/QEMU.md)
for an unprivileged disposable firmware-process test and Crostini resource limits.

## Portable live-CD companion

Run `bash build-livecd.sh` to build a USB-copyable folder with Python, offline UI
dependencies and optional Codex. See [live-CD setup](docs/LIVE-CD.md) for the
unprivileged launcher and fresh authentication. No ISO flashing or disk writes
are enabled. [AGENTS.md](AGENTS.md) documents personality and authority settings.

The permanent [`butler` executable](docs/BUTLER.md) supports interactive chat,
one-shot questions, explicit session resume and offline help. Stage it into the
mounted target with `bash install-butler.sh --target-root /mnt/gentoo` before
reboot; the live bundle carries its required Python/Codex runtimes. It runs only
as an ordinary user, verifies actual instruction discovery, and shares the
canonical [personality policy](forgeworth/AGENTS.md) with the Textual interface.

## Current storage work

`bash forge-install.sh doctor` checks Gentoo live prerequisites;
`bash forge-install.sh plan --disk /dev/EXPLICIT_DISK` inspects identity/ancestry
and proposes allocations only in existing GPT free space. It never resizes or
clears existing partitions. Physical writes remain qualification-locked. Read
the [live-CD engineering handoff](docs/LIVE-CD-HANDOFF.md) before continuing work.

The [Handbook traceability matrix](docs/HANDBOOK-COVERAGE.md) maps the complete
selected installation path to code, tests and verification procedures. The
[minimal Gentoo VM qualification](docs/MINIMAL-VM.md) runs on a sufficiently
resourced PC or GitHub runner, with retained boot evidence. It is not a completed
Plasma installer, and the Chromebook install VM must not be retried after its OOM.
