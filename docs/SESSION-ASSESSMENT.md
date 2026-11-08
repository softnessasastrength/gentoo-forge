# Assessment and delivery: 2026-11-08

The existing feature branch at `89b1e91` and draft PR #3 already contained a
Textual interface, restricted optional Codex backend, supervised asynchronous
read-only inspections, telemetry, personality settings and VirtualBox guidance.
Bootstrap, chroot, kernel, desktop and finalization scripts deliberately exit
without installing anything. The existing checkpoint is an inspection record,
not a resumable Gentoo installation protocol. Those boundaries remain intact.

No checkout was supplied locally and shell DNS could not reach GitHub. Source
files were retrieved from the exact feature commit through the connected GitHub
API; the remote delivery commit uses that actual commit as its parent, preserving
repository history. The initial local snapshot commit is only a validation aid.

## Implemented increment

- Resolve root and swap evidence against the inventory before target validation;
  reject malformed identity and mount data. Test Btrfs root suffixes, mapper
  descendants and unresolved aliases. No VM exemption or erase execution exists.
- Prevent predictable checkpoint temporary-file symlink writes.
- Feed subprocess input concurrently with output collection to avoid pipe
  deadlock; decode streamed UTF-8 incrementally and handle early stdin closure.
- Ignore malformed Codex JSON structures and reject explicit failure events even
  when the CLI exits zero. Error payloads do not enter conversation history.
- Observe explicit external emerge-log package records through a bounded,
  regular-file-only reader. Display counts independently from installation state;
  do not infer elapsed-time completion, ETA or already completed packages.
- Identify Ryzen hwmon CPU sensors without mislabelling GPU temperature.
- Expand GitHub Actions to Python 3.11, 3.12 and 3.13 with read-only token access.

## Validation evidence

Baseline: 26 non-UI tests passed. The two UI test modules failed import because
Textual was absent. Installing the pinned dependency was attempted using the
available bundled Python/pip and failed because pypi.org DNS was unavailable.
No UI test was skipped or reported as passing in this environment.

After changes: 38 non-UI tests pass, including 12 new regression tests. Python
compilation and shell syntax/destructive-command checks pass. ShellCheck is not
installed locally; CI installs it. Full discovery still has the same two UI
module import errors. The added compilation panel has not been rendered or
visually qualified in this session; existing screenshots predate this increment.

Installed CLI: `codex-cli 0.166.0`; inspected exec/login help and feature listing.
The required isolation options are advertised. Successful live inference was
not tested in this increment; the existing documentation records an earlier
environment's expired-session failure. CLI help is not proof of OS isolation.

## Remaining qualification gates

Current Gentoo compatibility remains pending: web retrieval of the Handbook,
Snapper and hibernation documentation was blocked by robots policy. No package
selection, USE-flag or boot guarantee has been inferred from unavailable pages.

A real installer still needs a narrowly scoped privileged helper, complete fresh
disk/mount/swap ancestry collection, durable authorization audit, verified Stage3
retrieval, deterministic target configuration and recovery-aware stage executors.
Root/home snapshot retention, GRUB boot rollback, OpenRC scheduling, graphics,
32-bit gaming dependencies and hibernate/resume need actual installed-system
acceptance tests. No isolated hypervisor/disk environment was established here;
no destructive test or host disk write was attempted. Keep the PR draft and do
not merge until the relevant qualification gates are met.
