# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: config.py
Descrizione:
    Utilità di configurazione centralizzate per il progetto. Fornisce:
      - Parsing robusto di variabili d'ambiente (bool, liste CSV, interi).
      - Funzioni per recuperare owner/repo e scope (user/org) con fallback da ENV
        e PROMPT opzionali (abilitabili/disabilitabili).
      - Dataclass tipizzate per impostazioni della funzionalità "social sync"
        (follow/unfollow) con caricamento da ENV e override parametrico.
      - Integrazione con il modulo di logging (src.utils.logging):
          * Logging strutturato degli eventi (log_event).
          * Rispetto di LOG_JSON e LOG_LEVEL.
          * Nessun log di segreti (token) o informazioni sensibili.

    Linee guida:
      - In ambienti non interattivi (CI/CD, GitHub Actions) disabilitare i prompt
        (interactive=False) e assicurarsi che le variabili d'ambiente necessarie
        siano definite (es. GH_OWNER, GH_REPO, GH_TOKEN).
      - Non salvare mai segreti nel repository. Usare sempre ENV o Secret manager.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
Licenza:
    Questo file è rilasciato secondo i termini della licenza del repository.
===============================================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Integrazione logging centrale
# NOTE: setup_logging è idempotente; get_logger eredita la configurazione root.
from .structured_logging import get_logger, log_event, setup_logging

# Logger di modulo (configurazione iniziale)
# ulteriori override avvengono in get_social_sync_settings)
_logger = get_logger(__name__)


# =============================================================================
# Helper di parsing ENV (bool, csv, int)
# =============================================================================
def _parse_bool(value: Optional[str], *, default: bool = False) -> bool:
    """
    Converte una stringa in booleano in modo tollerante.
    Accetta: "1", "true", "yes", "y", "on" (True) | "0", "false", "no", "n", "off" (False).
    Ignora maiuscole/minuscole e spazi. Se None o vuoto -> default.
    """
    if value is None:
        return default
    val = value.strip().lower()
    if val in ("1", "true", "yes", "y", "on"):
        return True
    if val in ("0", "false", "no", "n", "off"):
        return False
    # Se non riconosciuto, restituisce default (comportamento permissivo)
    return default


def _parse_csv(value: Optional[str]) -> List[str]:
    """
    Converte una stringa CSV in una lista di stringhe normalizzate (trim).
    Se None o vuoto, restituisce lista vuota.
    """
    if not value:
        return []
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


