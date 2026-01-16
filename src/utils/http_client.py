# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: http.py
Descrizione:
    Utilità HTTP enterprise per integrazione con le API di GitHub (e generiche).
    Fornisce:
      - Gestione centralizzata di sessioni `requests.Session` con caching per token.
      - Creazione header GitHub standard (Accept, Api-Version, Authorization).
      - Timeout (connect/read), retry con backoff esponenziale, gestione rate-limit.
      - Funzioni comode per GET/DELETE e una `request` generica.
      - Logging universale (JSON) per osservabilità coerente.

    Sicurezza:
      - Non salvare token in chiaro; usare variabili d'ambiente o Secret manager.
      - Variabili ENV supportate per token: GH_TOKEN (prioritaria), GITHUB_TOKEN.

    Note:
      - Le chiamate REST rispettano i limiti di rate GitHub:
        se `X-RateLimit-Remaining = 0`, attende fino a `X-RateLimit-Reset`.
      - Il modulo non lancia eccezioni custom; espone `requests.Response`. Error handling
        avanzato (raise per status, ecc.) è demandato ai layer chiamanti.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
Licenza:
    Vedi LICENSE alla radice del repository.
===============================================================================
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Mapping, Optional, Set, Tuple

import requests

from .structured_logging import get_logger, log_event

# =============================================================================
# Costanti e configurazione base
# =============================================================================

GITHUB_API: str = "https://api.github.com"

DEFAULT_HEADERS: Dict[str, str] = {
    "Accept": "application/vnd.github+json",
    # Versione API “storica” e compatibile; può essere sovrascritta da header extra
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "BiosaLabs-ForgeOpsManager/1.0",
}

# Timeout (connect, read) in secondi
DEFAULT_TIMEOUT: Tuple[float, float] = (10.0, 30.0)

# Retry/backoff
RETRYABLE_STATUS: Set[int] = {429, 500, 502, 503, 504}
MAX_RETRIES: int = 5
BACKOFF_BASE_SECONDS: float = 0.5
BACKOFF_MAX_SECONDS: float = 30.0

# Header rate-limit GitHub
HDR_RATE_REMAINING = "X-RateLimit-Remaining"
HDR_RATE_RESET = "X-RateLimit-Reset"

# Cache sessioni per token (riuso connessioni)
_sessions_by_token: Dict[str, requests.Session] = {}

_logger = get_logger(__name__)


# =============================================================================
# Utility token e header
# =============================================================================


