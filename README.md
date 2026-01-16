# ForgeOps Manager

Toolkit **CLI enterprise** per **manutenzione, pulizia e sincronizzazione** su forges Git.
Attualmente supporta **GitHub** (implementazione completa) e **GitLab** (mock a scopo dimostrativo).

Consente di:

- Eliminare **tutte** le **GitHub Actions cache** del repository
- Eliminare **tutte** le **Releases**
- Gestire **Packages** (elenco, cancellazione selettiva/totale, cancellazione sole versioni)
- Pulire **workflow runs** (COMPLETED) _(registrato via provider actions)_
- **Code Scanning**: cancellare analyses o **dismiss** delle alerts, con filtro opzionale per tool
- **Social sync** (followers/following) via subcomando dedicato: `social-sync`

> ⚠️ **Attenzione**: molte operazioni sono **distruttive** e **irreversibili**.
> Usare con prudenza, preferibilmente con `--dry-run` quando disponibile, e con token/scopes adeguati.

---

## Sommario

- Caratteristiche
- Architettura e componenti
- Prerequisiti
- Installazione
- Configurazione
- Utilizzo
  - Menu interattivo
  - Modalità CLI diretta
  - Code Scanning (delete/dismiss)
  - Social Sync (followers/following)
- Variabili d’ambiente
- Log e osservabilità
- Gestione errori, rate‑limit e retry
- Test & qualità del codice
  → **Guida rapida pre‑commit**
- CI/CD e sicurezza
- Versioning & release
- Contributi
- Licenza
- **Documentazione**

---

## Caratteristiche

- **Provider**:
  - **GitHub**: implementazione completa (cache, releases, packages, code scanning, social sync, workflow runs).
  - **GitLab**: mock (interfaccia dimostrativa per estensioni future).
- **Operazioni GitHub pronte**:
  - **Cache**: elimina **tutte** le GitHub Actions cache entries (`src/providers/github/cache.py`)
  - **Releases**: elimina **tutte** le releases (`src/providers/github/releases.py`)
  - **Packages**: elenco e cancellazione (tutto o selettivo; possibilità di eliminare solo versioni) (`src/providers/github/packages.py`)
  - **Workflow runs (COMPLETED)**: registrato nelle azioni del provider (`src/providers/github/actions.py`)
  - **Security/Code Scanning**:
    - `MODE=delete`: cancella analyses per tool (e.g. **Trivy**, **Grype**)
    - `MODE=dismiss`: fa **dismiss** delle alert (con **reason** e **comment**, filtro tool e stato) (`src/providers/github/security.py`)
  - **Social Sync**: `social-sync` (subcomando) per gestione followers/following con allowlist/blocklist e report JSON (`src/providers/github/social.py`, `src/utils/config.py`)
- **CLI**:
  - **Menu interattivo** (provider/operazione)
  - **Modalità diretta** da riga di comando (argomenti)
  - **Subcomando dedicato** per `social-sync`
- **Logging strutturato** (JSON/Plain), idempotente, senza segreti (token **mai** loggato)
- **Robustezza**: controlli tipologici, gestione **rate-limit** GitHub, skip di elementi non conformi

---

## Architettura e componenti

- `src/main.py`: entrypoint CLI multi‑provider
- `src/providers/base.py`: interfaccia `Provider` e registro operazioni
- `src/providers/github/`:
  - `cache.py`, `releases.py`, `packages.py`: operazioni CRUD lato repository/utente/org
  - `security.py`: client Code Scanning (analyses/alerts) con gestione rate‑limit
  - `actions.py`: registrazione operazioni come “Pulizia workflow runs (COMPLETED)”, “social-sync”, etc.
  - `social.py`: servizio “social-sync”
  - `api.py`: helpers (paginazione, DELETE, prompt owner/repo)
- `src/utils/`:
  - `http.py`: costanti (`GITHUB_API`) e wrapper HTTP
  - `config.py`: caricamento impostazioni social-sync (env/CLI)
  - `logging.py`: setup logging, `log_event`, `get_logger`

---

## Prerequisiti

- **Python 3.10+**
- **Token GitHub** (**Personal Access Token** o **GH_TOKEN** di GitHub Actions) con permessi adeguati:
  - `repo` (per repo privati/pubblici)
  - `workflow` (gestione workflow runs)
  - `read:packages`, `delete:packages`
  - **Security events** (per Code Scanning: `security-events: write`)
  - **Actions** scrittura nel repository (per cancellazione cache)
- **Raccomandato**: PAT “classic” con `repo`, `workflow`, `read:packages`, `delete:packages`.

