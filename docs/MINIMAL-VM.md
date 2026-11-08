# Gentoo qualification on a PC or CI runner

Do not retry the install VM on the Chromebook: the 768 MiB attempt was terminated
during Stage3 extraction after host memory pressure. It did not produce an
installed-boot result. `tools/gentoo_vm.py` now requires at least 1536 MiB guest
memory and checks available host RAM against guest RAM plus a 1 GiB reserve.
Default guest memory is 2 GiB. QEMU file growth is limited to 8 GiB per file so a
sparse 64 GiB fixture cannot consume all host storage. Allow at least 12 GiB free
space for media, the growing fixture, and temporary files.

## Run on another Linux x86_64 PC

Install dependencies using the reviewed root-level `setup-dev.sh` on Debian or
equivalent QEMU/OVMF/gpgv/Python packages on other distributions. No host package
installation happens automatically in the test driver. Run as an ordinary user:

```bash
.venv/bin/python -m tools.fetch_gentoo_fixture --output /chosen/cache/gentoo-iso
.venv/bin/python -m installer.media --output /chosen/cache/gentoo-stage3
bash test-gentoo-vm.sh \
  --iso /chosen/cache/gentoo-iso/install-amd64-minimal-20261101T164556Z.iso \
  --stage3 /chosen/cache/gentoo-stage3 \
  --report /chosen/reports/unique-run \
  --accel kvm --memory-mib 2048 --network
```

Choose new output directories; downloads and reports do not overwrite existing
data. Use explicit `--accel tcg` when KVM is unavailable. It is substantially
slower. The GitHub workflow `Gentoo live-media qualification` runs this job on
an external runner with 4 GiB guest RAM and retains serial/QEMU logs and structured results, including
logs on failure. CI uses `--accel auto`: it queries the accessible KVM API and
uses KVM only when available, otherwise TCG. It never changes `/dev/kvm` permissions.
The selected accelerator and memory are recorded in the result. Guest stage
messages stream to the CI log; they are activity reports, not completion percentages.
No VM is part of normal unit-test discovery.

## What the test actually does

The official ISO is pinned by SHA256 and its signed checksum is authenticated
against Gentoo release primary fingerprints. The OpenRC multilib Stage3 index
and checksum are independently signature-verified, then the exact byte count
and archive hash are verified. Cached signed metadata is reverified before use;
`VERIFIED.json` alone is never trusted.

QEMU gets private firmware variables and a newly created regular qcow2 image.
Only a read-only ISO and, for bootstrap, a read-only Stage3 data device are
attached. No host block device or shared directory is attached. Storage-only runs
have no NIC. Stage3 runs require explicit `--network`, enabling outbound QEMU
user networking without forwarded ports for authenticated package downloads. The guest
script additionally requires the explicit kernel fixture marker, UEFI, Gentoo,
the exact QEMU fixture serial/model and exactly 64 GiB capacity before writes.

It creates a synthetic 512 MiB NTFS partition, hashes all of it, allocates only
trailing free space, verifies GPT entries and FAT/swap/Btrfs UUIDs, rejects a
mounted descendant, and creates independent root/home snapshot subvolumes. The
entire NTFS partition must remain byte-identical.

With `--stage3`, it validates/extracts the authenticated archive with numeric
ownership and xattrs, mounts target/pseudo-filesystems with explicit cleanup,
activates only the verified installation swap and deactivates it during cleanup,
configures basic OpenRC settings, generates a normal Btrfs/resume dracut image,
and installs GRUB into the private ESP without firmware-variable writes. It then
shuts down and starts a new QEMU process with **no ISO, Stage3 device, direct
kernel or external initrd**. An installed OpenRC service reports the observed
root UUID/filesystem, separate home subvolume, PID 1, UEFI and absence of the ISO.
The host verifies those observations before recording a successful reboot.

## Scope and deviations

The minimal fixture installs `gentoo-kernel-bin`, installkernel, dracut, GRUB,
Btrfs and FAT utilities inside the target after `emerge-webrsync`. The boot-stack
dependency closure is an explicit VM binary exception; signatures are mandatory
and USE mismatches may fall back to source. Production source-first configuration
is still pending. No live-media kernel or host dracut is used for installed boot.

This does not yet prove installed network connectivity, Plasma, audio/graphics,
gaming, hibernation or rollback. Accounts are locked; no test password or automatic
login is installed. The fixture now stages the permanent Butler executable and
requires an ordinary-user `butler --offline` check after boot. That proves launcher
persistence/PATH only; native Codex discovery and live inference after reboot
still require separate verification. No credentials are copied to the fixture.

The earlier storage-only run passed. The Chromebook Stage3 run was interrupted.
Remote run 42506097798 completed extraction but lacked offline DNS; run
42506708482 passed chroot configuration then exposed missing live-media dracut.
The updated networked target-package path addresses that architectural problem
but requires a new remote test. There is no successful installed boot until a
retained current CI/PC result proves it. Physical installation remains gated.
