
# -----------------------------------------------------------------------------
# ForgeOps Manager - Setup Script (PowerShell)
# Purpose:
#   - Create/refresh a Python virtual environment
#   - Upgrade pip inside the venv (handle PEP 668-like restrictions)
#   - Install project dependencies into the venv
#   - Perform a basic health check
#
# Notes:
#   - Uses 'python -m pip' to bind pip to the venv interpreter.
#   - Designed for PowerShell on Windows (WSL is recommended for Bash script).
# -----------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

# Resolve repo root relative to this script location
$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Join-Path $scriptsDir ".." | Resolve-Path
$venvDir = Join-Path $repoRoot ".venv"

Write-Host "==> Repository root: $repoRoot"
Write-Host "==> Virtual environment: $venvDir"

# 1) Ensure Python is available
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found in PATH. Install Python 3.10+."
}

# 2) Create venv if missing
if (-not (Test-Path $venvDir)) {
    Write-Host "==> Creating virtual environment…"
    python -m venv $venvDir
}

# 3) Activate venv for this session
$activatePath = Join-Path $venvDir "Scripts\Activate.ps1"
if (-not (Test-Path $activatePath)) {
    Write-Error "Activation script not found: $activatePath"
}
# Activate (scoped to the current process)
. $activatePath
Write-Host "==> Activated venv. Python: " (Get-Command python).Source

# 4) Upgrade pip (explicitly avoid user installs)
# PowerShell equivalent to PIP_USER=0 for this process
$env:PIP_USER = "0"
Write-Host "==> Upgrading pip in venv…"
python -m pip install --upgrade pip --break-system-packages

# 5) Install dependencies
$requirements = Join-Path $repoRoot "requirements.txt"
if (-not (Test-Path $requirements)) {
    Write-Error "requirements.txt not found at repo root."
}
Write-Host "==> Installing dependencies from requirements.txt…"
python -m pip install --no-user -r $requirements --break-system-packages

# 6) Health check: import core dependency
Write-Host "==> Performing health check…"
$py = @"
import sys
print("Python:", sys.version)
try:
    import requests
    print("requests imported OK:", requests.__version__)
except Exception as e:
    print("ERROR: Failed to import 'requests':", e)
    sys.exit(1)
"@
python - <<$py

Write-Host "==> Setup completed successfully."
Write-Host "   To run the interactive CLI:"
Write-Host "     .\\.venv\\Scripts\\Activate.ps1"
Write-Host "     python -m src.main"
