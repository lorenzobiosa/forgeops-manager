import os
from typing import Any, Mapping, Optional

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def gh_headers() -> Mapping[str, str]:
    """
    Build GitHub API headers using the GITHUB_TOKEN env var.
    Returns an immutable mapping suitable for requests.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN. Set it as an environment variable.")
    return {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}"}


def get(url: str, params: Optional[Mapping[str, Any]] = None) -> requests.Response:
    """
    Typed wrapper for requests.get with standard GitHub headers.
    """
    return requests.get(url, headers=gh_headers(), params=params or {})


def delete(url: str, params: Optional[Mapping[str, Any]] = None) -> requests.Response:
    """
    Typed wrapper for requests.delete with standard GitHub headers.
    """
    return requests.delete(url, headers=gh_headers(), params=params or {})
