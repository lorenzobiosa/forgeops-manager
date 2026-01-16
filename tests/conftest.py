# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: tests/conftest.py
Descrizione:
  Fixture comuni per la suite di test:
    - fake_logger: logger configurato per i test.
    - gh_token: token GitHub fittizio (non utilizzato realmente).
    - gh_repo: repository fittizio (owner/repo).
    - fake_session: sessione HTTP finta (MagicMock) con metodi .request() e .get()
      e attributo .headers, per simulare una `requests.Session` senza importare
      il pacchetto a livello di modulo (evita warning Pylance in ambienti senza
      requests installato lato editor).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture
def fake_logger() -> logging.Logger:
    """
    Restituisce un logger di test con livello DEBUG.
    """
    logger = logging.getLogger("tests")
    logger.setLevel(logging.DEBUG)
    return logger


@pytest.fixture
def gh_token() -> str:
    """
    Token GitHub fittizio. Non viene usato per chiamate reali.
    """
    return "ghp_test_token"


@pytest.fixture
def gh_repo() -> str:
    """
    Repository fittizio (owner/repo) usato nei test.
    """
    return "acme-org/my-repo"


@pytest.fixture
def fake_session(monkeypatch: MonkeyPatch) -> MagicMock:
    """
    Sessione HTTP finta con interfaccia minima compatibile con `requests.Session`,
    senza importare `requests` a livello di modulo.

    - Espone:
        * .headers (dict-like)
        * .request(method, url, **kwargs) -> response
        * .get(url, params=None) -> response
    - La response finta espone:
        * .status_code, .headers, .text, .json()
    - I test possono ridefinire i return value:
        sess.request.return_value = <MagicMock response custom>
        sess.get.return_value = <MagicMock response custom>
    """
    # Response finta con default "OK" JSON
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/json"}
    resp.text = ""
    resp.json.return_value = {}

    # Spec minimale per evitare errori di attributi inesistenti nei test
    sess = MagicMock(spec_set=["request", "get", "headers"])
    sess.headers = {}  # dict-like mutabile
    sess.request.return_value = resp
    sess.get.return_value = resp

    return sess
