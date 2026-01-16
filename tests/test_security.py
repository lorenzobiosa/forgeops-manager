# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: tests/test_security.py
Descrizione:
  Test per la funzionalità di pulizia vulnerabilità (Code Scanning) su GitHub:
    - Flow `mode=delete`: elimina analyses cancellabili e ritorna (scanned, deleted).
    - Flow `mode=dismiss`: imposta dismissed sulle alert e ritorna (scanned, dismissed).
    - Validazione reason non valido: solleva ValueError.
  Il test patcha le dipendenze principali del modulo `src.providers.github.security`
  (sessione HTTP tramite `ensure_github_token_ready` e costruttore del client)
  usando `monkeypatch.setattr`, evitando dipendenze da rete e da `requests`.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.providers.github import security as sec_mod


def test_clear_vulns_delete_flow(
    gh_repo: str,
    gh_token: str,
    fake_session: MagicMock,
    fake_logger: logging.Logger,
    monkeypatch: MonkeyPatch,
) -> None:
    """
    Verifica: clear_vulns(mode=delete)
      - analizza items, cancella quelli deletable
      - restituisce (scanned, deleted)
    """

    # Stub tipizzato per evitare warning su lambda **kwargs
    def _ensure_ready_stub(**kwargs: Any) -> MagicMock:
        return fake_session

    monkeypatch.setattr(sec_mod, "ensure_github_token_ready", _ensure_ready_stub)

    # Prepara client mock
    mock_client: MagicMock = MagicMock(spec=sec_mod.GitHubSecurityClient)
    # Stream analyses: 3 item, 2 cancellabili
    analyses = [
        {"id": 101, "deletable": True, "tool": {"name": "Trivy"}},
        {"id": 102, "deletable": False, "tool": {"name": "Grype"}},
        {"id": 103, "deletable": True, "tool": {"name": "Grype"}},
    ]
    mock_client.list_code_scanning_analyses.return_value = analyses
    mock_client.delete_analysis.side_effect = [None, None]

    # Costruttore client stub
    def _client_factory_stub(*args: Any, **kwargs: Any) -> MagicMock:
        return mock_client

    monkeypatch.setattr(sec_mod, "GitHubSecurityClient", _client_factory_stub)

    result = sec_mod.clear_vulns(
        repo=gh_repo,
        mode="delete",
        token=gh_token,
        tools="Trivy,Grype",
        dry_run=False,
        session=None,
    )

    assert result["scanned"] == 3
    assert result["deleted"] == 2
    assert mock_client.delete_analysis.call_count == 2


def test_clear_vulns_dismiss_flow(
    gh_repo: str,
    gh_token: str,
    fake_session: MagicMock,
    fake_logger: logging.Logger,
    monkeypatch: MonkeyPatch,
) -> None:
    """
    Verifica: clear_vulns(mode=dismiss)
      - itera sulle alert, fa PATCH con reason/comment
      - restituisce (scanned, dismissed)
    """

    def _ensure_ready_stub(**kwargs: Any) -> MagicMock:
        return fake_session

    monkeypatch.setattr(sec_mod, "ensure_github_token_ready", _ensure_ready_stub)

    mock_client: MagicMock = MagicMock(spec=sec_mod.GitHubSecurityClient)
    alerts = [
        {"number": 11, "tool": {"name": "Trivy"}, "rule": {"id": "R1"}},
        {"number": 12, "tool": {"name": "Grype"}, "rule": {"name": "R2-name"}},
        {"number": "bad", "tool": {"name": "Trivy"}},  # skip (numero non intero)
    ]
    mock_client.list_code_scanning_alerts.return_value = alerts
    mock_client.dismiss_alert.side_effect = [None, None]

    def _client_factory_stub(*args: Any, **kwargs: Any) -> MagicMock:
        return mock_client

    monkeypatch.setattr(sec_mod, "GitHubSecurityClient", _client_factory_stub)

    result = sec_mod.clear_vulns(
        repo=gh_repo,
        mode="dismiss",
        token=gh_token,
        tools="Trivy,Grype",
        reason="won't_fix",
        comment="OK",
        state="open",
        dry_run=False,
        session=None,
    )

    assert result["scanned"] == 3
    assert result["dismissed"] == 2
    assert mock_client.dismiss_alert.call_count == 2


def test_clear_vulns_reason_invalid_raises(
    gh_repo: str,
    gh_token: str,
    fake_session: MagicMock,
    monkeypatch: MonkeyPatch,
) -> None:
    """
    Verifica che reason invalido per mode=dismiss causi ValueError.
    """

    def _ensure_ready_stub(**kwargs: Any) -> MagicMock:
        return fake_session

    monkeypatch.setattr(sec_mod, "ensure_github_token_ready", _ensure_ready_stub)

    with pytest.raises(ValueError):
        sec_mod.clear_vulns(
            repo=gh_repo,
            mode="dismiss",
            token=gh_token,
            tools="Trivy",
            reason="invalid",
            comment="",
            state="open",
            dry_run=False,
        )
