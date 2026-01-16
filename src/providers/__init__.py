# -*- coding: utf-8 -*-
"""
===============================================================================
Pacchetto: src.providers
Descrizione:
    Interfacce e implementazioni dei provider (GitHub, GitLab).
    Contiene classi e funzioni per operazioni amministrative su forges Git.

Linee guida:
    - Non importare automaticamente i sottopacchetti per evitare overhead.
    - Esporre solo l'interfaccia base comune (Provider).

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
===============================================================================
"""

from __future__ import annotations

from .base import Provider

__all__ = ["Provider"]