def _parse_int(
    value: Optional[str],
    *,
    default: int,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    """
    Converte una stringa in intero con default e vincoli opzionali.
    Se parsing fallisce o fuori vincoli, restituisce default.
    """
    if value is None or not value.strip():
        return default
    try:
        num = int(value.strip())
    except ValueError:
        return default
    if min_value is not None and num < min_value:
        return default
    if max_value is not None and num > max_value:
        return default
    return num


# =============================================================================
# Prompt sicuri (opzionalmente disabilitabili per CI/Actions)
# =============================================================================
def _ask_if_missing(value: Optional[str], prompt_label: str, *, interactive: bool) -> str:
    """
    Chiede interattivamente un valore se mancante (solo se interactive=True).
    Ritorna una stringa non vuota o solleva un errore se impossibile ottenere il valore.
    """
    if value and value.strip():
        return value.strip()

    if interactive:
        log_event(
            _logger,
            "prompt_request",
            {"label": prompt_label},
        )
        try:
            val = input(f"{prompt_label}: ").strip()
        except EOFError:
            # Ambiente non interattivo anche se richiesto interactive=True
            log_event(
                _logger,
                "config_error",
                {"reason": "EOFError durante prompt", "label": prompt_label},
                level=40,  # logging.ERROR
            )
            raise RuntimeError(f"{prompt_label} obbligatorio e non fornito.")
        if not val:
            log_event(
                _logger,
                "config_error",
                {"reason": "Valore vuoto durante prompt", "label": prompt_label},
                level=40,
            )
            raise RuntimeError(f"{prompt_label} obbligatorio.")
        return val

    # Non interattivo e valore mancante -> errore esplicito
    log_event(
        _logger,
        "config_error",
        {
            "reason": "Valore mancante in modalità non interattiva",
            "label": prompt_label,
        },
        level=40,
    )
    raise RuntimeError(f"{prompt_label} obbligatorio e non fornito (interactive disabilitato).")


# =============================================================================
# API di configurazione "generiche" (retrocompatibilità migliorata)
# =============================================================================
def get_owner_repo(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    *,
    interactive: bool = True,
) -> Tuple[str, str]:
    """
    Restituisce (owner, repo) da parametri/ENV o chiede via prompt se consentito.

    Precedenze:
      1) Parametri funzione (owner, repo)
      2) ENV: GH_OWNER, GH_REPO
      3) Prompt (solo se interactive=True)

    Args:
        owner: override proprietario/organizzazione.
        repo: override repository.
        interactive: se True consente prompt; se False, solleva errore se mancano.

    Returns:
        (owner, repo) come tuple di stringhe non vuote.

    Raises:
        RuntimeError: se i valori sono mancanti e non si può chiedere via prompt.
    """
    owner_env = owner or os.environ.get("GH_OWNER")
    repo_env = repo or os.environ.get("GH_REPO")

    owner_val = _ask_if_missing(owner_env, "Owner/Org o Username", interactive=interactive)
    repo_val = _ask_if_missing(repo_env, "Repository", interactive=interactive)

    source = (
        "params"
        if owner or repo
        else ("env" if (os.environ.get("GH_OWNER") or os.environ.get("GH_REPO")) else "prompt")
    )

    log_event(
        _logger,
        "owner_repo_resolved",
        {
            "owner": owner_val,
            "repo": repo_val,
            "source": source,
            "interactive": interactive,
        },
    )
    return owner_val, repo_val


def get_username_or_org(
    username: Optional[str] = None,
    org: Optional[str] = None,
    *,
    interactive: bool = True,
) -> Tuple[str, str]:
    """
    Determina lo scope per operazioni (user/org) relativo ai packages o ad altre API.

    Regole:
      - Se `org` è fornito, ritorna ("org", org).
      - Altrimenti, se `username` è fornito, ritorna ("user", username).
      - Se entrambi mancano:
          * In interactive=True: chiede via prompt "Packages scope? [1] Org, [2] User".
          * In interactive=False: prova da ENV GH_OWNER come fallback (assunto come org).
            Se manca, solleva errore.

    Returns:
        Una tupla (scope, name) dove scope ∈ {"user", "org"} e name è la stringa associata.

    Raises:
        RuntimeError: se non è possibile determinare lo scope e non si può chiedere via prompt.
    """
    if org:
        scope = ("org", org)
        log_event(_logger, "scope_resolved", {"scope": "org", "name": org, "source": "params"})
        return scope
    if username:
        scope = ("user", username)
        log_event(
            _logger,
            "scope_resolved",
            {"scope": "user", "name": username, "source": "params"},
        )
        return scope

    env_owner = os.environ.get("GH_OWNER", "").strip()

    if interactive:
        # Prompt scope
        choice = input("Packages scope? [1] Org, [2] User: ").strip() or "1"
        if choice == "1":
            name = input("Organization name: ").strip() or env_owner
            if not name:
                log_event(
                    _logger,
                    "config_error",
                    {"reason": "Organization mancante"},
                    level=40,
                )
                raise RuntimeError("Organization obbligatoria.")
            log_event(
                _logger,
                "scope_resolved",
                {"scope": "org", "name": name, "source": "prompt"},
            )
            return ("org", name)
        else:
            name = input("Username: ").strip() or env_owner
            if not name:
                log_event(_logger, "config_error", {"reason": "Username mancante"}, level=40)
                raise RuntimeError("Username obbligatorio.")
            log_event(
                _logger,
                "scope_resolved",
                {"scope": "user", "name": name, "source": "prompt"},
            )
            return ("user", name)

    # Non interattivo: assumiamo che GH_OWNER rappresenti l'organizzazione per default
    if env_owner:
        log_event(
            _logger,
            "scope_resolved",
            {"scope": "org", "name": env_owner, "source": "env"},
        )
        return ("org", env_owner)

    log_event(
        _logger,
        "config_error",
        {"reason": "Scope non determinabile in modalità non interattiva e GH_OWNER assente"},
        level=40,
    )
    raise RuntimeError(
        "Impossibile determinare lo scope (user/org) in modalità non interattiva: \
            definire GH_OWNER o fornire parametri."
    )


# =============================================================================
# Config per la funzionalità "social sync" (follow/unfollow)
# =============================================================================
# Factory tipizzata per evitare "list[Unknown]" su default_factory
def _list_str_factory() -> List[str]:
    return []


@dataclass(frozen=True)
class SocialSyncSettings:
    """
    Impostazioni tipizzate per il job di sincronizzazione follow/unfollow.

    Provenienza dei valori:
      - Variabili d'ambiente (prefisso suggerito: SYNC_* e GH_*)
      - Override da parametri funzione
    """

    github_token: str
    dry_run: bool = True
    allowlist: List[str] = field(default_factory=_list_str_factory)
    blocklist: List[str] = field(default_factory=_list_str_factory)
    log_json: bool = True
    log_level: str = "INFO"
    page_size: int = 100  # per_page per le API (1..100)

    def __post_init__(self) -> None:
        # Validazioni: token obbligatorio, page_size entro limiti
        token = self.github_token.strip()
        if not token:
            raise ValueError("github_token obbligatorio e non può essere vuoto.")
        if not (1 <= self.page_size <= 100):
            raise ValueError("page_size deve essere compreso tra 1 e 100.")


def get_social_sync_settings(
    *,
    github_token: Optional[str] = None,
    dry_run: Optional[bool] = None,
    allowlist: Optional[List[str]] = None,
    blocklist: Optional[List[str]] = None,
    log_json: Optional[bool] = None,
    log_level: Optional[str] = None,
    page_size: Optional[int] = None,
) -> SocialSyncSettings:
    """
    Costruisce le impostazioni per il job di social sync aggregando ENV e override.

    ENV supportate:
      - GH_TOKEN               : token GitHub (obbligatorio) con scope `user:follow`.
      - SYNC_DRY_RUN           : "true"/"false" (default: true).
      - SYNC_ALLOWLIST         : CSV utenti da non UNFOLLOWARE.
      - SYNC_BLOCKLIST         : CSV utenti da non FOLLOWARE.
      - LOG_JSON               : "true"/"false" (default: true).
      - LOG_LEVEL              : livello log (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: INFO.
      - SYNC_PAGE_SIZE         : intero tra 1 e 100. Default: 100.

    Args:
        github_token: override token, se non fornito usa GH_TOKEN.
        dry_run: override dry-run, se non fornito usa SYNC_DRY_RUN.
        allowlist: override allowlist, se non fornito usa SYNC_ALLOWLIST (CSV).
        blocklist: override blocklist, se non fornito usa SYNC_BLOCKLIST (CSV).
        log_json: override LOG_JSON.
        log_level: override LOG_LEVEL.
        page_size: override SYNC_PAGE_SIZE (1..100).

    Returns:
        SocialSyncSettings validato.

    Raises:
        ValueError: se token mancante o valori fuori dai vincoli (page_size).
    """

    # Evita conflitti di tipo con Mypy: dichiara esplicitamente Optional[str]
    _token_raw: Optional[str]
    if github_token is not None:
        _token_raw = github_token
    else:
        _token_raw = os.environ.get("GH_TOKEN")
    env_token = (_token_raw or "").strip()
    if not env_token:
        log_event(
            _logger,
            "config_error",
            {"reason": "GH_TOKEN mancante"},
            level=40,
        )
        raise ValueError("GH_TOKEN obbligatorio e non definito.")

    env_dry_run = (
        dry_run
        if dry_run is not None
        else _parse_bool(os.environ.get("SYNC_DRY_RUN"), default=True)
    )

    # Liste: override se fornito, altrimenti da CSV ENV
    env_allowlist = (
        allowlist if allowlist is not None else _parse_csv(os.environ.get("SYNC_ALLOWLIST"))
    )
    env_blocklist = (
        blocklist if blocklist is not None else _parse_csv(os.environ.get("SYNC_BLOCKLIST"))
    )

    env_log_json = (
        log_json if log_json is not None else _parse_bool(os.environ.get("LOG_JSON"), default=True)
    )
    # Evita conflitti di tipo con Mypy: dichiara esplicitamente Optional[str]
    _log_level_raw: Optional[str]
    if log_level is not None:
        _log_level_raw = log_level
    else:
        _log_level_raw = os.environ.get("LOG_LEVEL")
    # Se assente, default "INFO"
    env_log_level = ((_log_level_raw or "INFO").strip().upper()) or "INFO"

    env_page_size = (
        page_size
        if page_size is not None
        else _parse_int(
            os.environ.get("SYNC_PAGE_SIZE"),
            default=100,
            min_value=1,
            max_value=100,
        )
    )

    # Normalizzazione livelli supportati
    if env_log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        # Se non valido, ripristina a INFO
        log_event(
            _logger,
            "log_level_normalized",
            {"invalid_level": env_log_level, "normalized_to": "INFO"},
        )
        env_log_level = "INFO"

    # Configurazione (idempotente) del logging di processo con i valori risolti
    # Nota: se il logging è già configurato, questa chiamata non lo riconfigurerà.
    setup_logging(level=env_log_level, json_mode=env_log_json)

    # Aggiorna livello del logger di modulo secondo preferenza (senza toccare root se già impostato)
    # get_logger eredita la configurazione; qui impostiamo il livello specifico di questo modulo.
    module_logger = get_logger(__name__, level=env_log_level)

    # Log degli input (senza segreti)
    log_event(
        module_logger,
        "social_sync_settings_input",
        {
            "dry_run": env_dry_run,
            "allowlist_count": len(env_allowlist or []),
            "blocklist_count": len(env_blocklist or []),
            "log_json": env_log_json,
            "log_level": env_log_level,
            "page_size": env_page_size,
            "github_token_present": bool(env_token),
        },
    )

    settings = SocialSyncSettings(
        github_token=env_token,
        dry_run=env_dry_run,
        allowlist=list(env_allowlist),
        blocklist=list(env_blocklist),
        log_json=env_log_json,
        log_level=env_log_level,
        page_size=env_page_size,
    )

    # Log delle impostazioni finali (sanitizzate)
    log_event(
        module_logger,
        "social_sync_settings_built",
        {
            "dry_run": settings.dry_run,
            "allowlist_count": len(settings.allowlist),
            "blocklist_count": len(settings.blocklist),
            "log_json": settings.log_json,
            "log_level": settings.log_level,
            "page_size": settings.page_size,
            "github_token_present": True,  # non logghiamo il token
        },
    )

    return settings
