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
from ..git.repo_manager import LocationCloneInfo
from ..i18n import t
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
            Button(t("sync.pull"))
            .on_click(lambda _: on_pull())
            .bg_color(theme.colors.text_info)
            .fixed_width(70)
            .fixed_height(28)
        )

    if status.state == SyncState.LOCAL_AHEAD:
        actions.append(
            Button(t("sync.push"))
            .on_click(lambda _: on_push())
            .bg_color(theme.colors.text_success)
            .fixed_width(70)
            .fixed_height(28)
        )

    if status.state == SyncState.DIVERGED:
        actions.append(
            Button(t("sync.pull"))
            .on_click(lambda _: on_pull())
            .fixed_width(60)
            .fixed_height(28)
        )
        actions.append(Spacer().fixed_width(8))
        actions.append(
            Button(t("sync.create_pr"))
            .on_click(lambda _: on_create_pr())
            .bg_color(theme.colors.text_warning)
            .fixed_width(90)
            .fixed_height(28)
        )

    if status.state in [SyncState.SYNCED, SyncState.NOT_CLONED, SyncState.UNKNOWN]:
        actions.append(
            Button(t("common.sync"))
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


def _build_location_clone_card(
    clone_info: LocationCloneInfo,
    status: dict | None,
    on_pull: Callable[[], None],
    on_push: Callable[[], None],
    on_create_pr: Callable[[], None],
):
    """Build a card showing status for a Location clone."""
    theme = ThemeManager().current

    # Determine status icon and color based on git status
    if status is None:
        icon, color = "--", theme.colors.fg
        state_text = "Not cloned"
    elif status["ahead"] > 0 and status["behind"] > 0:
        icon, color = "<>", theme.colors.text_warning
        state_text = f"Diverged (+{status['ahead']}/-{status['behind']})"
    elif status["ahead"] > 0:
        icon, color = ">>", theme.colors.text_success
        state_text = f"Local ahead (+{status['ahead']})"
    elif status["behind"] > 0:
        icon, color = "<<", theme.colors.text_info
        state_text = f"Remote ahead (+{status['behind']})"
    else:
        icon, color = "OK", theme.colors.text_success
        state_text = "Synced"

    # Build action buttons
    actions = []

    if status:
        if status["behind"] > 0:
            actions.append(
                Button(t("sync.pull"))
                .on_click(lambda _: on_pull())
                .bg_color(theme.colors.text_info)
                .fixed_width(70)
                .fixed_height(28)
            )
            actions.append(Spacer().fixed_width(8))

        if status["ahead"] > 0:
            actions.append(
                Button(t("sync.push"))
                .on_click(lambda _: on_push())
                .bg_color(theme.colors.text_success)
                .fixed_width(70)
                .fixed_height(28)
            )
            actions.append(Spacer().fixed_width(8))
            actions.append(
                Button(t("sync.create_pr"))
                .on_click(lambda _: on_create_pr())
                .bg_color(theme.colors.text_warning)
                .fixed_width(90)
                .fixed_height(28)
            )

    # Details text
    details = f"{clone_info.owner}/{clone_info.repo}:{clone_info.branch}"
    if clone_info.path:
        details += f"/{clone_info.path}"

    return Row(
        Spacer().fixed_width(12),
        # Status icon
        Text(f"[{icon}]", font_size=14).text_color(color).fixed_width(40),
        # Clone info
        Column(
            Row(
                Text(t("sync.location_clone"), font_size=10).text_color(theme.colors.text_info),
                Spacer().fixed_width(8),
                Text(f"{clone_info.owner}/{clone_info.repo}", font_size=14).text_color(
                    theme.colors.text_primary
                ),
            ).fixed_height(18),
            Text(details, font_size=11).text_color(theme.colors.fg),
            Text(state_text, font_size=11).text_color(color),
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
        is_location: bool = False,
    ):
        super().__init__()
        self._source_name = source_name
        self._on_create = on_create
        self._on_cancel = on_cancel
        self._is_location = is_location

        self._title_state = InputState(f"bkstg: Update catalogs")
        self._body_state = InputState("Automated sync from bkstg")

    def view(self):
        theme = ThemeManager().current

        return Column(
            Spacer().fixed_height(16),
            Row(
                Spacer().fixed_width(16),
                Text(t("sync.pr_for", source=self._source_name), font_size=13).text_color(
                    theme.colors.text_primary
                ),
                Spacer(),
            ).fixed_height(24),
            Spacer().fixed_height(16),
            Row(
                Spacer().fixed_width(16),
                Text(t("sync.pr_title"), font_size=13).text_color(theme.colors.text_primary),
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
                Text(t("sync.pr_description"), font_size=13).text_color(theme.colors.text_primary),
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
                Button(t("common.cancel"))
                .on_click(lambda _: self._on_cancel())
                .fixed_width(80)
                .fixed_height(32),
                Spacer().fixed_width(8),
                Button(t("sync.create_pr"))
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
    """Main sync panel showing all GitHub sources and Location clones."""

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
        self._pr_is_location = False
        self._pr_location_info: LocationCloneInfo | None = None

    def view(self):
        theme = ThemeManager().current
        sources = self._catalog_state.get_github_sources()
        statuses = self._catalog_state.get_all_sync_status()
        location_clones = self._catalog_state.get_location_clones()

        # Build status map for quick lookup
        status_map = {s.source_name: s for s in statuses}

        main_content = Column(
            Spacer().fixed_height(16),
            # Header
            Row(
                Spacer().fixed_width(16),
                Text(t("sync.title"), font_size=18).text_color(theme.colors.text_primary),
                Spacer(),
                Button(t("sync.refresh"))
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
                Text(t("sync.help_text"), font_size=11).text_color(theme.colors.fg),
                Spacer(),
            ).fixed_height(20),
            Spacer().fixed_height(8),
            # Source cards (GitHub Sources + Location clones)
            self._build_source_list(sources, status_map, location_clones),
        ).flex(1)

        # PR creation modal
        modal = Modal(
            content=PRDialog(
                source_name=self._pr_source_name,
                on_create=self._create_pr,
                on_cancel=self._close_pr_dialog,
                is_location=self._pr_is_location,
            ),
            state=self._pr_modal_state,
            title=t("sync.create_pr"),
            width=500,
            height=320,
        )

        return Box(main_content, modal)

    def _build_source_list(
        self,
        sources: list[GitHubSource],
        status_map: dict[str, SyncStatus],
        location_clones: dict[str, LocationCloneInfo],
    ):
        theme = ThemeManager().current

        # Filter to sync-enabled sources
        sync_sources = [s for s in sources if s.sync_enabled]

        if not sync_sources and not location_clones:
            return Column(
                Spacer().fixed_height(100),
                Row(
                    Spacer(),
                    Text(t("sync.no_sync_sources"), font_size=14).text_color(theme.colors.fg),
                    Spacer(),
                ).fixed_height(24),
                Row(
                    Spacer(),
                    Text(t("sync.enable_sync_hint"), font_size=12).text_color(theme.colors.fg),
                    Spacer(),
                ).fixed_height(20),
            ).flex(1)

        items = []

        # GitHub Sources
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

        # Location clones
        for repo_key, clone_info in location_clones.items():
            status = self._catalog_state.get_location_clone_status(
                clone_info.owner, clone_info.repo, clone_info.branch
            )
            items.append(
                _build_location_clone_card(
                    clone_info=clone_info,
                    status=status,
                    on_pull=lambda ci=clone_info: self._pull_location(ci),
                    on_push=lambda ci=clone_info: self._push_location(ci),
                    on_create_pr=lambda ci=clone_info: self._show_location_pr_dialog(ci),
                )
            )
            items.append(Spacer().fixed_height(8))

        return Column(*items, scrollable=True).flex(1)

    def _refresh(self, _):
        self._status_message.set(t("sync.refreshed"))
        self._render_trigger.set(self._render_trigger() + 1)

    def _pull(self, source_name: str):
        self._is_syncing.set(True)
        self._status_message.set(t("sync.pulling", source=source_name))
        self._render_trigger.set(self._render_trigger() + 1)

        def on_progress(msg: str):
            self._status_message.set(msg)

        result = self._catalog_state.pull_source(source_name, on_progress)

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _push(self, source_name: str):
        self._is_syncing.set(True)
        self._status_message.set(t("sync.pushing", source=source_name))
        self._render_trigger.set(self._render_trigger() + 1)

        def on_progress(msg: str):
            self._status_message.set(msg)

        result = self._catalog_state.push_source(source_name, on_progress=on_progress)

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _sync(self, source_name: str):
        self._is_syncing.set(True)
        self._status_message.set(t("sync.syncing", source=source_name))
        self._render_trigger.set(self._render_trigger() + 1)

        def on_progress(msg: str):
            self._status_message.set(msg)

        result = self._catalog_state.sync_source(source_name, on_progress=on_progress)

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _show_pr_dialog(self, source_name: str):
        self._pr_source_name = source_name
        self._pr_is_location = False
        self._pr_location_info = None
        self._pr_modal_state.open()

    def _close_pr_dialog(self):
        self._pr_modal_state.close()
        self._render_trigger.set(self._render_trigger() + 1)

    def _create_pr(self, title: str, body: str):
        self._pr_modal_state.close()
        self._status_message.set(t("sync.creating_pr"))
        self._render_trigger.set(self._render_trigger() + 1)

        if self._pr_is_location and self._pr_location_info:
            # Location clone PR
            result = self._catalog_state.create_location_pr(
                self._pr_location_info.owner,
                self._pr_location_info.repo,
                self._pr_location_info.branch,
                title,
                body,
            )
        else:
            # GitHub source PR
            def on_progress(msg: str):
                self._status_message.set(msg)

            result = self._catalog_state.create_sync_pr(
                self._pr_source_name,
                title,
                body,
                on_progress=on_progress,
            )

        if result.pr_url:
            self._status_message.set(t("sync.pr_created", url=result.pr_url))
        else:
            self._status_message.set(result.message)

        self._render_trigger.set(self._render_trigger() + 1)

    # ========== Location clone methods ==========

    def _pull_location(self, clone_info: LocationCloneInfo):
        self._is_syncing.set(True)
        self._status_message.set(t("sync.pulling", source=f"{clone_info.owner}/{clone_info.repo}"))
        self._render_trigger.set(self._render_trigger() + 1)

        result = self._catalog_state.pull_location_clone(
            clone_info.owner, clone_info.repo, clone_info.branch
        )

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _push_location(self, clone_info: LocationCloneInfo):
        self._is_syncing.set(True)
        self._status_message.set(t("sync.pushing", source=f"{clone_info.owner}/{clone_info.repo}"))
        self._render_trigger.set(self._render_trigger() + 1)

        result = self._catalog_state.push_location_clone(
            clone_info.owner, clone_info.repo, clone_info.branch
        )

        self._is_syncing.set(False)
        self._status_message.set(result.message)
        self._render_trigger.set(self._render_trigger() + 1)

    def _show_location_pr_dialog(self, clone_info: LocationCloneInfo):
        self._pr_source_name = f"{clone_info.owner}/{clone_info.repo}"
        self._pr_is_location = True
        self._pr_location_info = clone_info
        self._pr_modal_state.open()
