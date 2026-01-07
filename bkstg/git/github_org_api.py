"""GitHub Organization API client using gh CLI."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GitHubMember:
    """GitHub organization member."""

    login: str
    id: int
    avatar_url: str | None = None
    html_url: str | None = None
    name: str | None = None
    email: str | None = None


@dataclass
class GitHubTeam:
    """GitHub organization team."""

    id: int
    slug: str
    name: str
    description: str | None = None
    privacy: str | None = None
    html_url: str | None = None


class GitHubOrgAPI:
    """Fetches organization data from GitHub using gh CLI."""

    def __init__(self, org: str):
        self.org = org

    def check_auth_status(self) -> bool:
        """Check if gh CLI is authenticated.

        Returns:
            True if authenticated, False otherwise.
        """
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to check gh auth status: {e}")
            return False

    def check_org_access(self) -> bool:
        """Check if authenticated user has access to the organization.

        Returns:
            True if access is granted, False otherwise.
        """
        try:
            result = subprocess.run(
                ["gh", "api", f"orgs/{self.org}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to check org access: {e}")
            return False

    def list_members(self) -> list[GitHubMember]:
        """List organization members.

        Returns:
            List of GitHubMember objects.
        """
        try:
            result = subprocess.run(
                ["gh", "api", f"orgs/{self.org}/members", "--paginate"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(f"Failed to list members: {result.stderr}")
                return []

            data = json.loads(result.stdout)
            return [
                GitHubMember(
                    login=m["login"],
                    id=m["id"],
                    avatar_url=m.get("avatar_url"),
                    html_url=m.get("html_url"),
                )
                for m in data
            ]
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout listing members for {self.org}")
            return []
        except FileNotFoundError:
            logger.error("gh CLI not found. Please install GitHub CLI.")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error listing members: {e}")
            return []

    def get_user_details(self, login: str) -> dict | None:
        """Get detailed user info (name, email).

        Args:
            login: GitHub username

        Returns:
            User details dict or None if failed.
        """
        try:
            result = subprocess.run(
                ["gh", "api", f"users/{login}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            return None

    def list_teams(self) -> list[GitHubTeam]:
        """List organization teams.

        Returns:
            List of GitHubTeam objects.
        """
        try:
            result = subprocess.run(
                ["gh", "api", f"orgs/{self.org}/teams", "--paginate"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(f"Failed to list teams: {result.stderr}")
                return []

            data = json.loads(result.stdout)
            return [
                GitHubTeam(
                    id=t["id"],
                    slug=t["slug"],
                    name=t["name"],
                    description=t.get("description"),
                    privacy=t.get("privacy"),
                    html_url=t.get("html_url"),
                )
                for t in data
            ]
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout listing teams for {self.org}")
            return []
        except FileNotFoundError:
            logger.error("gh CLI not found. Please install GitHub CLI.")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error listing teams: {e}")
            return []

    def list_team_members(self, team_slug: str) -> list[GitHubMember]:
        """List team members.

        Args:
            team_slug: Team slug identifier

        Returns:
            List of GitHubMember objects.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    f"orgs/{self.org}/teams/{team_slug}/members",
                    "--paginate",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(f"Failed to list team members: {result.stderr}")
                return []

            data = json.loads(result.stdout)
            return [
                GitHubMember(
                    login=m["login"],
                    id=m["id"],
                    avatar_url=m.get("avatar_url"),
                    html_url=m.get("html_url"),
                )
                for m in data
            ]
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout listing team members for {team_slug}")
            return []
        except FileNotFoundError:
            logger.error("gh CLI not found. Please install GitHub CLI.")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error listing team members: {e}")
            return []
