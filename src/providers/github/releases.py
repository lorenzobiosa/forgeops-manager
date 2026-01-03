import argparse
from typing import Optional

from src.providers.github.api import paginate, gh_delete, owner_repo_or_prompt
from src.utils.http import GITHUB_API


def delete_all_releases(
    owner: Optional[str] = None, repo: Optional[str] = None
) -> None:
    """
    Delete ALL releases from the specified repository.

    Args:
        owner: GitHub owner/org (optional; will prompt if missing).
        repo: GitHub repository name (optional; will prompt if missing).

    Raises:
        RuntimeError: If a DELETE call fails.
    """
    resolved_owner, resolved_repo = owner_repo_or_prompt(owner, repo)
    print(f"[GitHub] Deleting ALL releases for {resolved_owner}/{resolved_repo}…")
    url = f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/releases"

    total: int = 0
    for rel in paginate(url):
        rel_id = rel["id"]
        gh_delete(
            f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/releases/{rel_id}"
        )
        total += 1
        # Name can be None; tag_name is a fallback.
        print(
            f" - deleted release_id={rel_id} ({rel.get('name') or rel.get('tag_name')})"
        )

    print(f"Total deleted releases: {total}")


def main() -> None:
    """
    CLI entrypoint for deleting all releases.

    Flags:
        --owner: GitHub owner/org
        --repo: GitHub repository
    """
    parser = argparse.ArgumentParser(description="Delete all releases.")
    parser.add_argument("--owner", help="GitHub owner/org")
    parser.add_argument("--repo", help="GitHub repository")
    args = parser.parse_args()
    delete_all_releases(owner=args.owner, repo=args.repo)


if __name__ == "__main__":
    main()
