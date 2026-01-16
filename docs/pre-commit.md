# ✅ Pre‑commit Hooks — Guida rapida

Questa guida spiega come installare e usare i **pre‑commit hooks** per garantire qualità, sicurezza e coerenza del codice prima di ogni commit.

> Gli hook eseguono automaticamente: **black** (format), **isort** (import), **flake8** (lint), **mypy** (type check), **bandit** (security), **detect‑secrets** (secret scan), oltre a fix di base (whitespace, EoF, YAML).

---

## Requisiti

- Python 3.10+ e virtualenv (creata via `scripts/setup.sh` o `scripts/setup.ps1`)
- File `.pre-commit-config.yaml` nella root del repo
- Baseline segreti: `.secrets.baseline` (versionata)

---

## Installazione

1. **Attiva la virtualenv**

   ```bash
   source .venv/bin/activate        # Linux/macOS/WSL
   # Oppure:
   .\.venv\Scripts\Activate.ps1     # Windows PowerShell
   ```

2. **Installa pre‑commit**

   ```bash
   pip install pre-commit
   ```

3. **Inizializza la baseline dei segreti** (solo la prima volta)

   ```bash
   detect-secrets scan > .secrets.baseline
   git add .secrets.baseline
   ```

4. **Installa gli hook nel repo**

   ```bash
   pre-commit install
   ```

5. **Esegui tutti gli hook su tutto il repo (una tantum)**
   ```bash
   pre-commit run --all-files
   ```

---

## Cosa succede durante i commit

Ad ogni `git commit`, gli hook:

- formattano il codice (`black`),
- riordinano gli import (`isort`),
- eseguono linting (`flake8`),
- eseguono il type‑check (`mypy`),
- scansionano la sicurezza (`bandit`),
- controllano segreti (`detect‑secrets`),
- applicano fix di base (whitespace, end‑of‑file, YAML valido).

Se un hook fallisce, **il commit è bloccato** finché i problemi non sono risolti.

---

## Aggiornare le versioni degli hook

```bash
pre-commit autoupdate
# Verifica e committa le modifiche al file .pre-commit-config.yaml
```

---

## Troubleshooting

- **Errore mypy/bandit su WSL/Debian**
  Se i binari non vengono risolti correttamente:

  ```bash
  sudo apt-get update
  sudo apt-get install -y mypy bandit
  ```

  > In alternativa, assicurati che la tua venv sia attiva e che `pip install mypy bandit` sia andato a buon fine.

- **Detect‑secrets fallisce per mancanza baseline**
  Crea (o rigenera) la baseline e versionala:

  ```bash
  detect-secrets scan > .secrets.baseline
  git add .secrets.baseline
  ```

- **Hook troppo lenti la prima volta**
  L’esecuzione iniziale (`pre-commit run --all-files`) è più lenta; dai commit successivi gli hook lavorano **solo sui file modificati**.

---

## Policy di qualità (riassunto)

- Commit **bloccati** se: formatter/lint/type/security/secret non passano.
- **Zero segreti** nei commit (usare baseline e variabili d’ambiente).
- **Logging strutturato** e **nessun side‑effect all’import**.

Per dettagli completi vedi: `CONTRIBUTING.md`.

---
