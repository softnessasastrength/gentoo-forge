# Safety model

This foundation milestone is **read-only**. Preflight inspects hardware and the planner prints a proposal; all later stages fail closed.

Never run partitioning against an unverified disk. In future releases require an explicit target path, reject mounted disks and root/boot ancestry, verify disk identity, and require an interactive confirmation containing the disk identifier. Do not accept a generic `--yes` for destructive operations.

Back up data and use the official Gentoo Handbook. GitHub Actions shell validation does not prove installer safety or hardware compatibility.
