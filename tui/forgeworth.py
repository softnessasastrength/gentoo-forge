#!/usr/bin/env python3
"""Forgeworth: read-only Gentoo Forge terminal concierge."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
STAGES = [
    ("Preflight", "scripts/00-preflight.sh", True),
    ("Installation plan", "scripts/10-plan.sh", True),
    ("Bootstrap", "scripts/20-bootstrap.sh", False),
    ("Chroot", "scripts/30-chroot.sh", False),
    ("Kernel", "scripts/40-kernel.sh", False),
    ("Desktop", "scripts/50-desktop.sh", False),
    ("Finalize", "scripts/60-finalize.sh", False),
]
BANTER = {
    "welcome": "Good evening, sir. Shall we build an operating system the difficult way?",
    "preflight": "Inspecting the hardware, sir. One must know the patient before operating.",
    "plan": "A plan, sir. How refreshingly unlike your usual approach.",
    "locked": "That stage remains locked, sir. I refuse to turn your SSD into modern art.",
    "failure": "An unfortunate development, sir. At least we have not formatted anything.",
    "goodbye": "Very good, sir. The silicon survives another evening.",
}
RESET = "\033[0m"
GREEN = "\033[38;5;114m"
GOLD = "\033[38;5;221m"
DIM = "\033[2m"


def banner(color: bool = True) -> None:
    c, g, r = (GREEN, GOLD, RESET) if color else ("", "", "")
    print(f"{c}╔══════════════════════════════════════════════════════╗{r}")
    print(f"{c}║{r}  {g}G E N T O O   F O R G E{r}  //  FORGEWORTH          {c}║{r}")
    print(f"{c}║{r}  Your sarcastic installation concierge              {c}║{r}")
    print(f"{c}╚══════════════════════════════════════════════════════╝{r}")


def run_stage(index: int, config: Path | None = None) -> int:
    name, script, enabled = STAGES[index]
    if not enabled:
        print("\nFORGEWORTH:", BANTER["locked"])
        return 2
    print("\nFORGEWORTH:", BANTER["preflight" if index == 0 else "plan"])
    command = ["bash", str(ROOT / script)]
    if index == 1 and config is not None:
        command.append(str(config))
    # Never shell=True. Never elevate. Existing scripts remain the authority.
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        print("FORGEWORTH:", BANTER["failure"])
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Forgeworth read-only TUI")
    parser.add_argument("--config", type=Path, help="Path to declarative hardware config")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Show interface without executing scripts")
    args = parser.parse_args()
    color = sys.stdout.isatty() and not args.no_color and not os.environ.get("NO_COLOR")
    banner(color)
    print("\nFORGEWORTH:", BANTER["welcome"])
    while True:
        print("\n  1  Hardware preflight     [READ ONLY]")
        print("  2  Installation plan      [READ ONLY]")
        print("  3  Bootstrap              [LOCKED]")
        print("  4  Chroot                 [LOCKED]")
        print("  5  Kernel                 [LOCKED]")
        print("  6  Desktop                [LOCKED]")
        print("  7  Finalize               [LOCKED]")
        print("  q  Leave the premises")
        try:
            choice = input("\nYour command, sir > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nFORGEWORTH:", BANTER["goodbye"])
            return 0
        if choice in ("q", "quit", "exit"):
            print("FORGEWORTH:", BANTER["goodbye"])
            return 0
        if choice not in tuple(str(i) for i in range(1, 8)):
            print("FORGEWORTH: An imaginative selection, sir. Try a listed option.")
            continue
        index = int(choice) - 1
        if args.demo:
            print("FORGEWORTH: Demonstration only, sir. No scripts executed.")
        else:
            run_stage(index, args.config)


if __name__ == "__main__":
    raise SystemExit(main())
