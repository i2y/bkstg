"""GitHub content fetcher using gh CLI."""

from __future__ import annotations

import base64
import json
import logging
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GitHubFileInfo:
    """Parsed GitHub URL information."""

    owner: str
    repo: str
    ref: str
    path: str


class GitHubFetcher:
    """Fetches file content from GitHub repositories using gh CLI."""

    # Patterns for parsing GitHub URLs
    GITHUB_BLOB_PATTERN = re.compile(
        r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)"
    )
    GITHUB_RAW_PATTERN = re.compile(
        r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)"
    )

    def parse_github_url(self, url: str) -> GitHubFileInfo | None:
        """Parse a GitHub URL into its components.

        Supported formats:
        - https://github.com/{owner}/{repo}/blob/{ref}/{path}
        - https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}

        Returns:
            GitHubFileInfo if URL is valid, None otherwise.
        """
        for pattern in [self.GITHUB_BLOB_PATTERN, self.GITHUB_RAW_PATTERN]:
            match = pattern.match(url)
            if match:
                owner, repo, ref, path = match.groups()
                return GitHubFileInfo(owner=owner, repo=repo, ref=ref, path=path)
        return None

    def is_github_url(self, url: str) -> bool:
        """Check if URL is a supported GitHub URL."""
        return self.parse_github_url(url) is not None

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

    def fetch_raw_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = "main",
    ) -> str | None:
        """Fetch raw file content from a GitHub repository.

        Uses gh api to get file contents, then decodes from base64.

        Args:
            owner: Repository owner/organization
            repo: Repository name
            path: File path within repository
            ref: Git reference (branch, tag, or commit SHA)

        Returns:
            File content as string, or None if fetch failed.
        """
        api_path = f"repos/{owner}/{repo}/contents/{path}"
        if ref:
            api_path += f"?ref={ref}"

        try:
            result = subprocess.run(
                ["gh", "api", api_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.warning(
                    f"Failed to fetch {owner}/{repo}/{path}: {result.stderr}"
                )
                return None

            data = json.loads(result.stdout)

            # Check if it's a file (not a directory)
            if data.get("type") != "file":
                logger.warning(f"Path {path} is not a file in {owner}/{repo}")
                return None

            # Decode base64 content
            content_b64 = data.get("content", "")
            if not content_b64:
                logger.warning(f"No content found for {owner}/{repo}/{path}")
                return None

            # GitHub returns base64 with newlines
            content_b64 = content_b64.replace("\n", "")
            content = base64.b64decode(content_b64).decode("utf-8")
            return content

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout fetching {owner}/{repo}/{path}")
            return None
        except FileNotFoundError:
            logger.error("gh CLI not found. Please install GitHub CLI.")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response for {owner}/{repo}/{path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching {owner}/{repo}/{path}: {e}")
            return None

    def fetch_from_url(self, url: str) -> str | None:
        """Fetch content from a GitHub URL.

        Args:
            url: GitHub URL (blob or raw format)

        Returns:
            File content as string, or None if fetch failed.
        """
        info = self.parse_github_url(url)
        if not info:
            logger.warning(f"Invalid GitHub URL: {url}")
            return None

        return self.fetch_raw_content(
            owner=info.owner,
            repo=info.repo,
            path=info.path,
            ref=info.ref,
        )
