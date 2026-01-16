# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: providers/github/security.py
Descrizione:
  Provider per la gestione di vulnerabilità GitHub Code Scanning:
    - MODE=delete  : cancella analyses per uno o più tool (es. Trivy, Grype).
    - MODE=dismiss : imposta a "dismissed" le alert aperte (eventuale filtro per tool).
  Requisiti permessi: security-events: write

Linee guida:
  - Logging strutturato via src.utils.logging (JSON di default).
  - Nessun segreto nel log (mai loggare token).
  - Gestione rate-limit con attesa fino al reset e log evento dedicato.
  - Progress su console (print) per feedback CLI, più log strutturati.

Note di implementazione:
  - Per evitare warning Pylance quando l'editor non ha il pacchetto `requests`,
    non lo importiamo a livello di modulo; usiamo Protocol per i tipi runtime:
    (`RequestsSessionLike`, `ResponseLike`), compatibili con `requests.Session`
    e `requests.Response`.
  - Si esegue un `cast` esplicito verso il Protocol locale quando si usa la sessione
    restituita da `ensure_github_token_ready`, evitando la creazione di tipi union
    fra protocolli (es. `src.utils.token_guard.RequestsSessionLike`).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Protocol,
    Tuple,
    cast,
)

from utils.http_client import GITHUB_API
from utils.structured_logging import get_logger, log_event, setup_logging
from utils.token_guard import TokenScopeError, ensure_github_token_ready

__all__ = [
    "GitHubSecurityClient",
    "parse_tools_csv",
    "is_tool_selected",
    "delete_analyses",
    "dismiss_alerts",
    "clear_vulns",
    "main",
]


# -----------------------------------------------------------------------------
# Tipi minimi compatibili con requests (senza import a livello di modulo)
# -----------------------------------------------------------------------------
class ResponseLike(Protocol):
    headers: Mapping[str, str]
    status_code: int
    text: str

    def json(self) -> Any:
        raise NotImplementedError


class RequestsSessionLike(Protocol):
    headers: MutableMapping[str, str]

    # richieste generiche
    def request(self, method: str, url: str, **kwargs: Any) -> ResponseLike:
        raise NotImplementedError

    # metodi specifici usati in questo modulo
    def get(self, url: str, params: Optional[Mapping[str, Any]] = None) -> ResponseLike:
        raise NotImplementedError

    def delete(self, url: str, **kwargs: Any) -> ResponseLike:
        raise NotImplementedError


# Logger di modulo (eredita configurazione del root)
_logger = logging.getLogger(__name__)


