# src/providers/github/security.py
# -*- coding: utf-8 -*-
"""
GitHub Code Scanning vulnerability management:
- MODE=delete  : delete analyses for one or more tools (e.g., Trivy, Grype).
- MODE=dismiss : dismiss open alerts (optionally filtered by tool) with reason/comment.

Dependencies: requests (add to requirements.txt if missing).
Permissions: security-events: write.
"""

import os
import sys
import time
from typing import Iterable, Optional, Dict, Any, List, Tuple, cast

import requests


GITHUB_API = "https://api.github.com"


class GitHubSecurityClient:
    def __init__(self, token: str, repo: str, dry_run: bool = False):
        if not token:
            raise ValueError(
                "Missing GITHUB_TOKEN: provide --token or set env GITHUB_TOKEN."
            )
        if "/" not in repo:
            raise ValueError("repo must be in the form owner/repo.")
        self.token = token
        self.repo = repo
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "clear-vulns-script",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{GITHUB_API}{path}"
        resp = self.session.request(method, url, **kwargs)

        # Basic rate-limit handling (403)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset:
                wait_s = max(0, int(reset) - int(time.time()))
                print(
                    f"[WARN] Rate limit reached. Waiting {wait_s}s...", file=sys.stderr
                )
                time.sleep(wait_s + 1)
                resp = self.session.request(method, url, **kwargs)
        return resp

    # ---------- Analyses ----------
    def list_code_scanning_analyses(
        self, per_page: int = 100
    ) -> Iterable[Dict[str, Any]]:
        """
        Lists analyses starting with the most recent (paginated).
        """
        page = 1
        while True:
            path = f"/repos/{self.repo}/code-scanning/analyses"
            params: Dict[str, Any] = {"per_page": per_page, "page": page}
            resp = self._request("GET", path, params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"GET {path} failed: {resp.status_code} {resp.text}")
            items = cast(List[Dict[str, Any]], resp.json())
            if not items:
                break
            for it in items:
                yield it
            page += 1

    def delete_analysis(self, analysis_id: int) -> None:
        """
        Delete a code scanning analysis. If GitHub returns 200/202 with
        next_analysis_url / confirm_delete_url, follow-up DELETE requests are required
        until we reach 204 or a 200 with both URLs null (end of series). Also handle
        400 asking for confirm_delete by retrying with ?confirm_delete=true.
        """
        base_path = f"/repos/{self.repo}/code-scanning/analyses/{analysis_id}"

        if self.dry_run:
            print(f"[DRY-RUN] Would DELETE analysis {analysis_id}")
            return

        def _delete_raw_url(url: str) -> requests.Response:
            # Low-level DELETE against a fully-qualified URL (confirm/next)
            return self.session.delete(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "clear-vulns-script",
                },
            )

        # First attempt (no confirm flag)
        resp = self._request("DELETE", base_path)

        # Success
        if resp.status_code == 204:
            return

        # Last-of-type: GitHub asks for explicit confirmation (400)
        if resp.status_code == 400 and "confirm_delete" in (resp.text or "").lower():
            # Retry with explicit confirm_delete=true on the same analysis
            path_with_confirm = f"{base_path}?confirm_delete=true"
            resp2 = self._request("DELETE", path_with_confirm)
            if resp2.status_code == 204:
                return
            # If falls back to the usual 200/202 flow, treat below
            resp = resp2

        # 200/202 → follow-up flow (or last analysis with null URLs)
        if resp.status_code in (200, 202):
            try:
                payload = cast(Dict[str, Any], resp.json())
            except ValueError:
                payload = {}

            confirm_url = cast(Optional[str], payload.get("confirm_delete_url"))
            next_url = cast(Optional[str], payload.get("next_analysis_url"))

            # If both URLs are null, we’re done (final item processed)  ✅
            if not confirm_url and not next_url:
                return

            # Prefer confirm_delete_url to remove all analyses; next_analysis_url preserves a final one if desired
            target_url: Optional[str] = confirm_url or next_url
            if not target_url:
                raise RuntimeError(
                    f"DELETE {base_path} returned {resp.status_code} without confirm/next URL: {resp.text}"
                )

            # Ensure confirm_delete=true is present
            if "confirm_delete=" not in target_url:
                sep = "&" if "?" in target_url else "?"
                target_url = f"{target_url}{sep}confirm_delete=true"

            follow = _delete_raw_url(target_url)
            if follow.status_code == 204:
                return

            # Loop while the server continues to give next/confirm URLs
            while follow.status_code in (200, 202):
                try:
                    p2 = cast(Dict[str, Any], follow.json())
                except ValueError:
                    p2 = {}

                c2 = cast(Optional[str], p2.get("confirm_delete_url"))
                n2 = cast(Optional[str], p2.get("next_analysis_url"))

                if not c2 and not n2:
                    # Final 200 with null URLs -> success
                    return

                t2: Optional[str] = c2 or n2
                if t2 is None:
                    raise RuntimeError(
                        f"DELETE follow-up returned no URL: {follow.text}"
                    )

                if "confirm_delete=" not in t2:
                    sep = "&" if "?" in t2 else "?"
                    t2 = f"{t2}{sep}confirm_delete=true"

                follow = _delete_raw_url(t2)
                if follow.status_code == 204:
                    return

            # Non-handled status from follow-up
            if follow.status_code not in (200, 202, 204):
                raise RuntimeError(
                    f"DELETE follow-up {target_url} failed: {follow.status_code} {follow.text}"
                )
            return

        # Any other status is an error
        raise RuntimeError(f"DELETE {base_path} failed: {resp.status_code} {resp.text}")

    # ---------- Alerts ----------
    def list_code_scanning_alerts(
        self, state: str = "open", per_page: int = 100
    ) -> Iterable[Dict[str, Any]]:
        page = 1
        while True:
            path = f"/repos/{self.repo}/code-scanning/alerts"
            params: Dict[str, Any] = {
                "per_page": per_page,
                "page": page,
                "state": state,
            }
            resp = self._request("GET", path, params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"GET {path} failed: {resp.status_code} {resp.text}")
            items = cast(List[Dict[str, Any]], resp.json())
            if not items:
                break
            for it in items:
                yield it
            page += 1

    def dismiss_alert(self, alert_number: int, reason: str, comment: str) -> None:
        path = f"/repos/{self.repo}/code-scanning/alerts/{alert_number}"
        data: Dict[str, Any] = {
            "dismissed": True,
            "dismissed_reason": reason,
            "dismissed_comment": comment,
        }
        if self.dry_run:
            print(f"[DRY-RUN] Would dismiss alert #{alert_number} with {data}")
            return
        resp = self._request("PATCH", path, json=data)
        if resp.status_code != 200:
            raise RuntimeError(f"PATCH {path} failed: {resp.status_code} {resp.text}")


