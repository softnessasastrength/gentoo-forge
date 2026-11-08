#!/usr/bin/env bash
# Portable unprivileged FORGEWORTH launcher. No disk-writing commands.
set -Eeuo pipefail
umask 077
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-run}"
[[ $# -le 1 ]] || { echo 'Use livecd.sh --help for supported commands.' >&2; exit 2; }
case "$ACTION" in
  --help|help)
    echo 'Usage: bash livecd.sh [doctor|verify|setup|run|chat|login|status|logout|create-user]'
    echo 'run: local inspection; chat: explicit AI opt-in; login: fresh device authentication.'
    echo 'All runtime commands require an ordinary user. create-user is a separate root action.'
    exit 0 ;;
  doctor|verify|setup|run|chat|login|status|logout|create-user) ;;
  *) echo 'Unsupported action; use --help.' >&2; exit 2 ;;
esac
if [[ "$ACTION" == create-user ]]; then
  [[ $EUID -eq 0 ]] || { echo 'Only live-session root can create the dedicated account.' >&2; exit 1; }
  if id forgeworth >/dev/null 2>&1 || [[ -e /run/forgeworth ]]; then
    echo 'Account or home already exists; inspect it manually rather than reusing it automatically.' >&2; exit 1
  fi
  read -r -p 'Create locked, unprivileged user forgeworth with volatile home /run/forgeworth? Type LIVE SESSION: ' CONFIRM
  [[ "$CONFIRM" == 'LIVE SESSION' ]] || { echo 'Cancelled.'; exit 1; }
  useradd --create-home --home-dir /run/forgeworth --shell /bin/bash --user-group forgeworth
  echo 'Account created without sudo/disk groups. As root: su - forgeworth'
  echo "Then: bash '$ROOT_DIR/livecd.sh' setup"
  exit 0
fi
if [[ "$ACTION" == doctor ]]; then
  printf 'Architecture: %s\nUID: %s\n' "$(uname -m)" "$EUID"
  [[ $EUID -ne 0 ]] || echo 'Root session: runtime disabled; use create-user, then su - forgeworth.'
  for item in python/bin/python3 bin/codex wheelhouse SHA256SUMS app/AGENTS.md; do
    if [[ -e "$ROOT_DIR/$item" ]]; then echo "Present: $item"; else echo "Missing: $item"; fi
  done
  for tool in bash sha256sum lsblk findmnt; do
    command -v "$tool" >/dev/null || { echo "Missing system tool: $tool" >&2; exit 1; }
  done
  [[ "$(uname -m)" == x86_64 ]] || { echo 'This bundle supports Linux x86_64 only.' >&2; exit 1; }
  [[ -f "$ROOT_DIR/SHA256SUMS" && -x "$ROOT_DIR/python/bin/python3" ]] || exit 1
  exit 0
fi
verify_bundle() {
  [[ -f "$ROOT_DIR/SHA256SUMS" ]] || { echo 'Not a built bundle. Run bash build-livecd.sh first.' >&2; exit 1; }
  (cd "$ROOT_DIR" && sha256sum --check --quiet SHA256SUMS)
}
verify_bundle
if [[ "$ACTION" == verify ]]; then echo 'Bundle checksums passed.'; exit 0; fi
[[ $EUID -ne 0 ]] || { echo 'Runtime refuses root. Use create-user, then su - forgeworth.' >&2; exit 1; }
[[ "$(uname -m)" == x86_64 ]] || { echo 'Requires Linux x86_64.' >&2; exit 1; }
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME PYTHONPATH
export PATH="$ROOT_DIR/bin:/usr/local/bin:/usr/bin:/bin"
STATE_DIR="$HOME/.local/share/forgeworth-live"
mkdir -p "$STATE_DIR"
BUNDLE_ID="$(sha256sum "$ROOT_DIR/SHA256SUMS")"
BUNDLE_ID="${BUNDLE_ID%% *}"
VENV_DIR="$STATE_DIR/venv-$BUNDLE_ID"
export CODEX_HOME="$HOME/.local/state/forgeworth/codex"
export XDG_STATE_HOME="$HOME/.local/state/forgeworth-live"
mkdir -p "$CODEX_HOME"
chmod 700 "$CODEX_HOME"
if [[ "$ACTION" == login || "$ACTION" == status || "$ACTION" == logout ]]; then
  [[ -x "$ROOT_DIR/bin/codex" ]] || { echo 'Codex was not bundled.' >&2; exit 1; }
  case "$ACTION" in
    login) exec "$ROOT_DIR/bin/codex" login --device-auth ;;
    status) exec "$ROOT_DIR/bin/codex" login status ;;
    logout) exec "$ROOT_DIR/bin/codex" logout ;;
  esac
fi
if [[ ! -f "$VENV_DIR/.ready" ]]; then
  LOCK_DIR="$STATE_DIR/setup.lock"
  mkdir "$LOCK_DIR" || { echo 'Setup already active or interrupted. Inspect setup.lock before retrying.' >&2; exit 1; }
  trap 'rmdir "$LOCK_DIR"' EXIT
  "$ROOT_DIR/python/bin/python3" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --no-index --require-hashes \
    --find-links "$ROOT_DIR/wheelhouse" -r "$ROOT_DIR/requirements-live.lock"
  "$VENV_DIR/bin/python" -c 'import textual, rich'
  touch "$VENV_DIR/.ready"
  rmdir "$LOCK_DIR"
  trap - EXIT
fi
if [[ "$ACTION" == setup ]]; then echo 'Offline UI setup complete. Use run, or login then chat.'; exit 0; fi
cd "$ROOT_DIR/app"
if [[ "$ACTION" == chat ]]; then
  [[ -x "$ROOT_DIR/bin/codex" ]] || { echo 'Codex was not bundled.' >&2; exit 1; }
  export FORGEWORTH_CODEX=1
else
  export FORGEWORTH_CODEX=0
fi
exec "$VENV_DIR/bin/python" -m tui.app
