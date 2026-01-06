"""Create Pull Requests via gh CLI."""

from __future__ import annotations

import json
import logging
import subprocess

logger = logging.getLogger(__name__)


class PRCreator:
    """Create Pull Requests using gh CLI."""

    def create_pr(
        self,
        owner: str,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> str | None:
        """Create a Pull Request.

        Args:
            owner: Repository owner
            repo: Repository name
            head: Head branch (with changes)
            base: Base branch (target)
            title: PR title
            body: PR description

        Returns:
            PR URL if successful, None otherwise.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    f"{owner}/{repo}",
                    "--head",
                    head,
                    "--base",
                    base,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                # gh pr create outputs the PR URL
                pr_url = result.stdout.strip()
                logger.info(f"Created PR: {pr_url}")
                return pr_url
            else:
                logger.error(f"Failed to create PR: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            logger.error("PR creation timed out")
            return None
        except FileNotFoundError:
            logger.error("gh CLI not found. Please install GitHub CLI.")
            return None
        except Exception as e:
            logger.error(f"PR creation exception: {e}")
            return None

    def get_pr_status(
        self,
        owner: str,
        repo: str,
        branch: str,
    ) -> dict | None:
        """Get PR status for a branch.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch to check for PRs

        Returns:
            PR info dict or None if no PR exists.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    branch,
                    "--repo",
                    f"{owner}/{repo}",
                    "--json",
                    "number,state,url,title",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return json.loads(result.stdout)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("PR status check timed out")
            return None
        except json.JSONDecodeError:
            return None
        except Exception as e:
            logger.error(f"Failed to get PR status: {e}")
            return None

    def list_open_prs(
        self,
        owner: str,
        repo: str,
        head_prefix: str = "bkstg-sync-",
    ) -> list[dict]:
        """List open PRs created by bkstg.

        Args:
            owner: Repository owner
            repo: Repository name
            head_prefix: Prefix for PR head branches

        Returns:
            List of PR info dicts.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    f"{owner}/{repo}",
                    "--state",
                    "open",
                    "--json",
                    "number,state,url,title,headRefName",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                prs = json.loads(result.stdout)
                # Filter by head prefix
                return [
                    pr
                    for pr in prs
                    if pr.get("headRefName", "").startswith(head_prefix)
                ]
            return []
        except Exception as e:
            logger.error(f"Failed to list PRs: {e}")
            return []
