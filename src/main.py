# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: main.py
Descrizione:
  Entrypoint CLI “enterprise” per operazioni di manutenzione e sincronizzazione
  su provider Git (GitHub/GitLab). Fornisce:
    - Menu interattivo per operazioni (#actions, packages, releases, cache, code scanning).
    - Subcomando dedicato `social-sync` per la funzionalità follow/unfollow,
      con configurazioni caricate da ENV/override (vedi src/utils/config.py).

  Osservabilità:
    - Logging centralizzato via src.utils.logging:
        * JSON strutturato (default) o plain text (LOG_JSON=false).
        * Livello configurabile via LOG_LEVEL / override subcomando.
    - Nessun log di segreti (token).

Linee guida:
  - In ambienti CI/CD (GitHub Actions), usare il subcomando `social-sync` e
    gestire le impostazioni via variabili d’ambiente (vedi src/utils/config.py).
  - In ambienti interattivi, è disponibile il menu testuale.
  - Le operazioni sono idempotenti/tolleranti ai retry quando possibile.

Licenza:
  Questo file è rilasciato secondo i termini della licenza del repository.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Dict, cast

# Provider base e implementazioni
from src.providers.base import Provider

# Operazioni GitHub
from src.providers.github.actions import (
    register_actions,  # registra azioni: pulizia workflow + social-sync
)
from src.providers.github.cache import delete_all_actions_cache
from src.providers.github.packages import interactive_delete_packages
from src.providers.github.releases import delete_all_releases

# Import del Protocol del modulo security per cast tip-safe
from src.providers.github.security import RequestsSessionLike as GHRequestsSessionLike
from src.providers.github.security import clear_vulns

# Social sync (subcomando)
from src.providers.github.social import GitHubSocialService
from src.providers.gitlab.mock import GitLabMockProvider

# Config e logging universali
from src.utils.config import get_social_sync_settings
from src.utils.structured_logging import get_logger, log_event, setup_logging

# Guardrail token & rate-limit (enterprise)
from src.utils.token_guard import TokenScopeError, ensure_github_token_ready

# Logger di modulo (usato dagli helper; il setup avviene in main())
_logger = logging.getLogger(__name__)


# =============================================================================
# Wrapper interattivo per code scanning (retrocompatibilità)
# =============================================================================
def interactive_clear_vulns() -> None:
    """
    Wrapper interattivo per pulizia Code Scanning su GitHub.
    Chiede repo, modalità, strumenti, token e (per dismiss) reason/comment/state.
    """
    print("\n=== GitHub Code Scanning cleanup ===")
    repo = input("Repository (owner/repo): ").strip() or os.environ.get("REPO", "")
    if not repo:
        print("ERROR: repository richiesto (owner/repo).")
        log_event(
            _logger,
            "clear_vulns_input_error",
            {"reason": "repo mancante"},
            level=logging.ERROR,
        )
        return

    mode = input("Mode [delete|dismiss] (default: delete): ").strip().lower() or "delete"
    if mode not in ("delete", "dismiss"):
        print("ERROR: mode deve essere 'delete' o 'dismiss'.")
        log_event(
            _logger,
            "clear_vulns_input_error",
            {"reason": "mode invalido", "mode": mode},
            level=logging.ERROR,
        )
        return

    tools_in = input("Tools CSV (vuoto per tutti) [default: Trivy,Grype]: ").strip()
    tools = "" if tools_in == "" else (tools_in or "Trivy,Grype")

    token_env = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    token_in = input("GitHub token (vuoto per usare env GH_TOKEN/GITHUB_TOKEN): ").strip()
    token = token_in or token_env
    if not token:
        print("ERROR: token mancante. Imposta GH_TOKEN/GITHUB_TOKEN o fornisci un token.")
        log_event(
            _logger,
            "clear_vulns_input_error",
            {"reason": "token mancante"},
            level=logging.ERROR,
        )
        return

    dry_answer = input("Dry-run? [y/N]: ").strip().lower()
    dry_run = dry_answer in ("y", "yes")

    reason = "won't_fix"
    comment = "Bulk reset: issues will reappear if they persist."
    state = "open"

    if mode == "dismiss":
        reason_in = input(
            "Dismiss reason [false_positive|won't_fix|used_in_tests] (default: won't_fix): "
        ).strip()
        reason = reason_in or "won't_fix"
        comment_in = input(
            "Dismiss comment (default: Bulk reset: issues will reappear if they persist.): "
        ).strip()
        comment = comment_in or "Bulk reset: issues will reappear if they persist."
        state_in = input("Alert state to process [open|dismissed|fixed] (default: open): ").strip()
        state = state_in or "open"

    print("\nEsecuzione clear-vulns …")
    print(f"  repo  = {repo}")
    print(f"  mode  = {mode}")
    print(f"  tools = {tools if tools != '' else '(tutti)'}")
    if mode == "dismiss":
        print(f"  reason= {reason}")
        print(f"  state = {state}")
        print(f"  comment: {comment}")
    print(f"  dry-run = {dry_run}")

    try:
        # Validazione token + rate-limit + probe (enterprise)
        # fallisce velocemente se PAT è insufficiente
        session = ensure_github_token_ready(
            token=token,
            required_scopes={"security_events"},
            repo=repo,
            op_name="clear-vulns",
            logger=_logger,
        )
        # Cast al Protocol richiesto da clear_vulns (che usa il proprio RequestsSessionLike)
        gh_session = cast(GHRequestsSessionLike, session)

        log_event(
            _logger,
            "clear_vulns_start",
            {
                "repo": repo,
                "mode": mode,
                "tools": tools or "(tutti)",
                "dry_run": dry_run,
            },
        )
        result = clear_vulns(
            repo=repo,
            mode=mode,
            token=token,  # NON loggato
            tools=tools,
            reason=reason,
            comment=comment,
            state=state,
            dry_run=dry_run,
            session=gh_session,  # iniezione sessione (Protocol compatibile)
        )
        print("\nResult:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        log_event(_logger, "clear_vulns_complete", {"repo": repo, "mode": mode})
    except TokenScopeError as e:
        _logger.error(str(e))
        log_event(
            _logger,
            "clear_vulns_scope_error",
            {"repo": repo, "mode": mode, "error_message": str(e)},
            level=logging.ERROR,
        )
        print(f"\nERROR: {e}")
    except Exception as e:
        print(f"\nERROR: {e}")
        _logger.exception("Errore clear_vulns")
        log_event(
            _logger,
            "clear_vulns_error",
            {
                "repo": repo,
                "mode": mode,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            level=logging.ERROR,
        )


# =============================================================================
# Provider registry (retrocompatibile) + registrazione azioni GitHub
# =============================================================================
class GitHubProvider(Provider):
    def __init__(self) -> None:
        super().__init__("GitHub")

        # Operazioni “classiche” in italiano
        self.register_operation("Elimina packages", interactive_delete_packages)
        self.register_operation("Elimina releases", delete_all_releases)
        self.register_operation("Elimina Actions cache", delete_all_actions_cache)
        self.register_operation("Elimina vulnerabilità Code Scanning", interactive_clear_vulns)

        # Azioni da actions.py (pulizia workflow runs + social-sync)
        register_actions(self)


def providers_registry() -> Dict[str, Provider]:
    return {
        "github": GitHubProvider(),
        "gitlab": GitLabMockProvider(),
    }


# =============================================================================
# Menu interattivo (fallback)
# =============================================================================
def interactive_menu() -> None:
    providers = list(providers_registry().values())
    print("Seleziona un provider:")
    for i, p in enumerate(providers, start=1):
        print(f"[{i}] {p.name}")
    sel = input("Scelta: ").strip() or "1"
    try:
        idx = int(sel) - 1
    except ValueError:
        idx = 0
    idx = max(0, min(idx, len(providers) - 1))
    provider = providers[idx]

    log_event(_logger, "menu_provider_selected", {"provider": provider.name, "index": idx})

    ops = provider.list_operations()
    print(f"\nOperazioni disponibili per {provider.name}:")
    for i, o in enumerate(ops, start=1):
        print(f"[{i}] {o}")
    sel = input("Scelta: ").strip() or "1"
    try:
        idx = int(sel) - 1
    except ValueError:
        idx = 0
    idx = max(0, min(idx, len(ops) - 1))
    op_key = ops[idx]
    print(f"\nEsecuzione: {op_key}\n")

    try:
        provider.run(op_key)
        log_event(
            _logger,
            "menu_operation_executed",
            {"provider": provider.name, "operation": op_key},
        )
    except Exception as exc:
        _logger.exception("Errore durante esecuzione operazione da menu")
        log_event(
            _logger,
            "menu_operation_error",
            {
                "provider": provider.name,
                "operation": op_key,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            level=logging.ERROR,
        )
        print(f"Errore: {exc}")


# =============================================================================
# Subcomando: social-sync (follow/unfollow)
# =============================================================================
def _cmd_social_sync(args: argparse.Namespace) -> int:
    """
    Esegue la sincronizzazione follow/unfollow:
      - Carica impostazioni da ENV (override via CLI).
      - Configura logging universale.
      - Invoca GitHubSocialService con page_size, token.
      - Salva/stampa report strutturato.
    """
    # Carica impostazioni (e configura logging in modo idempotente all'interno)
    settings = get_social_sync_settings(
        github_token=args.token,
        dry_run=args.dry_run,
        allowlist=(args.allowlist.split(",") if args.allowlist else None),
        blocklist=(args.blocklist.split(",") if args.blocklist else None),
        log_json=args.log_json,
        log_level=args.log_level,
        page_size=args.page_size,
    )

    # Logging globale coerente (idempotente, rispetta LOG_LEVEL/LOG_JSON e override)
    setup_logging(level=settings.log_level, json_mode=settings.log_json, console=True)
    local_logger = get_logger("social-sync")

    svc = GitHubSocialService(
        token=settings.github_token,  # NON loggato
        page_size=settings.page_size,
    )

    log_event(
        local_logger,
        "social_sync_start",
        {
            "dry_run": settings.dry_run,
            "allowlist_count": len(settings.allowlist),
            "blocklist_count": len(settings.blocklist),
            "page_size": settings.page_size,
        },
    )

    report = svc.sync_followers(
        dry_run=settings.dry_run,
        allowlist=settings.allowlist,
        blocklist=settings.blocklist,
    )

    # Output report
    out_path = Path(args.report_out).resolve()
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.to_json(), encoding="utf-8")
        log_event(
            local_logger,
            "social_sync_report_written",
            {"path": str(out_path), "bytes": len(report.to_json().encode("utf-8"))},
        )
    except Exception as exc:
        _logger.exception("Errore scrivendo il report JSON di social-sync")
        log_event(
            local_logger,
            "social_sync_report_error",
            {
                "path": str(out_path),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            level=logging.ERROR,
        )
        print(f"Errore scrivendo report su {out_path}: {exc}")
        return 2

    # Stampa breve riassunto su stdout
    print(
        json.dumps(
            {
                "summary": {
                    "dry_run": report.dry_run,
                    "followers": report.followers_count,
                    "following": report.following_count,
                    "to_follow": len(report.to_follow),
                    "to_unfollow": len(report.to_unfollow),
                    "followed": len(report.followed),
                    "unfollowed": len(report.unfollowed),
                    "skipped": len(report.skipped),
                }
            },
            ensure_ascii=False,
        )
    )
    log_event(
        local_logger,
        "social_sync_complete",
        {
            "dry_run": report.dry_run,
            "followed": len(report.followed),
            "unfollowed": len(report.unfollowed),
            "skipped": len(report.skipped),
            "to_follow": len(report.to_follow),
            "to_unfollow": len(report.to_unfollow),
        },
    )
    return 0


# =============================================================================
# Parser CLI
# =============================================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="forgeops-manager",
        description="ForgeOps Manager — toolkit di pulizia e sincronizzazione per forges Git.",
    )
    sub = p.add_subparsers(dest="cmd", required=False)

    # Subcomando: social-sync
    sp = sub.add_parser("social-sync", help="Sincronizza follow/unfollow su GitHub")
    sp.add_argument("--token", type=str, default=None, help="PAT GitHub (override GH_TOKEN)")
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Esegui in dry-run (override SYNC_DRY_RUN)",
    )
    sp.add_argument("--allowlist", type=str, default=None, help="CSV utenti da NON unfolloware")
    sp.add_argument("--blocklist", type=str, default=None, help="CSV utenti da NON followare")
    sp.add_argument(
        "--log-json",
        type=lambda x: x.strip().lower() in ("1", "true", "yes", "y", "on"),
        default=None,
        help="Forza log JSON true/false (override LOG_JSON)",
    )
    sp.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="DEBUG|INFO|WARNING|ERROR|CRITICAL (override LOG_LEVEL)",
    )
    sp.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="per_page API (1..100, override SYNC_PAGE_SIZE)",
    )
    sp.add_argument(
        "--report-out",
        type=str,
        default="social_sync_report.json",
        help="Percorso file report",
    )
    sp.set_defaults(_func=_cmd_social_sync)

    # Opzioni “classiche” (retrocompatibili) per menu/operazioni
    p.add_argument("--provider", choices=["github", "gitlab"], help="Provider da usare")
    p.add_argument(
        "--operation",
        choices=[
            "delete-workflows",
            "delete-packages",
            "delete-releases",
            "delete-cache",
            "clear-vulns",
        ],
        help="Operazione da eseguire (provider-specifica)",
    )
    # Argomenti per clear-vulns (GitHub Code Scanning)
    p.add_argument("--repo", help="owner/repo (richiesto per clear-vulns)")
    p.add_argument(
        "--mode",
        choices=["delete", "dismiss"],
        help="clear-vulns: delete analyses o dismiss alerts",
    )
    p.add_argument(
        "--tools",
        default="Trivy,Grype",
        help="clear-vulns: CSV tools filter (vuoto per tutti)",
    )
    p.add_argument(
        "--reason",
        default="won't_fix",
        help="clear-vulns (dismiss): reason (false_positive|won't_fix|used_in_tests)",
    )
    p.add_argument(
        "--comment",
        default="Bulk reset: issues will reappear if they persist.",
        help="clear-vulns (dismiss): comment",
    )
    p.add_argument(
        "--state",
        default="open",
        help="clear-vulns (dismiss): alert state da processare (open|dismissed|fixed)",
    )
    p.add_argument("--token", help="GitHub token (default ENV GH_TOKEN/GITHUB_TOKEN)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="clear-vulns: stampa azioni senza modificare",
    )

    return p


