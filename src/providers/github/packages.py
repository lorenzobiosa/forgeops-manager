# -*- coding: utf-8 -*-
"""
===============================================================================
Modulo: packages.py
Descrizione:
    Gestione pacchetti GitHub Packages a livello utente/organizzazione.
    Fornisce:
      - Elenco pacchetti per scope (user/org) e tipo (container/npm/maven/...).
      - Cancellazione di pacchetti interi o solo versioni selezionate.
      - Flusso interattivo (CLI) con prompt guidati.
      - Entrypoint CLI con opzioni di logging e "solo lista".

Linee guida:
    - Logging strutturato via src.utils.logging (JSON di default).
    - Nessun segreto nei log; traccia solo metadati (nomi pacchetti, visibilità).
    - Comportamento robusto: skip di elementi non conformi, errori loggati con stack.

Dipendenze:
    - src.utils.http: get, delete, GITHUB_API
    - src.utils.config: get_username_or_org
    - src.providers.github.api: paginate (per cancellazione versioni)
    - src.utils.logging: get_logger, log_event, setup_logging

Autore: Lorenzo Biosa <lorenzo@biosa-labs.com>
Licenza:
    Questo file è rilasciato secondo i termini della licenza del repository.
===============================================================================
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

import requests

from src.utils.config import get_username_or_org
from src.utils.http_client import GITHUB_API, delete, get
from src.utils.structured_logging import get_logger, log_event, setup_logging

__all__ = [
    "_list_packages",
    "_delete_package",
    "_delete_package_versions",
    "interactive_delete_packages",
    "main",
]

# Logger di modulo (NON configura nulla all'import; viene ribindato in main() o dal chiamante)
_logger = logging.getLogger(__name__)

# Tipi pacchetti supportati (coerenti con GitHub)
_SUPPORTED_TYPES: set[str] = {"container", "npm", "maven", "rubygems", "nuget"}


# =============================================================================
# API interne
# =============================================================================
def _list_packages(scope: Tuple[str, str], pkg_type: str = "container") -> List[Dict[str, Any]]:
    """
    Elenca i pacchetti per uno scope ('org' o 'user') e tipo.

    Args:
        scope: Tupla ('org'|'user', name)
        pkg_type: Tipo pacchetto ('container'|'npm'|'maven'|'rubygems'|'nuget')

    Returns:
        List[Dict[str, Any]]: Oggetti pacchetto come restituiti dalla API GitHub.

    Raises:
        RuntimeError: se la risposta non è JSON/array conforme.
    """
    typ, name = scope

    # Normalizza tipo
    pkg_type_norm = (pkg_type or "container").strip().lower()
    if pkg_type_norm not in _SUPPORTED_TYPES:
        log_event(
            _logger,
            "packages_type_normalized",
            {"provided": pkg_type, "normalized_to": "container"},
            level=logging.WARNING,
        )
        pkg_type_norm = "container"

    params: Dict[str, Any] = {"package_type": pkg_type_norm, "per_page": 100}
    url = f"{GITHUB_API}/{'orgs' if typ == 'org' else 'users'}/{name}/packages"

    log_event(
        _logger,
        "packages_list_start",
        {"scope_type": typ, "scope_name": name, "package_type": pkg_type_norm},
    )

    # Annotazione esplicita per evitare tipi "unknown"
    r: requests.Response = get(url, params=params)
    r.raise_for_status()
    data_any: Any = r.json()

    if not isinstance(data_any, list):
        log_event(
            _logger,
            "packages_list_error",
            {"reason": "risposta non list", "type": type(data_any).__name__},
            level=logging.ERROR,
        )
        raise RuntimeError("Risposta inattesa dalla API packages (atteso array).")

    iterable_any = cast(Iterable[Any], data_any)
    data: List[Any] = list(iterable_any)

    packages: List[Dict[str, Any]] = []
    for item in data:
        # item è Any → isinstance(dict) NON è ridondante (evita warning Pylance)
        if isinstance(item, dict):
            packages.append(cast(Dict[str, Any], item))
        else:
            log_event(
                _logger,
                "packages_skip_non_dict",
                {"element_type": type(item).__name__},
                level=logging.WARNING,
            )

    log_event(
        _logger,
        "packages_list_complete",
        {
            "scope_type": typ,
            "scope_name": name,
            "package_type": pkg_type_norm,
            "count": len(packages),
        },
    )
    return packages


def _delete_package(typ: str, name: str, pkg_type: str, pkg_name: str) -> None:
    """
    Cancella un pacchetto allo scope e tipo indicati.

    Args:
        typ: 'org' o 'user'
        name: nome org/user
        pkg_type: tipo pacchetto (es. 'container')
        pkg_name: nome/identificativo del pacchetto

    Raises:
        RuntimeError: se la cancellazione fallisce.
    """
    pkg_type_norm = (pkg_type or "container").strip().lower()
    url = f"{GITHUB_API}/{('orgs' if typ == 'org' else 'users')}\
        /{name}/packages/{pkg_type_norm}/{pkg_name}"
    r: requests.Response = delete(url)
    if r.status_code not in (200, 202, 204):
        log_event(
            _logger,
            "packages_delete_error",
            {
                "scope_type": typ,
                "scope_name": name,
                "package_type": pkg_type_norm,
                "package": pkg_name,
                "status": r.status_code,
            },
            level=logging.ERROR,
        )
        raise RuntimeError(f"Cancellazione pacchetto fallita: {r.status_code} - {r.text}")

    log_event(
        _logger,
        "packages_delete_package",
        {
            "scope_type": typ,
            "scope_name": name,
            "package_type": pkg_type_norm,
            "package": pkg_name,
        },
    )


def _delete_package_versions(
    typ: str, name: str, pkg_type: str, pkg_name: str, version_ids: List[int]
) -> None:
    """
    Cancella versioni specifiche di un pacchetto.

    Args:
        typ: 'org' o 'user'
        name: nome org/user
        pkg_type: tipo pacchetto
        pkg_name: nome/identificativo pacchetto
        version_ids: lista di ID versione da cancellare

    Raises:
        RuntimeError: se una cancellazione fallisce.
    """
    pkg_type_norm = (pkg_type or "container").strip().lower()
    url_base = f"{GITHUB_API}/{('orgs' if typ == 'org' else 'users')}\
        /{name}/packages/{pkg_type_norm}/{pkg_name}/versions"

    if not version_ids:
        log_event(
            _logger,
            "packages_delete_versions_empty",
            {"package": pkg_name, "package_type": pkg_type_norm},
            level=logging.WARNING,
        )
        return

    for vid in version_ids:
        r: requests.Response = delete(f"{url_base}/{vid}")
        if r.status_code not in (200, 202, 204):
            log_event(
                _logger,
                "packages_delete_version_error",
                {"package": pkg_name, "version_id": vid, "status": r.status_code},
                level=logging.ERROR,
            )
            raise RuntimeError(f"Cancellazione versione {vid} fallita: {r.status_code} - {r.text}")

        print(f" - eliminata versione_id={vid}")
        log_event(_logger, "packages_delete_version", {"package": pkg_name, "version_id": vid})


# =============================================================================
# Flusso interattivo
# =============================================================================
def interactive_delete_packages() -> None:
    """
    Flusso interattivo:
      - Determina lo scope (org/user).
      - Chiede tipo pacchetto.
      - Elenca i pacchetti presenti.
      - Cancella tutti o selezionati (pacchetto intero o sole versioni).
    """
    scope: Tuple[str, str] = get_username_or_org()
    pkg_type_in: str = (
        input("Tipo pacchetto? [container|npm|maven|rubygems|nuget] (default: container): ").strip()
        or "container"
    )
    pkg_type = pkg_type_in.lower()
    if pkg_type not in _SUPPORTED_TYPES:
        print("Tipo non valido, uso 'container'.")
        log_event(
            _logger,
            "packages_type_normalized",
            {"provided": pkg_type_in, "normalized_to": "container"},
            level=logging.WARNING,
        )
        pkg_type = "container"

    packages: List[Dict[str, Any]] = _list_packages(scope, pkg_type)
    if not packages:
        print("Nessun pacchetto trovato.")
        return

    print("\nPacchetti trovati:")
    for i, p in enumerate(packages, start=1):
        name = cast(str, p.get("name"))
        visibility = cast(Optional[str], p.get("visibility"))
        print(f"[{i}] {name} (type={pkg_type}) visibilità={visibility}")

    choice = (input("\nCancellare [t]utti, [s]elezionati o [n]essuno? ").strip() or "n").lower()
    typ, name = scope

    if choice == "t":
        for p in packages:
            pkg_name = cast(str, p["name"])
            try:
                _delete_package(typ, name, pkg_type, pkg_name)
                print(f" - eliminato package={pkg_name}")
            except Exception as exc:
                _logger.exception("Errore cancellando pacchetto (tutti)")
                log_event(
                    _logger,
                    "packages_delete_error",
                    {
                        "scope_type": typ,
                        "scope_name": name,
                        "package_type": pkg_type,
                        "package": pkg_name,
                        "error_message": str(exc),
                    },
                    level=logging.ERROR,
                )
        print("Cancellazione completata.")

    elif choice == "s":
        idxs_raw = input("Indici (separati da virgola, es.: 1,3,5): ").strip()
        to_del: List[Dict[str, Any]] = []
        for raw in idxs_raw.split(","):
            raw = raw.strip()
            if not raw:
                continue
            i = int(raw) - 1
            if 0 <= i < len(packages):
                to_del.append(packages[i])

        for p in to_del:
            pkg_name = cast(str, p["name"])
            del_choice = (
                input(f"Cancellare [p]acchetto '{pkg_name}' o sole [v]ersioni? ").strip() or "p"
            ).lower()
            if del_choice == "v":
                # Elenca versioni usando paginate
                from .api import paginate

                url_base = f"{GITHUB_API}/{('orgs' if typ == 'org' else 'users')}\
                    /{name}/packages/{pkg_type}/{pkg_name}/versions"
                versions_any: List[Any] = list(paginate(url_base))
                version_ids: List[int] = []
                for v_any in versions_any:
                    if isinstance(v_any, dict):
                        v_dict: Dict[str, Any] = cast(Dict[str, Any], v_any)

                        # Tipizza esplicitamente vid_raw come opzionale
                        vid_raw: Optional[Any] = v_dict.get("id", None)

                        if isinstance(vid_raw, int):
                            version_ids.append(vid_raw)
                        elif isinstance(vid_raw, str):
                            try:
                                version_ids.append(int(vid_raw))
                            except (TypeError, ValueError):
                                log_event(
                                    _logger,
                                    "packages_versions_invalid_id",
                                    {
                                        "package": pkg_name,
                                        "raw_id_value": vid_raw,
                                        "raw_id_type": "str",
                                    },
                                    level=logging.WARNING,
                                )
                        else:
                            log_event(
                                _logger,
                                "packages_versions_invalid_id_type",
                                {
                                    "package": pkg_name,
                                    "raw_id_type": type(vid_raw).__name__,
                                },
                                level=logging.WARNING,
                            )
                    else:
                        log_event(
                            _logger,
                            "packages_versions_skip_non_dict",
                            {"package": pkg_name, "element_type": type(v_any).__name__},
                            level=logging.WARNING,
                        )
                try:
                    _delete_package_versions(typ, name, pkg_type, pkg_name, version_ids)
                except Exception as exc:
                    _logger.exception("Errore cancellando versioni pacchetto (selezionati)")
                    log_event(
                        _logger,
                        "packages_delete_versions_error",
                        {"package": pkg_name, "error_message": str(exc)},
                        level=logging.ERROR,
                    )
            else:
                try:
                    _delete_package(typ, name, pkg_type, pkg_name)
                    print(f" - eliminato package={pkg_name}")
                except Exception as exc:
                    _logger.exception("Errore cancellando pacchetto (selezionati)")
                    log_event(
                        _logger,
                        "packages_delete_error",
                        {
                            "scope_type": typ,
                            "scope_name": name,
                            "package_type": pkg_type,
                            "package": pkg_name,
                            "error_message": str(exc),
                        },
                        level=logging.ERROR,
                    )

        print("Operazione completata.")

    else:
        print("Nessuna azione eseguita.")


# =============================================================================
# CLI
# =============================================================================
def main() -> None:
    """
    Entrypoint CLI per elencare o cancellare pacchetti GitHub.

    Flag:
        --org        : Nome organizzazione
        --user       : Username
        --type       : Tipo pacchetto (default 'container')
        --list       : Solo lista (nessuna cancellazione)
        --log-level  : Livello log [DEBUG|INFO|WARNING|ERROR|CRITICAL]
        --log-json   : Abilita logging JSON
        --no-log-json: Disabilita logging JSON
    """
    parser = argparse.ArgumentParser(description="Elenca o cancella pacchetti GitHub Packages.")
    parser.add_argument("--org", help="Nome organizzazione")
    parser.add_argument("--user", help="Username")
    parser.add_argument(
        "--type",
        default="container",
        help="Tipo pacchetto (container|npm|maven|rubygems|nuget)",
    )
    parser.add_argument("--list", action="store_true", help="Solo elenco (non cancella)")
    # Opzioni logging
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Livello di logging",
    )
    parser.add_argument(
        "--log-json", dest="log_json", action="store_true", help="Abilita logging JSON"
    )
    parser.add_argument(
        "--no-log-json",
        dest="log_json",
        action="store_false",
        help="Disabilita logging JSON",
    )
    parser.set_defaults(log_json=None)

    args = parser.parse_args()

    # Configura logging in base alla modalità:
    # - Solo lista (comando CLI): log in console ABILITATI
    # - Interattivo (prompt): log in console DISABILITATI per non sporcare output
    if args.list:
        setup_logging(level=args.log_level, json_mode=args.log_json, console=True)
    else:
        setup_logging(level=args.log_level, json_mode=args.log_json, console=False)

    # Rebind logger dopo la configurazione
    global _logger
    _logger = get_logger(__name__)

    # Determina scope (se non fornito via CLI)
    scope: Optional[Tuple[str, str]] = (
        ("org", args.org) if args.org else ("user", args.user) if args.user else None
    )

    if args.list:
        if not scope:
            # Prompt sicuro (interattivo) per scope
            scope = get_username_or_org()

        packages: List[Dict[str, Any]] = _list_packages(scope, args.type)
        if not packages:
            print("Nessun pacchetto trovato.")
            return

        print("Elenco pacchetti:")
        for p in packages:
            name = cast(str, p.get("name"))
            visibility = cast(Optional[str], p.get("visibility"))
            ptype = args.type.lower() if args.type else "container"
            print(f"- {name} (type={ptype}) visibilità={visibility}")
    else:
        # Flusso interattivo
        interactive_delete_packages()


if __name__ == "__main__":
    main()
