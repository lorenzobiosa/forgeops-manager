# -*- coding: utf-8 -*-
"""
===============================================================================
Pacchetto: src.providers.github
Descrizione:
    Implementazioni specifiche per GitHub:
      - Azioni su workflow, pacchetti, release, cache, sicurezza.
      - Servizio social (follow/unfollow) con API REST ufficiali.

Note:
    - Importare solo le API pubbliche principali (evitare import circolari/pesanti).
    - Le chiamate HTTP sono nei moduli specifici, non in questo __init__.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
===============================================================================
"""

from __future__ import annotations

# API principali (selezione ragionata)
from .actions import delete_all_completed_workflow_runs
from .cache import delete_all_actions_cache
from .packages import interactive_delete_packages
from .releases import delete_all_releases
from .security import clear_vulns
from .social import GitHubSocialService

__all__ = [
    "delete_all_completed_workflow_runs",
    "interactive_delete_packages",
    "delete_all_releases",
    "delete_all_actions_cache",
    "clear_vulns",
    "GitHubSocialService",
]
