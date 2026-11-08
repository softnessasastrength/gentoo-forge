# Architecture and delivery status

Gentoo Forge currently combines a functional inspection/conversation TUI with a
separate, partially implemented installation engine. It is **not yet a verified
end-to-end Gentoo installer**. Physical writes remain qualification-locked. The
[Handbook matrix](HANDBOOK-COVERAGE.md) records the remaining required stages;
code presence and unit tests do not imply a successful installed-system boot.

## Processes and authority

`tui/app.py` owns Textual widgets and separate
operation/chat workers. `tui/engine.py` currently allows only read-only inspection
scripts, publishes structured events, and atomically replaces inspection
checkpoints. Interrupted inspections rerun. These checkpoints do not yet implement
installation resume and never authorize writes.

`tui/process.py` supervises asynchronous argv-only subprocesses, bounded output,
deadlines and whole-process-group cleanup. `tui/compilation.py` observes real
Portage log records, distinguishing package-count progress from elapsed time.
Unknown totals remain unknown. Telemetry reports observed load/memory and identified
CPU sensors; it never substitutes GPU temperature for CPU temperature.

The root installation modules are separate from the UI and Codex. `forge-install.sh`
exposes read-only preflight/doctor/plan commands and a separately gated storage
operation. There is no arbitrary shell dispatch API, model authorization token,
automatic target selection or generic `--yes` destructive bypass. The root CLI
requires fresh target identity, `--nuke-it`, a real interactive terminal, and exact
disk/serial/extent/plan confirmation when its qualification gate is eventually
released. The current public CLI does not perform a full installation.

## Installation modules

- `installer/preflight.py`: architecture, UEFI, Secure Boot support, memory,
  prerequisites, DNS/TLS and clock checks.
- `installer/storage.py` and `partition_plan.py`: live kernel disk identity,
  mount/swap/overlay ancestry, GPT free-space allocation, private GPT backups,
  pinned block descriptors, exact extent/size rechecks, filesystem verification
  and audit records. Existing partitions are preserved; no NTFS resize or whole-
  disk wipe path is implemented.
- `installer/media.py`: official Stage3 selection, pinned primary signing keys,
  signed index/checksum authentication, exact archive hash/size and cache revalidation.
- `installer/bootstrap.py`: bounded archive validation, numeric-owner/xattr
  extraction, target configuration, private mount propagation, DNS preparation,
  opt-in verified target swap and cleanup. Chroot subprocess groups are supervised;
  build output is spooled outside RAM and failures report a sanitized bounded tail.
- `installer/portage.py`: exact stable minimal/Plasma OpenRC profile selection from
  repository metadata, in-target multilib verification, and compiler settings.
  The recognized Ryzen 5 4500 uses `znver2`; unknown CPUs use generic `x86-64`.
  Compilation defaults to `-j6 -l6` with validated configurable limits.
- `installer/boot.py`: source-first distribution kernel, dracut and GRUB stage;
  installkernel USE flags are checked through the target's Portage metadata before
  the solver's pretend plan. Signed official binary packages require an explicit
  per-invocation exception. GRUB syntax/root UUID and actual initramfs Btrfs/resume
  modules are checked. These checks do not establish working hibernation.

These stages are exercised progressively by the isolated VM harness. They are not
yet wired into a complete resumable physical-install workflow. Desktop package
configuration, real account authentication, firmware, service setup, verified
snapshots/rollback/hibernate, bootable Forge media and desktop login remain work.

## FORGEWORTH and permanent Butler

`tui/backend.py` owns an in-memory bounded conversation independent of installation.
`tui/personality.py` and `butler_cli.py` share `forgeworth/AGENTS.md`. The permanent
`butler` executable supports a REPL, one-shot questions, explicit session resume,
authentication guidance and offline help. `tools/install_butler.py` stages versioned
releases and an atomic current pointer under `/usr/local`, preserving portable
Python/Codex runtimes when present. Credentials are never copied automatically.

AI requests contain bounded conversation and explicit read-only context. Raw logs,
disk inventories and environment variables are not automatically uploaded. Text
is untrusted and rendered without Rich markup. Codex manages its own credentials;
the application does not read authentication files or forward CLI authentication
diagnostics into model prompts. Users must not paste secrets into chat.

Codex runs as an ordinary user with a read-only sandbox in a dedicated instruction
workspace. Shell/unified execution, apps/plugins and web search are disabled via
checked CLI settings. These are defense in depth, not a certified OS isolation
boundary. Both conversational entry points refuse root. Native instruction
discovery is actually tested before inference. No model output reaches the root
installation executor.

## Verification evidence and limits

A storage-only Gentoo UEFI VM run allocated/formatted new partitions, preserved the
entire synthetic NTFS partition byte-for-byte, rejected a mounted descendant, and
created independent Btrfs subvolumes. Later remote runs extracted authenticated
Stage3 and entered the chroot, exposing missing offline DNS and then missing
live-media dracut. The current harness installs the boot stack inside the target
and requires a fresh boot with ISO, Stage3 device, external kernel and external
initrd detached. It also requires an ordinary-user Butler offline/PATH check.
There is no installed-boot success until retained evidence actually passes.

CI run `42509458105` passed 98 unit/UI tests on Python 3.11, 3.12 and 3.13, shell
checks, portable bundle construction, native instruction discovery and staged
Butler checks at commit `00900f8`. Subsequent changes require their own CI result.
No successful Codex inference on the development host or installed guest is claimed.
The user reported successful live-CD conversation on their own PC.

Heavy installation VMs run on a sufficiently resourced external PC or CI, never
again on the Chromebook after its OOM. QEMU receives private firmware variables,
a newly created regular disk image, read-only authenticated media and optional
outbound user networking without forwarded ports. It receives no host block device
or shared directory. See [VM qualification](MINIMAL-VM.md) for the exact scope.
