# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: api.py
Descrizione:
    Helper per interagire con la API di GitHub (wrapper generici).
    - `paginate`: itera su risposte paginabili della API (array raw o dizionari).
    - `owner_repo_or_prompt`: recupera owner/repo con fallback a prompt/ENV.
    - `gh_delete`: esegue una DELETE robusta con gestione degli errori.

Dipendenze:
    - src.utils.http: get, delete
    - src.utils.config: get_owner_repo
    - src.utils.logging: get_logger, log_event

Linee guida:
    - Tipizzazione esplicita e conforme a Pylance/mypy.
    - Messaggi ed eccezioni in italiano.
    - Logging strutturato (JSON) per osservabilità.
    - Comportamento difensivo su JSON eterogeneo (array raw o dizionari).
    - Nessuna assunzione forte sulla paginazione oltre a `per_page`/`page`
      e alla dimensione del batch restituito.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Licenza:
    Questo file è rilasciato secondo i termini della licenza del repository.
===============================================================================
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, cast

import requests

from src.utils.config import get_owner_repo
from src.utils.http_client import delete, get
from src.utils.structured_logging import get_logger, log_event

__all__ = ["paginate", "owner_repo_or_prompt", "gh_delete"]

# Logger di modulo (coerente con il logging strutturato del progetto)
_logger = get_logger(__name__)


# Helper interno: filtra una sequenza tenendo solo i dict[str, Any]
def _only_dicts(seq: Sequence[object]) -> List[Dict[str, Any]]:
    """
    , Any].+    Restituisce una lista contenente solo gli elementi di `seq` che sono dizionari,
    """
    out: List[Dict[str, Any]] = []
    for e in seq:
        if isinstance(e, dict):
            out.append(cast(Dict[str, Any], e))
    return out