# =============================================================================
# Client GitHub Security
# =============================================================================
class GitHubSecurityClient:
    """
    Client specializzato per operazioni di Code Scanning (analyses/alerts).
    """

    def __init__(
        self,
        token: str,
        repo: str,
        dry_run: bool = False,
        session: Optional[RequestsSessionLike] = None,
    ):
        if not token:
            raise ValueError("Manca GITHUB_TOKEN: passare --token o definire env GITHUB_TOKEN.")
        if "/" not in repo:
            raise ValueError("repo deve essere nel formato owner/repo.")

        self.token = token
        self.repo = repo
        self.dry_run = dry_run

        # Usa la sessione fornita oppure costruiscine una pronta con token_guard
        if session is None:
            _sess = ensure_github_token_ready(
                token=token,
                required_scopes={"security_events"},
                repo=repo,
                op_name="clear-vulns",
                logger=_logger,
            )
            # Cast esplicito al Protocol locale per evitare union di protocolli
            self.session: RequestsSessionLike = cast(RequestsSessionLike, _sess)
        else:
            self.session = session

        # Assicura intestazioni base (idempotente)
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "forgeops-manager/clear-vulns",
            }
        )

        log_event(_logger, "security_client_initialized", {"repo": repo, "dry_run": dry_run})

    # ----------------------------- HTTP base ----------------------------- #
    def _request(self, method: str, path: str, **kwargs: Any) -> ResponseLike:
        """
        Esegue una richiesta HTTP verso GitHub API, con gestione rate-limit.
        Se il rate-limit è esaurito, attende fino al reset e ritenta UNA volta.
        """
        url = f"{GITHUB_API}{path}"
        resp = self.session.request(method, url, **kwargs)
        resp = self._rate_limit_retry_if_needed(resp, method=method, url=url, kwargs=kwargs)
        return resp

    def _rate_limit_retry_if_needed(
        self,
        resp: ResponseLike,
        *,
        method: str,
        url: str,
        kwargs: Dict[str, Any],
    ) -> ResponseLike:
        """
        Se la response indica rate-limit esaurito, attende fino al reset e
        ritenta una seconda volta. Ritorna la response finale.
        """
        hdr_rem = resp.headers.get("X-RateLimit-Remaining")
        hdr_reset = resp.headers.get("X-RateLimit-Reset")

        wait_seconds: Optional[int] = None
        now = int(time.time())

        # Se header presenti e remaining == 0
        if hdr_rem is not None and hdr_reset is not None:
            try:
                remaining = int(hdr_rem)
                reset_epoch = int(hdr_reset)
                if remaining <= 0:
                    wait_seconds = max(0, reset_epoch - now) + 1
            except ValueError:
                wait_seconds = None

        # Fallback: 403 con "rate limit" nel body
        if (
            wait_seconds is None
            and getattr(resp, "status_code", 0) == 403
            and "rate limit" in (getattr(resp, "text", "") or "").lower()
        ):
            if hdr_reset:
                try:
                    reset_epoch = int(hdr_reset)
                    wait_seconds = max(0, reset_epoch - now) + 1
                except ValueError:
                    wait_seconds = 30  # fallback prudenziale
            else:
                wait_seconds = 30

        if wait_seconds and wait_seconds > 0:
            log_event(_logger, "rate_limit_wait", {"wait_seconds": wait_seconds})
            # Stampa anche su stderr per visibilità CLI
            print(f"[WARN] Rate limit raggiunto. Attendo {wait_seconds}s…", file=sys.stderr)
            time.sleep(wait_seconds)
            retry = self.session.request(method, url, **kwargs)
            return retry

        return resp

    # ----------------------------- Analyses ----------------------------- #
    def list_code_scanning_analyses(self, per_page: int = 100) -> Iterable[Dict[str, Any]]:
        """
        Restituisce le analyses a partire dalle più recenti (paginato).
        """
        page = 1
        while True:
            path = f"/repos/{self.repo}/code-scanning/analyses"
            params: Dict[str, Any] = {"per_page": per_page, "page": page}
            resp = self._request("GET", path, params=params)
            if resp.status_code != 200:
                log_event(
                    _logger,
                    "security_list_analyses_error",
                    {"status": resp.status_code, "text": resp.text[:300]},
                    level=logging.ERROR,
                )
                raise RuntimeError(f"GET {path} fallita: {resp.status_code} {resp.text}")

            items_any = resp.json()
            if not items_any:
                break
            if not isinstance(items_any, list):
                log_event(
                    _logger,
                    "security_list_analyses_invalid",
                    {"type": type(items_any).__name__},
                    level=logging.ERROR,
                )
                raise RuntimeError("Risposta inattesa: atteso array.")

            iterable_any = cast(Iterable[Any], items_any)
            items_list: List[Any] = list(iterable_any)
            for it_any in items_list:
                if isinstance(it_any, dict):
                    it: Dict[str, Any] = cast(Dict[str, Any], it_any)
                    yield it
                else:
                    log_event(
                        _logger,
                        "security_list_analyses_skip_non_dict",
                        {"type": type(it_any).__name__},
                        level=logging.WARNING,
                    )
            page += 1

    def delete_analysis(self, analysis_id: int) -> None:
        """
        Cancella una analysis di code scanning.
        GitHub può richiedere follow-up DELETE su URL di conferma/next fino a 204.
        Gestisce anche il caso 400 con conferma esplicita (confirm_delete=true).
        """
        base_path = f"/repos/{self.repo}/code-scanning/analyses/{analysis_id}"

        if self.dry_run:
            print(f"[DRY-RUN] Eliminerei analysis {analysis_id}")
            log_event(
                _logger,
                "security_delete_analysis_dry_run",
                {"analysis_id": analysis_id},
            )
            return

        def _delete_raw_url(url: str) -> ResponseLike:
            # DELETE a URL assoluta (confirm/next)
            return self.session.delete(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "forgeops-manager/clear-vulns",
                },
            )

        # Primo tentativo senza confirm flag
        resp = self._request("DELETE", base_path)

        # 204: finito
        if resp.status_code == 204:
            log_event(
                _logger,
                "security_delete_analysis_done",
                {"analysis_id": analysis_id, "status": 204},
            )
            return

        # 400: serve conferma esplicita
        if resp.status_code == 400 and "confirm_delete" in (resp.text or "").lower():
            path_with_confirm = f"{base_path}?confirm_delete=true"
            resp2 = self._request("DELETE", path_with_confirm)
            if resp2.status_code == 204:
                log_event(
                    _logger,
                    "security_delete_analysis_done",
                    {"analysis_id": analysis_id, "status": 204},
                )
                return
            resp = resp2  # prosegui come 200/202

        # 200/202: flusso con follow-up (o finale con null URLs)
        if resp.status_code in (200, 202):
            payload_any = resp.json()
            payload_dict: Dict[str, Any] = (
                cast(Dict[str, Any], payload_any) if isinstance(payload_any, dict) else {}
            )

            confirm_url = cast(Optional[str], payload_dict.get("confirm_delete_url"))
            next_url = cast(Optional[str], payload_dict.get("next_analysis_url"))

            # Se entrambi null -> finito (ultimo elemento)
            if not confirm_url and not next_url:
                log_event(
                    _logger,
                    "security_delete_analysis_done",
                    {"analysis_id": analysis_id, "status": resp.status_code},
                )
                return

            # Precedenza a confirm_delete_url
            target_url: Optional[str] = confirm_url or next_url
            if not target_url:
                log_event(
                    _logger,
                    "security_delete_followup_missing_url",
                    {
                        "analysis_id": analysis_id,
                        "status": resp.status_code,
                        "text": resp.text[:300],
                    },
                    level=logging.ERROR,
                )
                raise RuntimeError(
                    f"DELETE {base_path} ha restituito {resp.status_code} senza URL di \
                        conferma/next."
                )

            # Assicura confirm_delete=true
            if "confirm_delete=" not in target_url:
                sep = "&" if "?" in target_url else "?"
                target_url = f"{target_url}{sep}confirm_delete=true"

            follow = _delete_raw_url(target_url)
            if follow.status_code == 204:
                log_event(
                    _logger,
                    "security_delete_analysis_done",
                    {"analysis_id": analysis_id, "status": 204},
                )
                return

            # Continua finché il server fornisce URL di follow-up
            while follow.status_code in (200, 202):
                p2_any = follow.json()
                p2_dict: Dict[str, Any] = (
                    cast(Dict[str, Any], p2_any) if isinstance(p2_any, dict) else {}
                )

                c2 = cast(Optional[str], p2_dict.get("confirm_delete_url"))
                n2 = cast(Optional[str], p2_dict.get("next_analysis_url"))

                if not c2 and not n2:
                    log_event(
                        _logger,
                        "security_delete_analysis_done",
                        {"analysis_id": analysis_id, "status": follow.status_code},
                    )
                    return

                t2: Optional[str] = c2 or n2
                if t2 is None:
                    log_event(
                        _logger,
                        "security_delete_followup_missing_url",
                        {
                            "analysis_id": analysis_id,
                            "status": follow.status_code,
                            "text": follow.text[:300],
                        },
                        level=logging.ERROR,
                    )
                    raise RuntimeError("DELETE follow-up senza URL.")

                if "confirm_delete=" not in t2:
                    sep = "&" if "?" in t2 else "?"
                    t2 = f"{t2}{sep}confirm_delete=true"

                follow = _delete_raw_url(t2)
                if follow.status_code == 204:
                    log_event(
                        _logger,
                        "security_delete_analysis_done",
                        {"analysis_id": analysis_id, "status": 204},
                    )
                    return

            if follow.status_code not in (200, 202, 204):
                log_event(
                    _logger,
                    "security_delete_followup_error",
                    {
                        "analysis_id": analysis_id,
                        "status": follow.status_code,
                        "text": follow.text[:300],
                    },
                    level=logging.ERROR,
                )
                raise RuntimeError(
                    f"DELETE follow-up {target_url} fallita: {follow.status_code} {follow.text}"
                )
            return

        # Altri status -> errore
        log_event(
            _logger,
            "security_delete_analysis_error",
            {
                "analysis_id": analysis_id,
                "status": resp.status_code,
                "text": resp.text[:300],
            },
            level=logging.ERROR,
        )
        raise RuntimeError(f"DELETE {base_path} fallita: {resp.status_code} {resp.text}")

    # ----------------------------- Alerts ----------------------------- #
    def list_code_scanning_alerts(
        self, state: str = "open", per_page: int = 100
    ) -> Iterable[Dict[str, Any]]:
        """
        Restituisce le alert di code scanning (paginato).
        """
        page = 1
        while True:
            path = f"/repos/{self.repo}/code-scanning/alerts"
            params: Dict[str, Any] = {"per_page": per_page, "page": page, "state": state}
            resp = self._request("GET", path, params=params)
            if resp.status_code != 200:
                log_event(
                    _logger,
                    "security_list_alerts_error",
                    {"status": resp.status_code, "text": resp.text[:300]},
                    level=logging.ERROR,
                )
                raise RuntimeError(f"GET {path} fallita: {resp.status_code} {resp.text}")

            items_any = resp.json()
            if not items_any:
                break
            if not isinstance(items_any, list):
                log_event(
                    _logger,
                    "security_list_alerts_invalid",
                    {"type": type(items_any).__name__},
                    level=logging.ERROR,
                )
                raise RuntimeError("Risposta inattesa: atteso array.")

            iterable_any = cast(Iterable[Any], items_any)
            items_list: List[Any] = list(iterable_any)
            for it_any in items_list:
                if isinstance(it_any, dict):
                    it: Dict[str, Any] = cast(Dict[str, Any], it_any)
                    yield it
                else:
                    log_event(
                        _logger,
                        "security_list_alerts_skip_non_dict",
                        {"type": type(it_any).__name__},
                        level=logging.WARNING,
                    )
            page += 1

    def dismiss_alert(self, alert_number: int, reason: str, comment: str) -> None:
        """
        Dismiss di una alert aperta: imposta dismissed=True con reason/comment.
        """
        path = f"/repos/{self.repo}/code-scanning/alerts/{alert_number}"
        data: Dict[str, Any] = {
            "dismissed": True,
            "dismissed_reason": reason,
            "dismissed_comment": comment,
        }

        if self.dry_run:
            print(f"[DRY-RUN] Dismiss alert #{alert_number} con {data}")
            log_event(
                _logger,
                "security_dismiss_alert_dry_run",
                {"alert_number": alert_number, "reason": reason},
            )
            return

        resp = self._request("PATCH", path, json=data)
        if resp.status_code != 200:
            log_event(
                _logger,
                "security_dismiss_alert_error",
                {
                    "alert_number": alert_number,
                    "status": resp.status_code,
                    "text": resp.text[:300],
                },
                level=logging.ERROR,
            )
            raise RuntimeError(f"PATCH {path} fallita: {resp.status_code} {resp.text}")

        log_event(_logger, "security_dismiss_alert_done", {"alert_number": alert_number})


