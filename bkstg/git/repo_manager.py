"""Git repository manager for local clones of GitHub sources."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import GitHubSource

logger = logging.getLogger(__name__)


@dataclass
class CloneInfo:
    """Information about a local clone."""

    local_path: Path
    remote_url: str
    branch: str
    last_pull: float | None = None
    last_push: float | None = None


@dataclass
class GitStatus:
    """Git status information."""

    modified: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0
    has_conflicts: bool = False


class GitRepoManager:
    """Manages local git clones for GitHub sources."""

    CLONES_DIR = ".bkstg-clones"

    def __init__(self, base_path: Path | None = None):
        """Initialize with base path for clones.

        Args:
            base_path: Base path for clones. Defaults to ~/.bkstg-clones/
        """
        self._base_path = base_path or (Path.home() / self.CLONES_DIR)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._clones: dict[str, CloneInfo] = {}

    def get_clone_path(self, source: GitHubSource) -> Path:
        """Get local path for a GitHub source clone.

        Pattern: {base_path}/{owner}_{repo}_{branch}/
        """
        safe_name = f"{source.owner}_{source.repo}_{source.branch}"
        return self._base_path / safe_name

    def clone_or_update(self, source: GitHubSource) -> Path | None:
        """Clone repository if not exists, or fetch latest.

        Returns:
            Local path to clone, or None if failed.
        """
        clone_path = self.get_clone_path(source)

        if clone_path.exists() and (clone_path / ".git").exists():
            # Fetch latest
            return self._fetch(clone_path, source.branch)
        else:
            # Clone fresh
            return self._clone(source, clone_path)

    def _clone(self, source: GitHubSource, clone_path: Path) -> Path | None:
        """Clone repository using gh CLI."""
        repo_url = f"https://github.com/{source.owner}/{source.repo}.git"

        try:
            result = subprocess.run(
                [
                    "gh",
                    "repo",
                    "clone",
                    f"{source.owner}/{source.repo}",
                    str(clone_path),
                    "--",
                    "-b",
                    source.branch,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info(f"Cloned {repo_url} to {clone_path}")
                return clone_path
            else:
                logger.error(f"Clone failed: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout cloning {repo_url}")
            return None
        except FileNotFoundError:
            logger.error("gh CLI not found. Please install GitHub CLI.")
            return None
        except Exception as e:
            logger.error(f"Clone exception: {e}")
            return None

    def _fetch(self, clone_path: Path, branch: str) -> Path | None:
        """Fetch latest changes from remote."""
        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "fetch", "origin"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(f"Fetch failed: {result.stderr}")
            return clone_path
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout fetching {clone_path}")
            return clone_path
        except Exception as e:
            logger.error(f"Fetch exception: {e}")
            return clone_path

    def get_status(self, source: GitHubSource) -> GitStatus | None:
        """Get git status for a source's local clone."""
        clone_path = self.get_clone_path(source)
        if not (clone_path / ".git").exists():
            return None

        try:
            # Get file status
            result = subprocess.run(
                ["git", "-C", str(clone_path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            modified = []
            added = []
            deleted = []
            untracked = []

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                status = line[:2]
                filepath = line[3:]

                if status[0] == "M" or status[1] == "M":
                    modified.append(filepath)
                elif status[0] == "A":
                    added.append(filepath)
                elif status[0] == "D" or status[1] == "D":
                    deleted.append(filepath)
                elif status == "??":
                    untracked.append(filepath)

            # Get ahead/behind
            ahead, behind = 0, 0
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone_path),
                    "rev-list",
                    "--left-right",
                    "--count",
                    f"origin/{source.branch}...HEAD",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    behind, ahead = int(parts[0]), int(parts[1])

            return GitStatus(
                modified=modified,
                added=added,
                deleted=deleted,
                untracked=untracked,
                ahead=ahead,
                behind=behind,
                has_conflicts=False,
            )
        except Exception as e:
            logger.error(f"Status failed: {e}")
            return None

    def commit(
        self,
        source: GitHubSource,
        message: str,
        files: list[str] | None = None,
    ) -> bool:
        """Commit changes in local clone.

        Args:
            source: GitHub source
            message: Commit message
            files: Specific files to commit (None = all changes)

        Returns:
            True if commit succeeded, False otherwise.
        """
        clone_path = self.get_clone_path(source)

        try:
            # Stage files
            if files:
                for f in files:
                    subprocess.run(
                        ["git", "-C", str(clone_path), "add", f],
                        capture_output=True,
                        timeout=30,
                    )
            else:
                subprocess.run(
                    ["git", "-C", str(clone_path), "add", "-A"],
                    capture_output=True,
                    timeout=30,
                )

            # Commit
            result = subprocess.run(
                ["git", "-C", str(clone_path), "commit", "-m", message],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(f"Committed: {message}")
                return True
            else:
                # No changes to commit is ok
                if "nothing to commit" in result.stdout:
                    return True
                logger.warning(f"Commit failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            return False

    def push(
        self,
        source: GitHubSource,
        branch: str | None = None,
    ) -> tuple[bool, str]:
        """Push commits to remote.

        Args:
            source: GitHub source
            branch: Branch to push (None = source.branch)

        Returns:
            (success, message) tuple
        """
        clone_path = self.get_clone_path(source)
        target_branch = branch or source.branch

        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "push", "origin", target_branch],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info(f"Pushed to origin/{target_branch}")
                return True, "Push successful"
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Push timed out"
        except Exception as e:
            return False, str(e)

    def push_with_upstream(
        self,
        source: GitHubSource,
        branch: str,
    ) -> tuple[bool, str]:
        """Push a new branch with upstream tracking.

        Args:
            source: GitHub source
            branch: Branch to push

        Returns:
            (success, message) tuple
        """
        clone_path = self.get_clone_path(source)

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone_path),
                    "push",
                    "-u",
                    "origin",
                    branch,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info(f"Pushed new branch origin/{branch}")
                return True, "Push successful"
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Push timed out"
        except Exception as e:
            return False, str(e)

    def create_branch(self, source: GitHubSource, branch_name: str) -> bool:
        """Create a new branch.

        Args:
            source: GitHub source
            branch_name: Name for new branch

        Returns:
            True if branch created successfully.
        """
        clone_path = self.get_clone_path(source)

        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "checkout", "-b", branch_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(f"Created branch: {branch_name}")
                return True
            else:
                logger.error(f"Branch creation failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Branch creation failed: {e}")
            return False

    def checkout_branch(self, source: GitHubSource, branch_name: str) -> bool:
        """Checkout existing branch.

        Args:
            source: GitHub source
            branch_name: Branch to checkout

        Returns:
            True if checkout succeeded.
        """
        clone_path = self.get_clone_path(source)

        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "checkout", branch_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(f"Checked out: {branch_name}")
                return True
            else:
                logger.error(f"Checkout failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Checkout failed: {e}")
            return False

    def merge(
        self,
        source: GitHubSource,
        branch: str | None = None,
    ) -> tuple[bool, str]:
        """Merge remote branch into current branch.

        Args:
            source: GitHub source
            branch: Remote branch to merge (default: origin/{source.branch})

        Returns:
            (success, message) tuple
        """
        clone_path = self.get_clone_path(source)
        target = branch or f"origin/{source.branch}"

        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "merge", target],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return True, "Merge successful"
            else:
                if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
                    return False, "Merge conflict detected"
                return False, result.stderr
        except Exception as e:
            return False, str(e)

    def get_file_diff(self, source: GitHubSource, filepath: str) -> str:
        """Get diff for a specific file.

        Args:
            source: GitHub source
            filepath: Path to file

        Returns:
            Diff output as string.
        """
        clone_path = self.get_clone_path(source)

        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "diff", "HEAD", "--", filepath],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout
        except Exception as e:
            return f"Error getting diff: {e}"

    def get_remote_diff(self, source: GitHubSource) -> str:
        """Get diff between local and remote.

        Args:
            source: GitHub source

        Returns:
            Diff output as string.
        """
        clone_path = self.get_clone_path(source)

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone_path),
                    "diff",
                    f"origin/{source.branch}...HEAD",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout
        except Exception as e:
            return f"Error getting remote diff: {e}"

    def get_current_branch(self, source: GitHubSource) -> str | None:
        """Get current branch name.

        Args:
            source: GitHub source

        Returns:
            Current branch name or None.
        """
        clone_path = self.get_clone_path(source)

        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def has_clone(self, source: GitHubSource) -> bool:
        """Check if a clone exists for the source.

        Args:
            source: GitHub source

        Returns:
            True if clone exists.
        """
        clone_path = self.get_clone_path(source)
        return clone_path.exists() and (clone_path / ".git").exists()

    def get_catalogs_path(self, source: GitHubSource) -> Path:
        """Get the path to catalogs directory within clone.

        Args:
            source: GitHub source

        Returns:
            Path to catalogs directory.
        """
        clone_path = self.get_clone_path(source)
        if source.path:
            return clone_path / source.path
        return clone_path
