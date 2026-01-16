# 🤝 Linee guida per contribuire

Grazie per l’interesse nel contribuire! 🙌
Accogliamo con piacere contributi di ogni tipo: **bug fix**, **migliorie**, **documentazione**, **segnalazioni** e **nuove feature**.
Per garantire collaborazione efficace, coerente e scalabile, segui per favore le linee guida sottostanti.

---

## 🧭 Indice

1.  Ambito e requisiti
2.  Come contribuire
3.  Issue & Pull Request
4.  Stile del codice
5.  Test e qualità
6.  Sicurezza e segnalazioni
7.  Comunicazione e condotta
8.  Flusso di release e versioning
9.  Ambiente di sviluppo: comandi rapidi
10. Domande e supporto

---

## 📌 Ambito e requisiti

Prima di contribuire, assicurati di:

- Aver letto il **README** per comprendere obiettivi e funzionalità del progetto.
- Seguire questo documento **CONTRIBUTING.md**.
- Utilizzare **Python 3.10+** e una **virtualenv** isolata.
- Non inserire **mai** segreti nei log o nel codice (token, password, chiavi).

**Tecnologie principali**:

- Python (CLI e servizi)
- Tipizzazione statica (**Pylance/mypy**)
- Linting/formatting (**flake8**, **black**, **isort**)
- Test (**pytest**)
- Logging strutturato (JSON/Plain) con **`src.utils.logging`**
- Integrazione GitHub (HTTP API), gestione **rate‑limit**

---

## 🚀 Come contribuire

Puoi contribuire in diversi modi:

### 🐛 Segnalare bug

- Apri una **Issue** usando il template _Bug Report_.
- Includi: passi per riprodurre, comportamento atteso/evidenze, versione, OS.

### 💡 Proporre feature

- Apri una **Issue** usando il template _Feature Request_.
- Spiega il problema da risolvere, il valore per l’utente, eventuali alternative.

### 📘 Migliorare la documentazione

- Correggi errori, aggiorna esempi, aggiungi sezioni utili.
- Le PR di sola documentazione sono benvenute.

### 🧰 Inviare codice

- Consulta le sezioni: **Stile del codice**, **Test e qualità**, **Issue & PR**.

---

## 📝 Issue & Pull Request

1.  **Cerca** tra le issue/PR esistenti prima di aprirne di nuove.
2.  Usa sempre i **template** appropriati (bug/feature).
3.  Collega la PR a una issue tramite:
    ```text
    Closes #<numero_issue>
    ```
4.  Titoli PR secondo **Conventional Commits** (vedi sotto), ad es.:
    ```text
    feat: aggiunge dismiss alerts per Code Scanning
    fix: corregge gestione rate limit su delete analyses
    docs: aggiorna guida social-sync
    ```
5.  La PR deve includere:
    - Descrizione chiara di cosa cambia e perché
    - Evidenza di test locali (comando eseguito, output sintetico)
    - Eventuali impatti (breaking changes, migrazioni)
6.  **Checklist PR** (obbligatoria):
    - [ ] Test locali passano (`pytest`), linting e formatting passano
    - [ ] Nessun **segreto** esposto nei log o nel codice
    - [ ] Logging coerente (`log_event`) senza PII/token
    - [ ] Tipi e firme coerenti (nessun warning Pylance)
    - [ ] Documentazione aggiornata se serve (README/CLI)

> **Nota**: le PR vengono accettate solo se la **CI** è verde (lint, type‑check, test).

---

## 📋 Stile del codice

**Conventional Commits** (obbligatorio):

- `feat:` nuova funzionalità
- `fix:` correzione bug
- `docs:` documentazione
- `refactor:`, `perf:`, `test:`, `build:`, `ci:`, `chore:`

**Formattazione e lint**:

