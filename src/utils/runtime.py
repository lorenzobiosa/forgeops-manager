# -*- coding: utf-8 -*-
"""
Autore:        Lorenzo Biosa
Email:         lorenzo@biosa-labs.com
Copyright:
  © 2026 Biosa Labs. Tutti i diritti riservati.

Modulo: runtime.py
Descrizione:
  Definisce il contesto runtime dell'applicazione/operazione. Fornisce una
  struttura dati tipizzata per raggruppare gli elementi comuni necessari
  alle chiamate verso API esterne (es. GitHub), come:
    - token di autenticazione,
    - sessione HTTP con intestazioni mutabili (compatibile con requests.Session),
    - metadati dell'operazione (nome, repo, org),
    - insieme di scope richiesti.

Note di implementazione:
  - Per evitare il warning Pylance "Import 'requests' could not be resolved
    from source" in ambienti dove 'requests' non è installato, si utilizza un
    Protocol (RequestsSessionLike) che modella l'attributo 'headers' senza
    importare il pacchetto.
  - Il campo 'required_scopes' usa un default factory tipizzato (_empty_str_set)
    per rendere noto a Pylance il tipo degli elementi (Set[str]) ed evitare
    i warning "unknown variable type" e "unknown lambda return type".
  - Richiede Python 3.9+ per l'uso di 'set[str]' e 'slots=True'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import MutableMapping, Optional, Protocol, Set


class RequestsSessionLike(Protocol):
    """
    Protocol per rappresentare una requests.Session senza dipendenza diretta.
    L'oggetto compatibile deve esporre un attributo 'headers' mutabile
    con chiavi e valori di tipo 'str'.
    """

    headers: MutableMapping[str, str]


def _empty_str_set() -> Set[str]:
    """
    Factory tipizzata per un set di stringhe vuoto.
    Evita i warning Pylance su default_factory con lambda di tipo ignoto.
    """
    return set()


@dataclass(frozen=False, slots=True)
class RuntimeContext:
    """
    Contesto runtime dell'applicazione/operazione.

    Attributi:
        token: Token di autenticazione (es. GitHub PAT). Deve essere non vuoto.
        session: Sessione HTTP compatibile con requests (espone 'headers' dict-like).
        op_name: Nome dell'operazione corrente (opzionale).
        repo: Repository in formato 'owner/name' (opzionale).
        org: Organizzazione (opzionale).
        required_scopes: Insieme di scope richiesti per l'operazione.
    """

    token: str
    session: RequestsSessionLike
    op_name: Optional[str] = None
    repo: Optional[str] = None
    org: Optional[str] = None
    required_scopes: Set[str] = field(default_factory=_empty_str_set)
