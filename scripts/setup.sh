#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# ForgeOps Manager - Setup Script (Bash)
# Autore:        Lorenzo Biosa
# Email:         lorenzo@biosa-labs.com
# Copyright:
#   © 2025 Biosa Labs. Tutti i diritti riservati.
#   Questo script è distribuito come parte del progetto ForgeOps Manager.
#
# Scopo:
#   - Creare/aggiornare un ambiente virtuale Python (venv)
#   - Aggiornare pip all'interno della venv (gestione PEP 668)
#   - Installare le dipendenze del progetto (requirements.txt) senza user site-packages
#   - Eseguire un health check di base/esteso
#
# Note:
#   - Idempotente: può essere eseguito più volte in sicurezza.
#   - Usa `python -m pip` per legare pip all'interprete della venv.
#   - Non stampa segreti né variabili sensibili.
#
# Uso:
#   ./scripts/setup.sh [--python <path_python>] [--venv <path_venv>] [--recreate]
#                      [--requirements <path_req>] [--install-dev]
#                      [--proxy <url>] [--quiet] [--skip-health-check]
#
# Esempi:
#   ./scripts/setup.sh
#   ./scripts/setup.sh --recreate --install-dev
#   ./scripts/setup.sh --python "/usr/bin/python3" --proxy "http://proxy:8080"
#   ./scripts/setup.sh --requirements "./requirements.txt" --quiet
# -----------------------------------------------------------------------------

# ------------------------------ Parametri ------------------------------------
PYTHON_BIN="python3"
VENV_DIR_DEFAULT=""
RECREATE=false
REQUIREMENTS_PATH=""
INSTALL_DEV=false
PROXY_URL=""
QUIET=false
SKIP_HEALTH_CHECK=false

print_info() { if ! $QUIET; then echo -e "==> $*"; fi; }
print_ok() { if ! $QUIET; then echo -e "✓ $*"; fi; }
print_warn() { if ! $QUIET; then echo -e "WARN: $*" >&2; fi; }
print_fail() { echo -e "ERROR: $*" >&2; }

usage() {
  cat <<'USAGE'
Uso:
  ./scripts/setup.sh [opzioni]

Opzioni:
  --python <path>        Percorso dell'interprete Python (default: python3)
  --venv <path>          Percorso della virtualenv (default: <repo>/.venv)
  --recreate             Ricrea la venv rimuovendo quella esistente
  --requirements <path>  Percorso del requirements.txt (default: <repo>/requirements.txt)
  --install-dev          Installa strumenti dev (pre-commit, flake8, black, isort, mypy, bandit, detect-secrets)
  --proxy <url>          Imposta HTTP_PROXY/HTTPS_PROXY (es. http://proxy:8080)
  --quiet                Riduce l'output ai soli errori
  --skip-health-check    Salta l'health check finale

Esempi:
  ./scripts/setup.sh --recreate --install-dev
  ./scripts/setup.sh --python "/usr/bin/python3" --proxy "http://proxy:8080"
USAGE
}

# Parse argomenti
while [[ $# -gt 0 ]]; do
  case "$1" in
  --python)
    PYTHON_BIN="${2:-}"
    shift 2
    ;;
  --venv)
    VENV_DIR_DEFAULT="${2:-}"
    shift 2
    ;;
  --recreate)
    RECREATE=true
    shift 1
    ;;
  --requirements)
    REQUIREMENTS_PATH="${2:-}"
    shift 2
    ;;
  --install-dev)
    INSTALL_DEV=true
    shift 1
    ;;
  --proxy)
    PROXY_URL="${2:-}"
    shift 2
    ;;
  --quiet)
    QUIET=true
    shift 1
    ;;
  --skip-health-check)
    SKIP_HEALTH_CHECK=true
    shift 1
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    print_fail "Argomento sconosciuto: $1"
    usage
    exit 2
    ;;
  esac
done

# --------------------------- Risoluzione percorsi -----------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${VENV_DIR_DEFAULT:-"${REPO_ROOT}/.venv"}"
REQ_FILE="${REQUIREMENTS_PATH:-"${REPO_ROOT}/requirements.txt"}"

print_info "Radice repository: ${REPO_ROOT}"
print_info "Percorso venv:     ${VENV_DIR}"
print_info "File requirements: ${REQ_FILE}"

# --------------------------- 1) Verifica Python -------------------------------
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  print_fail "Interprete Python non trovato: '${PYTHON_BIN}'. Installare Python 3.10+ (es.: 'sudo apt install python3 python3-venv')."
  exit 3
fi

