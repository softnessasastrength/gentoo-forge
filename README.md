# gentoo-forge

A safety-first, reproducible Gentoo Linux workstation installer for AMD Ryzen 5 4500 and Radeon RX 6600 XT.

> **Status: experimental.** No disk modifications are performed by the initial scripts. Review the Gentoo Handbook before installing.

The initial implementation is developed on a feature branch and reviewed before merging.

## Read-only terminal mission control

Run with Python 3 (standard library only, no pip dependencies):

```sh
python3 tui/forge.py
python3 tui/forge.py --validate
python3 tui/forge.py --json-plan 100
```

The curses interface offers seven keyboard-navigable panels: overview, hardware, storage plan, system profile, validation, recovery, and safety. Arrow keys or Tab navigate, number keys jump to a panel, Page Up/Down scroll, and Q quits. The JSON mode uses a **synthetic disk capacity in GiB**, not a disk path. No partitioning, formatting, or installation action exists in this TUI. Live hardware inspection uses fixed read-only commands. Unit tests run via `bash tests/validate.sh`.

**Important:** The TUI is a planning prototype, not an installer. Exact Btrfs subvolume layout, GRUB snapshot integration, firmware and USE flag resolution, and live boot tests are still pending.

### Attitude settings

The TUI displays optional section-specific, lighthearted commentary. It defaults to `mild`; press **A** to cycle `mild` → `spicy` → `off`, or launch with `python3 tui/forge.py --attitude off`. Commentary is presentation-only and never changes validation results, safety decisions, or error messages.
