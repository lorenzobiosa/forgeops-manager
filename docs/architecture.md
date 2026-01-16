# Architettura & Componenti

Questo documento descrive l’architettura logica del progetto, i principali componenti applicativi, i flussi operativi (incluso Code Scanning), la gestione del rate‑limit GitHub, il modello di logging strutturato e come estendere il sistema con nuovi provider/azioni.

---

## Panoramica componenti

- `src/main.py`: **entrypoint CLI** multi‑provider e subcomandi (menu interattivo, `social-sync`, mapping operazioni).
- `src/providers/base.py`: interfaccia `Provider` e **registro** delle azioni eseguibili.
- `src/providers/github/`:
  - `cache.py`, `releases.py`, `packages.py`: operazioni CRUD su **Actions cache**, **Releases**, **Packages**.
  - `security.py`: **Code Scanning** (analyses/alerts) con gestione **rate‑limit** e flusso `delete`/`dismiss`.
  - `actions.py`: **registra** azioni provider (es. “Pulizia workflow runs (COMPLETED)”).
  - `social.py`: **social‑sync** followers/following (allowlist/blocklist, report).
  - `api.py`: helper **HTTP**, **paginazione**, **DELETE** e prompt owner/repo (se flusso interattivo).
- `src/utils/`:
  - `http.py`: costanti (`GITHUB_API`) e **wrapper HTTP** (intestazioni, versione API).
  - `logging.py`: logging **strutturato** (JSON/plain), `log_event`, `get_logger`, setup CLI.
  - `config.py`: caricamento **configurazioni** (env/CLI), in particolare per social‑sync.

### Diagramma componenti (alto livello)

```mermaid
flowchart LR
  subgraph CLI
    MAIN[main.py<br>CLI entrypoint]
  end

  subgraph Providers
    BASE[base.py<br>Provider interface/registry]
    subgraph GitHub
      GH_CACHE[cache.py]
      GH_REL[releases.py]
      GH_PKG[packages.py]
      GH_SEC[security.py<br>Code Scanning]
      GH_ACT[actions.py<br>register_actions]
      GH_SOC[social.py]
      GH_API[api.py<br>HTTP/pagination helpers]
    end
  end

  subgraph Utils
    U_HTTP[utils/http.py<br>GITHUB_API/headers]
    U_LOG[utils/logging.py<br>log_event/setup]
    U_CFG[utils/config.py]
  end

  MAIN --> BASE
  MAIN --> GH_ACT
  MAIN --> GH_SEC
  MAIN --> GH_CACHE
  MAIN --> GH_REL
  MAIN --> GH_PKG
  MAIN --> GH_SOC

  GH_SEC --> U_HTTP
  GH_CACHE --> U_HTTP
  GH_REL --> U_HTTP
  GH_PKG --> U_HTTP
  GH_SOC --> U_HTTP

  MAIN --> U_LOG
  GH_SEC --> U_LOG
  GH_CACHE --> U_LOG
  GH_REL --> U_LOG
  GH_PKG --> U_LOG
  GH_SOC --> U_LOG

  MAIN --> U_CFG
  GH_SOC --> U_CFG
```

---

## Flussi principali

### 1) Code Scanning — `delete analyses`

**Obiettivo**: eliminare analyses per i tool selezionati (es. Trivy, Grype), dal più recente a ritroso, seguendo eventuali **follow‑up** (`confirm_delete_url` / `next_analysis_url`) fino a **204**.

```mermaid
sequenceDiagram
  autonumber
  participant CLI as CLI (main.py)
  participant SEC as GitHubSecurityClient (security.py)
  participant API as GitHub API
  participant LOG as log_event

  CLI->>SEC: delete_analyses(tools_filter)
  loop scan pages
    SEC->>API: GET /repos/{r}/code-scanning/analyses?page=N
    API-->>SEC: 200 [list]
    SEC->>LOG: security_list_analyses_* (ok/skip/error)
    SEC->>SEC: filtro tool + check deletable
    alt trovato elemento deletable
      SEC->>SEC: delete_analysis(id)
      SEC->>API: DELETE /code-scanning/analyses/{id}
      alt 204
        API-->>SEC: 204 No Content
        SEC->>LOG: security_delete_analysis_done
      else 400 (confirm needed)
        API-->>SEC: 400 (confirm_delete)
        SEC->>API: DELETE ...?confirm_delete=true
        API-->>SEC: 204/20x
        SEC->>LOG: security_delete_analysis_done/error
      else 200/202 (follow-up)
        API-->>SEC: 200/202 {confirm_delete_url|next_analysis_url}
        loop follow-up
          SEC->>API: DELETE confirm/next (+confirm_delete=true)
          API-->>SEC: 20x or {next}
          SEC->>LOG: security_delete_followup_*
        end
      end
    else nessun deletable
      SEC->>SEC: fine flusso
    end
  end
```

