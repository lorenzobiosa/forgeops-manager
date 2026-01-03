#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# ForgeOps Manager - Setup Script (Bash)
# Purpose:
#   - Create/refresh a Python virtual environment
#   - Upgrade pip inside the venv (handling PEP 668 on Debian/Ubuntu)
#   - Install project dependencies into the venv (NO user installs)
#   - Perform a basic health check
#
# Notes:
#   - Safe to run multiple times (idempotent for venv/deps).
#   - Uses `python -m pip` for interpreter-bound pip execution to avoid path issues.
# -----------------------------------------------------------------------------

# Resolve repo root relative to this script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

echo "==> Repository root: ${REPO_ROOT}"
echo "==> Virtual environment: ${VENV_DIR}"

# -----------------------------------------------------------------------------
# 1) Ensure Python 3 is available
# -----------------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found in PATH."
    echo "       Please install Python 3.10+ (e.g., 'sudo apt install python3 python3-venv')."
    exit 1
fi

# -----------------------------------------------------------------------------
# 2) Create venv if missing
# -----------------------------------------------------------------------------
if [ ! -d "${VENV_DIR}" ]; then
    echo "==> Creating virtual environment…"
    python3 -m venv "${VENV_DIR}"
fi

# -----------------------------------------------------------------------------
# 3) Activate venv
# -----------------------------------------------------------------------------
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
echo "==> Activated venv: $(which python)"

# -----------------------------------------------------------------------------
# 4) Upgrade pip (handle PEP 668 with --break-system-packages if needed)
# -----------------------------------------------------------------------------
# Explicitly disable user installs to force venv site-packages usage.
export PIP_USER=0
echo "==> Upgrading pip in venv…"
python -m pip install --upgrade pip --break-system-packages

# -----------------------------------------------------------------------------
# 5) Install dependencies into venv
# -----------------------------------------------------------------------------
REQ_FILE="${REPO_ROOT}/requirements.txt"
if [ ! -f "${REQ_FILE}" ]; then
    echo "ERROR: requirements.txt not found at repo root: ${REQ_FILE}"
    exit 1
fi

echo "==> Installing dependencies from requirements.txt (no user site-packages)…"
python -m pip install --no-user -r "${REQ_FILE}" --break-system-packages

# -----------------------------------------------------------------------------
# 6) Health check: import core dependency
# -----------------------------------------------------------------------------
echo "==> Performing health check…"
python - <<'PYCODE'
import sys
print("Python:", sys.version)
try:
    import requests
    print("requests imported OK:", requests.__version__)
except Exception as e:
    print("ERROR: Failed to import 'requests':", e)
    sys.exit(1)
PYCODE

# -----------------------------------------------------------------------------
# 7) Success message and next steps
# -----------------------------------------------------------------------------
echo "==> Setup completed successfully."
echo "   To run the interactive CLI:"
echo "     source .venv/bin/activate"
echo "     python -m src.main"