def paginate(
    url: str,
    params: Optional[Mapping[str, Any]] = None,
    array_key: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """
    Itera su risposte paginabili della API GitHub.

    Supporta due forme comuni di risposta JSON:
      - Array "raw": es. `[ { ... }, { ... } ]`
      - Dizionario che avvolge un array: es. `{ "workflow_runs": [ ... ] }`

    Args:
        url: Endpoint base della API da interrogare.
        params: Parametri query opzionali (es. {"status": "completed"}).
        array_key: Chiave esplicita dell'array da estrarre in caso di risposta dizionario.
                   Utile quando l'API avvolge i risultati (es. "workflow_runs", "caches").

    Yields:
        Dict[str, Any]: Singoli elementi dalla risposta paginata.

    Raises:
        RuntimeError: se la risposta è un dizionario e non è possibile determinare
                      la chiave dell'array da cui estrarre gli elementi.
        RuntimeError: se il tipo della risposta JSON è inatteso.
    """
    page: int = 1
    while True:
        # Costruzione parametri di pagina con default coerenti
        p: Dict[str, Any] = dict(params or {})
        per_page_val_raw: Any = p.get("per_page", 100)
        try:
            per_page_val: int = int(per_page_val_raw)
        except (TypeError, ValueError):
            per_page_val = 100
        # Bound tra 1 e 100 (limite GitHub)
        per_page_val = max(1, min(per_page_val, 100))

        p["per_page"] = per_page_val
        p["page"] = page

        # Log richiesta paginata
        log_event(
            _logger,
            "paginate_request",
            {
                "url": url,
                "page": page,
                "per_page": per_page_val,
                "params": dict(params or {}),
            },
        )

        # Richiesta HTTP (annotazione esplicita per Pylance)
        r: requests.Response = get(url, params=p)
        r.raise_for_status()
        data: Any = r.json()

        items: List[Dict[str, Any]] = []

        if isinstance(data, list):
            # Risposta come array raw: cast esplicito a List[object]
            data_list: List[object] = cast(List[object], data)
            items = _only_dicts(data_list)

        elif isinstance(data, dict):
            # Risposta come dizionario; cast esplicito a Dict[str, object]
            data_dict: Dict[str, object] = cast(Dict[str, object], data)

            # Individua la chiave contenente l'array
            key: Optional[str] = array_key

            # Fallback per endpoint GitHub comuni se array_key non è fornita
            if key is None:
                if "workflow_runs" in data_dict:
                    key = "workflow_runs"
                elif "caches" in data_dict:
                    key = "caches"

            if key is not None and key in data_dict and isinstance(data_dict[key], list):
                inner: List[object] = cast(List[object], data_dict[key])
                items = _only_dicts(inner)

            else:
                # Ultima risorsa: prima voce di tipo lista nel dizionario
                candidate: Optional[List[Dict[str, Any]]] = None

                # Otteniamo le values con tipo noto
                values_list: List[object] = list(data_dict.values())

                for v_any in values_list:
                    if isinstance(v_any, list):
                        v_list: List[object] = cast(List[object], v_any)
                        candidate = _only_dicts(v_list)
                        break

                if candidate is not None:
                    items = candidate
                else:
                    # Errore esplicito con elenco chiavi disponibili (tipizzate come str)
                    keys_list: List[str] = list(data_dict.keys())
                    msg = (
                        "paginate: impossibile determinare la chiave dell'array \
                            nella risposta di tipo dict. "
                        f"Chiavi disponibili: {keys_list}. "
                        f"Specificare 'array_key' per URL={url}"
                    )
                    log_event(
                        _logger,
                        "paginate_error_array_key",
                        {"url": url, "page": page, "keys": keys_list},
                        level=30,
                    )
                    raise RuntimeError(msg)
        else:
            msg = f"paginate: tipo di risposta inatteso {type(data).__name__} da URL={url}"
            log_event(
                _logger,
                "paginate_error_type",
                {"url": url, "page": page, "resp_type": type(data).__name__},
                level=30,
            )
            raise RuntimeError(msg)

        # Nessun elemento: interrompe
        if not items:
            log_event(_logger, "paginate_empty_page", {"url": url, "page": page})
            break

        # Log della pagina ottenuta
        log_event(_logger, "paginate_page_ok", {"url": url, "page": page, "count": len(items)})

        # Emetti gli elementi della pagina (già dict)
        for item in items:
            yield item

        # Se la dimensione della pagina è inferiore a per_page, è ultima pagina
        if len(items) < per_page_val:
            log_event(
                _logger,
                "paginate_last_page",
                {"url": url, "page": page, "count": len(items)},
            )
            break

        page += 1


def owner_repo_or_prompt(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Recupera (owner, repo) da parametri o via ENV/prompt tramite `get_owner_repo`.

    Args:
        owner: Owner/organizzazione GitHub (override).
        repo: Nome del repository (override).

    Returns:
        Tuple[str, str]: coppia (owner, repo) non vuota.
    """
    # Nessun logging qui per evitare messaggi duplicati: è responsabilità del caller
    return get_owner_repo(owner, repo)


def gh_delete(url: str, params: Optional[Mapping[str, Any]] = None) -> None:
    """
    Esegue una richiesta HTTP DELETE verso l'endpoint specificato.

    Args:
        url: Endpoint completo della API.
        params: Parametri query opzionali.

    Raises:
        RuntimeError: se lo status HTTP non è tra quelli di successo (200, 202, 204).
    """
    log_event(_logger, "gh_delete_request", {"url": url, "params": dict(params or {})})
    r: requests.Response = delete(url, params=params)
    status: int = r.status_code
    if status not in (200, 202, 204):
        body: str = r.text
        log_event(
            _logger,
            "gh_delete_error",
            {"url": url, "status": status, "body": body},
            level=30,
        )
        raise RuntimeError(f"DELETE fallita ({status}): {body}")
    log_event(_logger, "gh_delete_ok", {"url": url, "status": status})
