# ForgeOps Manager

**ForgeOps Manager** is an enterprise-grade CLI toolkit for cleanup and maintenance across Git forges — starting with **GitHub** (implemented) and **GitLab** (mock).  
It enables automated removal of workflow runs, packages, releases, and Actions cache entries via an interactive menu or direct commands.

> ⚠️ **Warning**: All operations are **destructive** and **irreversible**. Use with caution and ensure your token has appropriate scopes.

---

## ✅ Features

- **Provider selection**:
  - GitHub (fully implemented)
  - GitLab (mock placeholder for future implementation)
- **GitHub operations**:
  - Delete Actions/workflow runs (**all completed**)
  - Delete packages (list → delete all or selected; optionally delete versions only)
  - Delete releases (**all**)
  - Delete Actions cache (**all entries**)

---

## ✅ Requirements

- Python **3.10+**
- `requests` library (installed via `requirements.txt`)
- GitHub **Personal Access Token (PAT)** with scopes:
  - `repo` (private/public repositories)
  - `workflow` (manage workflow runs)
  - `read:packages`, `delete:packages` (list/delete packages and versions)
  - Actions cache deletion requires **Actions write permissions** on the repository

Recommended: **Classic PAT** with `repo`, `workflow`, `read:packages`, `delete:packages`.

---

## ✅ Configuration

You can provide configuration via **environment variables** (recommended), **CLI flags**, or **interactive prompts**.

### Environment variables

```bash
export GITHUB_TOKEN="ghp_…"
export GH_OWNER="acme-org"    # organization or user
export GH_REPO="my-repo"      # repository name
```

---

## ✅ Installation & Setup

Clone the repository:

```bash
git clone https://github.com/<your-account>/forgeops-manager.git
cd forgeops-manager
```

### Automated Setup (Recommended)

Use the provided scripts in `scripts/` for environment setup:

#### Linux/macOS:

```bash
bash scripts/setup.sh
# or:
chmod +x scripts/setup.sh && ./scripts/setup.sh
```

#### Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

After setup completes:

```bash
source .venv/bin/activate    # Linux/macOS
# OR
.\.venv\Scripts\Activate.ps1 # Windows
```

---

### Manual Setup (Alternative)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip --break-system-packages
pip install -r requirements.txt --break-system-packages
```

---

## ✅ Usage

### Interactive Menu

```bash
python -m src.main
```

Flow:

1.  Select provider (GitHub / GitLab mock)
2.  Select operation:
    - Delete all **completed** workflow runs
    - List packages → delete all or select specific ones (optionally versions-only)
    - Delete all releases
    - Delete all Actions cache entries

---

### Direct (Non-Interactive)

```bash
# Delete all completed workflow runs
python -m src.providers.github.actions --owner acme-org --repo my-repo --delete-all-completed

# List packages for an organization (container images)
python -m src.providers.github.packages --org acme-org --type container --list

# Delete all releases
python -m src.providers.github.releases --owner acme-org --repo my-repo --delete-all

# Delete all Actions cache entries
python -m src.providers.github.cache --owner acme-org --repo my-repo --delete-all
```

_(This initial version uses env vars/prompts; full argparse flags are available in `main.py` for provider/op selection.)_

---

## ✅ GitHub API Endpoints

- **Workflow runs**

  - List: `GET /repos/{owner}/{repo}/actions/runs?status=completed&per_page=100`
  - Delete: `DELETE /repos/{owner}/{repo}/actions/runs/{run_id}`

- **Packages**

  - List (org): `GET /orgs/{org}/packages?package_type={type}`
  - List (user): `GET /users/{username}/packages?package_type={type}`
  - List versions: `GET /orgs/{org}/packages/{type}/{name}/versions`
  - Delete version: `DELETE /orgs/{org}/packages/{type}/{name}/versions/{version_id}`
  - Delete package: `DELETE /orgs/{org}/packages/{type}/{name}`

- **Releases**

  - List: `GET /repos/{owner}/{repo}/releases`
  - Delete: `DELETE /repos/{owner}/{repo}/releases/{release_id}`

- **Actions cache**
  - List: `GET /repos/{owner}/{repo}/actions/caches?per_page=100`
  - Delete (single): `DELETE /repos/{owner}/{repo}/actions/caches/{cache_id}`  
    _(No single-call “delete all”; iterate cache IDs.)_

Recommended headers:

    Accept: application/vnd.github+json
    Authorization: Bearer <GITHUB_TOKEN>
    X-GitHub-Api-Version: 2022-11-28

---

## ✅ Notes & Caveats

- Handle pagination (`per_page=100`), rate limits, and large datasets.
- Operations are **irreversible**.
- Packages scope differs for **user** vs **org**.

---

## ✅ Roadmap

- Add **dry-run** and structured **logging**
- Extend **GitLab** (API v4) implementations
- Add a **Makefile** and CI workflow for testing
- Implement **Bitbucket** and other providers for multi-forge support

---
