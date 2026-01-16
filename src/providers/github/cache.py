# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: cache.py
Descrizione:
    Utility per la gestione della GitHub Actions Cache a livello di repository.
    Fornisce:
      - Funzione per eliminare TUTTE le entries di cache (paginato).
      - Entrypoint CLI con opzioni di logging e risoluzione owner/repo.

Linee guida:
    - Logging strutturato via src.utils.logging (JSON di default).
    - Nessun log di segreti; vengono tracciati solo metadati (id, key).
    - Comportamento robusto: skip di elementi non conformi, errori loggati con
      stack trace ed eccezioni ripropagate al chiamante.

Dipendenze:
    - src.providers.github.api: paginate, gh_delete, owner_repo_or_prompt
    - src.utils.http: GITHUB_API
    - src.utils.logging: get_logger, log_event, setup_logging

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Licenza:
    Questo file è rilasciato secondo i termini della licenza del repository.
===============================================================================
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from utils.http_client import GITHUB_API
from utils.structured_logging import get_logger, log_event, setup_logging

from .api import gh_delete, owner_repo_or_prompt, paginate

__all__ = ["delete_all_actions_cache", "main"]

# Logger di modulo (NON configura nulla all'import;
# viene configurato/ribindato in main() o dal chiamante)
_logger = logging.getLogger(__name__)


def delete_all_actions_cache(owner: Optional[str] = None, repo: Optional[str] = None) -> None:
    """
    Elimina TUTTE le entries della GitHub Actions cache per il repository fornito.

    Argomenti:
        owner: Proprietario/organizzazione GitHub (se None, viene risolto via prompt/fallback).
        repo : Nome del repository GitHub (se None, viene risolto via prompt/fallback).

    Eccezioni:
        RuntimeError o eccezioni propagate da gh_delete in caso di errori HTTP.
    """
    resolved_owner, resolved_repo = owner_repo_or_prompt(owner, repo)
    log_event(
        _logger,
        "actions_cache_cleanup_start",
        {"owner": resolved_owner, "repo": resolved_repo},
    )

    print(
        f"[GitHub] Eliminazione di TUTTE le Actions cache entries per \
            {resolved_owner}/{resolved_repo}…"
    )

    list_url = f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/caches"
    total: int = 0

    for cache in paginate(list_url):
        # Validazione robusta: elementi non dict-like → skip
        if not hasattr(cache, "get"):
            log_event(
                _logger,
                "actions_cache_cleanup_skip",
                {"reason": "elemento non-dict-like", "type": type(cache).__name__},
                level=logging.WARNING,
            )
            continue

        cache_id = cache.get("id")
        cache_key = cache.get("key")

        if cache_id is None:
            log_event(
                _logger,
                "actions_cache_cleanup_skip",
                {"reason": "elemento privo di id", "keys": list(cache.keys())},
                level=logging.WARNING,
            )
            continue

        delete_url = (
            f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/caches/{cache_id}"
        )

        try:
            # `gh_delete` solleva eccezioni in caso di errore HTTP
            gh_delete(delete_url)
            total += 1

            print(f" - eliminato cache_id={cache_id} (key={cache_key})")
            log_event(
                _logger,
                "actions_cache_cleanup_deleted",
                {"cache_id": cache_id, "key": cache_key},
            )
        except Exception as exc:
            # Log con stack e rilancio
            _logger.exception(
                f"Errore eliminando cache_id={cache_id} per {resolved_owner}/{resolved_repo}"
            )
            log_event(
                _logger,
                "actions_cache_cleanup_error",
                {
                    "cache_id": cache_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=logging.ERROR,
            )
            raise

    print(f"Totale cache entries eliminate: {total}")
    log_event(
        _logger,
        "actions_cache_cleanup_complete",
        {"owner": resolved_owner, "repo": resolved_repo, "deleted_total": total},
    )


def main() -> None:
    """
    Entrypoint CLI per eliminare tutte le Actions cache entries.

    Flag:
        --owner      : Proprietario/organizzazione GitHub.
        --repo       : Repository GitHub.
        --log-level  : Livello log [DEBUG|INFO|WARNING|ERROR|CRITICAL].
        --log-json   : Abilita logging JSON.
        --no-log-json: Disabilita logging JSON.
    """
    parser = argparse.ArgumentParser(description="Elimina tutte le GitHub Actions cache entries.")
    parser.add_argument("--owner", type=str, help="Proprietario/organizzazione GitHub")
    parser.add_argument("--repo", type=str, help="Repository GitHub")

    # Opzioni logging (override opzionali)
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Livello di logging",
    )
    parser.add_argument(
        "--log-json",
        dest="log_json",
        action="store_true",
        help="Abilita logging in formato JSON",
    )
    parser.add_argument(
        "--no-log-json",
        dest="log_json",
        action="store_false",
        help="Disabilita logging in formato JSON",
    )
    parser.set_defaults(log_json=None)

    args = parser.parse_args()

    # Configurazione logging idempotente con override CLI (se forniti)
    setup_logging(level=args.log_level, json_mode=args.log_json, console=True)
    # Rebind del logger ora che il logging è configurato
    global _logger
    _logger = get_logger(__name__)

    log_event(_logger, "cli_invocation", {"command": "delete-actions-cache"})

    delete_all_actions_cache(owner=args.owner, repo=args.repo)


if __name__ == "__main__":
    main()
