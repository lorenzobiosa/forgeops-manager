# CI & Quality Gate

La CI (`.github/workflows/ci.yml`) esegue Quality Gate e Sicurezza.

## Quality gate (job `quality`)

- **Black**: `black . --check`
- **Isort**: `isort . --check-only`
- **Flake8**: `flake8 .`
- **Mypy**: `mypy src --strict`

Config centralizzata in `pyproject.toml`:

```toml
[tool.black]        # line-length=100
[tool.isort]        # profile=black, line_length=100
[tool.mypy]         # strict=true, python_version=3.10
[tool.flake8]       # max-line-length=100, ignore E203 W503
```

## Test (job `tests`)

- `pytest -q --cov=src --cov-report=xml`
- Artifact: `coverage.xml`, JUnit XML

## Sicurezza (job `security`)

- **Bandit**: `bandit -r src`
- **Detect-Secrets** (baseline): `detect-secrets-hook --baseline .secrets.baseline --all-files`
- **pip-audit**: report JSON (non blocking per default)

## Matrix

- Python 3.10 / 3.11 su Ubuntu.

## Risoluzione problemi CI

- Formattazione: `black . && isort .`
- Lint: `flake8 .`
- Tipi: `mypy src --strict`
- Segreti: rigenera baseline `detect-secrets scan > .secrets.baseline` (e versiona)
- Vulnerabilità: verifica report `pip-audit-report.json`

---
