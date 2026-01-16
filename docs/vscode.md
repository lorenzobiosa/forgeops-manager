# VS Code — Integrazione

## Estensioni raccomandate

Vedi `.vscode/extensions.json` (Python, Pylance, Black, isort, Flake8, Mypy).

## Impostazioni

`.vscode/settings.json`

- Pylance `strict`
- Default formatter: **black**, organizzazione import on save (**isort**)
- pytest abilitato
- `editor.rulers: [100]`

## Task

`.vscode/tasks.json`

- `setup:dev (Linux/macOS/WSL)` / `setup:dev (Windows)`
- `pre-commit:install` / `pre-commit:run-all`
- `format:black+isort` / `format:check`
- `lint:flake8` / `types:mypy (strict)` / `test:pytest`
- `security:bandit` / `security:secrets`
- `quality:gate` (tutto)

Esegui: **Terminal → Run Task** o `Ctrl+Shift+B` (quality gate).

## Launch

`.vscode/launch.json`

- Main interattivo
- Security (delete/dismiss)
- Social-sync
- Packages/Releases/Azione cache

## .env

Usa `.env` per variabili **locali** (mai committare). Fornisci `.env.example`.

---
