# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: structured_logging.py
Descrizione:
    Logging universale, strutturato e "enterprise/production-ready", con:
      - JSON logger (default) o plain text.
      - Idempotenza della configurazione.
      - Event logging coerente: `log_event(logger, event, payload, level=...)`.
      - Correlazione/Trace:
          * `request_id` (ContextVar) incluso in ogni log.
          * Propagazione HTTP: `X-Request-ID` (+ alias `X-Correlation-ID`).
      - MDC/Context aggiuntivo (ContextVar dict) per arricchire i log.
      - Redazione automatica di campi sensibili (token, secret, password...).
      - Opzionale file logging con rotazione (env LOG_FILE / LOG_MAX_BYTES / LOG_BACKUP_COUNT).

Variabili d'ambiente supportate:
    LOG_LEVEL        = DEBUG|INFO|WARNING|ERROR|CRITICAL (default: INFO)
    LOG_JSON         = true|false                         (default: true)
    LOG_CONSOLE      = true|false                         (default: false)
    LOG_FILE         = path al file di log (disabilitato se vuoto)
    LOG_MAX_BYTES    = dimensione rotazione in byte (default: 5_000_000)
    LOG_BACKUP_COUNT = numeri file di backup (default: 3)

Uso tipico:
    from utils.logging import (
        setup_logging, get_logger, log_event,
        new_request_id, request_id_context,
        set_context, scoped_context,
        get_correlation_headers, attach_correlation_to_session,
    )

    setup_logging()
    logger = get_logger(__name__)

    rid = new_request_id()
    log_event(logger, "startup", {"version": "1.0.0"})

    with scoped_context(repo="owner/repo", operation="clear-vulns"):
        log_event(logger, "operation_begin", {"dry_run": False})

    # Propagazione richieste verso GitHub:
    session = requests.Session()
    attach_correlation_to_session(session)  # aggiunge X-Request-ID/X-Correlation-ID
    session.get(url, headers=get_correlation_headers())

Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.
===============================================================================
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

try:
    # Rotating file handler (opzionale)
    from logging.handlers import RotatingFileHandler
except Exception:  # pragma: no cover
    RotatingFileHandler = None  # type: ignore

__all__ = [
    "setup_logging",
    "get_logger",
    "log_event",
    # Correlazione / trace
    "REQUEST_ID_HEADER",
    "CORRELATION_ID_HEADER",
    "new_request_id",
    "set_request_id",
    "get_request_id",
    "request_id_context",
    # MDC / context
    "set_context",
    "clear_context",
    "get_context",
    "scoped_context",
    # Propagazione header
    "get_correlation_headers",
    "attach_correlation_to_session",
]

# -----------------------------------------------------------------------------
# Stato della configurazione
# -----------------------------------------------------------------------------
_configured: bool = False
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"
_DEFAULT_PLAIN_FMT = "%(asctime)s %(levelname)s %(name)s - %(message)s"

# -----------------------------------------------------------------------------
# Correlazione / Trace ID (ContextVar)
# -----------------------------------------------------------------------------
REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"

# Evita default calcolati per B039: usa None e genera on-demand
_request_id_cv: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """Genera e imposta un nuovo request_id nel contesto corrente."""
    rid = uuid.uuid4().hex
    _request_id_cv.set(rid)
    return rid


def set_request_id(request_id: str) -> str:
    """Imposta un request_id specifico nel contesto corrente."""
    if not request_id:
        raise ValueError("request_id non valido: deve essere una stringa non vuota.")
    _request_id_cv.set(request_id)
    return request_id


def get_request_id() -> str:
    """
    Restituisce il request_id corrente dal contesto.
    Se assente, ne genera uno e lo imposta (lazy init).
    """
    rid = _request_id_cv.get()
    if not rid:
        rid = uuid.uuid4().hex
        _request_id_cv.set(rid)
    return rid


@contextlib.contextmanager
def request_id_context(request_id: Optional[str] = None) -> Iterator[str]:
    """
    Context manager per impostare un `request_id` temporaneo (nuovo o fornito).
    Ripristina il precedente al termine.
    """

    rid: str = request_id or uuid.uuid4().hex
    token = _request_id_cv.set(rid)
    try:
        yield rid
    finally:
        _request_id_cv.reset(token)


