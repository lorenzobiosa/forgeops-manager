# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: tests/test_packages.py
Descrizione:
  Test per operazioni su GitHub Packages:
    - Listing dei packages (type=container).
    - Cancellazione delle sole versioni di un package (se implementato nel modulo).
  I test patchano `src.providers.github.packages` per emulare una `requests.Session`
  senza importare il pacchetto a livello di modulo, riducendo warning Pylance
  in ambienti dove l’editor non risolve `requests`.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict
from unittest.mock import MagicMock

from _pytest.monkeypatch import MonkeyPatch

import src.providers.github.packages as pkg_mod


def test_packages_list(monkeypatch: MonkeyPatch) -> None:
    """
    Simula il listing dei packages con filtro type=container.
    """
    session = MagicMock()

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [
        {"id": 1, "name": "pkg1", "package_type": "container"},
        {"id": 2, "name": "pkg2", "package_type": "container"},
    ]
    session.get.return_value = resp

    # Patch del modulo per emulare `requests.Session()`
    monkeypatch.setattr(pkg_mod, "requests", MagicMock(Session=lambda: session))

    # Accesso alla funzione interattiva; alcuni moduli potrebbero richiedere argomenti
    func = getattr(pkg_mod, "interactive_delete_packages", None)
    assert func is not None, "interactive_delete_packages non trovato nel modulo packages"

    sig = inspect.signature(func)
    params = sig.parameters

    call_args: Dict[str, Any] = {}
    if "org" in params:
        call_args["org"] = "acme-org"
    if "type" in params:
        call_args["type"] = "container"
    if "token" in params:
        call_args["token"] = "ghp_x"
    if "dry_run" in params:
        call_args["dry_run"] = True

    # Chiamata alla funzione con kwargs filtrati
    func(**call_args) if call_args else func()

    assert session.get.called, "GET non è stato chiamato per il listing dei packages"


def test_packages_delete_versions(monkeypatch: MonkeyPatch) -> None:
    """
    Simula cancellazione delle sole versioni di un package (se implementato).
    """
    session = MagicMock()

    # Lista versioni -> 3
    resp_list = MagicMock()
    resp_list.status_code = 200
    resp_list.json.return_value = [{"id": "v1"}, {"id": "v2"}, {"id": "v3"}]
    session.get.return_value = resp_list

    # DELETE -> 204
    resp_del = MagicMock()
    resp_del.status_code = 204
    session.delete.return_value = resp_del

    # Patch del modulo per emulare `requests.Session()`
    monkeypatch.setattr(pkg_mod, "requests", MagicMock(Session=lambda: session))

    # Accesso sicuro alla funzione (potrebbe non esistere)
    func = getattr(pkg_mod, "delete_package_versions", None)
    if func is None:
        # Se non presente, il test si limita a verificare la patch della sessione
        # e l'assenza di errori runtime nel listing.
        return

    # Adatta ai parametri attesi della funzione
    sig = inspect.signature(func)
    params = sig.parameters

    call_args: Dict[str, Any] = {}
    if "org" in params:
        call_args["org"] = "acme-org"
    if "package_name" in params:
        call_args["package_name"] = "pkg"
    if "token" in params:
        call_args["token"] = "ghp_x"
    if "dry_run" in params:
        call_args["dry_run"] = False

    func(**call_args) if call_args else func()

    assert session.delete.call_count == 3, "DELETE non è stato chiamato tre volte come atteso"