> In CI GitHub Actions il token **GH_TOKEN** erogato dal runner può avere permessi impostati nel workflow (`permissions:`); assicurarsi di concedere **write** dove necessario.

---

## Installazione

Clonare il repository:

```bash
git clone https://github.com/<org>/<repo>.git
cd forgeops-manager
```

### Setup virtualenv (consigliato)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# oppure su Windows:
# .\.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt
```

_(Opzionale)_: script `scripts/setup.sh` e `scripts/setup.ps1` se presenti.
→ Per la qualità del codice tramite hook automatici, vedi **docs/pre-commit.md**.

---

## Configurazione

### Variabili d’ambiente tipiche

```bash
export GH_TOKEN="ghp_..."  # o GH_TOKEN in GitHub Actions
export GH_OWNER="acme-org"     # owner/organization GitHub
export GH_REPO="my-repo"       # nome repo
# Social sync
export SYNC_DRY_RUN="true"
export SYNC_PAGE_SIZE="100"
export LOG_JSON="true"
export LOG_LEVEL="INFO"
```

I valori possono essere **sovrascritti** da flag CLI (vedi sezioni seguenti).

---

## Utilizzo

### Menu interattivo

```bash
python -m src.main
```

Flusso:

1.  Seleziona provider (**GitHub**, **GitLab** mock)
2.  Seleziona operazione (in italiano), ad es.:
    - “Elimina Actions cache”
    - “Elimina releases”
    - “Elimina packages”
    - “Elimina vulnerabilità Code Scanning”
    - “Pulizia workflow runs (COMPLETED)” _(via `actions.register_actions`)_

---

### Modalità CLI diretta

La maggior parte delle operazioni espone un **entrypoint CLI** dedicato.

#### Azioni cache — elimina **tutte** le entries

```bash
python -m src.providers.github.cache --owner acme-org --repo my-repo \
  --log-level INFO --log-json
```

#### Releases — elimina **tutte** le releases

```bash
python -m src.providers.github.releases --owner acme-org --repo my-repo \
  --log-level INFO --log-json
```

#### Packages — elenco o cancellazione interattiva

```bash
# Solo elenco (non cancella)
python -m src.providers.github.packages --org acme-org --type container --list --log-json

# Interattivo (prompt per cancellazioni)
python -m src.providers.github.packages --org acme-org --type container
```

#### Workflow runs (COMPLETED)

Registrato nel provider GitHub via `actions.register_actions(self)` ed eseguibile dal menu interattivo o dalla mappatura CLI in `main.py`.

---

### Code Scanning (delete/dismiss)

Funzionalità esposta tramite `src/main.py` (flusso classico), oppure via entrypoint di `security.py`:

**Delete analyses** per tool selezionati (o tutti):

```bash
python -m src.providers.github.security \
  --repo acme-org/my-repo \
  --mode delete \
  --tools "Trivy,Grype" \
  --log-level INFO --log-json
```

**Dismiss alerts** (state=open di default), con reason/comment:

```bash
python -m src.providers.github.security \
  --repo acme-org/my-repo \
  --mode dismiss \
  --tools "" \
  --reason "won't_fix" \
  --comment "Bulk reset: issues will reappear if they persist." \
  --state open \
  --log-level INFO --log-json
```

> Reason valide: `false_positive` | `won't_fix` | `used_in_tests`.

> In `main.py` è disponibile anche il flusso classico:
>
>     python -m src.main --operation clear-vulns --repo owner/repo --mode delete|dismiss \
>       --tools "Trivy,Grype" --token <PAT> --dry-run

---

### Social Sync (followers/following)

Subcomando dedicato in `main.py`:

```bash
python -m src.main social-sync \
  --token "$GH_TOKEN" \
  --dry-run \
  --allowlist "octocat,dependabot" \
  --blocklist "someuser" \
  --log-level INFO --log-json \
  --page-size 100 \
  --report-out social_sync_report.json
```

Genera un **report JSON** con:

- conteggio followers/following
- liste `to_follow` / `to_unfollow`
- esiti finali (`followed`, `unfollowed`, `skipped`)

---

## Variabili d’ambiente

- `GH_TOKEN` – token GitHub (**mai** loggato)
- `GH_OWNER` / `GH_REPO` – owner e repo per operazioni repo‑scoped
- **Logging**:
  - `LOG_JSON` (`true|false`)
  - `LOG_LEVEL` (`DEBUG|INFO|WARNING|ERROR|CRITICAL`)
