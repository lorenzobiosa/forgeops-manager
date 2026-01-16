from typing import Callable, Dict

from ..base import Provider


class GitLabMockProvider(Provider):
    def __init__(self) -> None:
        super().__init__("GitLab (mock)")
        self.operations: Dict[str, Callable[[], None]] = {
            "Delete workflow runs (all)": self.not_implemented,
            "Delete packages (list)": self.not_implemented,
            "Delete releases (all)": self.not_implemented,
            "Delete cache (all)": self.not_implemented,
        }

    def not_implemented(self) -> None:
        print("[GitLab] Feature not implemented yet. (mock)")