# =============================================================================
# Main
# =============================================================================
def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Subcomando social-sync: logging su console abilitato (CLI)
    if getattr(args, "cmd", None) == "social-sync":
        setup_logging(level=None, json_mode=None, console=True)
        logger = get_logger(__name__)
        try:
            log_event(logger, "cli_invocation", {"command": "social-sync"})
            # mypy: tipizza il subcommand handler impostato con set_defaults(_func=...)
            func_any = getattr(args, "_func", None)
            if func_any is None:
                logger.error("Handler del subcomando non trovato (_func mancante).")
                return 2
            func = cast(Callable[[argparse.Namespace], int], func_any)
            return func(args)
        except Exception as exc:
            logger.exception("Errore eseguendo subcomando social-sync")
            sys.stderr.write(f"Errore social-sync: {exc}\n")
            return 2

    # Modalità interattiva (menu): silenzia i log su console
    if not args.provider or not args.operation:
        setup_logging(level=None, json_mode=None, console=False)
        logger = get_logger(__name__)
        log_event(logger, "cli_interactive_menu")
        interactive_menu()
        return 0

    # Flusso “classico” CLI: provider + operation (log su console abilitati)
    setup_logging(level=None, json_mode=None, console=True)
    logger = get_logger(__name__)

    registry = providers_registry()
    provider = registry[args.provider]

    # Mappa operation -> etichetta menu del Provider (in italiano)
    op_map = {
        # etichetta da actions.register_actions
        "delete-workflows": "Pulizia workflow runs (COMPLETED)",
        "delete-packages": "Elimina packages",
        "delete-releases": "Elimina releases",
        "delete-cache": "Elimina Actions cache",
        "clear-vulns": "Elimina vulnerabilità Code Scanning",
    }

    if args.operation == "clear-vulns":
        # Chiamata diretta (bypass registry) per mantenere l'interfaccia classica
        if not args.repo or not args.mode:
            msg = "clear-vulns richiede --repo owner/repo e --mode delete|dismiss"
            sys.stderr.write(msg + "\n")
            log_event(
                logger,
                "cli_args_error",
                {"operation": "clear-vulns", "reason": msg},
                level=logging.ERROR,
            )
            return 2

        # Risolvi token da CLI/ENV
        token_value = (
            args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        ).strip()
        if not token_value:
            msg = "Token GitHub mancante. Impostare GH_TOKEN/GITHUB_TOKEN o passare --token."
            sys.stderr.write(msg + "\n")
            log_event(
                logger,
                "cli_args_error",
                {"operation": "clear-vulns", "reason": msg},
                level=logging.ERROR,
            )
            return 2

        print(
            f"Esecuzione clear-vulns (GitHub):\n"
            f"  repo={args.repo}\n"
            f"  mode={args.mode}\n"
            f"  tools={args.tools}\n"
            f"  dry-run={args.dry_run}"
        )
        try:
            # ✅ Guardia enterprise: scopes, rate-limit, probe
            session = ensure_github_token_ready(
                token=token_value,
                required_scopes={"security_events"},
                repo=args.repo,
                op_name="clear-vulns",
                logger=logger,
            )
            # Cast al Protocol del modulo security
            gh_session = cast(GHRequestsSessionLike, session)

            log_event(
                logger,
                "clear_vulns_cli_start",
                {
                    "repo": args.repo,
                    "mode": args.mode,
                    "tools": args.tools,
                    "dry_run": args.dry_run,
                },
            )
            result = clear_vulns(
                repo=args.repo,
                mode=args.mode,
                token=token_value,  # NON loggato
                tools=args.tools,
                reason=args.reason,
                comment=args.comment,
                state=args.state,
                dry_run=args.dry_run,
                session=gh_session,  # iniezione sessione (Protocol compatibile)
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            log_event(
                logger,
                "clear_vulns_cli_complete",
                {"repo": args.repo, "mode": args.mode},
            )
            return 0
        except TokenScopeError as exc:
            logger.error(str(exc))
            log_event(
                logger,
                "clear_vulns_cli_scope_error",
                {"repo": args.repo, "mode": args.mode, "error_message": str(exc)},
                level=logging.ERROR,
            )
            sys.stderr.write(f"Errore: {exc}\n")
            return 2
        except Exception as exc:
            logger.exception("Errore clear-vulns (CLI classico)")
            log_event(
                logger,
                "clear_vulns_cli_error",
                {
                    "repo": args.repo,
                    "mode": args.mode,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=logging.ERROR,
            )
            sys.stderr.write(f"Errore: {exc}\n")
            return 2
    else:
        op_key = op_map[args.operation]
        print(f"Esecuzione {op_key} su {provider.name}…")
        try:
            provider.run(op_key)
            log_event(
                logger,
                "cli_operation_executed",
                {"provider": provider.name, "operation": op_key},
            )
            return 0
        except KeyError as exc:
            logger.exception("Operazione non disponibile")
            log_event(
                logger,
                "cli_operation_missing",
                {
                    "provider": provider.name,
                    "operation": op_key,
                    "error_message": str(exc),
                },
                level=logging.ERROR,
            )
            sys.stderr.write(f"Operazione non disponibile: {op_key}\n")
            return 2
        except Exception as exc:
            logger.exception("Errore durante esecuzione operazione")
            log_event(
                logger,
                "cli_operation_error",
                {
                    "provider": provider.name,
                    "operation": op_key,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=logging.ERROR,
            )
            sys.stderr.write(f"Errore: {exc}\n")
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
