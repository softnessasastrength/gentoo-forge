# Continue Gentoo Forge on the real Gentoo live CD

This is an engineering handoff, not an authorization to write to any disk.
Read root `AGENTS.md`, `forgeworth/AGENTS.md`, and this file before continuing.
Repository: softnessasastrength/gentoo-forge. Branch: feature/forgeworth-tui.
Do not merge main. Do not run Codex as root or grant it disk/sudo group membership.

## Latest user requirement — preserve NTFS

The user initially described a sacrificial disk, but subsequent read-only output
showed existing NTFS and the user explicitly chose **Preserve NTFS; inspect
unallocated space**. That later instruction controls. Do not erase, resize,
reformat, move or remove the existing partition. No erase authorization exists.

User-reported device: `/dev/sda`, 1.8 TiB, Seagate ST2000LM015-2E8174,
serial WY215406, RO=0. `/dev/sda1` is an unmounted 1.6 TiB NTFS partition.
Revalidate these facts on the actual live machine; paths can change after reboot.

User-supplied `sfdisk --json /dev/sda`:

```json
{
  "partitiontable": {
    "label": "gpt",
    "id": "3F186CC2-AE72-475F-AF4C-CC719D2617B4",
    "device": "/dev/sda",
    "unit": "sectors",
    "firstlba": 34,
    "lastlba": 3907029134,
    "sectorsize": 512,
    "partitions": [{
      "node": "/dev/sda1", "start": 2048, "size": 3395026944,
      "type": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
      "uuid": "8DE32841-0474-43CA-85E9-261DD4E8C2B9",
      "name": "Basic data partition"
    }]
  }
}
```

Derived proposal only: retain partition 1 exactly; allocate new partitions 2–4
in aligned trailing sectors 3395028992–3907028991. Approximately 244.14 GiB is
truly unallocated there. Proposed ESP 1 GiB, swap 20 GiB and Btrfs 223.140625 GiB.
This is not filesystem free space, and no NTFS shrink is needed for that proposal.
Do not execute these sector numbers from this document; regenerate a fresh plan.

## Working implementation and limits

- Textual/Rich asynchronous inspection UI and restricted optional Codex backend.
- Permanent `butler` executable, shared canonical personality, real local CLI
  instruction-discovery check, one-shot questions and explicit saved-thread resume.
- Portable live payload: Python 3.13.18, Codex 0.166.0, offline wheelhouse and
  checksums. Root-level build/setup/install launchers; no credentials bundled.
- Earlier complete suite: 59 tests passed. New storage/planning tests add checks
  for GPT free extents, preserved partition metadata, authorization, kernel identity,
  audit permissions, and Gentoo's overlay root ancestry. Rerun the full suite.
- `forge-install.sh doctor` reports Gentoo live prerequisites. `plan --disk PATH`
  performs fresh read-only inspection and proposes free-space-only allocations.
- `installer/partition_plan.py` refuses MBR conversion, overlaps and insufficient
  contiguous space. Its generated commands contain no zap/clear/delete/resize.
- `installer/storage.py` has an experimental private allocation/format executor,
  but the **public physical-write CLI is locked**. Do not flip that lock to make
  a demo work. The executor has not passed a destructive Gentoo VM test.
- Bootstrap/Stage3, chroot configuration, kernel, desktop and finalization remain
  locked/unimplemented. No complete Gentoo installation or successful live AI
  inference has been claimed. The user specifically wants a Gentoo live CD,
  not Debian; Debian is only the previous Crostini development host.

## Evidence from the prior development machine

QEMU/KVM works inside its Crostini. An official Gentoo minimal ISO was downloaded:
install-amd64-minimal-20261101T164556Z.iso. SHA256:
8a1ff6aec1355d055fad53d22d93b91138d09874e648811b5aa0e032536028d3.
Its signed checksum verified under Gentoo's automated release primary key
13EBBDBEDE7A12775DFDB1BABB572E0E2D182910, listed on Gentoo's official signatures page.

It booted in a private QEMU guest with only a regular 64 GiB qcow2 fixture disk,
a read-only ISO and no NIC. Guest read-only checks found Gentoo Base System 2.18,
Python 3.14.10 and sgdisk/mkfs.fat/mkfs.btrfs/mkfs.ntfs. Root is overlay over
read-only squashfs plus memory-backed upper/work directories. lsblk omitted the
fixture serial despite the kernel VPD page containing it; the new inspector reads
the actual VPD serial without synthesizing identity. Inspection succeeded.
No guest partitioning or formatting had run at handoff. The discarded Alpine
netboot investigation was not used for qualification. No host block device was
partitioned, formatted or mounted by development tests.

## Next safe vertical slice

1. Run all unit/UI tests. Review the new executor before execution: GPT backup
   and recovery, opened-device races, exclusive formatter access and per-partition
   extent revalidation still need qualification. Keep the physical CLI locked.
2. In a disposable QEMU VM booted from verified Gentoo media, create a synthetic
   NTFS partition with known sentinel content. Exercise allocating only trailing
   space, verify the old GPT entry and the entire small NTFS fixture remain
   unchanged, verify filesystem types/UUIDs, and test interruptions/recovery.
3. Add independent root/home subvolumes, signed Stage3 verification and safe
   extraction. Design resumability so a completed destructive stage is never
   silently repeated. Install permanent Butler into the target without auth copies.
4. Resolve the actual synced Gentoo Plasma/OpenRC profile and supported IUSE
   flags before configuration. The user explicitly raised USE flags. Do not dump
   guessed global flags into make.conf; validate per-package Wayland/XWayland,
   AMDGPU/RADV, PipeWire and required 32-bit Steam/Wine ABI choices using a
   readable Portage pretend plan before compilation. Source-first, initial -j6 -l6.
5. Implement/qualify kernel/dracut/GRUB, installed boot, desktop, hibernation and
   root/home rollback separately. Packages installed do not establish success.

## Start a coding session on the live PC

As an ordinary user, clone this branch into that user's writable home. Start
Codex there and ask it to read this handoff and both AGENTS files. Use Codex's
normal reviewed workspace permissions. Keep privilege-requiring installer actions
in a separately reviewed root terminal. `butler` remains a restricted conversation
interface; it is not the unrestricted development agent or an installation executor.

Installing/signing into Codex does not automatically import the previous machine's
chat. This handoff plus the version-controlled code provides continuation context.
Resume on the new machine applies to sessions actually saved in its selected
CODEX_HOME. Do not copy auth files or private chat databases into the repository.