# =============================================================================
# Helper
# =============================================================================
def parse_tools_csv(csv_value: Optional[str]) -> List[str]:
    if not csv_value:
        return []
    return [t.strip() for t in csv_value.split(",") if t.strip()]


def is_tool_selected(tool_name: Optional[str], tools_filter: List[str]) -> bool:
    if not tools_filter:
        return True  # nessun filtro => applica a tutti
    if not tool_name:
        return False
    return tool_name in tools_filter


# =============================================================================
# Operazioni
# =============================================================================
def delete_analyses(gh: GitHubSecurityClient, tools_filter: List[str]) -> Tuple[int, int]:
    """
    Bulk delete: trova una analysis cancellabile per i tool selezionati, la cancella,
    e continua fino ad esaurimento. Segue le linee guida GitHub (più recenti -> indietro).
    Restituisce: (scansionate, cancellate)
    """
    scanned = 0
    deleted = 0

    while True:
        found: Optional[Dict[str, Any]] = None

        # Ricerca della prima analysis "deletable" nello stream
        for a in gh.list_code_scanning_analyses():
            scanned += 1

            # Estrai tool in modo tip-safe
            tool_name: Optional[str] = None
            t_any = a.get("tool")
            if isinstance(t_any, dict):
                t_dict: Dict[str, Any] = cast(Dict[str, Any], t_any)
                tn = t_dict.get("name")
                if isinstance(tn, str):
                    tool_name = tn

            if not is_tool_selected(tool_name, tools_filter):
                continue

            if a.get("deletable", False):
                found = a
                break

        if not found:
            # Nessuna altra analysis cancellabile per i tool selezionati
            break

        analysis_id_any = found.get("id")
        if analysis_id_any is None:
            # Elemento malformato -> skip
            log_event(_logger, "security_delete_analysis_skip", {"reason": "id mancante"})
            continue
        try:
            analysis_id = int(analysis_id_any)
        except (TypeError, ValueError):
            log_event(_logger, "security_delete_analysis_skip", {"reason": "id non intero"})
            continue

        # Ricalcolo di tool_name dal record "found"
        tool_name = None
        tool_any = found.get("tool")
        if isinstance(tool_any, dict):
            tool_dict: Dict[str, Any] = cast(Dict[str, Any], tool_any)
            tn2 = tool_dict.get("name")
            if isinstance(tn2, str):
                tool_name = tn2

        print(f"[INFO] Eliminazione analysis id={analysis_id} tool={tool_name or 'unknown'}")
        try:
            gh.delete_analysis(analysis_id)
            deleted += 1
            log_event(
                _logger,
                "security_delete_analysis_ok",
                {"analysis_id": analysis_id, "tool": tool_name},
            )
        except Exception as exc:
            _logger.exception("Errore cancellando analysis")
            log_event(
                _logger,
                "security_delete_analysis_exception",
                {
                    "analysis_id": analysis_id,
                    "tool": tool_name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=logging.ERROR,
            )
            # continua con la successiva

    return scanned, deleted


def dismiss_alerts(
    gh: GitHubSecurityClient,
    tools_filter: List[str],
    reason: str,
    comment: str,
    state: str = "open",
) -> Tuple[int, int]:
    """
    Dismiss delle alert (state=open di default). Filtro opzionale per tool.
    Restituisce: (scansionate, dismesse)
    """
    scanned = 0
    dismissed = 0

    for al in gh.list_code_scanning_alerts(state=state):
        scanned += 1

        # Estrai tool in modo tip-safe
        tool_name: Optional[str] = None
        t_any = al.get("tool")
        if isinstance(t_any, dict):
            t_dict: Dict[str, Any] = cast(Dict[str, Any], t_any)
            tn = t_dict.get("name")
            if isinstance(tn, str):
                tool_name = tn

        if not is_tool_selected(tool_name, tools_filter):
            continue

        number_any = al.get("number")
        if number_any is None:
            log_event(_logger, "security_dismiss_alert_skip", {"reason": "numero mancante"})
            continue
        try:
            number = int(number_any)
        except (TypeError, ValueError):
            log_event(_logger, "security_dismiss_alert_skip", {"reason": "numero non intero"})
            continue

        # Estrai rule tip-safe
        rule_id: Optional[str] = None
        r_any = al.get("rule")
        if isinstance(r_any, dict):
            r_dict: Dict[str, Any] = cast(Dict[str, Any], r_any)
            rid = r_dict.get("id")
            rname = r_dict.get("name")
            if isinstance(rid, str):
                rule_id = rid
            elif isinstance(rname, str):
                rule_id = rname

        print(f"[INFO] Dismiss alert #{number} tool={tool_name} rule={rule_id} reason={reason}")
        try:
            gh.dismiss_alert(number, reason=reason, comment=comment)
            dismissed += 1
            log_event(
                _logger,
                "security_dismiss_alert_ok",
                {"alert_number": number, "tool": tool_name, "rule": rule_id},
            )
        except Exception as exc:
            _logger.exception("Errore durante dismiss alert")
            log_event(
                _logger,
                "security_dismiss_alert_exception",
                {
                    "alert_number": number,
                    "tool": tool_name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=logging.ERROR,
            )
            # continua con la successiva

    return scanned, dismissed


# =============================================================================
# Facade (usata da main.py e CLI)
# =============================================================================
def clear_vulns(
    repo: str,
    mode: str,
    token: Optional[str] = None,
    tools: Optional[str] = "Trivy,Grype",
    reason: str = "won't_fix",
    comment: str = "Bulk reset: issues will reappear if they persist.",
    state: str = "open",
    dry_run: bool = False,
    *,
    session: Optional[RequestsSessionLike] = None,
) -> Dict[str, int]:
    """
    Entrypoint singolo usato da src/main.py, CLI e workflows.

    Returns:
        dict con campi:
          - scanned: int
          - deleted|dismissed: int
    """
    # Recupero token in modo sicuro (mai loggare)
    token = (token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        raise ValueError("Manca GH_TOKEN/GITHUB_TOKEN. Passare --token o definire env.")

    # Validazione enterprise all'avvio (se la sessione non è già stata fornita)
    if session is None:
        try:
            _sess = ensure_github_token_ready(
                token=token,
                required_scopes={"security_events"},
                repo=repo,
                op_name="clear-vulns",
                logger=_logger,
            )
            session = cast(RequestsSessionLike, _sess)
        except TokenScopeError:
            # Rilancia per far gestire al chiamante (CLI/integrazione)
            raise

    tools_filter = parse_tools_csv(tools)
    gh = GitHubSecurityClient(token=token, repo=repo, dry_run=dry_run, session=session)

    log_event(
        _logger,
        "clear_vulns_start",
        {
            "repo": repo,
            "mode": mode,
            "dry_run": dry_run,
            "tools_count": len(tools_filter),
            "state": state,
        },
    )

    if mode == "delete":
        scanned, deleted = delete_analyses(gh, tools_filter)
        result: Dict[str, int] = {"scanned": scanned, "deleted": deleted}
        log_event(_logger, "clear_vulns_complete", {"mode": "delete", **result})
        return result

    if mode == "dismiss":
        valid = {"false_positive", "won't_fix", "used_in_tests"}
        if reason not in valid:
            log_event(
                _logger,
                "clear_vulns_reason_invalid",
                {"reason": reason, "valid": sorted(valid)},
                level=logging.ERROR,
            )
            raise ValueError(f"Reason non valida '{reason}'. Ammesse: {', '.join(sorted(valid))}")
        scanned, dism = dismiss_alerts(
            gh, tools_filter, reason=reason, comment=comment, state=state
        )
        result = {"scanned": scanned, "dismissed": dism}
        log_event(_logger, "clear_vulns_complete", {"mode": "dismiss", **result})
        return result

    log_event(_logger, "clear_vulns_mode_invalid", {"mode": mode}, level=logging.ERROR)
    raise ValueError("mode deve essere 'delete' o 'dismiss'.")


# =============================================================================
# CLI standalone (opzionale)
# =============================================================================
def main() -> None:
    """
    CLI standalone per gestire Code Scanning:
      - delete  : cancella analyses per i tool indicati (o tutti).
      - dismiss : imposta alert a dismissed secondo reason/comment.
    """
    parser = argparse.ArgumentParser(
        description="Gestione Code Scanning (delete analyses / dismiss alerts)."
    )
    parser.add_argument("--repo", required=True, help="Repository GitHub (owner/repo)")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["delete", "dismiss"],
        help="Operazione: delete|dismiss",
    )
    parser.add_argument("--token", help="PAT GitHub (default env GH_TOKEN/GITHUB_TOKEN)")
    parser.add_argument("--tools", default="Trivy,Grype", help="CSV tool (vuoto per tutti)")
    parser.add_argument(
        "--reason",
        default="won't_fix",
        help="Dismiss reason (false_positive|won't_fix|used_in_tests)",
    )
    parser.add_argument(
        "--comment",
        default="Bulk reset: issues will reappear if they persist.",
        help="Dismiss comment",
    )
    parser.add_argument("--state", default="open", help="Alert state da processare (default: open)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Esegui senza modificare (stampa azioni)"
    )
    # Opzioni logging
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Livello di logging",
    )
    parser.add_argument(
        "--log-json", dest="log_json", action="store_true", help="Abilita logging JSON"
    )
    parser.add_argument(
        "--no-log-json", dest="log_json", action="store_false", help="Disabilita logging JSON"
    )
    parser.set_defaults(log_json=None)

    args = parser.parse_args()

    # In CLI standalone abilitiamo log su console
    setup_logging(level=args.log_level, json_mode=args.log_json, console=True)
    cli_logger = get_logger(__name__)

    try:
        log_event(
            cli_logger, "cli_invocation", {"command": "security-clear-vulns", "mode": args.mode}
        )

        token_value = (
            args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        ).strip()
        if not token_value:
            raise ValueError(
                "Token GitHub mancante. Impostare GH_TOKEN/GITHUB_TOKEN o passare --token."
            )

        _sess = ensure_github_token_ready(
            token=token_value,
            required_scopes={"security_events"},
            repo=args.repo,
            op_name="clear-vulns",
            logger=cli_logger,
        )
        session = cast(RequestsSessionLike, _sess)

        result = clear_vulns(
            repo=args.repo,
            mode=args.mode,
            token=token_value,
            tools=args.tools,
            reason=args.reason,
            comment=args.comment,
            state=args.state,
            dry_run=args.dry_run,
            session=session,  # iniezione della sessione pronta
        )
        print("\nRisultato:")
        print(result)
    except TokenScopeError as exc:
        cli_logger.error(str(exc))
        log_event(
            cli_logger,
            "cli_scope_error",
            {"error_type": type(exc).__name__, "error_message": str(exc)},
            level=logging.ERROR,
        )
        sys.stderr.write(f"Errore: {exc}\n")
        sys.exit(2)
    except Exception as exc:
        cli_logger.exception("Errore CLI security")
        log_event(
            cli_logger,
            "cli_error",
            {"error_type": type(exc).__name__, "error_message": str(exc)},
            level=logging.ERROR,
        )
        sys.stderr.write(f"Errore: {exc}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
