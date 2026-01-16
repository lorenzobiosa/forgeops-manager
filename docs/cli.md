# Guida CLI

Questa guida elenca i comandi principali e gli esempi per l’uso.

## Menu interattivo

```bash
python -m src.main
```

## GitHub – Actions cache (delete all)

```bash
python -m src.providers.github.cache --owner acme-org --repo my-repo --log-level INFO --log-json
```

## GitHub – Releases (delete all)

```bash
python -m src.providers.github.releases --owner acme-org --repo my-repo --log-level INFO --log-json
```

## GitHub – Packages

Elenco:

```bash
python -m src.providers.github.packages --org acme-org --type container --list --log-json
```

Interattivo:

```bash
python -m src.providers.github.packages --org acme-org --type container
```

## Code Scanning – delete analyses

```bash
python -m src.providers.github.security \
  --repo acme-org/my-repo \
  --mode delete \
  --tools "Trivy,Grype" \
  --log-level INFO --log-json
```

## Code Scanning – dismiss alerts

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

Reason: `false_positive` | `won't_fix` | `used_in_tests`.

## Social Sync

```bash
python -m src.main social-sync \
  --token "$GH_TOKEN" \
  --dry-run \
  --allowlist "octocat,dependabot" \
  --log-level INFO --log-json \
  --page-size 100 \
  --report-out social_sync_report.json
```

---
