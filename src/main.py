import argparse
from typing import Dict
from src.providers.base import Provider
from src.providers.gitlab.mock import GitLabMockProvider
from src.providers.github.actions import delete_all_completed_workflow_runs
from src.providers.github.packages import interactive_delete_packages
from src.providers.github.releases import delete_all_releases
from src.providers.github.cache import delete_all_actions_cache


class GitHubProvider(Provider):
    def __init__(self):
        super().__init__("GitHub")
        self.operations = {
            "Delete Actions/workflow runs (all completed)": delete_all_completed_workflow_runs,
            "Delete packages (list → all or selected)": interactive_delete_packages,
            "Delete releases (all)": delete_all_releases,
            "Delete Actions cache (all)": delete_all_actions_cache,
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
    idx = int(sel) - 1
    provider = providers[idx]

    ops = provider.list_operations()
    print(f"\nAvailable operations for {provider.name}:")
    for i, o in enumerate(ops, start=1):
        print(f"[{i}] {o}")
    sel = input("Choice: ").strip() or "1"
    idx = int(sel) - 1
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
        ],
        help="Operation to run (provider-specific)",
    )
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
    }

    op_key = op_map[args.operation]
    print(f"Running {op_key} on {provider.name}…")
    provider.run(op_key)


if __name__ == "__main__":
    main()
