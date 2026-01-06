"""Detect conflicts between local and remote changes."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import GitHubSource
    from .repo_manager import GitRepoManager

logger = logging.getLogger(__name__)


@dataclass
class ConflictInfo:
    """Information about a conflict."""

    filepath: str
    conflict_type: str  # "both_modified", "deleted_modified", etc.


class ConflictDetector:
    """Detect merge conflicts before actual merge."""

    def __init__(self, repo_manager: GitRepoManager):
        """Initialize with repo manager.

        Args:
            repo_manager: GitRepoManager instance
        """
        self._repo_manager = repo_manager

    def detect_conflicts(self, source: GitHubSource) -> list[ConflictInfo]:
        """Detect potential conflicts between local and remote.

        Uses dry-run merge to detect conflicts without modifying the working tree.

        Args:
            source: GitHub source to check

        Returns:
            List of conflicting files, empty if no conflicts.
        """
        clone_path = self._repo_manager.get_clone_path(source)
        if not clone_path.exists():
            return []

        try:
            # Try a dry-run merge
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone_path),
                    "merge",
                    "--no-commit",
                    "--no-ff",
                    f"origin/{source.branch}",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            conflicts = []

            # Check for conflicts in output
            if result.returncode != 0:
                output = result.stdout + result.stderr
                if "CONFLICT" in output:
                    # Parse conflict files from output
                    for line in output.split("\n"):
                        if "CONFLICT" in line:
                            # Extract filepath from various CONFLICT messages
                            if "Merge conflict in" in line:
                                filepath = line.split("Merge conflict in ")[-1].strip()
                                conflicts.append(
                                    ConflictInfo(
                                        filepath=filepath,
                                        conflict_type="both_modified",
                                    )
                                )
                            elif "deleted in" in line:
                                # e.g., "CONFLICT (modify/delete): file.txt deleted in HEAD..."
                                parts = line.split(":")
                                if len(parts) > 1:
                                    filepath = parts[1].strip().split()[0]
                                    conflicts.append(
                                        ConflictInfo(
                                            filepath=filepath,
                                            conflict_type="deleted_modified",
                                        )
                                    )

            # Always abort the merge to restore state
            subprocess.run(
                ["git", "-C", str(clone_path), "merge", "--abort"],
                capture_output=True,
                timeout=30,
            )

            return conflicts

        except subprocess.TimeoutExpired:
            # Try to abort any in-progress merge
            subprocess.run(
                ["git", "-C", str(clone_path), "merge", "--abort"],
                capture_output=True,
                timeout=10,
            )
            logger.error("Conflict detection timed out")
            return []
        except Exception as e:
            logger.error(f"Conflict detection failed: {e}")
            return []

    def get_conflicting_files(self, source: GitHubSource) -> list[str]:
        """Get list of files that would conflict in a merge.

        This is a lightweight check that only compares which files
        were modified on both sides.

        Args:
            source: GitHub source to check

        Returns:
            List of file paths that may conflict.
        """
        clone_path = self._repo_manager.get_clone_path(source)
        if not clone_path.exists():
            return []

        try:
            # Get files modified locally (staged + unstaged)
            local_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone_path),
                    "diff",
                    "--name-only",
                    f"origin/{source.branch}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            local_files = set(
                f for f in local_result.stdout.strip().split("\n") if f
            )

            # Get files modified on remote since common ancestor
            remote_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone_path),
                    "diff",
                    "--name-only",
                    f"HEAD...origin/{source.branch}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            remote_files = set(
                f for f in remote_result.stdout.strip().split("\n") if f
            )

            # Intersection = potential conflicts
            return list(local_files & remote_files)

        except Exception as e:
            logger.error(f"Failed to get conflicting files: {e}")
            return []

    def has_uncommitted_changes(self, source: GitHubSource) -> bool:
        """Check if there are uncommitted changes.

        Args:
            source: GitHub source to check

        Returns:
            True if there are uncommitted changes.
        """
        status = self._repo_manager.get_status(source)
        if status is None:
            return False

        return bool(
            status.modified
            or status.added
            or status.deleted
            or status.untracked
        )
