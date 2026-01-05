"""Catalog Sources Settings UI for managing catalog sources."""

from __future__ import annotations

from typing import Callable

from castella import (
    Box,
    Button,
    CheckBox,
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

from ..config import BkstgConfig, GitHubSource, LocalSource
from ..state.catalog_state import CatalogState


class LocalSourceEditor(Component):
    """Editor for a local directory source."""

    def __init__(
        self,
        source: LocalSource | None,
        on_save: Callable[[LocalSource], None],
        on_cancel: Callable[[], None],
    ):
        super().__init__()
        self._source = source
        self._on_save = on_save
        self._on_cancel = on_cancel

        # Form states
        self._name_state = InputState(source.name if source else "")
        self._path_state = InputState(source.path if source else "./catalogs")
        self._enabled = source.enabled if source else True

        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current

        return Column(
            Spacer().fixed_height(16),
            # Name field
            Text("Name *", font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            Input(self._name_state).fixed_height(36),
            Spacer().fixed_height(16),
            # Path field
            Text("Path *", font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            Input(self._path_state).fixed_height(36),
            Spacer().fixed_height(16),
            # Enabled checkbox
            Row(
                CheckBox(self._enabled).on_click(self._toggle_enabled).fixed_width(24),
                Spacer().fixed_width(8),
                Text("Enabled", font_size=13).text_color(theme.colors.text_primary),
            ).fixed_height(32),
            Spacer(),
            # Buttons
            Row(
                Spacer(),
                Button("Cancel").on_click(lambda _: self._on_cancel()).fixed_width(80),
                Spacer().fixed_width(8),
                Button("Save")
                .on_click(self._save)
                .bg_color(theme.colors.text_success)
                .fixed_width(80),
            ).fixed_height(40),
            Spacer().fixed_height(16),
        )

    def _toggle_enabled(self, _):
        self._enabled = not self._enabled
        self._render_trigger.set(self._render_trigger() + 1)

    def _save(self, _):
        name = self._name_state.value().strip()
        path = self._path_state.value().strip()

        if not name or not path:
            return

        source = LocalSource(
            name=name,
            path=path,
            enabled=self._enabled,
        )
        self._on_save(source)


class GitHubSourceEditor(Component):
    """Editor for a GitHub repository source."""

    def __init__(
        self,
        source: GitHubSource | None,
        on_save: Callable[[GitHubSource], None],
        on_cancel: Callable[[], None],
    ):
        super().__init__()
        self._source = source
        self._on_save = on_save
        self._on_cancel = on_cancel

        # Form states
        self._name_state = InputState(source.name if source else "")
        self._owner_state = InputState(source.owner if source else "")
        self._repo_state = InputState(source.repo if source else "")
        self._branch_state = InputState(source.branch if source else "main")
        self._path_state = InputState(source.path if source else "")
        self._enabled = source.enabled if source else True

        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current

        return Column(
            Spacer().fixed_height(16),
            # Name field
            Text("Name *", font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            Input(self._name_state).fixed_height(36),
            Spacer().fixed_height(12),
            # Owner field
            Text("Owner *", font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            Input(self._owner_state).fixed_height(36),
            Spacer().fixed_height(12),
            # Repo field
            Text("Repository *", font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            Input(self._repo_state).fixed_height(36),
            Spacer().fixed_height(12),
            # Branch field
            Text("Branch", font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            Input(self._branch_state).fixed_height(36),
            Spacer().fixed_height(12),
            # Path field
            Text("Path (within repo)", font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            Input(self._path_state).fixed_height(36),
            Spacer().fixed_height(12),
            # Enabled checkbox
            Row(
                CheckBox(self._enabled).on_click(self._toggle_enabled).fixed_width(24),
                Spacer().fixed_width(8),
                Text("Enabled", font_size=13).text_color(theme.colors.text_primary),
            ).fixed_height(32),
            Spacer(),
            # Buttons
            Row(
                Spacer(),
                Button("Cancel").on_click(lambda _: self._on_cancel()).fixed_width(80),
                Spacer().fixed_width(8),
                Button("Save")
                .on_click(self._save)
                .bg_color(theme.colors.text_success)
                .fixed_width(80),
            ).fixed_height(40),
            Spacer().fixed_height(16),
        )

    def _toggle_enabled(self, _):
        self._enabled = not self._enabled
        self._render_trigger.set(self._render_trigger() + 1)

    def _save(self, _):
        name = self._name_state.value().strip()
        owner = self._owner_state.value().strip()
        repo = self._repo_state.value().strip()
        branch = self._branch_state.value().strip() or "main"
        path = self._path_state.value().strip()

        if not name or not owner or not repo:
            return

        source = GitHubSource(
            name=name,
            owner=owner,
            repo=repo,
            branch=branch,
            path=path,
            enabled=self._enabled,
        )
        self._on_save(source)


class CatalogSourcesSettingsTab(Component):
    """Settings tab for managing catalog sources."""

    def __init__(self, catalog_state: CatalogState):
        super().__init__()
        self._catalog_state = catalog_state
        self._config = catalog_state.get_config()

        # Deep copy sources for editing
        self._sources = [s.model_copy() for s in self._config.sources]

        # Modal state
        self._modal_state = ModalState()
        self._modal_state.attach(self)

        # Editing state
        self._editing_index: int | None = None
        self._editing_type: str = "local"  # "local" or "github"

        # UI state
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

        self._is_dirty = State(False)
        self._is_dirty.attach(self)

        self._status = State("")
        self._status.attach(self)

    def view(self):
        theme = ThemeManager().current

        main_content = Column(
            Spacer().fixed_height(16),
            # Header
            Row(
                Spacer().fixed_width(16),
                Text("Catalog Sources", font_size=18).text_color(theme.colors.text_primary),
                Spacer(),
                Button("+ Local")
                .on_click(lambda _: self._add_source("local"))
                .fixed_width(80)
                .fixed_height(32),
                Spacer().fixed_width(8),
                Button("+ GitHub")
                .on_click(lambda _: self._add_source("github"))
                .fixed_width(90)
                .fixed_height(32),
                Spacer().fixed_width(16),
                Button("Save" + (" *" if self._is_dirty() else ""))
                .on_click(self._save_config)
                .bg_color(theme.colors.text_success if self._is_dirty() else theme.colors.bg_secondary)
                .fixed_width(80)
                .fixed_height(32),
                Spacer().fixed_width(16),
            ).fixed_height(48),
            # Status message
            Row(
                Spacer().fixed_width(16),
                Text(self._status(), font_size=12)
                .text_color(theme.colors.text_info)
                .fixed_height(20)
                if self._status()
                else Spacer().fixed_height(4),
            ).fixed_height(20),
            Spacer().fixed_height(8),
            # Sources list
            self._build_sources_list(),
        ).flex(1)

        # Modal for editing
        modal = Modal(
            content=self._build_modal_content(),
            state=self._modal_state,
            title=self._get_modal_title(),
            width=450,
            height=500 if self._editing_type == "github" else 350,
        )

        return Box(main_content, modal)

    def _build_sources_list(self):
        theme = ThemeManager().current
        items = []

        for i, source in enumerate(self._sources):
            items.append(self._source_card(i, source))
            items.append(Spacer().fixed_height(8))

        if not items:
            return Column(
                Spacer(),
                Text("No sources configured", font_size=14).text_color(theme.colors.fg),
                Text("Click '+ Local' or '+ GitHub' to add a source", font_size=12).text_color(theme.colors.fg),
                Spacer(),
            ).flex(1)

        return Column(*items, scrollable=True).flex(1)

    def _source_card(self, index: int, source: LocalSource | GitHubSource):
        theme = ThemeManager().current

        if isinstance(source, LocalSource):
            icon = "L"
            details = source.path
            icon_color = theme.colors.text_info
        else:
            icon = "GH"
            details = f"{source.owner}/{source.repo}:{source.branch}"
            if source.path:
                details += f"/{source.path}"
            icon_color = theme.colors.text_warning

        bg = theme.colors.bg_secondary if source.enabled else theme.colors.bg_primary

        return Row(
            Spacer().fixed_width(8),
            # Enable checkbox
            CheckBox(source.enabled)
            .on_click(lambda _, idx=index: self._toggle_source(idx))
            .fixed_width(24),
            Spacer().fixed_width(12),
            # Icon
            Text(f"[{icon}]", font_size=13).text_color(icon_color).fixed_width(40),
            Spacer().fixed_width(8),
            # Name and details
            Column(
                Text(source.name, font_size=14).text_color(theme.colors.text_primary),
                Text(details, font_size=11).text_color(theme.colors.fg),
            ).flex(1),
            # Actions
            Button("Edit")
            .on_click(lambda _, idx=index: self._edit_source(idx))
            .fixed_width(60)
            .fixed_height(28),
            Spacer().fixed_width(8),
            Button("Del")
            .on_click(lambda _, idx=index: self._delete_source(idx))
            .bg_color(theme.colors.text_danger)
            .fixed_width(50)
            .fixed_height(28),
            Spacer().fixed_width(8),
        ).fixed_height(56).bg_color(bg)

    def _toggle_source(self, index: int):
        if 0 <= index < len(self._sources):
            self._sources[index].enabled = not self._sources[index].enabled
            self._is_dirty.set(True)
            self._render_trigger.set(self._render_trigger() + 1)

    def _add_source(self, source_type: str):
        self._editing_index = None
        self._editing_type = source_type
        self._modal_state.open()

    def _edit_source(self, index: int):
        if 0 <= index < len(self._sources):
            self._editing_index = index
            source = self._sources[index]
            self._editing_type = "local" if isinstance(source, LocalSource) else "github"
            self._modal_state.open()

    def _delete_source(self, index: int):
        if 0 <= index < len(self._sources):
            self._sources.pop(index)
            self._is_dirty.set(True)
            self._render_trigger.set(self._render_trigger() + 1)

    def _save_config(self, _):
        # Create updated config
        new_config = BkstgConfig(
            version=self._config.version,
            sources=self._sources,
            settings=self._config.settings,
        )
        self._catalog_state.update_config(new_config)
        self._config = new_config
        self._is_dirty.set(False)
        self._status.set("Configuration saved and catalog reloaded")
        self._render_trigger.set(self._render_trigger() + 1)

    def _get_modal_title(self) -> str:
        action = "Edit" if self._editing_index is not None else "Add"
        source_type = "Local Source" if self._editing_type == "local" else "GitHub Source"
        return f"{action} {source_type}"

    def _build_modal_content(self):
        source = None
        if self._editing_index is not None and 0 <= self._editing_index < len(self._sources):
            source = self._sources[self._editing_index]

        if self._editing_type == "local":
            return LocalSourceEditor(
                source=source if isinstance(source, LocalSource) else None,
                on_save=self._on_source_save,
                on_cancel=self._close_modal,
            )
        else:
            return GitHubSourceEditor(
                source=source if isinstance(source, GitHubSource) else None,
                on_save=self._on_source_save,
                on_cancel=self._close_modal,
            )

    def _on_source_save(self, source: LocalSource | GitHubSource):
        if self._editing_index is not None:
            self._sources[self._editing_index] = source
        else:
            self._sources.append(source)

        self._is_dirty.set(True)
        self._close_modal()

    def _close_modal(self):
        self._editing_index = None
        self._modal_state.close()
        self._render_trigger.set(self._render_trigger() + 1)
