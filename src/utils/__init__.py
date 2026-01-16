# -*- coding: utf-8 -*-
"""
===============================================================================
Pacchetto: src.utils
Descrizione:
    Utilità comuni riutilizzabili:
      - Logging universale (setup/get_logger/log_event).
      - Configurazione (parsing ENV, impostazioni job social-sync).
      - HTTP helpers (wrapper/timeout/backoff) se presenti.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
===============================================================================
"""

from __future__ import annotations

from .config import (
    SocialSyncSettings,
    get_owner_repo,
    get_social_sync_settings,
    get_username_or_org,
)
from .structured_logging import get_logger, log_event, setup_logging

# Se vuoi esporre http helpers (opzionale)
# from .http import <funzioni/classes>

__all__ = [
    "get_logger",
    "setup_logging",
    "log_event",
    "get_owner_repo",
    "get_username_or_org",
    "get_social_sync_settings",
    "SocialSyncSettings",
]
