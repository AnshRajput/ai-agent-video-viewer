#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/AnshRajput/ai-agent-video-viewer"
INSTALL_DIR="${AI_AGENT_VIDEO_VIEWER_DIR:-$HOME/.local/share/ai-agent-video-viewer/source}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "python3 is required before installing ai-agent-video-viewer." >&2
  exit 1
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/scripts/install.py" ]; then
  exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/install.py" "$@"
fi

# Supports: curl -fsSL https://.../install.sh | bash -s -- [args]
# Prefer cloning and reading the script first for maximum supply-chain safety.
if ! command -v git >/dev/null 2>&1; then
  echo "git is required for remote bootstrap install. Install git first or download the release archive manually." >&2
  exit 1
fi

if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone "$REPO_URL.git" "$INSTALL_DIR"
fi

exec "$PYTHON_BIN" "$INSTALL_DIR/scripts/install.py" "$@"
