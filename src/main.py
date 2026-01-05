# src/main.py
# -*- coding: utf-8 -*-

import argparse
import os
import json
from typing import Dict

from src.providers.base import Provider
from src.providers.gitlab.mock import GitLabMockProvider
from src.providers.github.actions import delete_all_completed_workflow_runs
from src.providers.github.packages import interactive_delete_packages
from src.providers.github.releases import delete_all_releases
from src.providers.github.cache import delete_all_actions_cache
from src.providers.github.security import clear_vulns  # NEW


def interactive_clear_vulns():
    """
    Interactive wrapper for GitHub Code Scanning cleanup.
    Prompts for repo, mode, tools, token, and (for dismiss) reason/comment/state.
    """
    print("\n=== GitHub Code Scanning cleanup ===")
    repo = input("Repository (owner/repo): ").strip() or os.environ.get("REPO", "")
    if not repo:
        print("ERROR: repository is required (owner/repo).")
        return

    mode = (input("Mode [delete|dismiss] (default: delete): ").strip().lower() or "delete")
    if mode not in ("delete", "dismiss"):
        print("ERROR: mode must be 'delete' or 'dismiss'.")
        return

    tools_in = input("Tools CSV (empty for all) [default: Trivy,Grype]: ").strip()
    if tools_in == "":
        tools = ""  # apply to all tools
    else:
        tools = tools_in or "Trivy,Grype"

    # Token from env as default
    token_env = os.environ.get("GITHUB_TOKEN", "")
    token_in = input("GitHub token (leave empty to use env GITHUB_TOKEN): ").strip()
    token = token_in or token_env
    if not token:
        print("ERROR: missing token. Set GITHUB_TOKEN or provide one here.")
        return

    dry_answer = input("Dry-run? [y/N]: ").strip().lower()
    dry_run = dry_answer in ("y", "yes")

    reason = "won't_fix"
    comment = "Bulk reset: issues will reappear if they persist."
    state = "open"

    if mode == "dismiss":
        reason_in = input("Dismiss reason [false_positive|won't_fix|used_in_tests] (default: won't_fix): ").strip()
        reason = reason_in or "won't_fix"
        comment_in = input("Dismiss comment (default: Bulk reset: issues will reappear if they persist.): ").strip()
        comment = comment_in or "Bulk reset: issues will reappear if they persist."
        state_in = input("Alert state to process [open|dismissed|fixed] (default: open): ").strip()
        state = state_in or "open"

    print("\nExecuting clear-vulns …")
    print(f"  repo  = {repo}")
    print(f"  mode  = {mode}")
    print(f"  tools = {tools if tools != '' else '(all tools)'}")
    if mode == "dismiss":
        print(f"  reason= {reason}")
        print(f"  state = {state}")
        print(f"  comment: {comment}")
    print(f"  dry-run = {dry_run}")

    try:
        result = clear_vulns(
            repo=repo,
            mode=mode,
            token=token,
            tools=tools,
            reason=reason,
            comment=comment,
            state=state,
            dry_run=dry_run,
        )
        print("\nResult:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\nERROR: {e}")


class GitHubProvider(Provider):
    def __init__(self):
        super().__init__("GitHub")
        self.operations = {
            "Delete Actions/workflow runs (all completed)": delete_all_completed_workflow_runs,
            "Delete packages (list → all or selected)": interactive_delete_packages,
            "Delete releases (all)": delete_all_releases,
            "Delete Actions cache (all)": delete_all_actions_cache,
            "Clear Code Scanning vulns (delete analyses / dismiss alerts)": interactive_clear_vulns,  # NEW
        }


def providers_registry() -> Dict[str, Provider]:
    return {
        "github": GitHubProvider(),
        "gitlab": GitLabMockProvider(),
    }


def interactive_menu():
    providers = list(providers_registry().values())
    print("Select a provider:")
    for i, p in enumerate(providers, start=1):
        print(f"[{i}] {p.name}")
    sel = input("Choice: ").strip() or "1"
    try:
        idx = int(sel) - 1
    except ValueError:
        idx = 0
    idx = max(0, min(idx, len(providers) - 1))
    provider = providers[idx]

    ops = provider.list_operations()
    print(f"\nAvailable operations for {provider.name}:")
    for i, o in enumerate(ops, start=1):
        print(f"[{i}] {o}")
    sel = input("Choice: ").strip() or "1"
    try:
        idx = int(sel) - 1
    except ValueError:
        idx = 0
    idx = max(0, min(idx, len(ops) - 1))
    op_key = ops[idx]
    print(f"\nRunning: {op_key}\n")
    provider.run(op_key)


def main():
    parser = argparse.ArgumentParser(
        description="ForgeOps Manager — cleanup toolkit for Git forges."
    )
    parser.add_argument(
        "--provider", choices=["github", "gitlab"], help="Provider to use"
    )
    parser.add_argument(
        "--operation",
        choices=[
            "delete-workflows",
            "delete-packages",
            "delete-releases",
            "delete-cache",
            "clear-vulns",  # NEW
        ],
        help="Operation to run (provider-specific)",
    )
    # Arguments for clear-vulns (GitHub Code Scanning)
    parser.add_argument("--repo", help="owner/repo (required for clear-vulns)")
    parser.add_argument("--mode", choices=["delete", "dismiss"], help="clear-vulns: delete analyses or dismiss alerts")
    parser.add_argument("--tools", default="Trivy,Grype", help="clear-vulns: CSV tools filter (empty for all)")
    parser.add_argument("--reason", default="won't_fix", help="clear-vulns (dismiss): reason (false_positive|won't_fix|used_in_tests)")
    parser.add_argument("--comment", default="Bulk reset: issues will reappear if they persist.", help="clear-vulns (dismiss): comment")
    parser.add_argument("--state", default="open", help="clear-vulns (dismiss): alert state to process (open|dismissed|fixed)")
    parser.add_argument("--token", help="GitHub token (defaults to env GITHUB_TOKEN)")
    parser.add_argument("--dry-run", action="store_true", help="clear-vulns: print actions without changing anything")
    args = parser.parse_args()

    if not args.provider or not args.operation:
        # Fallback to interactive menu if not enough CLI params are provided
        interactive_menu()
        return

    registry = providers_registry()
    provider = registry[args.provider]

    op_map = {
        "delete-workflows": "Delete Actions/workflow runs (all completed)",
        "delete-packages": "Delete packages (list → all or selected)",
        "delete-releases": "Delete releases (all)",
        "delete-cache": "Delete Actions cache (all)",
        "clear-vulns": "Clear Code Scanning vulns (delete analyses / dismiss alerts)",  # NEW
    }

    if args.operation == "clear-vulns":
        # Direct call to the GitHub Code Scanning cleanup (bypasses Provider registry)
        if not args.repo or not args.mode:
            raise SystemExit("clear-vulns requires --repo owner/repo and --mode delete|dismiss")
        print(f"Running clear-vulns on GitHub:\n  repo={args.repo}\n  mode={args.mode}\n  tools={args.tools}\n  dry-run={args.dry_run}")
        result = clear_vulns(
            repo=args.repo,
            mode=args.mode,
            token=args.token,
            tools=args.tools,
            reason=args.reason,
            comment=args.comment,
            state=args.state,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
        return
    else:
        op_key = op_map[args.operation]
        print(f"Running {op_key} on {provider.name}…")
        provider.run(op_key)


if __name__ == "__main__":
    main()