# Versione minima 3.10
PY_VER="$("${PYTHON_BIN}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
print_info "Python: ${PY_VER}"
PY_MAJ="$(echo "${PY_VER}" | cut -d. -f1)"
PY_MIN="$(echo "${PY_VER}" | cut -d. -f2)"
if [[ "${PY_MAJ}" -lt 3 || ("${PY_MAJ}" -eq 3 && "${PY_MIN}" -lt 10) ]]; then
  print_fail "Versione Python minima richiesta: 3.10. Rilevata: ${PY_VER}"
  exit 4
fi

# --------------------------- 2) Creazione/Ricreazione venv --------------------
if $RECREATE && [[ -d "${VENV_DIR}" ]]; then
  print_info "Ricreazione venv (rimozione directory esistente)…"
  rm -rf "${VENV_DIR}"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  print_info "Creazione virtual environment…"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  print_ok "Venv creata."
else
  print_info "Venv esistente rilevata: skip creazione."
fi

# --------------------------- 3) Attivazione venv ------------------------------
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
print_info "Venv attivata. Interprete: $(command -v python)"

# --------------------------- 4) Config pip e proxy ----------------------------
# Disabilita installazioni user (preferisci site-packages della venv)
export PIP_USER=0

# Imposta proxy se fornito
if [[ -n "${PROXY_URL}" ]]; then
  print_info "Proxy impostato: ${PROXY_URL}"
  export HTTP_PROXY="${PROXY_URL}"
  export HTTPS_PROXY="${PROXY_URL}"
fi

# --------------------------- 5) Aggiorna pip ----------------------------------
print_info "Aggiornamento pip nella venv…"
python -m pip install --upgrade pip --disable-pip-version-check --no-input
print_ok "pip aggiornato."

# --------------------------- 6) Install dipendenze ----------------------------
if [[ ! -f "${REQ_FILE}" ]]; then
  print_fail "requirements.txt non trovato: ${REQ_FILE}"
  exit 10
fi

print_info "Installazione dipendenze da requirements.txt… (no user site-packages)"
python -m pip install --no-user -r "${REQ_FILE}" --disable-pip-version-check --no-input
print_ok "Dipendenze installate."

# --------------------------- 6.1) Dev tools opzionali -------------------------
if $INSTALL_DEV; then
  print_info "Installazione strumenti di sviluppo (pre-commit, flake8, black, isort, mypy, bandit, detect-secrets)…"
  python -m pip install --no-user pre-commit flake8 black isort mypy bandit detect-secrets
  print_ok "Strumenti dev installati."
  if [[ -f "${REPO_ROOT}/.pre-commit-config.yaml" ]]; then
    print_info "Inizializzazione pre-commit hooks…"
    pre-commit install || print_warn "Installazione hook pre-commit fallita (continua comunque)."
    print_ok "pre-commit hooks attivati."
  fi

  # Fallback OS-level per WSL/Debian/Ubuntu se i binari non sono risolvibili nel PATH
  need_apt=false
  # Tool principali (formatter/lint/import/type/security)
  for tool in black isort flake8 bandit mypy; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      print_warn "Comando '$tool' non trovato nel PATH della venv."
      need_apt=true
    fi
  done

  if $need_apt && command -v apt-get >/dev/null 2>&1; then
    print_info "Tentativo di installazione di sistema (apt-get) per black/isort/flake8/mypy/bandit…"
    if sudo -n true 2>/dev/null; then
      sudo apt-get update -y
      # Pacchetti di sistema equivalenti (Debian/Ubuntu)
      sudo apt-get install -y \
        python3-black \
        python3-isort \
        python3-flake8 \
        mypy \
        bandit ||
        print_warn "Installazione apt parziale/non riuscita per alcuni tool (continua comunque)."
    else
      print_warn "Permessi sudo non disponibili. Esegui manualmente:
  sudo apt-get update -y && sudo apt-get install -y python3-black python3-isort python3-flake8 mypy bandit"
    fi
  fi
fi

# --------------------------- 7) Health check ----------------------------------
if ! $SKIP_HEALTH_CHECK; then
  print_info "Esecuzione health check…"
  set +e
  python - <<'PYCODE'
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
PYCODE
  HEALTH_RC=$?
  set -e
  if [[ ${HEALTH_RC} -ne 0 ]]; then
    print_fail "Health check fallito (vedi dettagli sopra)."
    exit 12
  else
    print_ok "Health check superato."
  fi
else
  print_warn "Health check saltato su richiesta."
fi

# --------------------------- 8) Messaggi finali -------------------------------
print_ok "Setup completato con successo."
if ! $QUIET; then
  echo "Per avviare la CLI interattiva:"
  echo "  source .venv/bin/activate"
  echo "  python -m src.main"
fi

exit 0
