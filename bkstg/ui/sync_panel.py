"""Sync panel UI component for GitHub synchronization."""

from __future__ import annotations

from typing import Callable

from castella import (
    Box,
    Button,
    Column,
    Component,
    Input,
    InputState,
    Modal,
    ModalState,
    Row,
    Spacer,
    State,
    Text,
)
from castella.theme import ThemeManager

from ..config import GitHubSource
from ..git.sync_manager import SyncState, SyncStatus
from ..state.catalog_state import CatalogState


def _get_state_icon(state: SyncState) -> tuple[str, str]:
    """Get icon and color for sync state."""
    theme = ThemeManager().current
    icons = {
        SyncState.SYNCED: ("OK", theme.colors.text_success),
        SyncState.LOCAL_AHEAD: (">>", theme.colors.text_info),
        SyncState.REMOTE_AHEAD: ("<<", theme.colors.text_warning),
        SyncState.DIVERGED: ("<>", theme.colors.text_warning),
        SyncState.CONFLICT: ("!!", theme.colors.text_danger),
        SyncState.NOT_CLONED: ("--", theme.colors.fg),
        SyncState.UNKNOWN: ("??", theme.colors.fg),
    }
    return icons.get(state, ("??", theme.colors.fg))


def _build_sync_status_card(
    status: SyncStatus,
    source: GitHubSource,
    on_pull: Callable[[], None],
    on_push: Callable[[], None],
    on_sync: Callable[[], None],
    on_create_pr: Callable[[], None],
):
    """Build a card showing sync status for a single source."""
    theme = ThemeManager().current
    icon, color = _get_state_icon(status.state)

    # Build action buttons based on state
    actions = []

    if status.state == SyncState.REMOTE_AHEAD:
        actions.append(
            Button("Pull")
            .on_click(lambda _: on_pull())
            .bg_color(theme.colors.text_info)
            .fixed_width(70)
            .fixed_height(28)
        )

    if status.state == SyncState.LOCAL_AHEAD:
        actions.append(
            Button("Push")
            .on_click(lambda _: on_push())
            .bg_color(theme.colors.text_success)
            .fixed_width(70)
            .fixed_height(28)
        )

    if status.state == SyncState.DIVERGED:
        actions.append(
            Button("Pull")
            .on_click(lambda _: on_pull())
            .fixed_width(60)
            .fixed_height(28)
        )
        actions.append(Spacer().fixed_width(8))
        actions.append(
            Button("Create PR")
            .on_click(lambda _: on_create_pr())
            .bg_color(theme.colors.text_warning)
            .fixed_width(90)
            .fixed_height(28)
        )

    if status.state in [SyncState.SYNCED, SyncState.NOT_CLONED, SyncState.UNKNOWN]:
        actions.append(
            Button("Sync")
            .on_click(lambda _: on_sync())
            .bg_color(theme.colors.text_info)
            .fixed_width(70)
            .fixed_height(28)
        )

    # Details text
    details = f"{source.owner}/{source.repo}:{source.branch}"
    if source.path:
        details += f"/{source.path}"

    return Row(
        Spacer().fixed_width(12),
        # Status icon
        Text(f"[{icon}]", font_size=14).text_color(color).fixed_width(40),
        # Source name and status
        Column(
            Text(status.source_name, font_size=14).text_color(
                theme.colors.text_primary
            ),
            Text(details, font_size=11).text_color(theme.colors.fg),
            Text(status.message, font_size=11).text_color(color),
        ).flex(1),
        # Actions
        *actions,
        Spacer().fixed_width(12),
    ).fixed_height(72).bg_color(theme.colors.bg_secondary)


class PRDialog(Component):
    """Dialog for creating a Pull Request."""

    def __init__(
        self,
        source_name: str,
        on_create: Callable[[str, str], None],
        on_cancel: Callable[[], None],
    ):
        super().__init__()
        self._source_name = source_name
        self._on_create = on_create
        self._on_cancel = on_cancel

        self._title_state = InputState(f"bkstg: Update catalogs")
        self._body_state = InputState("Automated sync from bkstg")

    def view(self):
        theme = ThemeManager().current

        return Column(
            Spacer().fixed_height(16),
            Row(
                Spacer().fixed_width(16),
                Text(f"Create PR for: {self._source_name}", font_size=13).text_color(
                    theme.colors.text_primary
                ),
                Spacer(),
            ).fixed_height(24),
            Spacer().fixed_height(16),
            Row(
                Spacer().fixed_width(16),
                Text("Title", font_size=13).text_color(theme.colors.text_primary),
                Spacer(),
            ).fixed_height(24),
            Row(
                Spacer().fixed_width(16),
                Input(self._title_state).flex(1),
                Spacer().fixed_width(16),
            ).fixed_height(36),
            Spacer().fixed_height(16),
            Row(
                Spacer().fixed_width(16),
                Text("Description", font_size=13).text_color(theme.colors.text_primary),
                Spacer(),
            ).fixed_height(24),
            Row(
                Spacer().fixed_width(16),
                Input(self._body_state).flex(1),
                Spacer().fixed_width(16),
            ).fixed_height(36),
            Spacer(),
            Row(
                Spacer(),
                Button("Cancel")
                .on_click(lambda _: self._on_cancel())
                .fixed_width(80)
                .fixed_height(32),
                Spacer().fixed_width(8),
                Button("Create PR")
                .on_click(self._create)
                .bg_color(theme.colors.text_success)
                .fixed_width(100)
                .fixed_height(32),
                Spacer().fixed_width(16),
            ).fixed_height(40),
            Spacer().fixed_height(16),
        )

    def _create(self, _):
        title = self._title_state.value().strip()
        body = self._body_state.value().strip()
        if title:
            self._on_create(title, body)


