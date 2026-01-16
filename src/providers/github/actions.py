# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: actions.py
Descrizione:
    Utility per la gestione delle GitHub Actions a livello di repository e
    per la sincronizzazione social (follow/unfollow) basata su regole.

    Funzionalità:
      - Eliminazione TUTTE le workflow runs in stato COMPLETED (paginato).
      - Sincronizzazione social (follow/unfollow) con dry-run, allowlist, blocklist.
      - Entrypoint CLI con sottocomandi.
      - Registrazione operazioni nel menu tramite Provider.

Dipendenze:
    - src.providers.github.api: paginate, gh_delete, owner_repo_or_prompt
    - src.utils.http: GITHUB_API
    - src.utils.logging: get_logger, log_event, setup_logging
    - src.providers.base: Provider (per registrazione voci di menu)
    - src.providers.github.social: GitHubSocialService
    - src.utils.config: get_social_sync_settings

Linee guida:
    - Le API sono chiamate in modo paginato e idempotente quando possibile.
    - Tipizzazione esplicita e conformità Pylance.
    - CLI con sottocomandi: delete-completed-runs | social-sync.
    - Nessun log di segreti (token) o payload eccessivi.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Licenza:
    Questo file è rilasciato secondo i termini della licenza del repository.
===============================================================================
"""

from __future__ import annotations

import argparse
from typing import Optional

from src.utils.config import get_social_sync_settings
from src.utils.http_client import GITHUB_API
from src.utils.structured_logging import get_logger, log_event, setup_logging

from ..base import Provider
from .api import gh_delete, owner_repo_or_prompt, paginate
from .social import GitHubSocialService

__all__ = [
    "delete_all_completed_workflow_runs",
    "run_social_sync",
    "register_actions",
    "main",
]

# Logger di modulo (eredita configurazione root; override possibile in main())
_logger = get_logger(__name__)


# =============================================================================
# Azione: eliminazione workflow runs COMPLETED
# =============================================================================
def delete_all_completed_workflow_runs(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
) -> None:
    """
    Elimina tutte le workflow runs di GitHub Actions in stato COMPLETED
    per il repository indicato.

    Argomenti:
        owner: Proprietario/organizzazione GitHub (se None, viene risolto via prompt/fallback).
        repo: Nome del repository GitHub (se None, viene risolto via prompt/fallback).

    Eccezioni:
        RuntimeError o eccezioni propagate da gh_delete in caso di errori HTTP.
    """
    resolved_owner, resolved_repo = owner_repo_or_prompt(owner, repo)
    log_event(
        _logger,
        "actions_cleanup_start",
        {"owner": resolved_owner, "repo": resolved_repo},
    )

    list_url = f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/runs"
    total: int = 0

    # Paginazione dei risultati filtrando per status=completed
    for run in paginate(list_url, params={"status": "completed"}):
        run_id = run.get("id")
        if run_id is None:
            # Salta in modo robusto se l'elemento non è conforme
            log_event(
                _logger,
                "actions_cleanup_skip",
                {"reason": "run privo di id"},
                level=30,  # WARNING
            )
            continue

        delete_url = f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/runs/{run_id}"

        try:
            # `gh_delete` solleva eccezioni in caso di errore HTTP
            gh_delete(delete_url)
            total += 1
            log_event(
                _logger,
                "actions_cleanup_run_deleted",
                {"run_id": run_id},
            )
        except Exception as exc:
            # Log dell'errore e rilancio
            _logger.exception(
                f"Errore eliminando run_id={run_id} per {resolved_owner}/{resolved_repo}"
            )
            log_event(
                _logger,
                "actions_cleanup_error",
                {
                    "run_id": run_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=40,  # ERROR
            )
            raise

    log_event(
        _logger,
        "actions_cleanup_complete",
        {"owner": resolved_owner, "repo": resolved_repo, "deleted_total": total},
    )


# =============================================================================
# Azione: social sync (follow/unfollow)
# =============================================================================
def run_social_sync(
    *,
    dry_run: Optional[bool] = None,
    allowlist_csv: Optional[str] = None,
    blocklist_csv: Optional[str] = None,
    page_size: Optional[int] = None,
    report_json_path: Optional[str] = None,
) -> None:
    """
    Esegue la sincronizzazione social (follow/unfollow) su GitHub.

    Parametri (override opzionali; se non forniti, usa ENV):
        dry_run: True/False. Default: da ENV SYNC_DRY_RUN (True se non definito).
        allowlist_csv: CSV utenti da non UNFOLLOWARE. ENV: SYNC_ALLOWLIST.
        blocklist_csv: CSV utenti da non FOLLOWARE. ENV: SYNC_BLOCKLIST.
        page_size: dimensione pagina API (1..100). ENV: SYNC_PAGE_SIZE (default 100).
        report_json_path: percorso facoltativo per salvare il report JSON.

    ENV richieste:
        GH_TOKEN (obbligatorio, scope: user:follow)

    Eccezioni:
        ValueError o GitHubAPIError in caso di configurazioni o chiamate fallite.
    """
    # Costruzione impostazioni aggregando ENV + override
    settings = get_social_sync_settings(
        dry_run=dry_run,
        allowlist=(allowlist_csv.split(",") if allowlist_csv else None),
        blocklist=(blocklist_csv.split(",") if blocklist_csv else None),
        page_size=page_size,
    )

    # Logger modulo già configurato; log evento di start (senza segreti)
    log_event(
        _logger,
        "social_sync_start",
        {
            "dry_run": settings.dry_run,
            "allowlist_count": len(settings.allowlist),
            "blocklist_count": len(settings.blocklist),
            "page_size": settings.page_size,
        },
    )

    # Istanzia servizio con token (non loggato)
    service = GitHubSocialService(
        token=settings.github_token,
        page_size=settings.page_size,
    )

    # Esecuzione sincronizzazione
    report = service.sync_followers(
        dry_run=settings.dry_run,
        allowlist=settings.allowlist,
        blocklist=settings.blocklist,
    )

    # Output opzionale del report su file
    if report_json_path:
        try:
            with open(report_json_path, "w", encoding="utf-8") as f:
                f.write(report.to_json())
            log_event(
                _logger,
                "social_sync_report_written",
                {
                    "path": report_json_path,
                    "bytes": len(report.to_json().encode("utf-8")),
                },
            )
        except Exception as exc:
            _logger.exception(f"Errore scrivendo report JSON su {report_json_path}")
            log_event(
                _logger,
                "social_sync_report_error",
                {
                    "path": report_json_path,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=40,
            )
            raise

    # Log di completamento
    log_event(
        _logger,
        "social_sync_complete",
        {
            "dry_run": settings.dry_run,
            "followed": len(report.followed),
            "unfollowed": len(report.unfollowed),
            "skipped": len(report.skipped),
            "to_follow": len(report.to_follow),
            "to_unfollow": len(report.to_unfollow),
        },
    )


# =============================================================================
# Registrazione voci di menu nel Provider
# =============================================================================
def register_actions(provider: Provider) -> None:
    """
    Registra le azioni GitHub nel menu del Provider.

    Voci:
      - "Pulizia workflow runs" -> delete_all_completed_workflow_runs
      - "Sincronizzazione social" -> run_social_sync (non-dry-run)
    """
    provider.register_operation(
        "Pulizia workflow runs",
        lambda: delete_all_completed_workflow_runs(),
    )
    # 🔧 Forziamo esecuzione **senza dry-run** quando avviato dal menu
    provider.register_operation(
        "Sincronizzazione social",
        lambda: run_social_sync(dry_run=False),
    )
    log_event(
        _logger,
        "provider_actions_registered",
        {"provider": provider.name, "operations_count": len(provider.operations)},
    )


# =============================================================================
# CLI
# =============================================================================
def main() -> None:
    """
    Entrypoint CLI.

    Sottocomandi:
      - delete-completed-runs: Elimina tutte le workflow runs in stato COMPLETED.
          --owner: Proprietario/organizzazione GitHub.
          --repo: Repository GitHub.

      - social-sync: Esegue la sincronizzazione social (follow/unfollow).
          --dry-run / --no-dry-run: Abilita/Disabilita dry-run (default: ENV o True).
          --allowlist: CSV utenti da non UNFOLLOWARE.
          --blocklist: CSV utenti da non FOLLOWARE.
          --page-size: per_page (1..100).
          --report-json: Percorso per salvare il report JSON.

    Opzioni logging:
      --log-level: Livello log [DEBUG|INFO|WARNING|ERROR|CRITICAL].
      --log-json / --no-log-json: Abilita/Disabilita formattazione JSON.
    """
    parser = argparse.ArgumentParser(
        description="Utility GitHub Actions e sincronizzazione social."
    )

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

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: delete-completed-runs
    p_delete = subparsers.add_parser(
        "delete-completed-runs",
        help="Elimina tutte le workflow runs in stato COMPLETED per un repository.",
    )
    p_delete.add_argument("--owner", type=str, help="Proprietario/organizzazione GitHub")
    p_delete.add_argument("--repo", type=str, help="Repository GitHub")

    # Subcommand: social-sync
    p_sync = subparsers.add_parser(
        "social-sync",
        help="Esegue la sincronizzazione social.",
    )
    # Dry-run toggle
    dry_run_group = p_sync.add_mutually_exclusive_group()
    dry_run_group.add_argument(
        "--dry-run", dest="dry_run", action="store_true", help="Abilita dry-run"
    )
    dry_run_group.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false", help="Disabilita dry-run"
    )
    p_sync.set_defaults(dry_run=None)

    p_sync.add_argument("--allowlist", type=str, help="CSV utenti da non UNFOLLOWARE")
    p_sync.add_argument("--blocklist", type=str, help="CSV utenti da non FOLLOWARE")
    p_sync.add_argument("--page-size", type=int, help="Dimensione pagina API (1..100)")
    p_sync.add_argument("--report-json", type=str, help="Percorso file per salvare il report JSON")

    args = parser.parse_args()

    # Configurazione logging idempotente con override CLI (se forniti)
    setup_logging(level=args.log_level, json_mode=args.log_json)

    log_event(
        _logger,
        "cli_invocation",
        {"command": args.command},
    )

    if args.command == "delete-completed-runs":
        delete_all_completed_workflow_runs(owner=args.owner, repo=args.repo)
    elif args.command == "social-sync":
        run_social_sync(
            dry_run=args.dry_run,
            allowlist_csv=args.allowlist,
            blocklist_csv=args.blocklist,
            page_size=args.page_size,
            report_json_path=args.report_json,
        )
    else:
        # Non dovrebbe accadere per via di required=True
        log_event(_logger, "cli_unknown_command", {"command": str(args.command)}, level=40)
        parser.print_help()


if __name__ == "__main__":
    main()