**Note operative**:

- Se `confirm_delete_url`/`next_analysis_url` è presente, il client segue finché non riceve **204** o la coppia è `null`.
- `confirm_delete=true` è aggiunto quando mancante.
- **Rate‑limit** gestito a livello `_request` (vedi sezione dedicata).

---

### 2) Code Scanning — `dismiss alerts`

**Obiettivo**: eseguire **dismiss** delle alert in `state=open` (default), con `reason` e `comment`, filtrando opzionalmente per **tool**.

```mermaid
sequenceDiagram
  autonumber
  participant CLI as CLI (main.py)
  participant SEC as GitHubSecurityClient (security.py)
  participant API as GitHub API
  participant LOG as log_event

  CLI->>SEC: dismiss_alerts(tools_filter, reason, comment, state)
  loop pagine alert
    SEC->>API: GET /repos/{r}/code-scanning/alerts?state=open&page=N
    API-->>SEC: 200 [alerts]
    SEC->>LOG: security_list_alerts_* (ok/skip/error)
    SEC->>SEC: filtro tool + estrazione rule id/name
    alt numero ok
      SEC->>API: PATCH /alerts/{number} {dismissed:true, reason, comment}
      API-->>SEC: 200 OK
      SEC->>LOG: security_dismiss_alert_ok
    else numero mancante/non int
      SEC->>LOG: security_dismiss_alert_skip
    end
  end
```

**Reason valide**: `false_positive` | `won't_fix` | `used_in_tests`.

---

## Gestione rate‑limit GitHub

L’HTTP client usa `_request()` che intercetta gli header **`X-RateLimit-Remaining`** e **`X-RateLimit-Reset`** (oltre a un fallback su risposta **403** con “rate limit” nel body). Se necessario, **attende** fino al reset e **ritenta una volta**.

```mermaid
flowchart TD
  A[HTTP request] --> B{X-RateLimit-Remaining <= 0?}
  B -- No --> C[Return response]
  B -- Yes --> D{X-RateLimit-Reset presente?}
  D -- Yes --> E[Calcola wait_seconds = reset-now+1]
  D -- No --> F[wait_seconds = 30s di fallback]
  E --> G[Sleep(wait_seconds)]
  F --> G
  G --> H[Riprova la stessa request UNA volta]
  H --> I[Return response finale]
```

**Dettagli**:

- Se la risposta è **403** e il body contiene “rate limit”, il client usa `X-RateLimit-Reset` se presente o un **fallback** di 30s.
- L’evento `rate_limit_wait` è loggato con i **secondi di attesa**.

---

## Logging strutturato

Il sistema usa `src/utils/logging.py` con:

- `setup_logging(...)`: configurazione (console JSON/plain, livelli)
- `get_logger(__name__)`
- `log_event(logger, event_name, payload, level=...)` per **eventi strutturati** (chiavi coerenti)

**Principi**:

- **Mai** loggare **segreti** (PAT, credenziali, PII).
- Eventi standard per ogni operazione: `*_start`, `*_ok`, `*_skip`, `*_error`, `rate_limit_wait`, `cli_invocation`, `cli_error`.
- In modalità CLI, i **log** possono essere attivati/disattivati in base al contesto (interattivo vs diretto).

