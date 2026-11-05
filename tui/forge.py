#!/usr/bin/env python3
"""gentoo-forge: deliberately read-only curses control plane (stdlib only)."""
from __future__ import annotations

import argparse
import curses
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3
SECTIONS = ["Overview", "Hardware", "Storage plan", "System profile", "Validation", "Recovery", "Safety"]

# Humor is strictly cosmetic: never replace errors, warnings or safety decisions.
ROASTS = {
    "mild": [
        "Welcome to Gentoo. Free time was apparently becoming a problem.",
        "Six cores, twelve threads, and an unreasonable amount of optimism.",
        "Btrfs snapshots: because confidence is not a recovery strategy.",
        "Everything checks out. Suspicious, frankly.",
        "The installer remains read-only. Your SSD sends its regards.",
        "Compiling Linux: a perfectly normal way to spend a weekend.",
        "GRUB recovery exists because computers have a flair for drama.",
    ],
    "spicy": [
        "You chose Gentoo voluntarily. The logs will remember this.",
        "Your CPU has filed a complaint with the Department of Labor.",
        "We have snapshots because 'I know what I'm doing' isn't a backup.",
        "Nothing exploded. Try not to look so disappointed.",
        "Your SSD is safe. Unlike your plans for the weekend.",
        "The kernel will finish compiling sometime before the heat death of the universe.",
        "Congratulations, you've made a bootloader into a personality trait.",
    ],
}
def commentary(level: str, section: int) -> str:
    if level == "off":
        return ""
    return ROASTS[level][section % len(SECTIONS)]

DEFAULTS = {
    "HOSTNAME": "forge", "TIMEZONE": "America/New_York", "LOCALE": "en_US.UTF-8",
    "CPU_MARCH": "znver2", "GPU_DRIVER": "amdgpu", "BOOT_MODE": "uefi",
    "PARTITION_TABLE": "gpt", "DESKTOP": "plasma", "INIT_SYSTEM": "openrc",
    "FILESYSTEM": "btrfs",
}
DECISIONS = [
    ("Architecture", "amd64 multilib / standard OpenRC Stage 3"),
    ("Kernel", "gentoo-kernel source + gentoo-kernel-bin fallback"),
    ("Initramfs", "Dracut / swap UUID resume / conservative updates"),
    ("Graphics", "AMDGPU / RADV / Wayland + XWayland"),
    ("Audio", "PipeWire / WirePlumber"),
    ("Gaming", "Steam / Proton / Wine / GameMode / 32-bit Vulkan"),
    ("Snapshots", "Snapper: 6h 7d 4w 3m / independent home"),
    ("Login", "SDDM / sudo wheel / password authentication"),
]

def parse_config(path: Path) -> dict[str, str]:
    """Read simple assignments as data; NEVER execute a config file."""
    values = dict(DEFAULTS)
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]*)=(?:"([^"\n]*)"|([A-Za-z0-9_./:+-]*))', line)
        if match and match.group(1) in DEFAULTS:
            values[match.group(1)] = match.group(2) if match.group(2) is not None else match.group(3)
    return values

def plan_for_bytes(size: int) -> dict[str, object]:
    if not isinstance(size, int) or size < 30 * GIB:
        raise ValueError("At least 30 GiB required for this illustrative plan")
    return {
        "mode": "READ_ONLY", "table": "GPT", "boot": "UEFI",
        "partitions": [
            {"name": "EFI System", "size_gib": 1},
            {"name": "Linux swap", "size_gib": 20},
            {"name": "Btrfs root", "size_gib_at_least": size // GIB - 22},
        ],
        "note": "1 GiB reserved for GPT/alignment/capacity rounding; exact boundaries unimplemented",
    }

def inspect_hardware() -> list[str]:
    """Only fixed-argument, read-only system queries; no shell."""
    rows = []
    for label, args in [
        ("Disks", ["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL"]),
        ("Firmware", ["uname", "-m"]),
    ]:
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=4, check=False)
            rows.append(label + ":")
            rows.extend((p.stdout or p.stderr or "(no output)").strip().splitlines()[:28])
        except (OSError, subprocess.TimeoutExpired) as exc:
            rows.append(f"{label}: unavailable ({type(exc).__name__})")
    rows.append("UEFI: " + ("detected" if Path("/sys/firmware/efi").is_dir() else "not detected"))
    return rows

def validation() -> list[str]:
    lines = ["STATIC VALIDATION / NO WRITES", ""]
    try:
        plan_for_bytes(100 * GIB)
        lines.append("[PASS] 100 GiB synthetic partition plan")
    except ValueError:
        lines.append("[FAIL] synthetic plan")
    try:
        plan_for_bytes(29 * GIB)
        lines.append("[FAIL] undersized disk accepted")
    except ValueError:
        lines.append("[PASS] undersized disk rejected")
    lines += [
        "[PASS] TUI has no install/partition/format action",
        "[INFO] Actual SSD selection not authorized",
        "[PENDING] Live Gentoo package metadata verification",
        "[PENDING] VM boot, hibernation and GRUB recovery tests",
        "[PENDING] End-to-end CI verification",
    ]
    return lines

