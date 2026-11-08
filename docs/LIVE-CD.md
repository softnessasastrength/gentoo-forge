# FORGEWORTH on a live CD

Build on a networked Linux x86_64 machine using Python 3.12+:

```bash
bash build-livecd.sh
```

The builder downloads pinned Python 3.13.18 and Codex CLI 0.166.0 Linux runtimes,
checks their SHA-256 digests, and downloads UI dependency wheels. Their hashes
are recorded in an offline pip lock. `dist/forgeworth-live` contains everything
needed for the UI; Node/npm, system Python and compiling Gentoo packages are not
required on the live CD. Build dependencies, if needed, belong in `setup-dev.sh`.
`--no-codex` makes an inspection-only bundle. Existing output is never overwritten.

Copy the **whole folder** to a USB filesystem or other trusted storage. This is
an application payload, not a bootable ISO and not an image to flash. No USB or
block device is selected, formatted or written by these tools. Boot your trusted
amd64 Gentoo live media separately. A USB mount with `noexec` needs the folder
copied to an executable live-session location such as `/opt/forgeworth-live`.
Keep the containing directory readable by the unprivileged live user.

If the live CD starts as root, create a dedicated locked account explicitly:

```bash
bash /opt/forgeworth-live/livecd.sh create-user
# Read the prompt and type LIVE SESSION. Then, as root:
su - forgeworth
```

This creates only user `forgeworth`, with volatile home `/run/forgeworth` and no
sudo/disk groups. It refuses to silently reuse an existing account/home. If the
live environment already has a suitable ordinary user, use that user instead.
Do not add this account to disk or sudo groups. No root user is created or used
for AI. No account creation is run automatically on the development computer.

As the ordinary user:

```bash
bash /opt/forgeworth-live/livecd.sh doctor
bash /opt/forgeworth-live/livecd.sh verify
bash /opt/forgeworth-live/livecd.sh setup
bash /opt/forgeworth-live/livecd.sh run
```

Setup installs only from the local wheelhouse into a private user venv. `run`
starts local inspection with AI disabled. The folder includes `app/AGENTS.md`
with the butler's personality/safety settings. Python's normal root CA trust,
Linux x86_64 kernel/glibc compatibility, bash, coreutils, lsblk and findmnt are
still supplied by the live environment. Doctor reports missing prerequisites;
it does not install system packages or enable writes. A physical live-CD boot
has not yet been qualified.

## Optional conversation

```bash
bash /opt/forgeworth-live/livecd.sh login
bash /opt/forgeworth-live/livecd.sh status
bash /opt/forgeworth-live/livecd.sh chat
# When finished:
bash /opt/forgeworth-live/livecd.sh logout
```

Login uses Codex's device authorization flow; complete it in a browser on another
device if necessary. The bundled native binary needs no npm. Service/network and
account access are required for AI. See [official Codex authentication](https://developers.openai.com/codex/auth/).
Codex uses a private `~/.local/state/forgeworth/codex` credential directory,
shared with the permanent Butler launcher under the same ordinary user.
No credentials are copied from your development account. With the `/run` home,
credentials and inspection state disappear on reboot. With a persistent home,
use logout before leaving shared media. Do not paste secrets into conversation.

This launches FORGEWORTH with a fresh conversation, not the current Codex app
thread. Its installed backend enforces optional unprivileged conversation and
restricted tools; AI suggestions never execute as privileged commands. Do not
expect it to install Gentoo yet: installation writes remain locked. The
experimental backend restrictions are not a certified security boundary.

SHA256SUMS detects accidental corruption against the built manifest; it is not
a signature authenticating an arbitrary third-party bundle. Build from your
reviewed checkout and retain the pinned asset metadata in BUILD.json. Never run
an untrusted launcher as root. The payload allowlist excludes `.git`, venvs,
Codex homes, credentials, chat history, reports and local target disk configuration.
