#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"

INSTALL_AZ_CLI="true"
INSTALL_GH_CLI="true"

SUDO=""
if command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

usage() {
  cat <<'EOF'
Install local dependencies for this repo.

What it does:
- (Optional) Install Azure CLI (az) on Debian/Ubuntu via apt
- (Optional) Install GitHub CLI (gh) on Debian/Ubuntu via apt
- Create a Python venv and install Python dependencies (requirements.txt preferred)

Usage:
  ./scripts/install_deps.sh [options]

Options:
  --python-only        Only set up Python venv + pip deps
  --no-azure-cli       Skip installing Azure CLI (az)
  --no-github-cli      Skip installing GitHub CLI (gh)
  -h, --help           Show help

Notes:
- This script is optimized for Debian/Ubuntu (apt-get).
- On Windows, use: ./scripts/install_deps.ps1
EOF
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

require_apt_get_or_skip() {
  if have_cmd apt-get; then
    return 0
  fi
  echo "apt-get not found; skipping CLI installation." >&2
  echo "- Install Azure CLI:  https://learn.microsoft.com/cli/azure/install-azure-cli" >&2
  echo "- Install GitHub CLI: https://cli.github.com/" >&2
  return 1
}

install_azure_cli() {
  if [[ "$INSTALL_AZ_CLI" != "true" ]]; then
    return 0
  fi
  if command -v az >/dev/null 2>&1; then
    echo "Azure CLI already installed."
    return 0
  fi

  require_apt_get_or_skip || return 0

  echo "Installing Azure CLI..."
  $SUDO apt-get update -y
  $SUDO apt-get install -y ca-certificates curl apt-transport-https lsb-release gnupg

  curl -sL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | $SUDO tee /etc/apt/trusted.gpg.d/microsoft.gpg >/dev/null

  AZ_REPO="$(lsb_release -cs)"
  echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $AZ_REPO main" \
    | $SUDO tee /etc/apt/sources.list.d/azure-cli.list >/dev/null

  $SUDO apt-get update -y
  $SUDO apt-get install -y azure-cli
}

install_github_cli() {
  if [[ "$INSTALL_GH_CLI" != "true" ]]; then
    return 0
  fi
  if command -v gh >/dev/null 2>&1; then
    echo "GitHub CLI already installed."
    return 0
  fi

  require_apt_get_or_skip || return 0

  echo "Installing GitHub CLI (gh)..."
  $SUDO apt-get update -y
  $SUDO apt-get install -y curl gpg

  keyring_path="/usr/share/keyrings/githubcli-archive-keyring.gpg"
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | $SUDO dd of="$keyring_path" >/dev/null 2>&1
  $SUDO chmod go+r "$keyring_path"

  arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
  echo "deb [arch=${arch} signed-by=${keyring_path}] https://cli.github.com/packages stable main" \
    | $SUDO tee /etc/apt/sources.list.d/github-cli.list >/dev/null

  $SUDO apt-get update -y
  $SUDO apt-get install -y gh
}

setup_python_env() {
  echo "Setting up Python virtual environment..."
  if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  python -m pip install --upgrade pip

  echo "Installing Python dependencies..."
  if [ -f "$ROOT_DIR/requirements.txt" ]; then
    python -m pip install -r "$ROOT_DIR/requirements.txt"
  else
    python -m pip install \
      agent-framework \
      azure-identity \
      azure-ai-projects \
      azure-core \
      openai \
      httpx \
      python-dotenv \
      pyyaml
  fi
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      --python-only)
        INSTALL_AZ_CLI="false"
        INSTALL_GH_CLI="false"
        shift
        ;;
      --no-azure-cli)
        INSTALL_AZ_CLI="false"
        shift
        ;;
      --no-github-cli)
        INSTALL_GH_CLI="false"
        shift
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage
        exit 2
        ;;
    esac
  done

  install_azure_cli
  install_github_cli
  setup_python_env

  echo "Done. Virtual environment: $VENV_DIR"
  echo "Activate with: source $VENV_DIR/bin/activate"
}

main "$@"
