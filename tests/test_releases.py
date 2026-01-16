# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: tests/test_releases.py
Descrizione:
  Test per l’eliminazione di tutte le GitHub Releases:
    - GET paginato per elencare le releases.
    - DELETE di ogni release elencata.
  I test patchano il modulo `src.providers.github.releases` per emulare
  una `requests.Session` senza importare il pacchetto a livello di modulo,
  riducendo warning Pylance in ambienti dove l’editor non risolve `requests`.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict
from unittest.mock import MagicMock

from _pytest.monkeypatch import MonkeyPatch

import src.providers.github.releases as rel_mod


def test_delete_all_releases(monkeypatch: MonkeyPatch) -> None:
    """
    Simula eliminazione di tutte le releases:
      - GET elenca releases (paginato)
      - DELETE ogni release
    """
    session = MagicMock()

    # GET page 1 -> 2 releases, page 2 -> vuoto
    get_resp1 = MagicMock()
    get_resp1.status_code = 200
    get_resp1.json.return_value = [{"id": 10}, {"id": 20}]

    get_resp2 = MagicMock()
    get_resp2.status_code = 200
    get_resp2.json.return_value = []

    # get() restituirà prima get_resp1 poi get_resp2
    session.get.side_effect = [get_resp1, get_resp2]

    # DELETE -> 204
    del_resp = MagicMock()
    del_resp.status_code = 204
    session.delete.return_value = del_resp

    # Patch del modulo: emula `requests.Session()` che restituisce la sessione finta
    monkeypatch.setattr(rel_mod, "requests", MagicMock(Session=lambda: session))

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

    func(**call_args) if call_args else func()

    # Asserzioni: almeno una GET (paginazione), DELETE per ciascuna release (2)
    assert session.get.call_count >= 1, "GET non è stato chiamato come atteso"
    assert session.delete.call_count == 2, "DELETE non è stato chiamato due volte come atteso"
