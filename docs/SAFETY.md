# Safety model

This foundation milestone is **read-only**. Preflight inspects hardware and the planner prints a proposal; all later stages fail closed.

Never run partitioning against an unverified disk. In future releases require an explicit target path, reject mounted disks and root/boot ancestry, verify disk identity, and require an interactive confirmation containing the disk identifier. Do not accept a generic `--yes` for destructive operations.

Back up data and use the official Gentoo Handbook. GitHub Actions shell validation does not prove installer safety or hardware compatibility.

The pure Python safety module now rejects missing serial/model/size, unknown mount
state, active ancestry/swap and changed identity. Authorization requires both a
`nuke_it` flag and an interactive exact `ERASE <path> <serial> <bytes>` confirmation.
No generic yes is accepted. This is unit-tested policy, not an enabled CLI flag or
complete live-device authorization flow. No write helper is present. Never treat
validation of a supplied JSON inventory as proof of actual current device state.

VirtualBox mode does not establish disposability or relax any gate. Target checks
use fresh read-only observations and the shared physical-disk validator, and remain
non-authorizing. Unknown root/swap ancestry or absent serials block validation.
Reports, VM snapshots and completed checklist attestations never authorize writes.