- **black** (line‑length 100)
- **isort** (ordinamento import)
- **flake8** (lint)
- **mypy**/**Pylance** (tipi)

**Linee guida Python**:

- Tipizza sempre pubbliche API e funzioni principali
- Evita side‑effects all’import (configura logging solo in `main()` o CLI)
- Evita `print` se non per UX CLI; preferisci `log_event` per telemetria
- Non loggare **mai** segreti (token/credenziali)
- Funzioni piccole e focalizzate; fallisci **velocemente** con messaggi chiari
- Scrivi messaggi di commit chiari e sintetici

---

## 🧪 Test e qualità

**Test**:

- Usa **pytest**
- Mocka le chiamate HTTP (es.: `responses`, `pytest-httpx`, o doppio level di mock a livello `src.providers.github.api`)
- Testa i percorsi “critici”:
  - `security.py`: delete/dismiss, gestione confirm/next, rate‑limit
  - `packages.py`: parsing versioni/ID, cancellazione versioni
  - `releases.py`, `cache.py`: paginazione/iterazioni e error handling

**Quality gates** (obbligatori prima di aprire PR):

```bash
# Ambiente
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Lint & formatting
black . --check
isort . --check-only
flake8 .

# Tipi
mypy src

# Test
pytest -q
# (opzionale) coverage:
pytest --cov=src --cov-report=term-missing
```

> Se usi **pre‑commit**, configura gli hook per eseguire automaticamente i controlli.

---

## 🔐 Sicurezza e segnalazioni

- **Non aprire issue pubbliche** per vulnerabilità: segui la policy in `SECURITY.md` (responsible disclosure).
- Non includere mai token/credenziali nei commit, issue, o log.
- Evita di serializzare payload completi nei log; privilegia metadati sicuri.
- Verifica sempre gli header usati per le API GitHub:
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `Authorization: Bearer <TOKEN>` (**mai loggarlo**)

---

## 💬 Comunicazione e condotta

Adottiamo un ambiente **aperto, rispettoso e collaborativo**.
Partecipando, accetti di:

- Comunicare con rispetto e chiarezza
- Evitare linguaggio ostile o discriminatorio
- Fornire feedback costruttivi e circostanziati

Consulta **CODE_OF_CONDUCT.md** per i dettagli.

---

## 🚢 Flusso di release e versioning

- **SemVer**: `MAJOR.MINOR.PATCH`
- Ogni PR dovrebbe seguire i **Conventional Commits** per facilitare CHANGELOG e release notes
- **CHANGELOG.md** mantenuto e aggiornato durante le release
- Rilascio:
  - Tag delle versioni (`vX.Y.Z`)
  - Changelog generato (automatico se configurato)
  - (Opzionale) pubblicazione su PyPI privato / GitHub Packages

---

## 🧰 Ambiente di sviluppo: comandi rapidi

### Setup locale

```bash
python3 -m venv .venv
source .venv/bin/activate            # .\.venv\Scripts\Activate.ps1 su Windows
pip install --upgrade pip
pip install -r requirements.txt
```

### Lint/format/type/test

```bash
black . --check
isort . --check-only
flake8 .
mypy src
pytest -q
```

### Esecuzione CLI

```bash
# Menu interattivo
python -m src.main

# Esempi diretti
python -m src.providers.github.cache --owner <org> --repo <repo> --log-json
python -m src.providers.github.releases --owner <org> --repo <repo> --log-json
python -m src.providers.github.packages --org <org> --type container --list
python -m src.providers.github.security --repo <org>/<repo> --mode delete --tools "Trivy,Grype"
python -m src.main social-sync --token "$GH_TOKEN" --dry-run --log-json
```

---

## ❓ Domande e supporto

- Consulta **README.md**
- Apri una **Issue** per domande tecniche (se non sensibili)
- Per tematiche di sicurezza, segui **SECURITY.md**

---

## 🎉 Grazie!

Il tuo contributo è prezioso: grazie per aiutare a rendere il progetto migliore! 🚀

---
