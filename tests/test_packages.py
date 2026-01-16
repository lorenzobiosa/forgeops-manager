# pyright: reportPrivateUsage=false
# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: tests/test_packages.py
Descrizione:
  Test per operazioni su GitHub Packages (NON interattivi):
    - Listing dei packages (type=container) tramite `_list_packages`.
    - Cancellazione di versioni specifiche tramite `_delete_package_versions`.

Note:
  Il modulo `src.providers.github.packages` usa i wrapper HTTP `get`/`delete`
  importati in quel namespace dal modulo `src.utils.http_client`. Perciò i test
  patchano:
    - "src.providers.github.packages.get" (e fallback "src.utils.http_client.get")
    - "src.providers.github.packages.delete" (e fallback "src.utils.http_client.delete")
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional
from unittest.mock import MagicMock

from _pytest.monkeypatch import MonkeyPatch

import src.providers.github.packages as pkg_mod


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


def test_packages_list(monkeypatch: MonkeyPatch) -> None:
    """
    Simula il listing dei packages con filtro type=container usando la funzione NON interattiva.
    """
    # Fake response della API packages (lista "raw")
    fake_pkgs: List[Dict[str, Any]] = [
        {"id": 1, "name": "pkg1", "package_type": "container", "visibility": "public"},
        {"id": 2, "name": "pkg2", "package_type": "container", "visibility": "private"},
    ]
    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = fake_pkgs

    get_stub = GetStub(get_resp)

    # Patch del simbolo `get` nel namespace del modulo packages
    monkeypatch.setattr("src.providers.github.packages.get", get_stub, raising=True)
    # Fallback opzionale sul modulo di basso livello
    monkeypatch.setattr("src.utils.http_client.get", get_stub, raising=True)

    # Esecuzione: usa la funzione non-interattiva (evita prompt/input)
    out = pkg_mod._list_packages(("org", "acme"), "container")

    assert isinstance(out, list)
    assert {p["name"] for p in out} == {"pkg1", "pkg2"}
    assert get_stub.calls == 1


def test_packages_delete_versions(monkeypatch: MonkeyPatch) -> None:
    """
    Simula cancellazione delle versioni di un package con la funzione NON interattiva.
    """
    # DELETE -> 204
    del_resp = MagicMock()
    del_resp.status_code = 204
    delete_stub = DeleteStub(del_resp)

    # Patch del simbolo `delete` nel namespace del modulo packages
    monkeypatch.setattr("src.providers.github.packages.delete", delete_stub, raising=False)
    # Fallback opzionale sul modulo di basso livello
    monkeypatch.setattr("src.utils.http_client.delete", delete_stub, raising=True)

    # Esecuzione: usa la funzione non-interattiva
    pkg_mod._delete_package_versions(
        typ="org",
        name="acme",
        pkg_type="container",
        pkg_name="pkg1",
        version_ids=[111, 222, 333],
    )

    assert delete_stub.calls == 3
