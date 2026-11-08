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
