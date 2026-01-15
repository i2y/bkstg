"""Main bkstg application component."""

from datetime import datetime

from castella import Button, Column, Component, InputState, Row, Spacer, State, Text
from castella.graph.transform import CanvasTransform
from castella.i18n import I18nManager
from castella.theme import ThemeManager

from ..config import GitHubSource
from ..i18n import t
from ..state.catalog_state import CatalogState
from .catalog_browser import CatalogBrowser
from .dashboard import Dashboard
from .entity_detail import EntityDetail
from .sidebar import Sidebar
from .welcome_view import WelcomeView


class BkstgApp(Component):
    """Main bkstg application component."""

    def __init__(self, catalog_path: str):
        super().__init__()

        # Initialize catalog state
        self._catalog_state = CatalogState(catalog_path)

        # UI state - attach to trigger re-renders
        self._active_view = State("catalog")  # catalog, graph, editor
        self._active_view.attach(self)

        self._selected_entity_id = State("")
        self._selected_entity_id.attach(self)

        # Search input state (persists across re-renders to maintain focus)
        self._search_input_state = InputState("")

        self._status_message = State(t("app.ready"))
        self._status_message.attach(self)

        self._last_reload = State(datetime.now().strftime("%H:%M:%S"))
        self._last_reload.attach(self)

        # Dashboard tab state (persists across re-renders)
        self._dashboard_tab = State("overview")
        self._dashboard_tab.attach(self)

        # Catalog browser tab state (persists across re-renders)
        self._catalog_tab = State("All")
        self._catalog_tab.attach(self)

        # Graph view transform (persists across re-renders)
        self._graph_transform = CanvasTransform()

        # Graph filter states (persists across re-renders)
        self._graph_selected_relations: set[str] = {"dependsOn", "providesApi", "consumesApi"}
        self._graph_selected_kinds: set[str] = {
            "Component", "API", "Resource", "System", "Domain", "User", "Group"
        }
        self._graph_reach_depth: int | None = 2  # Default: 2 steps, None = unlimited

        # Right panel visibility state
        self._detail_panel_visible = State(True)
        self._detail_panel_visible.attach(self)

        # Locale change trigger for app-wide re-render
        self._locale_trigger = State(0)
        self._locale_trigger.attach(self)
        I18nManager().add_listener(self)

        # Settings status message (persists across SettingsView re-creation)
        self._settings_status = State("")
        self._settings_status.attach(self)

    def view(self):
        # Show welcome screen if no sources configured
        config = self._catalog_state.get_config()
        if not config.sources:
            return WelcomeView(on_complete=self._on_welcome_complete)

        active = self._active_view()
        selected_id = self._selected_entity_id()

        # Get selected entity if any
        selected_entity = None
        if selected_id:
            selected_entity = self._catalog_state.get_entity(selected_id)

        detail_visible = self._detail_panel_visible()

        return Column(
            # Main content row
            Row(
                # Left sidebar - navigation
                Sidebar(
                    active_view=active,
                    on_view_change=self._on_view_change,
                    counts=self._catalog_state.count_by_kind(),
                ).fixed_width(280),
                # Main content area
                Column(
                    # Content based on active view
                    self._build_content(active),
                ).flex(1),
                # Right panel toggle button
                self._build_panel_toggle(selected_entity, detail_visible),
                # Right panel - entity detail (when selected and visible)
                self._build_detail_panel(selected_entity, detail_visible),
            ).flex(1),
            # Status bar
            self._build_status_bar(),
        )

    def _on_welcome_complete(self, parsed: dict):
        """Handle welcome screen completion."""
        # Create GitHubSource from parsed URL
        source = GitHubSource(
            owner=parsed["owner"],
            repo=parsed["repo"],
            branch=parsed["branch"],
            path=parsed["path"],
            name=f"{parsed['owner']}/{parsed['repo']}",
        )

        # Update config with new source
        config = self._catalog_state.get_config()
        config.sources.append(source)
        self._catalog_state.update_config(config, save=True)

        # Trigger re-render
        self._status_message.set(t("app.ready"))

    def _build_content(self, view: str):
        if view == "about":
            from .about_view import AboutView

            return AboutView(catalog_state=self._catalog_state)
        elif view == "catalog":
            return CatalogBrowser(
                catalog_state=self._catalog_state,
                selected_id=self._selected_entity_id(),
                on_select=self._on_entity_select,
                search_input_state=self._search_input_state,
                active_tab=self._catalog_tab(),
                on_tab_change=self._catalog_tab.set,
                on_new=self._on_new_entity,
            )
        elif view == "graph":
            from .dependency_graph import DependencyGraphView

            return DependencyGraphView(
                catalog_state=self._catalog_state,
                selected_id_state=self._selected_entity_id,
                on_node_click=self._on_entity_select,
                transform=self._graph_transform,
                selected_relations=self._graph_selected_relations,
                selected_kinds=self._graph_selected_kinds,
                reach_depth=self._graph_reach_depth,
                on_reach_depth_change=self._on_graph_reach_depth_change,
            )
        elif view == "dashboard":
            return Dashboard(
                catalog_state=self._catalog_state,
                on_entity_select=self._on_entity_select,
                active_tab=self._dashboard_tab(),
                on_tab_change=self._dashboard_tab.set,
                selected_entity_id=self._selected_entity_id(),
            )
        elif view == "editor":
            from .form_editor import FormEditor

            entity_id = self._selected_entity_id()
            entity = self._catalog_state.get_entity(entity_id) if entity_id else None
            file_path = (
                self._catalog_state.get_file_path(entity_id) if entity_id else None
            )

            return FormEditor(
                entity=entity,
                file_path=file_path,
                catalog_state=self._catalog_state,
                on_save=self._on_entity_save,
                on_cancel=lambda: self._active_view.set("catalog"),
            )
        elif view == "sync":
            from .sync_panel import SyncPanel

            return SyncPanel(catalog_state=self._catalog_state)
        elif view == "settings":
            from .settings_view import SettingsView

            return SettingsView(
                catalog_state=self._catalog_state,
                status=self._settings_status(),
                on_status_change=self._settings_status.set,
            )
        else:
            return Spacer()

    def _build_panel_toggle(self, entity, visible: bool):
        """Build the toggle button for the detail panel."""
        if entity is None:
            return Spacer().fixed_width(0)

        theme = ThemeManager().current
        icon = ">" if visible else "<"
        return Button(icon).on_click(
            lambda _: self._detail_panel_visible.set(not self._detail_panel_visible())
        ).fixed_width(24).bg_color(theme.colors.bg_secondary)

    def _build_detail_panel(self, entity, visible: bool = True):
        if entity is None or not visible:
            return Spacer().fixed_width(0)

        entity_id = entity.entity_id
        return EntityDetail(
            entity=entity,
            relations=self._catalog_state.get_relations(entity_id),
            on_edit=lambda: self._active_view.set("editor"),
            on_navigate=self._on_entity_select,
            scores=self._catalog_state.get_entity_scores(entity_id),
            ranks=self._catalog_state.get_entity_ranks(entity_id),
            catalog_state=self._catalog_state,
        ).fixed_width(520)

    def _on_view_change(self, view: str):
        self._active_view.set(view)

    def _on_graph_reach_depth_change(self, depth: int | None):
        """Handle reach depth filter change from graph view."""
        self._graph_reach_depth = depth

    def _on_entity_select(self, entity_id_or_ref: str):
        # Try to resolve the ref to a valid entity ID
        resolved_id = self._catalog_state.resolve_ref(entity_id_or_ref)
        entity_id = resolved_id if resolved_id else entity_id_or_ref
        self._selected_entity_id.set(entity_id)

    def _on_new_entity(self):
        """Open editor for creating a new entity."""
        self._selected_entity_id.set("")  # Clear selection to create new
        self._active_view.set("editor")

    def _on_entity_save(self, entity):
        self._catalog_state.save_entity(entity)
        self._status_message.set(t("app.saved", name=entity.metadata.name))
        self._last_reload.set(datetime.now().strftime("%H:%M:%S"))
        self._active_view.set("catalog")

    def _on_reload(self, _):
        self._catalog_state.clear_location_cache()
        self._catalog_state.reload()
        self._last_reload.set(datetime.now().strftime("%H:%M:%S"))
        self._status_message.set(t("app.catalog_reloaded"))

    def _build_status_bar(self):
        theme = ThemeManager().current
        total = sum(self._catalog_state.count_by_kind().values())
        cycles = self._catalog_state.detect_cycles()
        cycle_warning = f" | {len(cycles)} cycles" if cycles else ""

        return Row(
            Button(t("common.reload")).on_click(self._on_reload).fixed_width(80),
            Spacer().fixed_width(16),
            Text(self._status_message(), font_size=12),
            Spacer(),
            Text(t("app.entities_count", count=total) + cycle_warning, font_size=12),
            Spacer().fixed_width(16),
            Text(t("app.last_reload", time=self._last_reload()), font_size=12),
            Spacer().fixed_width(8),
        ).fixed_height(32).bg_color(theme.colors.bg_primary)

    def on_locale_changed(self, locale: str) -> None:
        """Handle locale change - trigger app-wide re-render."""
        self._locale_trigger.set(self._locale_trigger() + 1)
