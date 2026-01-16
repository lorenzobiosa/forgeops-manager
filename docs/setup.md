# Setup & Ambienti

Questa guida descrive il setup dell’ambiente di sviluppo su Windows/WSL, Linux e macOS.

## Requisiti

- Python 3.10+ con modulo `venv`
- `git`
- Accesso rete (eventuale proxy)

## Setup rapido (consigliato)

### Linux/macOS/WSL

```bash
./scripts/setup.sh --install-dev
```

### Windows PowerShell

```powershell
pwsh -File .\scripts\setup.ps1 -InstallDev
```

> I flag `--install-dev`/`-InstallDev` installano strumenti: **pre-commit, black, isort, flake8, mypy, bandit, detect-secrets** e inizializzano gli hook se presente `.pre-commit-config.yaml`.

## Proxy

```bash
./scripts/setup.sh --proxy "http://proxy:8080" --install-dev
# PowerShell:
pwsh -File .\scripts\setup.ps1 -Proxy "http://proxy:8080" -InstallDev
```

## WSL/Debian/Ubuntu

Gli script tentano un fallback apt-get se i binari non sono nel PATH:

- `python3-black`, `python3-isort`, `python3-flake8`, `mypy`, `bandit`

Se necessario:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-black python3-isort python3-flake8 mypy bandit
```

## Attivare la venv

```bash
source .venv/bin/activate        # Linux/macOS/WSL
# Windows:
.\.venv\Scripts\Activate.ps1
```

## Dipendenze

```bash
pip install -r requirements.txt
```

## Health check

Gli script eseguono un health check importando i moduli principali.

---
