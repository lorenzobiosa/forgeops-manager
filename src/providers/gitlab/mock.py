from src.providers.base import Provider


class GitLabMockProvider(Provider):
    def __init__(self):
        super().__init__("GitLab (mock)")
        self.operations = {
            "Delete workflow runs (all)": self.not_implemented,
            "Delete packages (list)": self.not_implemented,
            "Delete releases (all)": self.not_implemented,
            "Delete cache (all)": self.not_implemented,
        }

    def not_implemented(self):
        print("[GitLab] Feature not implemented yet. (mock)")
