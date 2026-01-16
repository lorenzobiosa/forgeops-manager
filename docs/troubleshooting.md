# Troubleshooting

## pre-commit lento la prima volta

Usa `pre-commit run --all-files` una volta; poi agisce solo sui file modificati.

## mypy/flake8/black/isort non trovati

- Attiva la venv: `source .venv/bin/activate` o `.\.venv\Scripts\Activate.ps1`
- Installa dev tools con gli script:
  - `./scripts/setup.sh --install-dev`
  - `pwsh -File .\scripts\setup.ps1 -InstallDev`

## WSL/Debian: tool non nel PATH

Gli script tentano fallback `apt-get`:

```bash
sudo apt-get update
sudo apt-get install -y python3-black python3-isort python3-flake8 mypy bandit
```

## Detect-Secrets: baseline mancante

```bash
detect-secrets scan > .secrets.baseline
git add .secrets.baseline
```

## pip-audit fallisce la rete / mirror

Imposta proxy con gli script di setup (`--proxy` / `-Proxy`).

## CI fallisce su format/lint/types

Esegui localmente:

```bash
black . && isort .
flake8 .
mypy src --strict
pytest -q
```

---