```mermaid
sequenceDiagram
  autonumber
  participant CLI as CLI
  participant OP as Operazione (cache/releases/packages/security)
  participant LOG as log_event

  CLI->>LOG: cli_invocation
  CLI->>OP: esecuzione operazione
  OP->>LOG: <op>_start
  alt esito OK
    OP->>LOG: <op>_ok (conteggi/riassunto)
  else skip/invalid
    OP->>LOG: <op>_skip (motivo)
  else errore
    OP->>LOG: <op>_error (tipo, messaggio)
  end
  CLI->>LOG: clear_vulns_complete / summary
```

---

## Sicurezza

- Il **token** non viene **mai** serializzato nei log o incluso in eccezioni.
- **Reason** per `dismiss` sono **validate** (`false_positive`, `won't_fix`, `used_in_tests`).
- **Validazioni tipologiche**: ogni `resp.json()` è verificato (`isinstance(list/dict)`) e i valori sono castati solo dopo i controlli.
- Per elementi **malformati**: lo stream viene **skippato**, con evento `*_skip`.

---

## Estendibilità

Aggiungere **nuovi provider** o **nuove azioni** segue un pattern semplice:

1.  **Crea** una classe provider che implementa/estende l’interfaccia in `providers/base.py`.
2.  **Registra** le azioni nel provider (es. in `actions.py` o direttamente nel costruttore).
3.  **Esponi** entrypoint CLI (modulo Python o subcomando in `main.py`).
4.  **Usa** `utils/http.py` per coerenza degli header e delle versioni API.
5.  **Emetti** eventi coerenti via `utils/logging.py` (`log_event`).

### Diagramma di estensione (nuova azione provider)

```mermaid
flowchart LR
  NEWACT[Nuova azione es. providers/github/sbom.py] --> REG[Registro azioni<br>providers/base.py]
  REG --> MAIN[main.py<br>Menu/Dispatch CLI]
  NEWACT --> UHTTP[utils/http.py]
  NEWACT --> ULOG[utils/logging.py]
  MAIN --> NEWACT
```

**Checklist**:

- Tipizza in modo completo (mypy/Pylance **strict**).
- Gestisci **paginazione** e **rate‑limit** ove applicabile.
- **Non** loggare segreti; mantieni i payload multipli minimalisti.
- Aggiungi **task VS Code**/launch se utile e **documenta** in `docs/cli.md`.

---

## Sequenza end‑to‑end (esempio: “Elimina Releases”)

```mermaid
sequenceDiagram
  autonumber
  participant Dev as Sviluppatore
  participant VS as VS Code Task / Terminal
  participant CLI as python -m src.providers.github.releases
  participant OP as releases.py
  participant API as GitHub API
  participant LOG as log_event

  Dev->>VS: Avvia task "Releases (delete all)"
  VS->>CLI: Esecuzione modulo con argomenti
  CLI->>OP: main() / delete_all_releases(owner, repo)
  OP->>LOG: releases_start
  loop paginazione
    OP->>API: GET /repos/{o}/{r}/releases?page=N
    API-->>OP: 200 [list]
    OP->>LOG: releases_list_ok
    loop elementi
      OP->>API: DELETE /releases/{id}
      API-->>OP: 204 OK
      OP->>LOG: releases_delete_ok
    end
  end
  OP->>LOG: releases_complete {totali}
  CLI-->>VS: Riepilogo esito (stdout)
```

---

## Note di design

- **Separazione delle responsabilità**:
  - `main.py` orchestration/CLI
  - `providers/*` **business logic** per forgi specifici
  - `utils/*` **infrastruttura condivisa** (HTTP/log/config)
- **Resilienza**: stream di item (analyses/alerts/releases/caches) **tollerano** elementi malformati con `skip`, lasciando traccia nel log.
- **Idempotenza**: le operazioni sono progettate per essere ri‑eseguite in sicurezza (per quanto possibile), con indicatori chiari nel log.
- **Configurabilità**: via ENV/CLI; **VS Code tasks** e **CI** riflettono gli stessi gate (formattazione, lint, tipi, test, sicurezza).

---

### Collegamenti utili

- **Guida CLI**: `docs/cli.md`
- **CI / Quality Gate**: `docs/ci.md`
- **VS Code**: `docs/vscode.md`
- **Pre‑commit hooks**: `docs/pre-commit.md`
- **Setup & Ambienti**: `docs/setup.md`
- **Troubleshooting**: `docs/troubleshooting.md`

---