- **Social Sync**:
  - `SYNC_DRY_RUN` (`true|false`)
  - `SYNC_PAGE_SIZE` (`1..100`)
  - allowlist/blocklist possono essere passati via CLI o gestiti in config custom

> Le opzioni CLI **sovrascrivono** gli ENV dove previsto.

---

## Log e osservabilità

- **Logging strutturato** con `log_event` (JSON/Plain), idempotente.
- Eventi chiave:
  - start/complete/skip/error per ogni operazione
  - gestione rate‑limit (`rate_limit_wait`)
  - eccezioni con stack trace (senza esporre segreti)
- **Console**:
  - Interattivo: console “pulita” (log console disabilitati per non sporcare i prompt)
  - CLI diretta: log console **abilitati**

---

## Gestione errori, rate‑limit e retry

- **HTTP errors** → eccezioni con dettaglio (status, snippet testo)
- **Rate‑limit** GitHub:
  - attesa automatica fino al reset (header `X‑RateLimit‑Reset`)
  - un **retry** automatico
- **Robustezza input**:
  - validazione elementi paginati (skip se non conformi)
  - type‑safety su id/versioni (cast sicuri)
- **Sicurezza**:
  - token **mai** presente nei log
  - richieste firmate con `Accept: application/vnd.github+json` e `X-GitHub-Api-Version: 2022-11-28`

---

## Test & qualità del codice

- **Tipizzazione** completa (Pylance/mypy‑friendly)
- **Linting/formatting**: flake8, black, isort _(raccomandati via pre‑commit)_
- **Test** (raccomandati):
  - `pytest` + mocking HTTP (`responses`/`pytest‑httpx`) per API GitHub
  - `pytest --cov=src --cov-report=xml`

**Guida rapida pre‑commit**:
→ Segui **docs/pre-commit.md** per installazione e uso degli hook (black, isort, flake8, mypy, bandit, detect‑secrets).

---

## CI/CD e sicurezza

- **CI** (raccomandata):
  - workflow GitHub Actions: install, lint, type‑check, test, package
    → vedi **`.github/workflows/ci.yml`** e **docs/ci.md**
- **Sicurezza**:
  - **Dependabot** per aggiornare dipendenze
  - **CodeQL** per analisi SAST
  - **Secret scanning** e protezione branch (PR obbligatorie, CI mandatory)

---

## Versioning & release

- **Versionamento semantico** (`MAJOR.MINOR.PATCH`)
- **CHANGELOG.md** generato da commit convenzionali / GitHub Release Notes
- **Distribuzione**:
  - pacchetto Python (PyPI interno/GitHub Packages) **oppure**
  - uso diretto da sorgente con virtualenv
- **Artifact**: opzionale zip/tar delle utility CLI

---

## Contributi

Contributi benvenuti.
Aprire una **PR** seguendo queste linee guida:

- test e linting **obbligatori**
- motivare chiaramente la modifica
- evitare breaking changes senza major increment
- mantenere coerenza con lo **standard di logging** e sicurezza (no segreti in log)

---

## Licenza

Questo progetto è rilasciato secondo i termini indicati nel file **LICENSE** del repository.

---

### Esempi rapidi

**Interattivo**:

```bash
python -m src.main
```

**Releases: elimina tutte**:

```bash
python -m src.providers.github.releases --owner acme-org --repo my-repo --log-json
```

**Cache: elimina tutte**:

```bash
python -m src.providers.github.cache --owner acme-org --repo my-repo --log-json
```

**Packages: elenco (senza cancellare)**:

```bash
python -m src.providers.github.packages --org acme-org --type container --list
```

**Code Scanning: delete analyses (Trivy, Grype)**:

```bash
python -m src.providers.github.security --repo acme-org/my-repo --mode delete --tools "Trivy,Grype"
```

**Code Scanning: dismiss alerts (tutti i tool)**:

```bash
python -m src.providers.github.security --repo acme-org/my-repo --mode dismiss --tools "" --reason "won't_fix"
```

**Social Sync**:

```bash
python -m src.main social-sync --token "$GH_TOKEN" --dry-run --allowlist "octocat" --log-json
```

---

## Documentazione

- **Guida pre‑commit**: docs/pre-commit.md
- **Setup & ambienti**: docs/setup.md
- **Guida CLI (comandi & esempi)**: docs/cli.md
- **CI / Quality Gate**: docs/ci.md
- **Architettura & componenti**: docs/architecture.md
- **Integrazione VS Code**: docs/vscode.md
- **Troubleshooting**: docs/troubleshooting.md

---
