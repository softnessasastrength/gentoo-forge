# Safety model

This foundation milestone is **read-only**. Preflight inspects hardware and the planner prints a proposal; all later stages fail closed.

Never run partitioning against an unverified disk. In future releases require an explicit target path, reject mounted disks and root/boot ancestry, verify disk identity, and require an interactive confirmation containing the disk identifier. Do not accept a generic `--yes` for destructive operations.

Back up data and use the official Gentoo Handbook. GitHub Actions shell validation does not prove installer safety or hardware compatibility.

## Future --nuke-it authorization (not implemented)

The --nuke-it flag requests the guarded destructive workflow but is never itself consent to erase. The current installer must refuse destructive execution.

1. Discover physical disk model, full serial, size, stable identity, partition table, and storage dependency graph.
2. Fail closed for the live medium, running system disks, mounted filesystems, active swap, unresolved RAID/LVM/mapper relationships, ambiguous identities, or missing/duplicate/unreliable serial numbers. No force/yes/theme override exists.
3. Validate source artifacts, minimum capacity, complete proposed GPT layout, and exact target before showing a conspicuous irreversible-erase warning.
4. Require exact entry of the freshly detected full SSD serial number. No prefilled confirmation or noninteractive authorization.
5. Immediately before the first write, re-identify the disk and revalidate protections and the immutable reviewed plan; any discrepancy cancels authorization.
6. Never replay destructive phases automatically on resume. An interrupted destructive step requires new inspection and explicit device-specific confirmation.

This is a design contract only. No disk writes are enabled or authorized. Test all refusal cases in disposable virtual machines before implementing the destructive engine.
