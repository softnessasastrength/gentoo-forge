# Forgeworth full-screen preview

This is an **experimental read-only preview**, not a working installer. Never run an unreviewed installer against a disk containing important data.

## Launch

From the repository root, in a Python virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r tui/requirements.txt
python -m tui.app
```

The interface provides a hardware panel, a progress panel, a scrolling operations log, and a separate chat pane. Press F1 for help, F2 to focus chat, F3 for logs. The **Demo** button displays explicitly simulated progress. Preflight and Plan call the existing read-only shell scripts; Plan requires the existing hardware config and a valid unmounted whole disk. The progress bar is indeterminate for real operations rather than fabricating completion percentages.

## Optional Codex chat

Codex CLI must be installed and authenticated separately. To opt in:

```bash
FORGEWORTH_CODEX=1 python -m tui.app
```

Chat launches `codex exec` with a read-only sandbox in an empty temporary directory. It has a 90-second timeout and no direct interface to the installer. This is **not a hardened security sandbox**: local Codex configuration, authentication, model instructions, and environment access may still apply. Run under an unprivileged account; review your Codex configuration and network/data exposure before enabling. Never use on a privileged installer session until isolation has been independently reviewed. No API key is stored by this app.

Chat responses are asynchronous so the UI remains responsive. Conversation history and live installer telemetry are **not yet** sent to Codex. The offline response is deliberately a placeholder, not a fabricated AI answer.

## Next milestones

1. Add structured stage events from real installer engine operations and durable progress/checkpoint logs.
2. Add Textual tests for layout, button behavior, and chat failures.
3. Separate Codex into a restricted sidecar service with explicit data-sharing permissions and stronger isolation.
4. Add per-stage disk identity confirmation and VM-tested installation workflows before unlocking any writes.
