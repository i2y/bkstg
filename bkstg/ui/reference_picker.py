"""Entity reference picker components - Modal-free version.

The actual Modal is managed by the parent FormEditor using Box pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel, Field

from castella import (
    Button,
    Column,
    Component,
    DataTable,
    DataTableState,
    Input,
    InputState,
    Row,
    Spacer,
    State,
    Text,
)
from castella.theme import ThemeManager

from ..i18n import t
from ..models.base import EntityKind
from ..state.catalog_state import CatalogState

if TYPE_CHECKING:
    from ..models.base import BaseEntity


class PickerRow(BaseModel):
    """Row model for entity picker table."""

    name: str = Field(title="Name")
    kind: str = Field(title="Kind")
    title: str = Field(title="Title")


class ReferencePicker(Component):
    """Single entity reference picker - button only, Modal managed by parent."""

    def __init__(
        self,
        label: str,
        target_kinds: list[EntityKind],
        catalog_state: CatalogState,
        current_value: str,
        on_select: Callable[[str], None],
        on_open_picker: Callable[[], None],
        required: bool = False,
    ):
        super().__init__()
        self._label = label
        self._target_kinds = target_kinds
        self._catalog_state = catalog_state
        self._current_value = current_value
        self._on_select = on_select
        self._on_open_picker = on_open_picker
        self._required = required

        # Render trigger state
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def _trigger_render(self):
        """Trigger a re-render."""
        self._render_trigger.set(self._render_trigger() + 1)

    @property
    def label(self) -> str:
        return self._label

    @property
    def target_kinds(self) -> list[EntityKind]:
        return self._target_kinds

    @property
    def current_value(self) -> str:
        return self._current_value

    def set_value(self, value: str):
        """Set the current value."""
        self._current_value = value
        self._on_select(value)
        self._trigger_render()

    def view(self):
        theme = ThemeManager().current
        display_text = self._get_display_text()
        label_text = f"{self._label} *" if self._required else self._label

        return Column(
            Text(label_text, font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Row(
                Button(display_text or t("form.placeholder.select"))
                .on_click(lambda _: self._on_open_picker())
                .flex(1)
                .fixed_height(36),
                (
                    Button(t("common.x"))
                    .on_click(lambda _: self._clear())
                    .fixed_width(36)
                    .fixed_height(36)
                    if self._current_value
                    else Spacer().fixed_width(0)
                ),
            ).fixed_height(36),
            Spacer().fixed_height(8),
        )

    def _get_display_text(self) -> str:
        """Get display text for current selection."""
        if not self._current_value:
            return ""

        # Try to get entity title
        entity = self._catalog_state.get_by_id(self._current_value)
        if entity:
            return entity.get("title") or entity.get("name", self._current_value)

        # Fall back to ref format
        return self._current_value

    def _clear(self):
        """Clear current selection."""
        self._current_value = ""
        self._on_select("")
        self._trigger_render()


class MultiReferencePicker(Component):
    """Multiple entity reference picker - button only, Modal managed by parent."""

    def __init__(
        self,
        label: str,
        target_kinds: list[EntityKind],
        catalog_state: CatalogState,
        current_values: list[str],
        on_change: Callable[[list[str]], None],
        on_open_picker: Callable[[], None],
    ):
        super().__init__()
        self._label = label
        self._target_kinds = target_kinds
        self._catalog_state = catalog_state
        self._current_values = current_values
        self._on_change = on_change
        self._on_open_picker = on_open_picker

        # Render trigger state
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def _trigger_render(self):
        """Trigger a re-render."""
        self._render_trigger.set(self._render_trigger() + 1)

    @property
    def label(self) -> str:
        return self._label

    @property
    def target_kinds(self) -> list[EntityKind]:
        return self._target_kinds

    @property
    def current_values(self) -> list[str]:
        return self._current_values

    def add_value(self, value: str):
        """Add a value to the list."""
        if value and value not in self._current_values:
            self._current_values.append(value)
            self._on_change(self._current_values)
            self._trigger_render()

    def view(self):
        theme = ThemeManager().current
        # Build list of selected items
        children = [
            Text(self._label, font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
        ]

        for i, ref in enumerate(self._current_values):
            display = self._get_display_for_ref(ref)
            children.append(
                Row(
                    Text(display, font_size=12).flex(1),
                    Button(t("common.x"))
                    .on_click(lambda _, idx=i: self._remove_item(idx))
                    .fixed_width(28)
                    .fixed_height(28),
                )
                .fixed_height(32)
                .bg_color(theme.colors.bg_secondary)
            )
            children.append(Spacer().fixed_height(4))

        children.append(
            Button(t("common.add_item"))
            .on_click(lambda _: self._on_open_picker())
            .fixed_height(32)
            .fixed_width(80)
        )
        children.append(Spacer().fixed_height(8))

        return Column(*children)

    def _get_display_for_ref(self, ref: str) -> str:
        """Get display text for a reference."""
        entity = self._catalog_state.get_by_id(ref)
        if entity:
            return entity.get("title") or entity.get("name", ref)
        return ref

    def _remove_item(self, index: int):
        """Remove an item by index."""
        if 0 <= index < len(self._current_values):
            self._current_values.pop(index)
            self._on_change(self._current_values)
            self._trigger_render()


class EntityPickerModal:
    """Shared entity picker modal content builder."""

    def __init__(self, catalog_state: CatalogState):
        self._catalog_state = catalog_state
        self._search_state = InputState("")
        self._entities: list[dict] = []
        self._target_kinds: list[EntityKind] = []
        self._exclude_ids: list[str] = []
        self._on_select: Callable[[str], None] | None = None
        self._render_trigger = State(0)
        self._active_tab = State("catalog")  # "catalog" or "github"
        self._github_org: str | None = None

    def attach(self, component: Component):
        """Attach to a component for re-render triggers."""
        self._search_state.attach(component)
        self._render_trigger.attach(component)
        self._active_tab.attach(component)

    def configure(
        self,
        target_kinds: list[EntityKind],
        exclude_ids: list[str] | None = None,
        on_select: Callable[[str], None] | None = None,
    ):
        """Configure the picker for current use."""
        self._target_kinds = target_kinds
        self._exclude_ids = exclude_ids or []
        self._on_select = on_select
        self._search_state.set("")
        self._active_tab.set("catalog")
        self._load_entities()
        # Get github_org from config
        config = self._catalog_state.get_config()
        self._github_org = config.settings.github_org

    def _load_entities(self):
        """Load entities matching target kinds."""
        self._entities = []
        for kind in self._target_kinds:
            self._entities.extend(self._catalog_state.get_by_kind(kind.value))

    def _filter_entities(self) -> list[dict]:
        """Filter entities by search query and exclude list."""
        query = self._search_state.value().lower()
        result = []
        for e in self._entities:
            entity_id = e.get("id", "")
            if entity_id in self._exclude_ids:
                continue
            if query:
                if query not in e.get("name", "").lower() and query not in (
                    e.get("title") or ""
                ).lower():
                    continue
            result.append(e)
        return result

    def _should_show_github_tab(self) -> bool:
        """Check if GitHub tab should be shown."""
        # Only show for User/Group target kinds and if github_org is configured
        if not self._github_org:
            return False
        return EntityKind.USER in self._target_kinds or EntityKind.GROUP in self._target_kinds

    def _set_tab(self, tab: str):
        """Set active tab."""
        self._active_tab.set(tab)
        self._render_trigger.set(self._render_trigger() + 1)

    def build_content(self, on_close: Callable[[], None]) -> Column:
        """Build modal content with tabs."""
        theme = ThemeManager().current
        active_tab = self._active_tab()
        show_github = self._should_show_github_tab()

        # Tab buttons (only show if GitHub tab is available)
        if show_github:
            tabs = Row(
                Button(t("github.tab_catalog"))
                .on_click(lambda _: self._set_tab("catalog"))
                .bg_color(
                    theme.colors.bg_selected
                    if active_tab == "catalog"
                    else theme.colors.bg_secondary
                )
                .fixed_height(32),
                Spacer().fixed_width(8),
                Button(t("github.tab_github_org"))
                .on_click(lambda _: self._set_tab("github"))
                .bg_color(
                    theme.colors.bg_selected
                    if active_tab == "github"
                    else theme.colors.bg_secondary
                )
                .fixed_height(32),
                Spacer(),
            ).fixed_height(40)
        else:
            tabs = Spacer().fixed_height(0)

        if active_tab == "catalog":
            content = self._build_catalog_content(on_close)
        else:
            content = self._build_github_content(on_close)

        return Column(tabs, Spacer().fixed_height(8), content).flex(1)

    def _build_catalog_content(self, on_close: Callable[[], None]) -> Column:
        """Build catalog picker content."""
        filtered = self._filter_entities()

        rows = [
            PickerRow(
                name=e.get("name", ""),
                kind=e.get("kind", ""),
                title=e.get("title") or e.get("name", ""),
            )
            for e in filtered[:50]
        ]

        if rows:
            table_state = DataTableState.from_pydantic(rows)
        else:
            table_state = DataTableState(columns=["Name", "Kind", "Title"], rows=[])

        def on_entity_click(event):
            if 0 <= event.row < len(filtered):
                entity = filtered[event.row]
                entity_id = entity.get("id", "")
                if self._on_select:
                    self._on_select(entity_id)
                on_close()

        theme = ThemeManager().current
        return Column(
            Input(self._search_state)
            .on_change(lambda _: self._render_trigger.set(self._render_trigger() + 1))
            .fixed_height(36),
            Spacer().fixed_height(8),
            Text(t("status.found", count=len(filtered)), font_size=12)
            .text_color(theme.colors.fg)
            .fixed_height(20),
            DataTable(table_state).on_cell_click(on_entity_click).flex(1),
        ).flex(1)

    def _build_github_content(self, on_close: Callable[[], None]) -> Column:
        """Build GitHub org picker content."""
        from .github_org_picker import GitHubOrgPicker

        def on_github_select(data: dict):
            # Create entity and return its ID
            entity = self._create_entity_from_github(data)
            if entity and self._on_select:
                entity_id = f"{entity.kind.value}:default/{entity.metadata.name}"
                self._on_select(entity_id)
            on_close()

        return GitHubOrgPicker(
            org=self._github_org or "",
            target_kinds=self._target_kinds,
            on_select=on_github_select,
            on_close=on_close,
        )

    def _create_entity_from_github(self, data: dict) -> BaseEntity | None:
        """Create User/Group entity from GitHub data."""
        if data["type"] == "user":
            return self._create_user_from_github(data)
        elif data["type"] == "group":
            return self._create_group_from_github(data)
        return None

    def _create_user_from_github(self, data: dict) -> BaseEntity | None:
        """Create User entity from GitHub member data."""
        from ..git import EntityReader

        login = data["login"]

        # Check if entity already exists
        existing = self._catalog_state.get_by_id(f"user:default/{login}")
        if existing:
            # Return existing entity info to construct entity object
            entity_dict = {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "User",
                "metadata": {
                    "name": existing.get("name", login),
                    "namespace": existing.get("namespace", "default"),
                },
                "spec": {},
            }
            reader = EntityReader()
            return reader.parse_entity(entity_dict)

        entity_dict = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "User",
            "metadata": {
                "name": login,
                "title": data.get("name") or login,
                "annotations": {
                    "github.com/login": login,
                    "bkstg.io/imported-from": f"github-org:{self._github_org}",
                },
            },
            "spec": {
                "profile": {
                    "displayName": data.get("name") or login,
                    "email": data.get("email") or "",
                    "picture": data.get("avatar_url") or "",
                },
                "memberOf": [],
            },
        }

        reader = EntityReader()
        entity = reader.parse_entity(entity_dict)

        if entity:
            self._catalog_state.save_entity(entity)

        return entity

    def _create_group_from_github(self, data: dict) -> BaseEntity | None:
        """Create Group entity from GitHub team data."""
        from ..git import EntityReader

        slug = data["slug"]

        # Check if entity already exists
        existing = self._catalog_state.get_by_id(f"group:default/{slug}")
        if existing:
            # Return existing entity info to construct entity object
            entity_dict = {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Group",
                "metadata": {
                    "name": existing.get("name", slug),
                    "namespace": existing.get("namespace", "default"),
                },
                "spec": {"type": "team"},
            }
            reader = EntityReader()
            return reader.parse_entity(entity_dict)

        entity_dict = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Group",
            "metadata": {
                "name": slug,
                "title": data["name"],
                "description": data.get("description") or "",
                "annotations": {
                    "github.com/team-slug": slug,
                    "bkstg.io/imported-from": f"github-org:{self._github_org}",
                },
            },
            "spec": {
                "type": "team",
                "profile": {
                    "displayName": data["name"],
                },
                "members": [],
            },
        }

        reader = EntityReader()
        entity = reader.parse_entity(entity_dict)

        if entity:
            self._catalog_state.save_entity(entity)

        return entity
