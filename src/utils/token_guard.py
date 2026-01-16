# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: token_guard.py
Descrizione:
  Validazione e preparazione del token GitHub (PAT/GITHUB_TOKEN) prima
  dell'esecuzione di operazioni:
    - verifica degli scope minimi richiesti,
    - controllo del rate-limit con eventuale attesa fino al reset,
    - probe READ-only su endpoint pertinenti (facoltativa) per segnalare
      carenza permessi in modo precoce.
  Fornisce inoltre un decorator `@requires_github_scopes` per proteggere
  funzioni operative, costruendo una sessione autenticata pronta e
  verificando le condizioni precedenti.

Note di implementazione:
  - Per evitare warning Pylance quando l'editor non ha il pacchetto
    `requests`, non lo importiamo a livello di modulo; usiamo un import
    dinamico dentro `_build_session`. Per i tipi adottiamo dei Protocol
    (`RequestsSessionLike`, `ResponseLike`).
  - I payload del rate-limit sono tipizzati con `TypedDict` e cast,
    in modo da evitare tipi parzialmente ignoti.
"""

from __future__ import annotations

import functools
import importlib
import logging
import time
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    MutableMapping,
    Optional,
    ParamSpec,
    Protocol,
    Set,
    TypedDict,
    TypeVar,
    cast,
)

from .http_client import GITHUB_API
from .structured_logging import log_event


# -----------------------------------------------------------------------------
# Tipi (Protocol per evitare dipendenze di typing da `requests`)
# -----------------------------------------------------------------------------
class ResponseLike(Protocol):
    """Minimo set di attributi/metodi di una response `requests.Response`."""

    headers: Mapping[str, str]
    status_code: int
    text: str

    def json(self) -> Any:  # può sollevare eccezioni se il body non è JSON
        ...


class RequestsSessionLike(Protocol):
    """Minimo set di attributi/metodi di una `requests.Session`."""

    headers: MutableMapping[str, str]

    def get(self, url: str, params: Optional[Mapping[str, Any]] = None) -> ResponseLike:
        raise NotImplementedError


# -----------------------------------------------------------------------------
# Rate-limit payload tipizzato per evitare `Unknown`
# -----------------------------------------------------------------------------
class RateLimitCore(TypedDict, total=False):
    remaining: int
    reset: int


class RateLimitResources(TypedDict, total=False):
    core: RateLimitCore


class RateLimitPayload(TypedDict, total=False):
    resources: RateLimitResources


# -----------------------------------------------------------------------------
# Errori specifici
# -----------------------------------------------------------------------------
class TokenScopeError(PermissionError):
    """Sollevata quando il PAT non ha gli scope richiesti."""


# -----------------------------------------------------------------------------
# Costruzione sessione autenticata
# -----------------------------------------------------------------------------
def _build_session(token: str) -> RequestsSessionLike:
    """
    Costruisce una sessione HTTP autenticata (compatibile con `requests.Session`).
    Usa import dinamico di `requests` per evitare warning Pylance in ambienti
    che non lo hanno installato.
    """
    if not token:
        raise ValueError(
            "Token GitHub mancante. Impostare GH_TOKEN/GITHUB_TOKEN o passarlo via CLI."
        )

    try:
        requests = importlib.import_module("requests")
    except Exception as e:
        raise RuntimeError(
            "Il modulo 'requests' è necessario a runtime per creare la sessione HTTP. "
            "Installa 'requests' (pip install requests)."
        ) from e

    s: RequestsSessionLike = requests.Session()
    s.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "forgeops-manager/token-guard",
        }
    )
    return s


def _fetch_token_scopes(session: RequestsSessionLike) -> Set[str]:
    """
    Recupera gli scope del token da 'X-OAuth-Scopes' effettuando GET /user.
    Per GH Actions (GITHUB_TOKEN) spesso è vuoto -> si logga warning e si prosegue.
    """
    resp = session.get(f"{GITHUB_API}/user")
    scopes_hdr = resp.headers.get("X-OAuth-Scopes", "") or ""
    scopes = {s.strip() for s in scopes_hdr.split(",") if s.strip()}
    return scopes


# -----------------------------------------------------------------------------
# Mappature operative -> scope / endpoint probe
# -----------------------------------------------------------------------------
REQUIRED_SCOPES_BY_OP: Dict[str, Set[str]] = {
    # Repo-scoped operazioni
    "releases": {"repo"},
    "cache": {"repo"},  # PAT: 'repo' basta; in GH Actions usa permissions: actions: write
    "workflow-runs": {"repo", "workflow"},
    "packages-list": {"read:packages"},
    "packages-delete": {"delete:packages"},
    # Security / Code Scanning
    "clear-vulns": {"security_events"},  # PAT: 'security_events'
}

# Usa {repo} e {org} come placeholder
PROBE_ENDPOINT_BY_OP: Dict[str, str] = {
    "releases": "/repos/{repo}/releases?per_page=1",
    "cache": "/repos/{repo}/actions/caches?per_page=1",
    "workflow-runs": "/repos/{repo}/actions/runs?per_page=1",
    "clear-vulns": "/repos/{repo}/code-scanning/alerts?per_page=1",
    "packages-list": "/orgs/{org}/packages?per_page=1",
    "packages-delete": "/orgs/{org}/packages?per_page=1",
}


# -----------------------------------------------------------------------------
# Validazione scope
# -----------------------------------------------------------------------------
def _validate_scopes(
    token_scopes: Set[str], required_scopes: Set[str], logger: Optional[logging.Logger] = None
) -> None:
    if not required_scopes:
        return
    if not token_scopes:
        # GITHUB_TOKEN in Actions (scopes non esposti) o token non valido.
        if logger:
            log_event(
                logger,
                "token_scopes_unavailable",
                {
                    "info": (
                        "Header X-OAuth-Scopes vuoto; PAT non valido o GITHUB_TOKEN "
                        "(verificare 'permissions:' nel workflow)."
                    )
                },
                level=logging.WARNING,
            )
        return

    missing = {req for req in required_scopes if req not in token_scopes}
    if missing:
        if logger:
            log_event(
                logger,
                "token_scopes_invalid",
                {"missing": sorted(missing), "present": sorted(token_scopes)},
                level=logging.ERROR,
            )
        raise TokenScopeError(
            f"Token privo degli scope richiesti: {', '.join(sorted(missing))}. "
            f"Scope presenti: {', '.join(sorted(token_scopes))}."
        )


# -----------------------------------------------------------------------------
# Rate-limit (attesa eventuale fino a reset)
# -----------------------------------------------------------------------------
def _await_rate_limit_if_needed(
    session: RequestsSessionLike, logger: Optional[logging.Logger] = None
) -> None:
    try:
        r = session.get(f"{GITHUB_API}/rate_limit")
        content_type = r.headers.get("Content-Type", "") or ""

        # Inizializza payload con tipo noto in entrambi i rami
        if content_type.startswith("application/json"):
            body = r.json()
            if isinstance(body, dict):
                payload: RateLimitPayload = cast(RateLimitPayload, body)
            else:
                payload = {"resources": {}}
        else:
            payload = {"resources": {}}
    except Exception as e:
        if logger:
            log_event(logger, "rate_limit_probe_error", {"error": str(e)}, level=logging.WARNING)
        return

    resources = payload.get("resources", {})
    core = resources.get("core", {})
    remaining = int(core.get("remaining", 1) or 1)
    reset = int(core.get("reset", 0) or 0)

    if remaining <= 0 and reset > 0:
        now = int(time.time())
        wait_seconds = max(0, reset - now) + 1
        if logger:
            log_event(
                logger,
                "rate_limit_wait_start",
                {"wait_seconds": wait_seconds, "reset_epoch": reset},
            )
        time.sleep(wait_seconds)
        if logger:
            log_event(
                logger,
                "rate_limit_wait_complete",
                {"wait_seconds": wait_seconds, "reset_epoch": reset},
            )


# -----------------------------------------------------------------------------
# Probe permessi READ-only
# -----------------------------------------------------------------------------
def _probe_permissions(
    session: RequestsSessionLike,
    op_name: str,
    repo: Optional[str],
    org: Optional[str],
    logger: Optional[logging.Logger],
) -> None:
    """
    Effettua una chiamata READ-only a un endpoint correlato all'operazione per
    intercettare 403/404 in modo precoce e loggare un messaggio chiaro.
    Non blocca, ma aiuta a fallire velocemente prima di eseguire operazioni mass-delete.
    """
    tpl = PROBE_ENDPOINT_BY_OP.get(op_name)
    if not tpl:
        return
    if "{repo}" in tpl and not repo:
        return
    if "{org}" in tpl and not org:
        return

    path = tpl.format(repo=repo or "", org=org or "")
    url = f"{GITHUB_API}{path}"
    try:
        r = session.get(url, params={"per_page": 1})
    except Exception as e:
        if logger:
            log_event(
                logger,
                "token_probe_error",
                {"op": op_name, "url": url, "error": str(e)},
                level=logging.WARNING,
            )
        return

    if r.status_code == 403:
        # Permesso insufficiente -> log esplicito
        if logger:
            log_event(
                logger,
                "token_permission_denied",
                {
                    "op": op_name,
                    "url": url,
                    "status": 403,
                    "hint": "Verificare PAT scopes o permissions nel workflow GH Actions.",
                },
                level=logging.ERROR,
            )
        # Non solleviamo: lasciare che le operazioni operative gestiscano l'errore
    elif r.status_code >= 400:
        if logger:
            log_event(
                logger,
                "token_probe_http_error",
                {"op": op_name, "url": url, "status": r.status_code, "text": r.text[:200]},
                level=logging.WARNING,
            )


# -----------------------------------------------------------------------------
# API principale: costruzione/validazione sessione
# -----------------------------------------------------------------------------
def ensure_github_token_ready(
    token: str,
    required_scopes: Optional[Set[str]] = None,
    *,
    repo: Optional[str] = None,
    org: Optional[str] = None,
    op_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> RequestsSessionLike:
    """
    Crea una sessione autenticata, valida gli scope (se disponibili), esegue
    attesa rate-limit e (opzionale) probe autorizzativa.
    Ritorna la sessione pronta da riutilizzare nelle chiamate HTTP.
    """
    session = _build_session(token)
    token_scopes = _fetch_token_scopes(session)
    _validate_scopes(token_scopes, required_scopes or set(), logger=logger)
    _await_rate_limit_if_needed(session, logger=logger)
    if op_name:
        _probe_permissions(session, op_name=op_name, repo=repo, org=org, logger=logger)
    return session


# -----------------------------------------------------------------------------
# Decorator per proteggere funzioni operative
# -----------------------------------------------------------------------------
P = ParamSpec("P")
R = TypeVar("R")


def requires_github_scopes(
    op_name: str, *, repo: Optional[str] = None, org: Optional[str] = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator factory per proteggere funzioni operative.
    Prima dell'esecuzione:
      - costruisce sessione,
      - valida scopes (se PAT),
      - attende rate-limit,
      - effettua probe autorizzativa READ-only.

    La funzione decorata deve accettare argomenti 'token' e 'logger'
    (o recuperarli dal contesto).
    """
    req_scopes = REQUIRED_SCOPES_BY_OP.get(op_name, {"repo"})

    def _decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            token_val = kwargs.get("token") or kwargs.get("github_token") or ""
            token: str = str(token_val)  # garantisce tipo str
            logger: Optional[logging.Logger] = cast(Optional[logging.Logger], kwargs.get("logger"))

            if not token:
                raise ValueError(
                    "Token GitHub mancante. Impostare GH_TOKEN/GITHUB_TOKEN o passarlo via CLI."
                )

            session = ensure_github_token_ready(
                token=token,
                required_scopes=req_scopes,
                repo=repo,
                org=org,
                op_name=op_name,
                logger=logger,
            )
            # Passa la sessione alla funzione chiamata
            kwargs["session"] = session
            return func(*args, **kwargs)

        return _wrapper

    return _decorator