# ---------- Helpers ----------


def parse_tools_csv(csv_value: Optional[str]) -> List[str]:
    if not csv_value:
        return []
    return [t.strip() for t in csv_value.split(",") if t.strip()]


def is_tool_selected(tool_name: Optional[str], tools_filter: List[str]) -> bool:
    if not tools_filter:
        return True  # no filter => apply to all
    if not tool_name:
        return False
    return tool_name in tools_filter


# ---------- Operations ----------


def delete_analyses(
    gh: GitHubSecurityClient, tools_filter: List[str]
) -> Tuple[int, int]:
    """
    Bulk delete: repeatedly find a deletable analysis for selected tools, delete it,
    and continue until no deletable analyses remain. This follows GitHub guidance to
    start from the most recent and work backwards.
    Returns: (scanned, deleted)
    """
    scanned = 0
    deleted = 0

    while True:
        found: Optional[Dict[str, Any]] = None
        # Scan the current page of analyses to find one marked deletable
        for a in gh.list_code_scanning_analyses():
            scanned += 1
            tool_name = cast(Optional[str], (a.get("tool") or {}).get("name"))

            if not is_tool_selected(tool_name, tools_filter):
                continue

            if a.get("deletable", False):
                found = a
                break

        if not found:
            # No more deletable analyses for the selected tools
            break

        analysis_id_any = found.get("id")
        if analysis_id_any is None:
            # Skip malformed entry
            continue
        try:
            analysis_id = int(analysis_id_any)
        except (TypeError, ValueError):
            # Skip non-integer id
            continue

        tn = cast(Optional[str], (found.get("tool") or {}).get("name"))
        print(f"[INFO] Deleting analysis id={analysis_id} tool={tn or 'unknown'}")
        gh.delete_analysis(analysis_id)
        deleted += 1

    return scanned, deleted


def dismiss_alerts(
    gh: GitHubSecurityClient,
    tools_filter: List[str],
    reason: str,
    comment: str,
    state: str = "open",
) -> Tuple[int, int]:
    """
    Dismiss alerts (state=open by default). Optional tool filter.
    Returns: (scanned, dismissed)
    """
    scanned = 0
    dismissed = 0
    for al in gh.list_code_scanning_alerts(state=state):
        scanned += 1
        tool_name = cast(Optional[str], (al.get("tool") or {}).get("name"))
        if not is_tool_selected(tool_name, tools_filter):
            continue
        number_any = al.get("number")
        if number_any is None:
            continue
        try:
            number = int(number_any)
        except (TypeError, ValueError):
            continue
        rule_id = cast(Optional[str], (al.get("rule") or {}).get("id")) or cast(
            Optional[str], (al.get("rule") or {}).get("name")
        )
        print(
            f"[INFO] Dismiss alert #{number} tool={tool_name} rule={rule_id} reason={reason}"
        )
        gh.dismiss_alert(number, reason=reason, comment=comment)
        dismissed += 1
    return scanned, dismissed


# ---------- Facade function (to be called from main) ----------


def clear_vulns(
    repo: str,
    mode: str,
    token: Optional[str] = None,
    tools: Optional[str] = "Trivy,Grype",
    reason: str = "won't_fix",
    comment: str = "Bulk reset: issues will reappear if they persist.",
    state: str = "open",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Single entrypoint to use from src/main.py and workflows.

    mode: "delete" | "dismiss"
    tools: CSV of tool names ("" for all)
    reason/comment: only for mode=dismiss
    """
    token = token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError(
            "Missing GITHUB_TOKEN. Provide --token or set env GITHUB_TOKEN."
        )
    tools_filter = parse_tools_csv(tools)

    gh = GitHubSecurityClient(token=token, repo=repo, dry_run=dry_run)

    if mode == "delete":
        scanned, deleted = delete_analyses(gh, tools_filter)
        return {"mode": "delete", "scanned": scanned, "deleted": deleted}
    elif mode == "dismiss":
        valid = {"false_positive", "won't_fix", "used_in_tests"}
        if reason not in valid:
            raise ValueError(
                f"Invalid reason '{reason}'. Allowed: {', '.join(sorted(valid))}"
            )
        scanned, dism = dismiss_alerts(
            gh, tools_filter, reason=reason, comment=comment, state=state
        )
        return {"mode": "dismiss", "scanned": scanned, "dismissed": dism}
    else:
        raise ValueError("mode must be 'delete' or 'dismiss'.")
