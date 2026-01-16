# -----------------------------------------------------------------------------
# ForgeOps Manager - Setup Script (PowerShell)
# Autore:        Lorenzo Biosa
# Email:         lorenzo@biosa-labs.com
# Copyright:
#   © 2025 Biosa Labs. Tutti i diritti riservati.
#   Questo script è distribuito come parte del progetto ForgeOps Manager.
#
# Scopo:
#   - Creare/aggiornare un ambiente virtuale Python (venv)
#   - Aggiornare pip all'interno della venv (gestione restrizioni tipo PEP 668)
#   - Installare le dipendenze del progetto (requirements.txt)
#   - Installare/inizializzare strumenti di qualità (pre-commit, black, isort, flake8, mypy, bandit, detect-secrets)
#   - Eseguire un health check di base/esteso
#
# Note:
#   - Usa 'python -m pip' per vincolare pip all'interprete della venv.
#   - Progettato per PowerShell su Windows (per Bash usare scripts/setup.sh in WSL).
#   - Non stampa segreti né variabili sensibili.
#
# Uso:
#   pwsh -File scripts\setup.ps1 [-PythonPath <path_python>] [-VenvPath <path_venv>]
#                                [-RecreateVenv] [-RequirementsPath <path_req>]
#                                [-InstallDev] [-Proxy <url>] [-Quiet] [-SkipHealthCheck]
#
# Esempi:
#   .\scripts\setup.ps1
#   .\scripts\setup.ps1 -RecreateVenv -InstallDev
#   .\scripts\setup.ps1 -PythonPath "C:\Python310\python.exe" -Proxy "http://proxy:8080"
#   .\scripts\setup.ps1 -RequirementsPath ".\requirements.txt" -Quiet
# -----------------------------------------------------------------------------

[CmdletBinding()]
Param(
    [Parameter(Mandatory = $false)]
    [string] $PythonPath = "python",

    [Parameter(Mandatory = $false)]
    [string] $VenvPath,

    [Parameter(Mandatory = $false)]
    [switch] $RecreateVenv,

    [Parameter(Mandatory = $false)]
    [string] $RequirementsPath,

    [Parameter(Mandatory = $false)]
    [switch] $InstallDev,

    [Parameter(Mandatory = $false)]
    [string] $Proxy,  # es. http://proxy:8080

    [Parameter(Mandatory = $false)]
    [switch] $Quiet,

    [Parameter(Mandatory = $false)]
    [switch] $SkipHealthCheck
)

# Comportamento errori: interrompe su eccezioni non gestite
$ErrorActionPreference = "Stop"

function Write-Info($msg) { if (-not $Quiet) { Write-Host "==> $msg" -ForegroundColor Cyan } }
function Write-Ok($msg) { if (-not $Quiet) { Write-Host "✓ $msg" -ForegroundColor Green } }
function Write-Warn($msg) { if (-not $Quiet) { Write-Warning $msg } }
function Write-Fail($msg) { Write-Error $msg }

# Risoluzione path repo/venv/requirements
try {
    $scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $repoRoot = (Join-Path $scriptsDir ".." | Resolve-Path).Path
}
catch {
    Write-Fail "Impossibile risolvere la radice del repository: $_"
    exit 2
}

if (-not $VenvPath -or [string]::IsNullOrWhiteSpace($VenvPath)) {
    $VenvPath = Join-Path $repoRoot ".venv"
}
if (-not $RequirementsPath -or [string]::IsNullOrWhiteSpace($RequirementsPath)) {
    $RequirementsPath = Join-Path $repoRoot "requirements.txt"
}

Write-Info "Radice repository: $repoRoot"
Write-Info "Percorso venv:     $VenvPath"
Write-Info "File requirements: $RequirementsPath"

# 1) Verifica disponibilità Python
$pythonCmd = Get-Command $PythonPath -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Fail "Python non trovato in PATH o al percorso specificato: '$PythonPath'. Installare Python 3.10+."
    exit 3
}

# 1.1) Verifica versione minima (>= 3.10)
try {
    $pyVersion = & $PythonPath -c "import sys;print('.'.join(map(str,sys.version_info[:3])))"
    Write-Info ("Python: {0}" -f $pyVersion)
    $major, $minor, $patch = $pyVersion.Split('.')
    if ([int]$major -lt 3 -or ([int]$major -eq 3 -and [int]$minor -lt 10)) {
        Write-Fail "Versione Python minima richiesta: 3.10. Rilevata: $pyVersion"
        exit 4
    }
}
catch {
    Write-Fail "Impossibile determinare la versione di Python: $_"
    exit 5
}

# 2) Creazione/ricreazione venv
try {
    if ($RecreateVenv -and (Test-Path $VenvPath)) {
        Write-Info "Ricreazione venv (rimozione directory esistente)…"
        Remove-Item -Recurse -Force $VenvPath
    }

    if (-not (Test-Path $VenvPath)) {
        Write-Info "Creazione virtual environment…"
        & $PythonPath -m venv $VenvPath
        Write-Ok "Venv creata."
    }
    else {
        Write-Info "Venv esistente rilevata: skip creazione."
    }
}
catch {
    Write-Fail "Errore creando la venv: $_"
    exit 6
}

# 3) Attivazione venv (solo per la sessione corrente)
$activatePath = Join-Path $VenvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activatePath)) {
    Write-Fail "Script di attivazione non trovato: $activatePath"
    exit 7
}

