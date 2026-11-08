# Architecture and delivery status

FORGEWORTH is a functional read-only inspection and conversation application. It is
not yet a Gentoo installer. No installation or destructive VM test has run.

`app.py` owns Textual widgets and separate operation/chat workers. `engine.py`
owns a deterministic allowlist of inspection scripts, structured stage events and
atomic checkpoint replacement. Interrupted inspections rerun after restart; stale
success is never permission to write. Checkpoints are not an installation resume
protocol. `process.py` supervises argument-vector subprocesses, bounded streamed
output, deadlines and whole-process-group cleanup. `backend.py` owns an in-memory,
bounded conversation independent of the engine. `personality.py` supplies style
and safety policy. `telemetry.py` only observes the host. `safety.py` validates
explicit disk identities and exact confirmations against supplied inventories.
It is deliberately not connected to any write executor.

AI receives stage metadata, the latest question and up to 20 conversation messages.
No raw logs, environment variables, disk inventory or authentication material is
included automatically. Users must not paste secrets into chat. Replies and process
logs render as plain text with bounded scrollback. Codex manages its own credentials;
the application never reads credential files. Authentication failures return a
fixed error rather than exposing CLI diagnostics in prompts or logs.

Codex runs unprivileged in an empty temporary directory with read-only sandbox,
user configuration and execpolicy rules ignored, apps/plugins/shell/unified exec
and web search disabled. CLI capabilities are checked before sending a prompt.
These restrictions are defense in depth, not a substitute for an independently
audited OS isolation boundary. Do not enable AI in a privileged installer session.
The backend refuses root. Future privileged operations require a separate narrow
helper and authenticated IPC; no AI command dispatch API exists.

Development baseline: six unit tests passed; shell syntax passed (ShellCheck was
absent). Existing PR #2 was merged before this work. Codex 0.167.0-alpha.4 help,
feature names and login commands were inspected. Login status reported ChatGPT
authentication, but a real greeting request returned HTTP 401 / expired session.
Mocked conversation tests pass; successful live inference remains unverified here.

## Next implementation gates

1. Bind disk inventory collection to mount ancestry, mapper/RAID ancestry, swaps,
   stable device IDs and serial revalidation. The pure validator alone is not a
   complete live disk guard. Add durable proposed/approved action audit records.
2. Isolated UEFI VM tests: signed Stage3 verification, partition/extraction/mount
   operations, deterministic configuration and scoped privileged helper.
3. Package event parsing, actual compilation counts, identified hwmon sensors,
   failed build inspection and verified resumable install checkpoints.
4. Kernel/initramfs/GRUB boot verification, hibernate/resume, independent root/home
   snapshots, recovery-media rollback and interrupted-install recovery.
5. Real hardware qualification, accessibility review, hardened AI sidecar.
