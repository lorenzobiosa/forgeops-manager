# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: social.py
Descrizione:
    Servizio di sincronizzazione "follow/unfollow" per GitHub basato su regole:
      - Se un utente mi segue (follower), lo seguo (follow reciproco).
      - Se seguo un utente che non mi segue, eseguo "unfollow".
    Il modulo espone una classe "GitHubSocialService" che fornisce metodi
    idempotenti e osservabili per:
        * Recupero follower e following (con paginazione e gestione rate-limit).
        * Follow/unfollow utente (con retry/backoff).
        * Sincronizzazione completa con modalità "dry-run", allowlist e blocklist.
        * Produzione di un report strutturato per audit/artefatti CI.

    Sicurezza:
      - Necessita di un token GitHub (PAT o fine-grained) con scope: user:follow.
      - Nessun segreto deve essere salvato nel repository; usare variabili d'ambiente
        o GitHub Actions Secrets (es. GH_TOKEN).

    Limitazioni note:
      - La API REST GitHub supporta follow/unfollow *solo per utenti*.
        Per organizzazioni non è disponibile un endpoint REST equivalente.
      - Il servizio quindi agisce esclusivamente su account utente (login).

    Osservabilità:
      - Logging universale via src.utils.logging (JSON coerente).
      - Rate-limit aware: attende fino al reset se esaurito.
      - Report JSON/CSV suggerito a livello chiamante (workflow) salvando un artefatto.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
Licenza:
    Questo file è rilasciato secondo i termini della licenza del repository.
===============================================================================
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple, cast

import requests

from utils.structured_logging import get_logger, log_event

# ==============================
# Costanti di configurazione
# ==============================
GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_USER_AGENT = "BiosaLabs-GitHubSocialService/1.0"

# Timeout (connect, read) in secondi
DEFAULT_TIMEOUT: Tuple[float, float] = (10.0, 30.0)

# Paginazione: GitHub consente fino a 100 per pagina
DEFAULT_PAGE_SIZE = 100

# Retry/backoff
RETRYABLE_STATUS: Set[int] = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 30.0

# Header rate limit
HDR_RATE_REMAINING = "X-RateLimit-Remaining"
HDR_RATE_RESET = "X-RateLimit-Reset"


# ==============================
# Eccezioni specializzate
# ==============================
class GitHubAPIError(Exception):
    """Errore generico della API GitHub."""


class AuthenticationError(GitHubAPIError):
    """Token mancante o non valido (401/403)."""


class RateLimitExceeded(GitHubAPIError):
    """Limite di rate GitHub esaurito."""


# ==============================
# Factory tipizzate per dataclass
# ==============================
def _list_str_factory() -> List[str]:
    return []


def _dict_str_str_factory() -> Dict[str, str]:
    return {}


# ==============================
# Strutture dati
# ==============================
@dataclass
class SocialSyncReport:
    """Report strutturato dell'esecuzione di sincronizzazione."""

    started_at: str
    completed_at: str
    dry_run: bool
    followers_count: int
    following_count: int
    to_follow: List[str] = field(default_factory=_list_str_factory)
    to_unfollow: List[str] = field(default_factory=_list_str_factory)
    followed: List[str] = field(default_factory=_list_str_factory)
    unfollowed: List[str] = field(default_factory=_list_str_factory)
    skipped: Dict[str, str] = field(default_factory=_dict_str_str_factory)  # username -> motivo
    allowlist: List[str] = field(default_factory=_list_str_factory)
    blocklist: List[str] = field(default_factory=_list_str_factory)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# ==============================
