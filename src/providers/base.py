# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: base.py
Descrizione:
    Astrazione base per i "provider" (es. GitHub, GitLab) usati dal toolkit.
    Definisce un registro di operazioni nominali (etichette leggibili) che
    mappano a funzioni/callable senza argomenti, eseguibili tramite chiave.

Linee guida:
    - Le operazioni devono essere idempotenti o tolleranti al riavvio quando possibile.
    - Le etichette sono destinate a UI/CLI, quindi scegliere nomi chiari e stabili.
    - Tipizzazione esplicita e conforme a Pylance.
    - Logging strutturato tramite `src.utils.logging` per tracciabilità e osservabilità.

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Licenza:
    Questo file è rilasciato secondo i termini della licenza del repository.
===============================================================================
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

# Integrazione logging centrale
from utils.structured_logging import get_logger, log_event

# Logger di modulo (eredita configurazione root definita altrove, es. in main.py)
_logger = get_logger(__name__)


class Provider:
    """
    Classe base per i provider.

    Attributi:
        name (str): Nome leggibile del provider (mostrato nei menu).
        operations (Dict[str, Callable[[], Any]]): Mappa tra etichette operazioni
            e callable senza argomenti che le implementano.
    """

    name: str
    operations: Dict[str, Callable[[], Any]]

    def __init__(self, name: str) -> None:
        """
        Inizializza un provider con il nome specificato e un registro operazioni vuoto.
        """
        # `name` è annotato come str; controllo solo contenuto non vuoto.
        if not name.strip():
            log_event(
                _logger,
                "provider_init_error",
                {"reason": "name vuoto"},
                level=40,  # logging.ERROR
            )
            raise ValueError("name obbligatorio e non può essere vuoto.")

        self.name = name.strip()
        self.operations = {}

        # Log evento di inizializzazione
        log_event(
            _logger,
            "provider_initialized",
            {"name": self.name, "operations_count": 0},
        )

    # --------------------------------------------------------------------- #
    # API di registrazione/consultazione operazioni
    # --------------------------------------------------------------------- #
    def register_operation(self, label: str, func: Callable[[], Any]) -> None:
        """
        Registra un'operazione nel provider.

        Args:
            label: Etichetta leggibile dell'operazione (usata in menu/CLI).
            func: Callable senza argomenti che implementa l'operazione.

        Raises:
            ValueError: Se `label` è vuota o `func` non è callable.
        """
        # `label` è annotato come str; controllo solo contenuto non vuoto.
        if not label.strip():
            log_event(
                _logger,
                "provider_register_error",
                {"name": self.name, "reason": "label vuota"},
                level=40,  # logging.ERROR
            )
            raise ValueError("label obbligatoria e non può essere vuota.")

        if not callable(func):
            log_event(
                _logger,
                "provider_register_error",
                {"name": self.name, "label": label, "reason": "func non callable"},
                level=40,
            )
            raise ValueError("func deve essere un callable senza argomenti.")

        self.operations[label.strip()] = func

        log_event(
            _logger,
            "provider_operation_registered",
            {
                "name": self.name,
                "label": label.strip(),
                "operations_count": len(self.operations),
            },
        )

    def has_operation(self, label: str) -> bool:
        """
        Verifica se un'operazione esiste nel registro.

        Args:
            label: Etichetta dell'operazione.

        Returns:
            True se presente, altrimenti False.
        """
        exists = label in self.operations
        log_event(
            _logger,
            "provider_operation_check",
            {"name": self.name, "label": label, "exists": exists},
        )
        return exists

    def list_operations(self) -> List[str]:
        """
        Restituisce la lista delle etichette delle operazioni in ordine deterministico.

        Returns:
            List[str]: Nomi leggibili delle operazioni, ordinati alfabeticamente.
        """
        ops = sorted(self.operations.keys())
        log_event(
            _logger,
            "provider_operations_list",
            {"name": self.name, "operations_count": len(ops), "operations": ops},
        )
        return ops

    # --------------------------------------------------------------------- #
    # Esecuzione
    # --------------------------------------------------------------------- #
    def run(self, op_key: str) -> Optional[Any]:
        """
        Esegue l'operazione identificata da `op_key`.

        Args:
            op_key: Etichetta dell'operazione come ritornata da `list_operations()`.

        Returns:
            Il risultato dell'operazione (se presente), altrimenti None.

        Raises:
            KeyError: Se l'operazione richiesta non è disponibile.
        """
        if op_key not in self.operations:
            log_event(
                _logger,
                "provider_run_error",
                {
                    "name": self.name,
                    "op_key": op_key,
                    "reason": "operazione non disponibile",
                },
                level=40,
            )
            raise KeyError(f"Operazione '{op_key}' non disponibile per provider '{self.name}'.")

        func = self.operations[op_key]
        log_event(
            _logger,
            "provider_run_start",
            {"name": self.name, "op_key": op_key},
        )

        start = time.perf_counter()
        try:
            result = func()
            duration_ms = (time.perf_counter() - start) * 1000.0

            # Nota: non serializziamo completamente `result` per evitare payload pesanti.
            # Usiamo solo una descrizione sintetica quando possibile.
            result_type = type(result).__name__
            is_none = result is None

            log_event(
                _logger,
                "provider_run_success",
                {
                    "name": self.name,
                    "op_key": op_key,
                    "duration_ms": round(duration_ms, 2),
                    "result_type": result_type,
                    "result_is_none": is_none,
                },
            )
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000.0
            # Log con traccia eccezione (exc_info) è gestito dal formatter JSON del modulo logging
            _logger.exception(
                f"Errore durante esecuzione operazione '{op_key}' per provider '{self.name}'"
            )
            log_event(
                _logger,
                "provider_run_failure",
                {
                    "name": self.name,
                    "op_key": op_key,
                    "duration_ms": round(duration_ms, 2),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                level=40,
            )
            # Propaghiamo l'eccezione per consentire gestione a livello superiore
            raise

    # --------------------------------------------------------------------- #
    # Rappresentazione
    # --------------------------------------------------------------------- #
    def __repr__(self) -> str:
        ops = ", ".join(self.list_operations()) or "(nessuna)"
        repr_str = f"{self.__class__.__name__}(name={self.name!r}, operations=[{ops}])"
        log_event(
            _logger,
            "provider_repr",
            {"name": self.name, "repr_len": len(repr_str)},
        )
        return repr_str
