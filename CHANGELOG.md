# 📦 CHANGELOG — ForgeOps Manager

Tutte le modifiche rilevanti al progetto sono documentate qui.

Il formato segue:

- **Semantic Versioning**: MAJOR.MINOR.PATCH
- **Conventional Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Compatibile con i Workflow di Release automatico (`github-release.yml`)

---

## [Unreleased]

### aggiungi qui manualmente se serve — le release le generano i tag SemVer

---

## [0.1.0] - 2026-01-14

### 🚀 Iniziale rilascio enterprise

#### ✨ feat

- Implementazione provider GitHub completo (cache, releases, packages, security, social-sync)
- CLI interattiva + modalità diretta
- Logging JSON strutturato, redazione segreti, trace/correlation ID
- Gestione robusta rate-limit GitHub
- Setup pre-commit (black, isort, flake8, mypy, bandit, detect-secrets)
- Workflow CI (quality + tests + security)
- Workflow Release automatico (tag, changelog, asset)
- Test automatici per GitHub providers
- Packaging Python (`pyproject.toml`, layout src)

#### 🐛 fix

- Gestione corretta `confirm_delete_url` e `next_analysis_url` nel Code Scanning
- Robustezza input nei provider (skip sicuri, validazioni)
- Logging consistente in modalità interattiva/CLI

#### 🔧 refactor

- Centralizzazione della sessione HTTP (rate-limit, headers, error handling)
- Miglioramento architettura `providers/base.py`
- Miglioramento struttura `src/utils` (http, config, token_guard, runtime)

#### 📚 docs

- Documentazione tecnica: CLI, setup, architettura, CI, pre‑commit, VS Code
- File README aggiornato e completo
- Documentazione developer nei provider
- Aggiornamento CONTRIBUTING e SECURITY

---

## Formato commit accettato

Per generare changelog coerenti:

- `feat: <descrizione>` — nuove feature
- `fix: <descrizione>` — bugfix
- `refactor: <descrizione>` — refactoring senza cambi comportamentali
- `docs: <descrizione>` — documentazione
- `chore: <descrizione>` — manutenzione, setup, tooling
- `test: <descrizione>` — aggiornamento test

---

## Come generare una nuova release

1. Aggiorna `version` in `pyproject.toml`
2. Commit con conventional commit
3. Crea tag:

   ```bash
   git tag -a v0.X.Y -m "Release v0.X.Y"
   git push origin v0.X.Y
   ```

4. Github Actions →
   - genera changelog
   - crea Release
   - allega pacchetti (wheel, sdist, zip, tar.gz, checksum)
   - pulisce cache Actions

---

## Formato Changelog

Conforme a **Keep a Changelog**:
<https://keepachangelog.com/>

Compatibile con **Semantic Versioning 2.0.0**
<https://semver.org/>

---
