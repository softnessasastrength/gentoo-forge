# Permanent FORGEWORTH / Butler GPT

`butler` is a real executable in `/usr/local/bin`, independent of shell aliases
and caller working directory. Bash, Zsh, Fish and conventional shells find it
through the usual `/usr/local/bin` PATH. If your environment removes that standard
directory, restore your normal system PATH or use `/usr/local/bin/butler`.

```bash
butler login
butler
butler "Why is Portage rebuilding GCC?"
butler --resume
butler --resume SESSION_UUID "Continue explaining the dependency change"
butler --mode roast --sarcasm 100 "Explain my questionable USE flags"
butler --offline
butler --check-instructions
```

The interactive prompt is a conversational REPL using Codex exec, not Codex's
unrestricted agent TUI. `/quit`, EOF or Ctrl+C exits; Ctrl+C also stops a pending
request. Each ordinary launch starts a new conversation; turns within it resume
the same saved Codex thread. `--resume` continues the last successful Butler
session; an explicit UUID selects another saved Codex thread. There is no global
`codex resume --last` that could accidentally choose an unrelated coding session.

## One policy, verified discovery

`forgeworth/AGENTS.md` is the canonical version-controlled policy, including
personality, Gentoo knowledge, safety boundaries and conversational behavior.
Both the Textual prompt and Butler load it. CLI mode/intensity select per-turn
settings; Emergency and critical situations suppress humor regardless of intensity.

Before inference Butler copies the complete policy into its dedicated stable
conversation directory as `AGENTS.md`, invokes the real CLI's local
`codex debug prompt-input` renderer, and verifies that the complete policy appears
in the discovered prompt. A missing, truncated or unsupported discovery result
blocks inference. The same policy is additionally included in each question's
prompt. Discovery does not require a model call. Tests exercise both a real
installed CLI when available and negative/mocked cases. Discovery is a local
loader check, not proof that a model will obey every instruction.

## Install before reboot

From the live bundle, with the Gentoo target already mounted by an authorized
human, run as live-session root:

```bash
bash /opt/forgeworth-live/install-butler.sh --target-root /mnt/gentoo
```

This copies only application policy/code and available bundled Python/Codex
runtimes into `/mnt/gentoo/usr/local/lib/gentoo-forge/releases/`, then atomically
selects the release and installs `/mnt/gentoo/usr/local/bin/butler`. It does not
mount, partition, format, create users, chroot or run a target executable. These
are ordinary files on the target filesystem, so they survive chroot and reboot.
No credentials, local disk selection, live-user state or environment are copied.

The intended target user still needs to be created by the actual installation
procedure. After boot, open Konsole **as that ordinary user**, run `butler login`
once, then `butler`. The source-checkout installer also works, but without the
live bundle you must supply target Python 3.11+ and Codex separately. The
portable bundle provides both; it does not need npm or a source build on target.

## Upgrade and uninstall

Build a reviewed new live bundle and rerun its installer with the same explicit
target root. On an already booted installed system, use `--target-root /` as
root. Existing unmanaged launchers and symlink target traversal are refused.
Release directories are immutable copies; the current-release pointer changes
atomically and old releases remain available for inspection. Never edit them in
place; change the version-controlled policy and reinstall to upgrade.

```bash
# Remove only owned application files (root for the running system):
bash install-butler.sh --target-root / --uninstall
```

Uninstall preserves user conversation state and authentication. Use `butler
logout` before uninstall if credentials should be removed. Inspect user state
before manually deleting it; it can contain private conversations.

## State, authentication and migration

Default credentials and Codex sessions live in
`~/.local/state/forgeworth/codex`; Butler's policy copy and last-successful thread
record are under `~/.local/state/forgeworth/conversation-*`. Permissions are private.
An explicitly supplied `CODEX_HOME` is honored and gets a separate last-session
record. `butler login/status/logout` operates on that same chosen Codex home.
Missing CLI/authentication yields setup guidance; `--offline` never contacts AI.
An apparently valid login can still expire or fail on the next model request.

Installed-user home files persist across terminal sessions and reboots. A live
user's volatile `/run` home disappears on reboot: sessions are not magically
transferred. If you explicitly want to migrate conversations, privately copy
that user's entire `.local/state/forgeworth` directory to the corresponding
installed user's home, preserving its directory layout, then correct ownership
and restrict access to that user. That copy includes credential material in the
Codex subdirectory: do it only with explicit consent, onto trusted encrypted
storage, never into the public bundle or repository. Prefer fresh authentication
on target when history migration is unnecessary. No migration occurs automatically.

## Permissions and limitations

Butler refuses root. Every request uses a read-only Codex sandbox, approval
policy never, ignored exec user configuration/rules, disabled shell/unified
exec/apps/plugins/patch/web tools, and a filtered environment. It does not inherit
arbitrary tool-provider environment settings. These restrictions only narrow
permissions; no CLI option grants write access or passes arbitrary Codex flags.
User model-provider configuration is not silently copied; this supported path
uses the bundled Codex default provider and selected Codex authentication home.
Questions, canonical policy and saved conversation history are shared with that
provider; logs/telemetry are not automatically sent. No model suggestion is an
authorization token or dispatchable privileged command.

The launcher reads user questions and prints answers; the fixed CLI subprocess
is its only execution path. Native CLI sandbox/tool restrictions remain defense
in depth, not an independently certified isolation boundary. A missing supported
CLI or failed discovery fails closed. Successful live inference and an actual
Gentoo post-reboot launch still require qualification; temporary-directory
staging/discovery tests do not prove an installed Gentoo system booted.
