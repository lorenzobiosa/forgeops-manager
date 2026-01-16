# -*- coding: utf-8 -*-
"""
===============================================================================
Pacchetto: src
Descrizione:
    Pacchetto principale dell'applicazione ForgeOps Manager. Contiene moduli per:
      - Provider GitHub/GitLab (azioni amministrative e manutenzione).
      - Utilità comuni (config, logging, HTTP).
      - Entrypoint CLI (vedi src/main.py).

Note:
    Questo __init__ definisce metadati e versione del pacchetto. Evitare import
    pesanti o esecuzione di codice con side-effect.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Copyright:
    © 2026 Biosa Labs. Tutti i diritti riservati.
Licenza:
    Vedi LICENSE alla radice del repository.
===============================================================================
"""

from __future__ import annotations

# Metadati pacchetto
__title__ = "forgeops-manager"
__author__ = "Lorenzo Biosa"
__email__ = "lorenzo@biosa-labs.com"
__license__ = "Repository License"
__version__ = "0.1.0"

# Esportazioni principali (facoltative)
__all__ = [
    "__title__",
    "__author__",
    "__email__",
    "__license__",
    "__version__",
]
