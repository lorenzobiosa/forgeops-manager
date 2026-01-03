import os
from typing import Optional, Tuple


def ask_if_missing(value: Optional[str], prompt_label: str) -> str:
    """
    Prompt for a value if missing.
    Returns a non-empty string or raises an error.
    """
    if value:
        return value
    val = input(f"{prompt_label}: ").strip()
    if not val:
        raise RuntimeError(f"{prompt_label} is required.")
    return val


def get_owner_repo(
    owner: Optional[str] = None, repo: Optional[str] = None
) -> Tuple[str, str]:
    """
    Get owner and repo from args/env or prompt. Returns (owner, repo) as strings.
    """
    owner = owner or os.environ.get("GH_OWNER")
    repo = repo or os.environ.get("GH_REPO")
    owner = ask_if_missing(owner, "Owner/Org or Username")
    repo = ask_if_missing(repo, "Repository")
    return owner, repo


def get_username_or_org(
    username: Optional[str] = None, org: Optional[str] = None
) -> Tuple[str, str]:
    """
    Choose whether to operate on user or organization scope for packages.
    Returns a tuple ('user'|'org', name).
    """
    if org:
        return ("org", org)
    if username:
        return ("user", username)

    env_owner = os.environ.get("GH_OWNER")
    choice = input("Packages scope? [1] Org, [2] User: ").strip() or "1"
    if choice == "1":
        name = input("Organization name: ").strip() or env_owner
        if not name:
            raise RuntimeError("Organization is required.")
        return ("org", name)
    else:
        name = input("Username: ").strip() or env_owner
        if not name:
            raise RuntimeError("Username is required.")
        return ("user", name)