class SyncPanel(Component):
    """Main sync panel showing all GitHub sources."""

    def __init__(self, catalog_state: CatalogState):
        super().__init__()
        self._catalog_state = catalog_state

        # UI State
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

        self._status_message = State("")
        self._status_message.attach(self)

        self._is_syncing = State(False)
        self._is_syncing.attach(self)

        # PR Dialog state
        self._pr_modal_state = ModalState()
        self._pr_modal_state.attach(self)
        self._pr_source_name = ""

    def view(self):
        theme = ThemeManager().current
        sources = self._catalog_state.get_github_sources()
        statuses = self._catalog_state.get_all_sync_status()

        # Build status map for quick lookup
        status_map = {s.source_name: s for s in statuses}

        main_content = Column(
            Spacer().fixed_height(16),
            # Header
            Row(
                Spacer().fixed_width(16),
                Text("GitHub Sync", font_size=18).text_color(theme.colors.text_primary),
                Spacer(),
                Button("Refresh")
                .on_click(self._refresh)
                .fixed_width(80)
                .fixed_height(32),
                Spacer().fixed_width(16),
            ).fixed_height(48),
            # Status message
            (
                Row(
                    Spacer().fixed_width(16),
                    Text(self._status_message(), font_size=12).text_color(
                        theme.colors.text_info
                    ),
                    Spacer(),
                ).fixed_height(24)
                if self._status_message()
                else Spacer().fixed_height(8)
            ),
            # Help text
            Row(
                Spacer().fixed_width(16),
                Text(
                    "Sync-enabled GitHub sources are shown below. Enable sync in Source Settings.",
                    font_size=11,
                ).text_color(theme.colors.fg),
                Spacer(),
            ).fixed_height(20),
            Spacer().fixed_height(8),
            # Source cards
            self._build_source_list(sources, status_map),
        ).flex(1)

        # PR creation modal
        modal = Modal(
            content=PRDialog(
                source_name=self._pr_source_name,
                on_create=self._create_pr,
                on_cancel=self._close_pr_dialog,
            ),
            state=self._pr_modal_state,
            title="Create Pull Request",
            width=500,
            height=320,
        )

        return Box(main_content, modal)

    def _build_source_list(
        self, sources: list[GitHubSource], status_map: dict[str, SyncStatus]
    ):
        theme = ThemeManager().current

        # Filter to sync-enabled sources
        sync_sources = [s for s in sources if s.sync_enabled]

        if not sync_sources:
            return Column(
                Spacer().fixed_height(100),
                Row(
                    Spacer(),
                    Text(
                        "No sync-enabled GitHub sources",
                        font_size=14,
                    ).text_color(theme.colors.fg),
                    Spacer(),
                ).fixed_height(24),
                Row(
                    Spacer(),
                    Text(
                        "Enable 'sync_enabled: true' in bkstg.yaml for a GitHub source",
                        font_size=12,
                    ).text_color(theme.colors.fg),
                    Spacer(),
                ).fixed_height(20),
            ).flex(1)

        items = []
        for source in sync_sources:
            status = status_map.get(source.name)
            if status:
                items.append(
                    _build_sync_status_card(
                        status=status,
                        source=source,
                        on_pull=lambda name=source.name: self._pull(name),
                        on_push=lambda name=source.name: self._push(name),
                        on_sync=lambda name=source.name: self._sync(name),
                        on_create_pr=lambda name=source.name: self._show_pr_dialog(name),
                    )
                )
                items.append(Spacer().fixed_height(8))

        return Column(*items, scrollable=True).flex(1)

    def _refresh(self, _):
        self._status_message.set("Refreshed")
        self._render_trigger.set(self._render_trigger() + 1)

    def _pull(self, source_name: str):
        self._is_syncing.set(True)
        self._status_message.set(f"Pulling {source_name}...")
        self._render_trigger.set(self._render_trigger() + 1)

        def on_progress(msg: str):
            self._status_message.set(msg)

        result = self._catalog_state.pull_source(source_name, on_progress)

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _push(self, source_name: str):
        self._is_syncing.set(True)
        self._status_message.set(f"Pushing {source_name}...")
        self._render_trigger.set(self._render_trigger() + 1)

        def on_progress(msg: str):
            self._status_message.set(msg)

        result = self._catalog_state.push_source(source_name, on_progress=on_progress)

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _sync(self, source_name: str):
        self._is_syncing.set(True)
        self._status_message.set(f"Syncing {source_name}...")
        self._render_trigger.set(self._render_trigger() + 1)

        def on_progress(msg: str):
            self._status_message.set(msg)

        result = self._catalog_state.sync_source(source_name, on_progress=on_progress)

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _show_pr_dialog(self, source_name: str):
        self._pr_source_name = source_name
        self._pr_modal_state.open()

    def _close_pr_dialog(self):
        self._pr_modal_state.close()
        self._render_trigger.set(self._render_trigger() + 1)

    def _create_pr(self, title: str, body: str):
        self._pr_modal_state.close()
        self._status_message.set("Creating PR...")
        self._render_trigger.set(self._render_trigger() + 1)

        def on_progress(msg: str):
            self._status_message.set(msg)

        result = self._catalog_state.create_sync_pr(
            self._pr_source_name,
            title,
            body,
            on_progress=on_progress,
        )

        if result.pr_url:
            self._status_message.set(f"PR created: {result.pr_url}")
        else:
            self._status_message.set(result.message)

        self._render_trigger.set(self._render_trigger() + 1)