# -----------------------------------------------------------------------------
# MDC / Context (campi extra da includere in ogni log)
# -----------------------------------------------------------------------------
# Evita default mutabile per B039: usa None e crea dict on-demand
_context_cv: ContextVar[Optional[Dict[str, Any]]] = ContextVar("mdc_context", default=None)


def set_context(key: str, value: Any) -> None:
    """Imposta/aggiorna un campo nel contesto MDC."""
    ctx = _context_cv.get()
    if ctx is None:
        ctx = {}
    else:
        ctx = dict(ctx)  # copia difensiva
    ctx[key] = value
    _context_cv.set(ctx)


def clear_context(keys: Optional[list[str]] = None) -> None:
    """Rimuove uno o più campi dal contesto MDC; se keys è None, svuota tutto."""
    if keys is None:
        _context_cv.set(None)
        return
    ctx = _context_cv.get()
    if not ctx:
        return
    new_ctx = dict(ctx)
    for k in keys:
        new_ctx.pop(k, None)
    _context_cv.set(new_ctx)


def get_context() -> Dict[str, Any]:
    """Restituisce una copia del contesto MDC corrente."""
    ctx = _context_cv.get()
    if not ctx:
        return {}
    return dict(ctx)


@contextlib.contextmanager
def scoped_context(**kwargs: Any) -> Iterator[Dict[str, Any]]:
    """
    Context manager per aggiungere campi MDC in un blocco logico (repo, operation, user, ecc.).
    Ripristina il precedente al termine.
    """
    prev = _context_cv.get()
    if prev is None:
        prev = {}
    else:
        prev = dict(prev)
    merged = dict(prev)
    merged.update(kwargs)
    token = _context_cv.set(merged)
    try:
        yield merged
    finally:
        _context_cv.reset(token)


# -----------------------------------------------------------------------------
# Redazione automatica di segreti
# -----------------------------------------------------------------------------
_SENSITIVE_KEYS = {
    "token",
    "github_token",
    "gh_token",
    "authorization",
    "password",
    "secret",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "refresh_token",
}


def _redact_value(v: Any) -> Any:
    """Redazione base: converte in stringa e nasconde contenuto."""
    try:
        s = str(v)
    except Exception:
        s = "<unserializable>"
    if not s:
        return s
    # conserva solo le prime/ultime 4, se sufficienti
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}***{s[-4:]}"


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Applica redazione ai campi sensibili nel payload."""
    safe: Dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in _SENSITIVE_KEYS:
            safe[k] = _redact_value(v)
        else:
            # prova serializzazione; se fallisce, cast a stringa
            try:
                json.dumps(v)
                safe[k] = v
            except Exception:
                safe[k] = str(v)
    return safe


# -----------------------------------------------------------------------------
# JSON Formatter
# -----------------------------------------------------------------------------
class _JsonLogFormatter(logging.Formatter):
    """
    Serializza il record di log in JSON con campi standard + correlazione + MDC.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        base: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "host": socket.gethostname(),
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        # Allegare MDC
        mdc = get_context()
        if mdc:
            # redazione MDC se contiene possibili segreti
            base["mdc"] = _redact_payload(mdc)

        # Allegare eccezione se presente
        if record.exc_info:
            try:
                base["exc_info"] = self.formatException(record.exc_info)
            except Exception:
                base["exc_info"] = "traceback_unavailable"

        # Allegare extra custom del record (evitando campi di sistema)
        skip = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
        }
        for key, value in record.__dict__.items():
            if key not in skip and key not in base:
                try:
                    json.dumps(value)
                    base[key] = value
                except Exception:
                    base[key] = str(value)

        try:
            return json.dumps(base, ensure_ascii=False)
        except Exception:
            # Fallback robusto
            return json.dumps(
                {
                    "ts": base["ts"],
                    "level": base["level"],
                    "logger": base["logger"],
                    "message": str(base.get("message")),
                },
                ensure_ascii=False,
            )


