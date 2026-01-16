# 🚀 Pull Request

## Sommario / Descrizione

Breve descrizione della modifica e del suo scopo.
Contesto e motivazione: perché è necessaria? Quale problema risolve?

**Tipo di modifica** (seleziona con `x`):

- [ ] `feat`: nuova funzionalità (non-breaking)
- [ ] `fix`: correzione bug (non-breaking)
- [ ] `refactor`: refactoring interno (senza cambiamenti funzionali)
- [ ] `perf`: miglioramenti prestazionali
- [ ] `docs`: aggiornamento documentazione
- [ ] `test`: aggiunta/aggiornamento test
- [ ] `build/ci`: pipeline, tooling, dipendenze
- [ ] `chore`: manutenzione generica
- [ ] **breaking change**: modifica non retro‑compatibile (richiede migrazione)

---

## Issue correlate

Collega le issue o feature request pertinenti:

- Closes / Resolves / Fixes: `#<numero_issue>`
- Related: `#<numero_issue>`

---

## Motivazione & Implementazione

**Perché** questa modifica è necessaria? **Come** affronta il problema?

- Dettagli implementativi principali
- Decisioni prese / trade‑off
- Dipendenze da altri moduli o PR
- Impatto su API pubbliche / CLI / flussi esistenti

---

## Ambito della modifica

- Moduli/aree toccate (es.: `src/providers/github/security.py`, `src/utils/logging.py`)
- Interfacce/contract modificati (se presenti)
- Compatibilità (backward/forward)

---

## Checklist (✅ OBBLIGATORIA)

La PR **non può essere mergeata** finché tutti i punti sono soddisfatti:

### Qualità & Stile

- [ ] Rispetto dei **Conventional Commits** nel titolo: `type: breve descrizione`
- [ ] Lint/formatting OK (`black`, `isort`, `flake8`)
- [ ] Tipi OK (nessun warning **Pylance/mypy**)
- [ ] Nessun side‑effect all’**import** (configurazione logging solo in `main()`/CLI)
- [ ] Logging **strutturato** (`log_event`) senza segreti/PII

### Test

- [ ] Test aggiunti/aggiornati per coprire la modifica
- [ ] Tutti i test passano (`pytest`)
- [ ] (Opzionale) Coverage accettabile (`pytest --cov`)

### Sicurezza

- [ ] **Nessun segreto** in codice/log/commit/issue (token, password, chiavi)
- [ ] Scope/token GitHub ridotti al **minimo necessario** (principio di least‑privilege)
- [ ] Header API corretti (es.: `Accept: application/vnd.github+json`, `X-GitHub-Api-Version`)
- [ ] Gestione **rate‑limit** con attesa e retry singolo (se applicabile)
- [ ] Validazione input e skip robusto per elementi non conformi

### Documentazione

- [ ] README/CONTRIBUTING aggiornati se cambia comportamento pubblico
- [ ] Esempi CLI aggiornati (se rilevanti)
- [ ] Commenti chiari per logiche complesse

### CI/CD

- [ ] Pipeline **verde** (lint, type‑check, test, build)
- [ ] Labels assegnate (es.: `feat`, `fix`, `security`, `ci`)
- [ ] Reviewer/i aggiunti (code owners coinvolti)
- [ ] Nessun file generato/di build committato (es.: `dist/`, `__pycache__/`)

---

## Breaking changes (se applicabile)

**Descrivi chiaramente**:

- Cosa rompe (API, CLI, contract)
- Piano di migrazione
- Impatto su ambienti/utenti
- Versionamento SemVer previsto (es.: incremento **MAJOR**)

---

## Note di rilascio (Release Notes)

Queste informazioni saranno usate per CHANGELOG / Release:

- **Feature**: …
- **Fix**: …
- **Perf/Refactor**: …
- **Breaking**: …

---

## Performance & Osservabilità

- Impatto prestazionale atteso (CPU/IO/latency)
- Eventi di logging introdotti/aggiornati (`log_event`)
- Metriche o tracing (se integrato, es.: OpenTelemetry/Datadog)
- Noise control: sono presenti flag per silenziare output (`--quiet`/log JSON)?

---

## Sicurezza: Considerazioni aggiuntive

- Token/PAT non loggati; variabili d’ambiente rispettate
- Minimizzazione rischio operazioni **distruttive**: conferme/dry‑run disponibili?
- Accesso/permessi verificati (repo, security‑events, packages)

---

## Test manuali / Smoke test (passi eseguiti)

Indica comandi e risultati sintetici (copia/incolla):

```bash
# Esempio
python -m src.providers.github.security --repo owner/repo --mode delete --tools "Trivy,Grype" --log-json
# Output sintetico atteso (senza segreti):
# { "scanned": 42, "deleted": 42 }
```

---

## Rollout & Revert Plan

**Rollout**:

- Ambienti di rollout (dev/stage/prod)
- Feature flags / toggles (se presenti)
- Comunicazione a utenti/maintainer

**Revert** (se necessario):

- Passi per ripristinare stato precedente
- Impatti collaterali
- Dati non recuperabili (se operazioni distruttive già eseguite)

---

## Screenshot / Allegati (facoltativi)

Allega immagini, diagrammi, log redatti, link a documenti di design o PoC.

---