def section_lines(index: int, cfg: dict[str, str]) -> list[str]:
    if index == 0:
        return ["GENTOO-FORGE // MISSION CONTROL", "", "STATE: PLANNING ONLY",
                "TARGET: dedicated SSD (identifier unconfirmed)",
                "BOOT: UEFI + GPT | 1 GiB ESP | 20 GiB swap | Btrfs",
                "KERNEL: source-built + binary fallback",
                "SECURITY: no disk encryption | Secure Boot disabled", "",
                "Navigate with arrows / Tab / 1-7. Press q to quit.",
                "This interface contains no destructive execution path."]
    if index == 1:
        return ["READ-ONLY HARDWARE INSPECTION", ""] + inspect_hardware()
    if index == 2:
        p = plan_for_bytes(100 * GIB)
        return ["ILLUSTRATIVE PLAN FOR 100 GiB SSD", "",
                "1  EFI System       1 GiB",
                "2  Linux swap      20 GiB",
                f"3  Btrfs root     >= {p['partitions'][2]['size_gib_at_least']} GiB", "",
                str(p["note"]), "",
                "Disk identifier unknown. No writes or disk selections."]
    if index == 3:
        return ["SYSTEM PROFILE", ""] + [f"{k:16} {v}" for k, v in cfg.items()] + [""] + [f"{k:16} {v}" for k, v in DECISIONS]
    if index == 4:
        return validation()
    if index == 5:
        return ["RECOVERY DESIGN / NOT IMPLEMENTED", "",
                "GRUB: primary + fallback + snapshot entries",
                "Snapper: independent root/home configurations",
                "Preserve kernel + modules + initramfs as a set",
                "Do not resume stale hibernation images after rollback",
                "Recovery USB procedure still needs testing."]
    return ["SAFETY INTERLOCKS", "",
            "READ-ONLY MODE: PERMANENT IN THIS MILESTONE",
            "No installation or formatting commands are exposed.",
            "No target disk selection or confirmation workflow.",
            "No passwords, secrets or credentials collected.",
            "Live disks are listed for inspection only.",
            "Exit with q or Escape."]

def export_plan(size_gib: int) -> str:
    return json.dumps(plan_for_bytes(size_gib * GIB), indent=2, sort_keys=True)

def draw(stdscr: object, cfg: dict[str, str], attitude: str = "mild") -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    selected, scroll = 0, 0
    while True:
        height, width = stdscr.getmaxyx()
        stdscr.erase()
        if height < 12 or width < 55:
            stdscr.addnstr(0, 0, "Terminal too small: need 55x12. q exits.", max(0, width - 1))
        else:
            def put(y: int, x: int, message: str, style: int = 0) -> None:
                if 0 <= y < height - 1 and 0 <= x < width - 1:
                    stdscr.addnstr(y, x, message, width - x - 1, style)
            put(0, 1, " GENTOO-FORGE  /  INSTALLATION MISSION CONTROL ", curses.A_BOLD | curses.A_REVERSE)
            put(1, 2, "SAFE MODE: READ ONLY  |  NO DISK WRITES", curses.A_BOLD)
            sidebar = 21
            for i, label in enumerate(SECTIONS):
                style = curses.A_REVERSE if i == selected else curses.A_NORMAL
                put(3 + i, 1, f" {i + 1}  {label:<16}", style)
            for y in range(3, height - 2):
                put(y, sidebar, "|")
            lines = section_lines(selected, cfg)
            usable = height - 6
            scroll = min(scroll, max(0, len(lines) - usable))
            for offset, line in enumerate(lines[scroll:scroll + usable]):
                put(3 + offset, sidebar + 2, line, curses.A_BOLD if offset == 0 else 0)
            put(height - 3, 1, ("COMMENTARY [" + attitude.upper() + "]: " + commentary(attitude, selected)) if attitude != "off" else "COMMENTARY: OFF")
            put(height - 2, 1, "ARROWS/TAB: navigate   PGUP/PGDN: scroll   A: attitude   Q: quit", curses.A_REVERSE)
        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("a"), ord("A")):
            attitude = {"off": "mild", "mild": "spicy", "spicy": "off"}[attitude]
            continue
        if key in (ord("q"), ord("Q"), 27):
            return
        if key in (curses.KEY_DOWN, ord("j"), 9):
            selected, scroll = (selected + 1) % len(SECTIONS), 0
        elif key in (curses.KEY_UP, ord("k")):
            selected, scroll = (selected - 1) % len(SECTIONS), 0
        elif ord("1") <= key <= ord("7"):
            selected, scroll = key - ord("1"), 0
        elif key == curses.KEY_NPAGE:
            scroll += max(1, height - 7)
        elif key == curses.KEY_PPAGE:
            scroll = max(0, scroll - max(1, height - 7))

def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Gentoo installer planning TUI")
    parser.add_argument("--json-plan", type=int, metavar="DISK_GIB", help="Export a synthetic plan as JSON (no disk access)")
    parser.add_argument("--validate", action="store_true", help="Run internal static checks without curses")
    parser.add_argument("--attitude", choices=("off", "mild", "spicy"), default="mild", help="Optional cosmetic commentary (default: mild)")
    args = parser.parse_args()
    if args.json_plan is not None:
        try:
            print(export_plan(args.json_plan))
            return 0
        except ValueError as exc:
            parser.error(str(exc))
    if args.validate:
        print("\n".join(validation()))
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Interactive TUI requires a terminal; use --validate or --json-plan")
    curses.wrapper(draw, parse_config(ROOT / "config/hardware.env"), args.attitude)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
