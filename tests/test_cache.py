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
  Per evitare dipendenze dal pacchetto 'requests' a livello di modulo,
  si patcha `cache_mod.requests` con un MagicMock che espone `Session`.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict
from unittest.mock import MagicMock

from _pytest.monkeypatch import MonkeyPatch

import src.providers.github.cache as cache_mod


def test_delete_all_actions_cache(monkeypatch: MonkeyPatch) -> None:
    """
    Simula cancellazione cache Actions:
      - API GET lista cache
      - API DELETE per ogni cache_id
    """
    # Finta lista cache
    fake_list = {"actions_caches": [{"id": 1, "key": "k1"}, {"id": 2, "key": "k2"}]}

    # Sessione finta + response finta per GET
    session = MagicMock()
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = fake_list
    session.get.return_value = get_resp

    # Response finta per DELETE (204 = ok)
    del_resp = MagicMock()
    del_resp.status_code = 204
    session.delete.return_value = del_resp

    # Patch del modulo: emula `requests.Session()` che restituisce la sessione finta
    monkeypatch.setattr(cache_mod, "requests", MagicMock(Session=lambda: session))

    # Esegui la funzione, adattandoti alla firma reale per evitare errori di parametri
    func = cache_mod.delete_all_actions_cache
    sig = inspect.signature(func)
    params = sig.parameters

    # Costruisci kwargs dinamici solo con le chiavi presenti nella firma (tipizzati con Any)
    call_args: Dict[str, Any] = {}
    if "owner" in params:
        call_args["owner"] = "acme-org"
    if "repo" in params:
        call_args["repo"] = "my-repo"
    if "token" in params:
        call_args["token"] = "ghp_x"
    if "dry_run" in params:
        call_args["dry_run"] = False

    # Chiamata alla funzione con kwargs filtrati
    func(**call_args)

    # Asserzioni: GET chiamato, DELETE chiamato due volte (2 cache_id)
    assert session.get.called, "GET non è stato chiamato"
    assert session.delete.call_count == 2, "DELETE non è stato chiamato due volte come atteso"
