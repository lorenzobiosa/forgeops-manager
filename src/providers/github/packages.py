import argparse
from typing import Any, Dict, List, Optional, Tuple, cast

from src.utils.http import get, delete, GITHUB_API
from src.utils.config import get_username_or_org


def _list_packages(
    scope: Tuple[str, str], pkg_type: str = "container"
) -> List[Dict[str, Any]]:
    """
    List packages for a given scope ('org' or 'user') and package type.

    Args:
        scope: Tuple ('org'|'user', name)
        pkg_type: Package type (e.g., 'container', 'npm', 'maven', 'rubygems', 'nuget')

    Returns:
        List[Dict[str, Any]]: Package objects as returned by GitHub API.
    """
    typ, name = scope
    params: Dict[str, Any] = {"package_type": pkg_type, "per_page": 100}

    if typ == "org":
        r = get(f"{GITHUB_API}/orgs/{name}/packages", params)
    else:
        r = get(f"{GITHUB_API}/users/{name}/packages", params)

    r.raise_for_status()
    data = r.json()
    # Ensure a concrete type for Pylance
    return cast(List[Dict[str, Any]], data)


def _delete_package(typ: str, name: str, pkg_type: str, pkg_name: str) -> None:
    """
    Delete a package at the given scope and type.

    Args:
        typ: 'org' or 'user'
        name: org/user name
        pkg_type: package type (e.g., 'container')
        pkg_name: package identifier
    """
    url = f"{GITHUB_API}/{('orgs' if typ == 'org' else 'users')}/{name}/packages/{pkg_type}/{pkg_name}"
    r = delete(url)
    if r.status_code not in (200, 202, 204):
        raise RuntimeError(f"Delete package failed: {r.status_code} - {r.text}")


def _delete_package_versions(
    typ: str, name: str, pkg_type: str, pkg_name: str, version_ids: List[int]
) -> None:
    """
    Delete specific versions of a package.

    Args:
        typ: 'org' or 'user'
        name: org/user name
        pkg_type: package type
        pkg_name: package identifier
        version_ids: list of version IDs to delete
    """
    url_base = f"{GITHUB_API}/{('orgs' if typ == 'org' else 'users')}/{name}/packages/{pkg_type}/{pkg_name}/versions"
    for vid in version_ids:
        r = delete(f"{url_base}/{vid}")
        if r.status_code not in (200, 202, 204):
            raise RuntimeError(
                f"Delete version {vid} failed: {r.status_code} - {r.text}"
            )
        print(f" - deleted version_id={vid}")


def interactive_delete_packages() -> None:
    """
    Interactive flow:
      - Resolve scope ('org' or 'user')
      - List packages for selected type
      - Delete all or selected packages (optionally versions-only)
    """
    scope: Tuple[str, str] = get_username_or_org()
    pkg_type: str = (
        input(
            "Package type? [container|npm|maven|rubygems|nuget] (default container): "
        ).strip()
        or "container"
    )

    packages: List[Dict[str, Any]] = _list_packages(scope, pkg_type)
    if not packages:
        print("No packages found.")
        return

    print("\nPackages found:")
    for i, p in enumerate(packages, start=1):
        name = cast(str, p.get("name"))
        visibility = cast(Optional[str], p.get("visibility"))
        print(f"[{i}] {name} (type={pkg_type}) visibility={visibility}")

    choice = (input("\nDelete [a]ll, [s]elected, or [n]one? ").strip() or "n").lower()
    typ, name = scope

    if choice == "a":
        for p in packages:
            pkg_name = cast(str, p["name"])
            _delete_package(typ, name, pkg_type, pkg_name)
            print(f" - deleted package={pkg_name}")
        print("Deletion completed.")

    elif choice == "s":
        idxs_raw = input("Indices (comma separated, e.g., 1,3,5): ").strip()
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
            del_versions = (
                input(f"Delete [p]ackage '{pkg_name}' or [v]ersion(s) only? ").strip()
                or "p"
            ).lower()
            if del_versions == "v":
                # List versions using paginate
                from src.providers.github.api import paginate

                url_base = f"{GITHUB_API}/{('orgs' if typ == 'org' else 'users')}/{name}/packages/{pkg_type}/{pkg_name}/versions"
                versions: List[Dict[str, Any]] = list(paginate(url_base))
                version_ids: List[int] = [cast(int, v["id"]) for v in versions]
                _delete_package_versions(typ, name, pkg_type, pkg_name, version_ids)
            else:
                _delete_package(typ, name, pkg_type, pkg_name)
                print(f" - deleted package={pkg_name}")

        print("Operation completed.")

    else:
        print("No action executed.")


def main() -> None:
    """
    CLI entrypoint for listing or deleting GitHub packages.

    Flags:
        --org: Organization name
        --user: Username
        --type: Package type (default 'container')
        --list: List packages only
    """
    parser = argparse.ArgumentParser(description="List or delete GitHub packages.")
    parser.add_argument("--org", help="Organization name")
    parser.add_argument("--user", help="Username")
    parser.add_argument(
        "--type",
        default="container",
        help="Package type (container|npm|maven|rubygems|nuget)",
    )
    parser.add_argument("--list", action="store_true", help="List packages only")
    args = parser.parse_args()

    scope: Optional[Tuple[str, str]] = (
        ("org", args.org) if args.org else ("user", args.user) if args.user else None
    )
    if args.list:
        if not scope:
            scope = get_username_or_org()
        packages: List[Dict[str, Any]] = _list_packages(scope, args.type)
        if not packages:
            print("No packages found.")
            return
        for p in packages:
            name = cast(str, p.get("name"))
            visibility = cast(Optional[str], p.get("visibility"))
            print(f"{name} (visibility={visibility})")
    else:
        interactive_delete_packages()


if __name__ == "__main__":
    main()
