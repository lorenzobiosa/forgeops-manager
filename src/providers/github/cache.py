import argparse
from typing import Optional

from src.providers.github.api import paginate, gh_delete, owner_repo_or_prompt
from src.utils.http import GITHUB_API


def delete_all_actions_cache(
    owner: Optional[str] = None, repo: Optional[str] = None
) -> None:
    """
    Delete ALL GitHub Actions cache entries for the provided repository.

    Args:
        owner: GitHub owner/org (optional; will prompt if missing).
        repo: GitHub repository name (optional; will prompt if missing).

    Raises:
        RuntimeError: If a DELETE call fails.
    """
    resolved_owner, resolved_repo = owner_repo_or_prompt(owner, repo)
    print(
        f"[GitHub] Deleting ALL Actions cache entries for {resolved_owner}/{resolved_repo}…"
    )
    url = f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/caches"

    total: int = 0
    for cache in paginate(url):
        cache_id = cache["id"]
        gh_delete(
            f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/caches/{cache_id}"
        )
        total += 1
        print(f" - deleted cache_id={cache_id} (key={cache.get('key')})")

    print(f"Total deleted cache entries: {total}")


def main() -> None:
    """
    CLI entrypoint for deleting all Actions cache entries.

    Flags:
        --owner: GitHub owner/org
        --repo: GitHub repository
    """
    parser = argparse.ArgumentParser(description="Delete all Actions cache entries.")
    parser.add_argument("--owner", help="GitHub owner/org")
    parser.add_argument("--repo", help="GitHub repository")
    args = parser.parse_args()
    delete_all_actions_cache(owner=args.owner, repo=args.repo)


if __name__ == "__main__":
    main()
