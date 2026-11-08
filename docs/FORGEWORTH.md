# Forgeworth: the Gentoo Forge butler

A dependency-free, read-only terminal prototype. It uses the existing shell scripts for preflight and planning; installation stages remain **locked**.

## Run

```bash
python3 tui/forgeworth.py --demo
python3 tui/forgeworth.py
python3 tui/forgeworth.py --config config/hardware.env
```

Run without root privileges. The plan command requires a real whole-disk device and refuses mounted targets. It **does not** partition, format, or install anything. The `--demo` flag does not execute shell scripts.

## Planned architecture

- A polished Textual-based TUI with progress panels, responsive layouts, accessible color themes, and keyboard navigation.
- A deterministic installer engine, separate from the UI and from any AI integration.
- Optional Codex CLI diagnostics using sanitized logs and a restricted workspace. No automatic privilege escalation or arbitrary command execution.
- Permission tiers: read-only analysis, proposed configuration patch, explicitly approved non-destructive action, and separately confirmed destructive action.
- Disk safety: independently verify target path, disk serial, mount ancestry, and exact confirmation; preserve the existing `--nuke-it` gate. The AI cannot override the gate.
- Butler / Engineer / Roast / Emergency personalities. Emergency mode is concise and never jokes about data loss.
- An offline fallback personality so installation guidance does not depend on internet access or a model subscription.

## Milestone scope

This first PR adds the interface skeleton, not Codex integration, not disk writes, and not a complete Gentoo installer. All future stages require independent testing, including disposable VM tests.
