from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, cast

from src.utils.http import get, delete
from src.utils.config import get_owner_repo


def paginate(
    url: str,
    params: Optional[Mapping[str, Any]] = None,
    array_key: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """
    Iterate through paginated GitHub API responses.

    Supports both:
      - raw arrays (e.g., [ { ... }, { ... } ])
      - dict-wrapped arrays (e.g., { "workflow_runs": [ ... ] }, { "caches": [ ... ] })

    Args:
        url: Base API endpoint to fetch.
        params: Optional query parameters (e.g., {"status": "completed"}).
        array_key: Optional explicit key to extract the array from a dict response.
                   Use this when the API wraps results (e.g., 'workflow_runs', 'caches').

    Yields:
        Dict[str, Any]: Items from the paginated response.

    Raises:
        RuntimeError: If the response is a dict and no array key can be determined.
    """
    page: int = 1
    while True:
        p: Dict[str, Any] = dict(params or {})
        p["per_page"] = p.get("per_page", 100)
        p["page"] = page

        r = get(url, p)
        r.raise_for_status()
        data = r.json()

        items: List[Dict[str, Any]] = []

        if isinstance(data, list):
            # Raw array response
            items = cast(List[Dict[str, Any]], data)

        elif isinstance(data, dict):
            # Dict-wrapped response; determine which key holds the array
            key: Optional[str] = array_key

            # Fallbacks for common GitHub endpoints if array_key not provided
            if key is None:
                if "workflow_runs" in data:
                    key = "workflow_runs"
                elif "caches" in data:
                    key = "caches"

            if key is not None and key in data and isinstance(data[key], list):
                items = cast(List[Dict[str, Any]], data[key])
            else:
                # As a last resort, pick the first list-valued entry
                candidate: Optional[List[Dict[str, Any]]] = None
                for k, v in data.items():
                    if isinstance(v, list):
                        candidate = cast(List[Dict[str, Any]], v)
                        break
                if candidate is not None:
                    items = candidate
                else:
                    # Give a helpful error with available keys
                    raise RuntimeError(
                        f"Paginate: Unable to determine array key in dict response. "
                        f"Available keys: {list(data.keys())}. "
                        f"Consider specifying array_key for URL={url}"
                    )
        else:
            raise RuntimeError(
                f"Paginate: Unexpected response type {type(data).__name__} from URL={url}"
            )

        if not items:
            break

        for item in items:
            yield item

        if len(items) < p["per_page"]:
            break
        page += 1


def owner_repo_or_prompt(
    owner: Optional[str] = None, repo: Optional[str] = None
) -> Tuple[str, str]:
    return get_owner_repo(owner, repo)


def gh_delete(url: str, params: Optional[Mapping[str, Any]] = None) -> None:
    r = delete(url, params)
    if r.status_code not in (200, 202, 204):
        raise RuntimeError(f"DELETE failed ({r.status_code}): {r.text}")
