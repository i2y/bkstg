"""High-level sync manager for bidirectional GitHub synchronization."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Callable

from .conflict_detector import ConflictDetector, ConflictInfo
from .pr_creator import PRCreator
from .repo_manager import GitRepoManager, GitStatus, LocationCloneInfo

if TYPE_CHECKING:
    from ..config import GitHubSource

logger = logging.getLogger(__name__)


class SyncState(Enum):
    """Current sync state."""

    SYNCED = "synced"  # Local and remote are identical
    LOCAL_AHEAD = "local_ahead"  # Local has unpushed changes
    REMOTE_AHEAD = "remote_ahead"  # Remote has changes to pull
    DIVERGED = "diverged"  # Both have changes (potential conflict)
    CONFLICT = "conflict"  # Actual merge conflict detected
    NOT_CLONED = "not_cloned"  # Repository not cloned yet
    UNKNOWN = "unknown"  # Not yet determined


@dataclass
class SyncStatus:
    """Sync status for a source."""

    source_name: str
    state: SyncState
    local_changes: int = 0
    remote_changes: int = 0
    conflicting_files: list[str] = field(default_factory=list)
    last_sync: datetime | None = None
    message: str = ""


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    message: str
    pr_url: str | None = None
    conflicts: list[ConflictInfo] | None = None


class SyncManager:
    """Manages bidirectional sync between local and GitHub."""

    def __init__(self, repo_manager: GitRepoManager | None = None):
        """Initialize sync manager.

        Args:
            repo_manager: GitRepoManager instance (creates new if None)
        """
        self._repo_manager = repo_manager or GitRepoManager()
        self._conflict_detector = ConflictDetector(self._repo_manager)
        self._pr_creator = PRCreator()
        self._last_sync: dict[str, datetime] = {}

    @property
    def repo_manager(self) -> GitRepoManager:
        """Get the repo manager instance."""
        return self._repo_manager

    def refresh_all(
        self,
        sources: list[GitHubSource],
        location_clones: list[LocationCloneInfo],
    ) -> None:
        """Fetch all sources and location clones to update remote tracking branches.

        This allows get_sync_status to return accurate ahead/behind counts.
        """
        # Fetch GitHub sources
        for source in sources:
            if self._repo_manager.has_clone(source):
                self._repo_manager.fetch_only(source)

        # Fetch location clones
        for clone_info in location_clones:
            self._repo_manager.fetch_location_clone(clone_info.local_path)

    def get_sync_status(self, source: GitHubSource) -> SyncStatus:
        """Get current sync status for a source.

        Args:
            source: GitHub source to check

        Returns:
            SyncStatus with current state information.
        """
        if not self._repo_manager.has_clone(source):
            return SyncStatus(
                source_name=source.name,
                state=SyncState.NOT_CLONED,
                message="Not cloned - click Sync to initialize",
            )

        status = self._repo_manager.get_status(source)

        if status is None:
            return SyncStatus(
                source_name=source.name,
                state=SyncState.UNKNOWN,
                last_sync=self._last_sync.get(source.name),
                message="Unable to get status",
            )

        local_changes = (
            len(status.modified)
            + len(status.added)
            + len(status.deleted)
            + len(status.untracked)
        )

        # Check for potential conflicts
        conflicting_files = []
        if local_changes > 0 and status.behind > 0:
            conflicting_files = self._conflict_detector.get_conflicting_files(
                source
            )

        if status.has_conflicts:
            state = SyncState.CONFLICT
            message = "Merge conflicts detected"
        elif conflicting_files:
            state = SyncState.DIVERGED
            message = f"{len(conflicting_files)} file(s) may conflict"
        elif status.ahead > 0 and status.behind > 0:
            # Committed changes on both sides - branches have diverged
            state = SyncState.DIVERGED
            message = f"+{status.ahead}/-{status.behind} commits diverged"
        elif local_changes > 0 and status.behind > 0:
            # Uncommitted local changes + remote ahead
            state = SyncState.DIVERGED
            message = f"{local_changes} local, {status.behind} remote changes"
        elif local_changes > 0 or status.ahead > 0:
            state = SyncState.LOCAL_AHEAD
            message = f"{status.ahead} commit(s) to push"
        elif status.behind > 0:
            state = SyncState.REMOTE_AHEAD
            message = f"{status.behind} commit(s) to pull"
        else:
            state = SyncState.SYNCED
            message = "Up to date"

        return SyncStatus(
            source_name=source.name,
            state=state,
            local_changes=local_changes,
            remote_changes=status.behind,
            conflicting_files=conflicting_files,
            last_sync=self._last_sync.get(source.name),
            message=message,
        )

    def pull(
        self,
        source: GitHubSource,
        on_progress: Callable[[str], None] | None = None,
    ) -> SyncResult:
        """Pull remote changes to local.

        Args:
            source: GitHub source to pull from
            on_progress: Progress callback

        Returns:
            SyncResult with success status and message.
        """
        if on_progress:
            on_progress("Fetching from remote...")

        clone_path = self._repo_manager.clone_or_update(source)
        if clone_path is None:
            return SyncResult(
                success=False, message="Failed to clone/update repository"
            )

        if on_progress:
            on_progress("Checking for conflicts...")

        # Check for conflicts before merge
        conflicts = self._conflict_detector.detect_conflicts(source)
        if conflicts:
            return SyncResult(
                success=False,
                message="Conflicts detected - create PR to resolve",
                conflicts=conflicts,
            )

        if on_progress:
            on_progress("Merging changes...")

        # Perform merge
        success, message = self._repo_manager.merge(source)

        if success:
            self._last_sync[source.name] = datetime.now()
            return SyncResult(success=True, message="Pull successful")
        else:
            if "conflict" in message.lower():
                return SyncResult(
                    success=False,
                    message="Merge conflict - create PR to resolve",
                )
            return SyncResult(success=False, message=f"Merge failed: {message}")

    def push(
        self,
        source: GitHubSource,
        commit_message: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> SyncResult:
        """Push local changes to remote.

        Args:
            source: GitHub source to push to
            commit_message: Commit message (if uncommitted changes exist)
            on_progress: Progress callback

        Returns:
            SyncResult with success status and message.
        """
        if on_progress:
            on_progress("Checking local status...")

        if not self._repo_manager.has_clone(source):
            return SyncResult(
                success=False, message="Clone not found - run Sync first"
            )

        status = self._repo_manager.get_status(source)
        if status is None:
            return SyncResult(success=False, message="Failed to get status")

        # Commit if there are uncommitted changes
        local_changes = (
            len(status.modified)
            + len(status.added)
            + len(status.deleted)
            + len(status.untracked)
        )

        if local_changes > 0:
            if not commit_message:
                commit_message = f"bkstg: Update {local_changes} file(s)"

            if on_progress:
                on_progress("Committing changes...")

            if not self._repo_manager.commit(source, commit_message):
                return SyncResult(success=False, message="Commit failed")

        # Re-check status after commit
        status = self._repo_manager.get_status(source)
        if status and status.ahead == 0:
            return SyncResult(success=True, message="Nothing to push")

        # Check if remote has changes we need to pull first
        if status and status.behind > 0:
            return SyncResult(
                success=False,
                message="Remote has changes - pull first or create PR",
            )

        if on_progress:
            on_progress("Pushing to remote...")

        success, message = self._repo_manager.push(source)
        if success:
            self._last_sync[source.name] = datetime.now()
            # Sync local clone after push to stay in sync with remote
            if on_progress:
                on_progress("Syncing local clone...")
            self._repo_manager.clone_or_update(source, skip_fetch=False)

        return SyncResult(success=success, message=message)

    def sync(
        self,
        source: GitHubSource,
        commit_message: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> SyncResult:
        """Full bidirectional sync: clone/fetch, then pull, then push.

        Args:
            source: GitHub source
            commit_message: Commit message for local changes
            on_progress: Progress callback

        Returns:
            SyncResult with success status and message.
        """
        # First, ensure we have a clone and fetch
        if on_progress:
            on_progress("Initializing...")

        clone_path = self._repo_manager.clone_or_update(source)
        if clone_path is None:
            return SyncResult(
                success=False, message="Failed to clone/update repository"
            )

        # Check status
        status = self.get_sync_status(source)

        if status.state == SyncState.SYNCED:
            return SyncResult(success=True, message="Already up to date")

        if status.state == SyncState.REMOTE_AHEAD:
            # Just pull
            return self.pull(source, on_progress)

        if status.state == SyncState.LOCAL_AHEAD:
            # Just push
            return self.push(source, commit_message, on_progress)

        if status.state == SyncState.DIVERGED:
            # Try to pull first, then push
            pull_result = self.pull(source, on_progress)
            if not pull_result.success:
                return pull_result

            return self.push(source, commit_message, on_progress)

        return SyncResult(success=True, message="Sync complete")

    def force_sync(
        self,
        source: GitHubSource,
        on_progress: Callable[[str], None] | None = None,
    ) -> SyncResult:
        """Force sync by discarding local changes and resetting to remote.

        WARNING: This will discard ALL local uncommitted and committed changes.

        Args:
            source: GitHub source to force sync
            on_progress: Progress callback

        Returns:
            SyncResult with success status and message.
        """
        if not self._repo_manager.has_clone(source):
            return SyncResult(
                success=False, message="Clone not found - run Sync first"
            )

        if on_progress:
            on_progress("Fetching from remote...")

        clone_path = self._repo_manager.get_clone_path(source)

        # Fetch latest from remote
        self._repo_manager.clone_or_update(source, skip_fetch=False)

        if on_progress:
            on_progress("Resetting to remote...")

        # Hard reset to remote branch
        success, msg = self._repo_manager.run_git_command(
            clone_path, ["reset", "--hard", f"origin/{source.branch}"]
        )
        if not success:
            return SyncResult(success=False, message=f"Reset failed: {msg}")

        # Clean untracked files
        self._repo_manager.run_git_command(clone_path, ["clean", "-fd"])

        self._last_sync[source.name] = datetime.now()
        return SyncResult(
            success=True, message="Force sync complete - local changes discarded"
        )

    def create_pr_for_conflicts(
        self,
        source: GitHubSource,
        title: str,
        body: str,
        branch_name: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> SyncResult:
        """Create a PR to resolve conflicts.

        When local and remote have diverged, create a PR from local changes.

        Args:
            source: GitHub source
            title: PR title
            body: PR description
            branch_name: Custom branch name (auto-generated if None)
            on_progress: Progress callback

        Returns:
            SyncResult with PR URL if successful.
        """
        if not self._repo_manager.has_clone(source):
            return SyncResult(
                success=False, message="Clone not found - run Sync first"
            )

        if branch_name is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"bkstg-sync-{timestamp}"

        # Make sure we have uncommitted changes committed
        status = self._repo_manager.get_status(source)
        if status:
            local_changes = (
                len(status.modified)
                + len(status.added)
                + len(status.deleted)
                + len(status.untracked)
            )
            if local_changes > 0:
                if on_progress:
                    on_progress("Committing local changes...")
                self._repo_manager.commit(
                    source, f"bkstg: Changes for PR {branch_name}"
                )

        if on_progress:
            on_progress(f"Creating branch {branch_name}...")

        # Create new branch
        if not self._repo_manager.create_branch(source, branch_name):
            return SyncResult(success=False, message="Failed to create branch")

        if on_progress:
            on_progress("Pushing branch to remote...")

        # Push the branch
        success, message = self._repo_manager.push_with_upstream(
            source, branch_name
        )
        if not success:
            # Switch back to main branch
            self._repo_manager.checkout_branch(source, source.branch)
            return SyncResult(
                success=False, message=f"Failed to push branch: {message}"
            )

        if on_progress:
            on_progress("Creating Pull Request...")

        # Create PR
        pr_url = self._pr_creator.create_pr(
            owner=source.owner,
            repo=source.repo,
            head=branch_name,
            base=source.branch,
            title=title,
            body=body,
        )

        # Switch back to main branch
        self._repo_manager.checkout_branch(source, source.branch)

        if pr_url:
            return SyncResult(
                success=True, message="PR created successfully", pr_url=pr_url
            )
        else:
            return SyncResult(success=False, message="Failed to create PR")

    def get_open_prs(self, source: GitHubSource) -> list[dict]:
        """Get open PRs created by bkstg for this source.

        Args:
            source: GitHub source

        Returns:
            List of PR info dicts.
        """
        return self._pr_creator.list_open_prs(source.owner, source.repo)
