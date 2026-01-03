import argparse
from typing import Optional

from src.providers.github.api import paginate, gh_delete, owner_repo_or_prompt
from src.utils.http import GITHUB_API


def delete_all_completed_workflow_runs(
    owner: Optional[str] = None, repo: Optional[str] = None
) -> None:
    """
    Delete all COMPLETED GitHub Actions workflow runs for the given repository.

    Args:
        owner: GitHub owner/org (optional; will prompt if missing).
        repo: GitHub repository name (optional; will prompt if missing).

    Raises:
        RuntimeError: If a DELETE call fails.
    """
    resolved_owner, resolved_repo = owner_repo_or_prompt(owner, repo)
    print(
        f"[GitHub] Deleting all COMPLETED workflow runs for {resolved_owner}/{resolved_repo}…"
    )
    url = f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/runs"

    total: int = 0
    for run in paginate(url, params={"status": "completed"}):
        run_id = run["id"]
        gh_delete(
            f"{GITHUB_API}/repos/{resolved_owner}/{resolved_repo}/actions/runs/{run_id}"
        )
        total += 1
        print(f" - deleted run_id={run_id}")

    print(f"Total deleted runs: {total}")


def main() -> None:
    """
    CLI entrypoint for deleting all completed workflow runs.

    Flags:
        --owner: GitHub owner/org
        --repo: GitHub repository
    """
    parser = argparse.ArgumentParser(description="Delete all completed workflow runs.")
    parser.add_argument("--owner", help="GitHub owner/org")
    parser.add_argument("--repo", help="GitHub repository")
    args = parser.parse_args()
    delete_all_completed_workflow_runs(owner=args.owner, repo=args.repo)


if __name__ == "__main__":
    main()