# Servizio principale
# ==============================
class GitHubSocialService:
    """
    Servizio per operazioni social (follow/unfollow) su GitHub.
    """

    def __init__(
        self,
        token: str,
        base_url: str = GITHUB_API_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: Tuple[float, float] = DEFAULT_TIMEOUT,
        page_size: int = DEFAULT_PAGE_SIZE,
        logger_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not token:
            raise AuthenticationError(
                "Token GitHub mancante. Impostare GH_TOKEN o passare 'token'."
            )

        self._base_url: str = base_url.rstrip("/")
        self._token: str = token
        self._timeout: Tuple[float, float] = timeout
        self._page_size: int = max(1, min(page_size, 100))

        # Session HTTP dedicata
        self._session: requests.Session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"token {self._token}",  # PAT
                "Accept": "application/vnd.github+json",
                "User-Agent": user_agent,
            }
        )

        # Logger universale
        self._logger = get_logger(logger_name or self.__class__.__name__)

    # --------------------------------------------------------------------- #
    # Costruttori ausiliari
    # --------------------------------------------------------------------- #
    @classmethod
    def from_env(
        cls,
        *,
        env_token_key: str = "GH_TOKEN",
        **kwargs: Any,
    ) -> "GitHubSocialService":
        token = os.getenv(env_token_key, "").strip()
        return cls(token=token, **kwargs)

    # --------------------------------------------------------------------- #
    # API pubbliche: elenchi
    # --------------------------------------------------------------------- #
    def get_followers(self) -> Set[str]:
        """Restituisce l'insieme dei login (username) degli utenti che seguono \
            l'account autenticato."""
        endpoint = "/user/followers"
        params: Dict[str, str] = {"per_page": str(self._page_size)}
        items = self._paginate(endpoint, params)
        followers: Set[str] = set()
        for item in items:
            login = item.get("login")
            if isinstance(login, str):
                followers.add(login)
        log_event(self._logger, "followers_fetched", {"count": len(followers)})
        return followers

    def get_following(self) -> Set[str]:
        """Restituisce l'insieme dei login (username) degli utenti seguiti \
            dall'account autenticato."""
        endpoint = "/user/following"
        params: Dict[str, str] = {"per_page": str(self._page_size)}
        items = self._paginate(endpoint, params)
        following: Set[str] = set()
        for item in items:
            login = item.get("login")
            if isinstance(login, str):
                following.add(login)
        log_event(self._logger, "following_fetched", {"count": len(following)})
        return following

    # --------------------------------------------------------------------- #
    # API pubbliche: azioni
    # --------------------------------------------------------------------- #
    def follow_user(self, username: str) -> bool:
        """Esegue follow di un utente."""
        if not username:
            raise ValueError("username non valido")
        path = f"/user/following/{username}"
        resp = self._request("PUT", path, expected_status={204, 304})
        ok = resp.status_code in (204, 304)
        log_event(
            self._logger,
            "follow_user",
            {"username": username, "result": ok, "status": resp.status_code},
        )
        return ok

    def unfollow_user(self, username: str) -> bool:
        """Esegue unfollow di un utente."""
        if not username:
            raise ValueError("username non valido")
        path = f"/user/following/{username}"
        resp = self._request("DELETE", path, expected_status={204, 304})
        ok = resp.status_code in (204, 304)
        log_event(
            self._logger,
            "unfollow_user",
            {"username": username, "result": ok, "status": resp.status_code},
        )
        return ok

    # --------------------------------------------------------------------- #
    # Sincronizzazione con regole
    # --------------------------------------------------------------------- #
    def sync_followers(
        self,
        *,
        dry_run: bool = True,
        allowlist: Optional[Iterable[str]] = None,
        blocklist: Optional[Iterable[str]] = None,
    ) -> SocialSyncReport:
        """
        Sincronizza lo stato following in base ai follower:
          - Segue chi mi segue (follower) ma che non sto già seguendo (esclusa blocklist).
          - Smette di seguire chi non mi segue (esclusa allowlist).
        """
        started = datetime.now(timezone.utc).isoformat()

        allow: Set[str] = {u.strip() for u in (allowlist or []) if u and u.strip()}
        block: Set[str] = {u.strip() for u in (blocklist or []) if u and u.strip()}

        followers = self.get_followers()
        following = self.get_following()

        # Manteniamo set per chiarezza e tipizzazione esplicita
        to_follow_set: Set[str] = (followers - following) - block
        to_unfollow_set: Set[str] = (following - followers) - allow

        followed: List[str] = []
        unfollowed: List[str] = []
        skipped: Dict[str, str] = {}

        # Follow
        for username in sorted(to_follow_set):
            if dry_run:
                log_event(self._logger, "dry_run_follow", {"username": username})
                skipped[username] = "dry_run_follow"
                continue
            try:
                if self.follow_user(username):
                    followed.append(username)
            except GitHubAPIError as exc:
                log_event(
                    self._logger,
                    "follow_error",
                    {"username": username, "error": str(exc)},
                    level=30,
                )
                skipped[username] = f"error:{exc.__class__.__name__}"

        # Unfollow
        for username in sorted(to_unfollow_set):
            if dry_run:
                log_event(self._logger, "dry_run_unfollow", {"username": username})
                skipped[username] = "dry_run_unfollow"
                continue
            try:
                if self.unfollow_user(username):
                    unfollowed.append(username)
            except GitHubAPIError as exc:
                log_event(
                    self._logger,
                    "unfollow_error",
                    {"username": username, "error": str(exc)},
                    level=30,
                )
                skipped[username] = f"error:{exc.__class__.__name__}"

        completed = datetime.now(timezone.utc).isoformat()

        # Convertiamo i set in liste ordinate SOLO per il report (tipi espliciti)
        to_follow_list: List[str] = sorted(to_follow_set)
        to_unfollow_list: List[str] = sorted(to_unfollow_set)

        report = SocialSyncReport(
            started_at=started,
            completed_at=completed,
            dry_run=dry_run,
            followers_count=len(followers),
            following_count=len(following),
            to_follow=to_follow_list,
            to_unfollow=to_unfollow_list,
            followed=sorted(followed),
            unfollowed=sorted(unfollowed),
            skipped=skipped,
            allowlist=sorted(allow),
            blocklist=sorted(block),
        )
        log_event(
            self._logger,
            "sync_complete",
            {
                "summary": {
                    "dry_run": dry_run,
                    "followers": len(followers),
                    "following": len(following),
                    "to_follow": len(to_follow_list),
                    "to_unfollow": len(to_unfollow_list),
                    "followed": len(followed),
                    "unfollowed": len(unfollowed),
                    "skipped": len(skipped),
                }
            },
        )
        return report

    # --------------------------------------------------------------------- #
    # Helpers HTTP (paginazione, retry, rate-limit)
    # --------------------------------------------------------------------- #
    def _paginate(
        self, path: str, params: Optional[Mapping[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Esegue richieste paginando risultati finché disponibile una "next page".
        """
        items: List[Dict[str, Any]] = []
        page = 1

        base_params: Dict[str, str] = dict(params or {})
        base_params["per_page"] = str(self._page_size)

        while True:
            page_params = dict(base_params)
            page_params["page"] = str(page)

            # Request della pagina
            resp = self._request("GET", path, params=page_params, expected_status={200})
            raw: Any = self._safe_json(resp)

            if not isinstance(raw, list):
                raise GitHubAPIError(f"Risposta inattesa in paginazione: {type(raw)!r}")

            iterable_any: Iterable[Any] = cast(Iterable[Any], raw)
            batch: List[Any] = list(iterable_any)

            # Colleziona solo dict (coerente con la API degli utenti)
            typed_batch: List[Dict[str, Any]] = []
            for elem in batch:
                if isinstance(elem, dict):
                    # Evita dict[Unknown, Unknown] in Pylance
                    typed_elem: Dict[str, Any] = cast(Dict[str, Any], elem)
                    typed_batch.append(typed_elem)

            items.extend(typed_batch)

            link_header = resp.headers.get("Link", "")
            has_next = _has_link_next(link_header)

            if len(typed_batch) < self._page_size and not has_next:
                break

            if not has_next:
                if len(typed_batch) < self._page_size:
                    break

            page += 1

        return items

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, str]] = None,
        expected_status: Optional[Set[int]] = None,
    ) -> requests.Response:
        """
        Esegue una richiesta HTTP con retry/backoff e gestione rate-limit.
        """
        expected: Set[int] = expected_status or {200}
        url = f"{self._base_url}{path}"
        attempt = 0

        while True:
            attempt += 1
            try:
                if method.upper() == "GET":
                    resp = self._session.request(
                        method=method.upper(),
                        url=url,
                        params=params,
                        timeout=self._timeout,
                    )
                else:
                    resp = self._session.request(
                        method=method.upper(),
                        url=url,
                        timeout=self._timeout,
                    )

                # Rate-limit: se esaurito, attendi fino a reset
                self._handle_rate_limit(resp)

                if resp.status_code in expected:
                    return resp

                if resp.status_code in (401, 403):
                    raise AuthenticationError(
                        f"Autenticazione fallita o permessi insufficienti: \
                            {resp.status_code} {resp.text}"
                    )

                if resp.status_code in RETRYABLE_STATUS and attempt <= MAX_RETRIES:
                    sleep_s = self._backoff_seconds(attempt)
                    log_event(
                        self._logger,
                        "http_retry",
                        {
                            "method": method,
                            "path": path,
                            "status": resp.status_code,
                            "attempt": attempt,
                            "sleep": round(sleep_s, 3),
                        },
                        level=30,
                    )
                    time.sleep(sleep_s)
                    continue

                raise GitHubAPIError(f"HTTP {resp.status_code} su {method} {path}: {resp.text}")

            except requests.RequestException as exc:
                if attempt <= MAX_RETRIES:
                    sleep_s = self._backoff_seconds(attempt)
                    log_event(
                        self._logger,
                        "network_retry",
                        {
                            "method": method,
                            "path": path,
                            "attempt": attempt,
                            "sleep": round(sleep_s, 3),
                            "error": str(exc),
                        },
                        level=30,
                    )
                    time.sleep(sleep_s)
                    continue
                raise GitHubAPIError(f"Errore di rete su {method} {path}: {exc}") from exc

    def _handle_rate_limit(self, resp: requests.Response) -> None:
        """Valuta gli header di rate-limit e, se necessario, attende fino al reset."""
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
            log_event(self._logger, "rate_limit_wait", {"wait_seconds": wait_s})
            time.sleep(wait_s)

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        """Calcola il tempo di attesa con backoff esponenziale con jitter."""
        factor: float = float(2 ** max(0, attempt - 1))
        base: float = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * factor)
        jitter: float = base * 0.1
        # jitter deterministico basato sulla FRAZIONE di time.time()
        frac: float = math.modf(time.time())[0]  # 0 <= frac < 1
        signed: float = (2.0 * frac) - 1.0  # in [-1, 1)
        value: float = base + (jitter * signed)
        return max(0.0, value)

    @staticmethod
    def _safe_json(resp: requests.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            raise GitHubAPIError("Risposta non in formato JSON valido")


# ==============================
# Utility header Link
# ==============================
def _has_link_next(link_header: str) -> bool:
    """
    Verifica se nell'header Link è presente una relazione 'next'.
    Esempio:
      <https://api.github.com/user/followers?per_page=100&page=2>; rel="next",
      <https://api.github.com/user/followers?per_page=100&page=3>; rel="last"
    """
    if not link_header:
        return False
    parts = [p.strip() for p in link_header.split(",")]
    for p in parts:
        if 'rel="next"' in p:
            return True
    return False
