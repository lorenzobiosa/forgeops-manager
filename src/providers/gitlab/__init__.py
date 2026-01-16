# -*- coding: utf-8 -*-
"""
===============================================================================
Pacchetto: src.providers.gitlab
Descrizione:
    Implementazioni per GitLab. Attualmente include un provider mock per test
    e dimostrazioni (nessuna chiamata reale alle API GitLab in produzione).

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
===============================================================================
"""

from __future__ import annotations

from .mock import GitLabMockProvider

__all__ = ["GitLabMockProvider"]
