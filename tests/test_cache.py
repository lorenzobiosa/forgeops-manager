# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: tests/test_cache.py
Descrizione:
  Test della funzionalità di cancellazione della cache di GitHub Actions.
  Il test simula:
    - una lista di cache restituita dall'API (GET),
    - la cancellazione delle entry (DELETE).
  Nota:
    - La lista dei cache viene letta tramite paginate() in src.providers.github.api,
      che usa il simbolo `get` importato in quel modulo → patch di "src.providers.github.api.get".
    - La cancellazione usa gh_delete() in src.providers.github.api, che chiama il simbolo
      `delete` importato in quel modulo → patch di "src.providers.github.api.delete".
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, Mapping, Optional
from unittest.mock import MagicMock

from _pytest.monkeypatch import MonkeyPatch

import src.providers.github.cache as cache_mod


class GetStub:
    """Stub tipizzato per simulare il wrapper HTTP `get`."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: int = 0

    def __call__(self, url: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        self.calls += 1
        return self.response


class DeleteStub:
    """Stub tipizzato per simulare il wrapper HTTP `delete`."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: int = 0

    def __call__(self, url: str, **kwargs: Any) -> Any:
        self.calls += 1
        return self.response


def test_delete_all_actions_cache(monkeypatch: MonkeyPatch) -> None:
    """
    Simula cancellazione cache Actions:
      - API GET lista cache
      - API DELETE per ogni cache_id
    """
    # Finta lista cache restituita da GET
    fake_list: Dict[str, Any] = {"actions_caches": [{"id": 1, "key": "k1"}, {"id": 2, "key": "k2"}]}

    # Response finte coerenti con il modulo sotto test
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = fake_list

    del_resp = MagicMock()
    del_resp.status_code = 204

    # Stub tipizzati
    get_stub = GetStub(get_resp)
    delete_stub = DeleteStub(del_resp)

    # --- Patch target effettivamente usati a runtime ---
    # 1) paginate() in src.providers.github.api usa `get` importato in quel modulo
    monkeypatch.setattr("src.providers.github.api.get", get_stub, raising=True)
    # (opzionale, ma utile) patch anche il modulo di basso livello
    monkeypatch.setattr("src.utils.http_client.get", get_stub, raising=True)

    # 2) gh_delete() in src.providers.github.api usa `delete` importato in quel modulo
    monkeypatch.setattr("src.providers.github.api.delete", delete_stub, raising=True)
    # (opzionale) fallback sul modulo di basso livello
    monkeypatch.setattr("src.utils.http_client.delete", delete_stub, raising=True)

    # Esegue la funzione adattandosi alla firma reale per evitare errori sui parametri
    func = cache_mod.delete_all_actions_cache
    sig = inspect.signature(func)
    params = sig.parameters

    # Costruzione kwargs dinamici solo per i parametri presenti nella firma
    call_args: Dict[str, Any] = {}
    if "owner" in params:
        call_args["owner"] = "acme-org"
    if "repo" in params:
        call_args["repo"] = "my-repo"
    if "token" in params:
        call_args["token"] = "ghp_x"
    if "dry_run" in params:
        call_args["dry_run"] = False

    # Invocazione
    func(**call_args)

    # Asserzioni: 1 chiamata GET e 2 chiamate DELETE (due cache_id)
    assert get_stub.calls == 1, "GET non è stato chiamato una volta"
    assert delete_stub.calls == 2, "DELETE non è stato chiamato due volte come atteso"