def gh_token_from_env() -> str:
    """
    Recupera il token GitHub da variabili d'ambiente, con priorità:
      1) GH_TOKEN
      2) GITHUB_TOKEN
    Solleva RuntimeError se non disponibile.
    """
    token = (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Token GitHub mancante. Imposta GH_TOKEN (o GITHUB_TOKEN).")
    return token


def build_github_headers(
    *,
    token: Optional[str] = None,
    extra: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """
    Costruisce gli header standard per GitHub API, includendo Authorization.

    Args:
        token: PAT/fine-grained token. Se None, legge da ENV (gh_token_from_env).
        extra: header extra da unire (sovrascrive quelli di default in caso di conflitto).

    Returns:
        Dizionario di header pronto per `requests`.
    """
    tkn = (token or gh_token_from_env()).strip()
    headers: Dict[str, str] = dict(DEFAULT_HEADERS)
    # Nota: i PAT moderni accettano "token" e "Bearer"; preferiamo Bearer.
    headers["Authorization"] = f"Bearer {tkn}"
    if extra:
        headers.update(extra)
    return headers


# =============================================================================
# Gestione sessioni
# =============================================================================


def get_session_for_token(token: Optional[str] = None) -> requests.Session:
    """
    Restituisce una `requests.Session` associata al token (cache per riuso connessioni).
    Se `token` è None, usa il token da ENV.

    Returns:
        requests.Session con header minimi impostati (Accept/User-Agent).
        L'header Authorization viene gestito a livello di richiesta per permettere
        override puntuali (se necessario).
    """
    # Usiamo il token come chiave di cache solo se disponibile (stringa non vuota).
    tkn = (token or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    key = tkn if tkn else "__no_token__"

    sess = _sessions_by_token.get(key)
    if sess is not None:
        return sess

    sess = requests.Session()
    # Impostiamo header “stabili”. Authorization verrà aggiunto per richiesta.
    sess.headers.update(
        {
            "Accept": DEFAULT_HEADERS["Accept"],
            "X-GitHub-Api-Version": DEFAULT_HEADERS["X-GitHub-Api-Version"],
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
        }
    )
    _sessions_by_token[key] = sess
    return sess


# =============================================================================
# Richiesta con retry/backoff e gestione rate-limit
# =============================================================================


def request(
    method: str,
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    json: Optional[Any] = None,
    data: Optional[Any] = None,
    headers: Optional[Mapping[str, str]] = None,
    token: Optional[str] = None,
    timeout: Optional[Tuple[float, float]] = None,
    expected_status: Optional[Set[int]] = None,
    session: Optional[requests.Session] = None,
) -> requests.Response:
    """
    Esegue una richiesta HTTP con:
      - Header GitHub standard + Authorization da token (ENV o esplicito).
      - Timeout di default (connect/read).
      - Retry su status transitori (429/5xx) con backoff esponenziale.
      - Attesa fino al reset rate-limit se `Remaining=0`.

    Args:
        method: verbo HTTP (GET/POST/PUT/PATCH/DELETE).
        url: URL assoluto (usa `build_github_url` per percorsi relativi).
        params: query string (facoltativa).
        json: payload JSON (facoltativo).
        data: payload form/bytes (facoltativo).
        headers: header extra/override.
        token: token GitHub (se None, legge da ENV).
        timeout: (connect, read). Default: DEFAULT_TIMEOUT.
        expected_status: set di status considerati “ok”. Default: {200, 201, 202, 204}.
        session: sessione `requests.Session` (se None, creata/recuperata).

    Returns:
        `requests.Response` (non solleva su status non 2xx di default).

    Note:
        La validazione dello status è demandata al chiamante. Questo per evitare
        comportamenti inattesi nei flussi che gestiscono errori in modo personalizzato.
    """
    expected = expected_status or {200, 201, 202, 204}
    sess = session or get_session_for_token(token=token)
    req_timeout = timeout or DEFAULT_TIMEOUT

    # Costruisci header unendo Authorization + extra
    auth_headers = build_github_headers(token=token, extra=headers or {})

    attempt = 0
    while True:
        attempt += 1
        try:
            resp = sess.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                data=data,
                headers=auth_headers,
                timeout=req_timeout,
            )

            _handle_rate_limit(resp)

            # Se status è tra gli attesi, ritorna
            if resp.status_code in expected:
                return resp

            # Retry su status transitori
            if resp.status_code in RETRYABLE_STATUS and attempt <= MAX_RETRIES:
                sleep_s = _backoff_seconds(attempt)
                log_event(
                    _logger,
                    "http_retry",
                    {
                        "method": method.upper(),
                        "url": url,
                        "status": resp.status_code,
                        "attempt": attempt,
                        "sleep": round(sleep_s, 3),
                    },
                    level=30,
                )
                time.sleep(sleep_s)
                continue

            # Status non atteso e non retryable: ritorna comunque la Response per gestione a valle
            log_event(
                _logger,
                "http_unexpected_status",
                {
                    "method": method.upper(),
                    "url": url,
                    "status": resp.status_code,
                },
                level=30,
            )
            return resp

        except requests.RequestException as exc:
            if attempt <= MAX_RETRIES:
                sleep_s = _backoff_seconds(attempt)
                log_event(
                    _logger,
                    "network_retry",
                    {
                        "method": method.upper(),
                        "url": url,
                        "attempt": attempt,
                        "sleep": round(sleep_s, 3),
                        "error": str(exc),
                    },
                    level=30,
                )
                time.sleep(sleep_s)
                continue
            # Dopo i retry, rilanciamo l'eccezione
            raise


def get(
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    token: Optional[str] = None,
    timeout: Optional[Tuple[float, float]] = None,
    expected_status: Optional[Set[int]] = None,
    session: Optional[requests.Session] = None,
) -> requests.Response:
    """
    Wrapper tipizzato per GET con header GitHub standard, retry/backoff e rate-limit.
    """
    return request(
        "GET",
        url,
        params=params,
        headers=headers,
        token=token,
        timeout=timeout,
        expected_status=expected_status,
        session=session,
    )


def delete(
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    token: Optional[str] = None,
    timeout: Optional[Tuple[float, float]] = None,
    expected_status: Optional[Set[int]] = None,
    session: Optional[requests.Session] = None,
) -> requests.Response:
    """
    Wrapper tipizzato per DELETE con header GitHub standard, retry/backoff e rate-limit.
    """
    return request(
        "DELETE",
        url,
        params=params,
        headers=headers,
        token=token,
        timeout=timeout,
        expected_status=expected_status,
        session=session,
    )


# =============================================================================
# Helpers
# =============================================================================


def build_github_url(path: str) -> str:
    """
    Costruisce un URL assoluto verso la GitHub API a partire da un percorso relativo.
    Esempio:
        build_github_url("/user/followers") -> "https://api.github.com/user/followers"
    """
    if not path:
        raise ValueError("Percorso vuoto non valido.")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = GITHUB_API.rstrip("/")
    rel = path if path.startswith("/") else f"/{path}"
    return f"{base}{rel}"


def _handle_rate_limit(resp: requests.Response) -> None:
    """
    Osserva gli header di rate-limit e, se necessario, attende fino al reset.
    """
    remaining = resp.headers.get(HDR_RATE_REMAINING)
    reset = resp.headers.get(HDR_RATE_RESET)
    if remaining is None or reset is None:
        return
    try:
        rem = int(remaining)
        reset_epoch = int(reset)
    except ValueError:
        return

    if rem > 0:
        return

    now = int(time.time())
    wait_s = max(0, reset_epoch - now) + 1
    if wait_s > 0:
        log_event(_logger, "rate_limit_wait", {"wait_seconds": wait_s})
        time.sleep(wait_s)


def _backoff_seconds(attempt: int) -> float:
    """
    Calcola il tempo di attesa con backoff esponenziale e jitter deterministico.
    """
    base: float = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    jitter: float = base * 0.1
    fraction: float = float(time.time() % 1)  # parte frazionaria del timestamp
    jitter_term: float = jitter * (2.0 * fraction - 1.0)
    return max(0.0, base + jitter_term)
