# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: tests/test_releases.py
Descrizione:
  Test per l’eliminazione di tutte le GitHub Releases:
    - GET (via paginate) per elencare le releases.
    - DELETE (via gh_delete) di ogni release elencata.

Note:
  Il modulo `src.providers.github.releases` non usa `requests.Session` direttamente:
  - l’elenco è fatto tramite paginate() in `src.providers.github.api`,
    che usa il simbolo `get` importato in quel modulo → patch di "src.providers.github.api.get";
  - la cancellazione usa gh_delete() in `src.providers.github.api`,
    che chiama il simbolo `delete` importato in quel modulo → patch di
    "src.providers.github.api.delete".
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Mapping, Optional
from unittest.mock import MagicMock

from _pytest.monkeypatch import MonkeyPatch

import src.providers.github.releases as rel_mod


class GetStub:
    """Stub tipizzato per simulare il wrapper HTTP `get` (paginazione)."""

    def __init__(self, responses: List[Any]) -> None:
        """
        responses: lista di Response mock per simulare pagine.
        Se le risposte fornite sono una sola, paginate farà una sola GET.
        """
        self._responses: List[Any] = list(responses)
        self.calls: int = 0

    def __call__(self, url: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        self.calls += 1
        idx = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[idx]


class DeleteStub:
    """Stub tipizzato per simulare il wrapper HTTP `delete`."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: int = 0

    def __call__(self, url: str, **kwargs: Any) -> Any:
        self.calls += 1
        return self.response


def test_delete_all_releases(monkeypatch: MonkeyPatch) -> None:
    """
    Simula eliminazione di tutte le releases:
      - GET elenca releases (paginato)
      - DELETE ogni release
    """
    # Page 1 -> 2 releases
    get_resp1 = MagicMock()
    get_resp1.status_code = 200
    get_resp1.json.return_value = [{"id": 10}, {"id": 20}]

    # Page 2 -> lista vuota (in molti casi paginate interrompe già a page 1)
    get_resp2 = MagicMock()
    get_resp2.status_code = 200
    get_resp2.json.return_value = []

    # Stub GET per paginate: forniamo due risposte per coprire entrambi i rami
    get_stub = GetStub([get_resp1, get_resp2])

    # Stub DELETE -> 204 (una per ciascuna release)
    del_resp = MagicMock()
    del_resp.status_code = 204
    delete_stub = DeleteStub(del_resp)

    # --- Patch dei target effettivi usati a runtime ---
    # paginate() usa `get` importato in src.providers.github.api
    monkeypatch.setattr("src.providers.github.api.get", get_stub, raising=True)
    # (facoltativo) fallback sul modulo di basso livello
    monkeypatch.setattr("src.utils.http_client.get", get_stub, raising=True)

    # gh_delete() usa `delete` importato in src.providers.github.api
    monkeypatch.setattr("src.providers.github.api.delete", delete_stub, raising=True)
    # (facoltativo) fallback sul modulo di basso livello
    monkeypatch.setattr("src.utils.http_client.delete", delete_stub, raising=True)

    # Invoca la funzione adattandoti alla firma reale per evitare mismatch parametri
    func = rel_mod.delete_all_releases
    sig = inspect.signature(func)
    params = sig.parameters

    call_args: Dict[str, Any] = {}
    if "owner" in params:
        call_args["owner"] = "acme-org"
    if "repo" in params:
        call_args["repo"] = "my-repo"
    if "token" in params:
        call_args["token"] = "ghp_x"
    if "dry_run" in params:
        call_args["dry_run"] = False

    # Esecuzione
    func(**call_args) if call_args else func()

    # Asserzioni:
    # - paginate ha fatto almeno una GET
    assert get_stub.calls >= 1, "GET non è stato chiamato come atteso"
    # - DELETE chiamato per ciascuna release (2)
    assert delete_stub.calls == 2, f"DELETE attese=2, trovate={delete_stub.calls}"