try {
    . $activatePath
    $activePython = (Get-Command python).Source
    Write-Info ("Venv attivata. Interprete: {0}" -f $activePython)
}
catch {
    Write-Fail "Errore attivando la venv: $_"
    exit 8
}

# 4) Configura ambiente pip (evita installazione user)
$env:PIP_USER = "0"

# 4.1) Imposta proxy se fornito
if ($Proxy -and -not [string]::IsNullOrWhiteSpace($Proxy)) {
    Write-Info "Proxy impostato: $Proxy"
    $env:HTTP_PROXY = $Proxy
    $env:HTTPS_PROXY = $Proxy
}

# 5) Aggiorna pip
try {
    Write-Info "Aggiornamento pip nella venv…"
    python -m pip install --upgrade pip --no-warn-script-location --disable-pip-version-check --no-input
    Write-Ok "pip aggiornato."
}
catch {
    Write-Fail "Errore aggiornando pip: $_"
    exit 9
}

# 6) Installazione dipendenze
if (-not (Test-Path $RequirementsPath)) {
    Write-Fail "requirements.txt non trovato: $RequirementsPath"
    exit 10
}

try {
    Write-Info "Installazione dipendenze da requirements.txt…"
    $pipArgs = @(
        "-m", "pip", "install",
        "--no-user",
        "--no-warn-script-location",
        "--disable-pip-version-check",
        "--no-input",
        "-r", $RequirementsPath
    )
    python $pipArgs
    Write-Ok "Dipendenze installate."
}
catch {
    Write-Fail "Errore installando dipendenze: $_"
    exit 11
}

# 6.1) Installazione strumenti dev opzionali (pre-commit, flake8, black, isort, mypy, bandit, detect-secrets)
if ($InstallDev) {
    try {
        Write-Info "Installazione strumenti di sviluppo (pre-commit, flake8, black, isort, mypy, bandit, detect-secrets)…"
        python -m pip install --no-user pre-commit flake8 black isort mypy bandit detect-secrets
        Write-Ok "Strumenti dev installati."
        # Inizializza pre-commit se presente la configurazione
        $precommitCfg = Join-Path $repoRoot ".pre-commit-config.yaml"
        if (Test-Path $precommitCfg) {
            Write-Info "Inizializzazione pre-commit hooks…"
            pre-commit install
            Write-Ok "pre-commit hooks attivati."
        }

        # Verifica disponibilità comandi principali nel PATH corrente (venv/bin)
        $missing = @()
        foreach ($tool in @("black", "isort", "flake8", "mypy", "bandit")) {
            if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
                Write-Warn "Comando '$tool' non trovato nel PATH corrente."
                $missing += $tool
            }
        }

        if ($missing.Count -gt 0) {
            # Guida per installazione di sistema su Windows (non WSL)
            Write-Warn @"
I seguenti comandi non risultano nel PATH: $($missing -join ", ").
Su Windows (non WSL) puoi installarli a livello sistema se necessario:

 - Con winget (se disponibile e pacchetti presenti):
     winget install Black
     winget install isort
     winget install Flake8
     winget install Bandit
     winget install mypy

 - Con Chocolatey (se disponibile):
     choco install black
     choco install isort
     choco install flake8
     choco install bandit
     choco install mypy

In alternativa, assicurati di avere la venv attiva quando li esegui:
  .\.venv\Scripts\Activate.ps1

Se stai usando WSL/Debian/Ubuntu usa lo script ./scripts/setup.sh
(che tenta l'installazione tramite apt-get: python3-black, python3-isort, python3-flake8, mypy, bandit).
"@
        }
    }
    catch {
        Write-Warn "Installazione strumenti dev fallita: $_ (continua comunque)"
    }
}

# 7) Health check (opzionale disattivazione con -SkipHealthCheck)
if (-not $SkipHealthCheck) {
    Write-Info "Esecuzione health check…"
    $py = @"
import sys
print("Python:", sys.version)
ok = True
def check_import(mod):
    global ok
    try:
        __import__(mod)
        print(f"[OK] import '{mod}'")
    except Exception as e:
        print(f"[ERRORE] import '{mod}': {e}")
        ok = False

# Dependency essenziale
check_import("requests")
# Logging e utilità
check_import("src.utils.logging")
check_import("src.utils.http")
check_import("src.utils.config")
# Provider GitHub
check_import("src.providers.github.cache")
check_import("src.providers.github.releases")
check_import("src.providers.github.packages")
check_import("src.providers.github.security")
check_import("src.providers.github.api")

sys.exit(0 if ok else 1)
"@

    try {
        # In PowerShell NON esiste '<<' (Bash). Usare pipe verso stdin del processo Python.
        $py | python -
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Health check fallito (vedi dettagli sopra)."
            exit 12
        }
        else {
            Write-Ok "Health check superato."
        }
    }
    catch {
        Write-Fail "Errore eseguendo health check: $_"
        exit 13
    }
}
else {
    Write-Warn "Health check saltato su richiesta."
}

Write-Ok "Setup completato con successo."
if (-not $Quiet) {
    Write-Host "Per avviare la CLI interattiva:" -ForegroundColor Yellow
    Write-Host "  .\\.venv\\Scripts\\Activate.ps1"
    Write-Host "  python -m src.main"
}
exit 0