# -----------------------------------------------------------------------------
# Configurazione centralizzata
# -----------------------------------------------------------------------------
def setup_logging(
    level: Optional[str] = None,
    json_mode: Optional[bool] = None,
    *,
    console: Optional[bool] = None,
) -> None:
    """
    Configura il logging di processo in modo idempotente.

    Args:
        level: livello di log (DEBUG/INFO/WARNING/ERROR/CRITICAL) — default: LOG_LEVEL.
        json_mode: True → JSON, False → plain — default: LOG_JSON.
        console: True/False abilita lo stdout — default: LOG_CONSOLE.

    Aggiunge opzionalmente un RotatingFileHandler se LOG_FILE è definito.
    """
    global _configured
    if _configured:
        return

    lvl_raw: Optional[str] = level if level is not None else os.getenv("LOG_LEVEL")
    env_level = (lvl_raw or "INFO").upper().strip()
    use_json = json_mode if json_mode is not None else _env_flag("LOG_JSON", default=True)
    use_console = console if console is not None else _env_flag("LOG_CONSOLE", default=False)

    root = logging.getLogger()
    root.setLevel(_parse_level(env_level))

    # Console handler
    if use_console:
        ch = logging.StreamHandler()
        ch.setFormatter(
            _JsonLogFormatter()
            if use_json
            else logging.Formatter(fmt=_DEFAULT_PLAIN_FMT, datefmt=_DEFAULT_DATEFMT)
        )
        root.addHandler(ch)
    else:
        root.addHandler(logging.NullHandler())

    # File handler (opzionale)
    log_file = os.getenv("LOG_FILE", "").strip()
    if log_file and RotatingFileHandler is not None:
        max_bytes = int(os.getenv("LOG_MAX_BYTES", "5000000"))
        backups = int(os.getenv("LOG_BACKUP_COUNT", "3"))
        fh = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
        )
        fh.setFormatter(
            _JsonLogFormatter()
            if use_json
            else logging.Formatter(fmt=_DEFAULT_PLAIN_FMT, datefmt=_DEFAULT_DATEFMT)
        )
        root.addHandler(fh)

    _configured = True


def get_logger(
    name: str, *, level: Optional[str] = None, json_mode: Optional[bool] = None
) -> logging.Logger:
    """
    Restituisce un logger coerente; garantisce setup idempotente.
    """
    setup_logging(level=None, json_mode=json_mode)
    logger = logging.getLogger(name)
    if level:
        logger.setLevel(_parse_level(level))
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    level: int = logging.INFO,
) -> None:
    """
    Registra un evento applicativo coerente, con redazione campi sensibili.

    Il messaggio JSON include:
      - ts, event, request_id
      - mdc (se presente)
      - payload (safe/redacted)
    """
    safe_payload = _redact_payload(payload or {})
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "request_id": get_request_id(),
        **safe_payload,
    }
    try:
        message = json.dumps(entry, ensure_ascii=False)
    except Exception:
        message = f"{event} | {safe_payload} | request_id={get_request_id()}"
    logger.log(level, message)


# -----------------------------------------------------------------------------
# Propagazione correlazione verso HTTP client (GitHub/API)
# -----------------------------------------------------------------------------
def get_correlation_headers() -> Dict[str, str]:
    """
    Restituisce le intestazioni HTTP di correlazione:
      - X-Request-ID
      - X-Correlation-ID (alias)
    """
    rid = get_request_id()
    return {
        REQUEST_ID_HEADER: rid,
        CORRELATION_ID_HEADER: rid,
    }


def attach_correlation_to_session(session: Any) -> None:
    """
    Inietta gli header di correlazione nella `requests.Session` fornita.
    Best-effort: non solleva errori se la sessione non espone .headers.
    """
    try:
        h = getattr(session, "headers", None)
        if isinstance(h, dict):
            rid = get_request_id()
            session.headers[REQUEST_ID_HEADER] = rid
            session.headers[CORRELATION_ID_HEADER] = rid
    except Exception:  # nosec B110 - best-effort: non interrompere il flusso applicativo
        pass


# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------
def _parse_level(value: Optional[str]) -> int:
    if value is None:
        return logging.INFO
    mapping = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }
    return mapping.get(value.upper().strip(), logging.INFO)


def _env_flag(name: str, *, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")
