"""Main bkstg application component."""

from datetime import datetime

from castella import Button, Column, Component, InputState, Row, Spacer, State, Text
from castella.graph.transform import CanvasTransform
from castella.theme import ThemeManager

from ..state.catalog_state import CatalogState
from .catalog_browser import CatalogBrowser
from .dashboard import Dashboard
from .entity_detail import EntityDetail
from .sidebar import Sidebar


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

        self._status_message = State("Ready")
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

    def view(self):
        active = self._active_view()
        selected_id = self._selected_entity_id()

        # Get selected entity if any
        selected_entity = None
        if selected_id:
            selected_entity = self._catalog_state.get_entity(selected_id)

        return Column(
            # Main content row
            Row(
                # Left sidebar - navigation
                Sidebar(
                    active_view=active,
                    on_view_change=self._on_view_change,
                    counts=self._catalog_state.count_by_kind(),
                ).fixed_width(220),
                # Main content area
                Column(
                    # Content based on active view
                    self._build_content(active),
                ).flex(1),
                # Right panel - entity detail (when selected)
                self._build_detail_panel(selected_entity),
            ).flex(1),
            # Status bar
            self._build_status_bar(),
        )

    def _build_content(self, view: str):
        if view == "catalog":
            return CatalogBrowser(
                catalog_state=self._catalog_state,
                selected_id=self._selected_entity_id(),
                on_select=self._on_entity_select,
                search_input_state=self._search_input_state,
                active_tab=self._catalog_tab(),
                on_tab_change=self._catalog_tab.set,
            )
        elif view == "graph":
            from .dependency_graph import DependencyGraphView

            return DependencyGraphView(
                catalog_state=self._catalog_state,
                selected_id=self._selected_entity_id(),
                on_node_click=self._on_entity_select,
                transform=self._graph_transform,
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
        else:
            return Spacer()

    def _build_detail_panel(self, entity):
        if entity is None:
            return Spacer().fixed_width(0)

        entity_id = entity.entity_id
        return EntityDetail(
            entity=entity,
            relations=self._catalog_state.get_relations(entity_id),
            on_edit=lambda: self._active_view.set("editor"),
            on_navigate=self._on_entity_select,
            scores=self._catalog_state.get_entity_scores(entity_id),
            ranks=self._catalog_state.get_entity_ranks(entity_id),
        ).fixed_width(380)

    def _on_view_change(self, view: str):
        self._active_view.set(view)

    def _on_entity_select(self, entity_id_or_ref: str):
        # Try to resolve the ref to a valid entity ID
        resolved_id = self._catalog_state.resolve_ref(entity_id_or_ref)
        entity_id = resolved_id if resolved_id else entity_id_or_ref
        self._selected_entity_id.set(entity_id)

    def _on_entity_save(self, entity):
        self._catalog_state.save_entity(entity)
        self._status_message.set(f"Saved: {entity.metadata.name}")
        self._last_reload.set(datetime.now().strftime("%H:%M:%S"))
        self._active_view.set("catalog")

    def _on_reload(self, _):
        self._catalog_state.clear_location_cache()
        self._catalog_state.reload()
        self._last_reload.set(datetime.now().strftime("%H:%M:%S"))
        self._status_message.set("Catalog reloaded")

    def _build_status_bar(self):
        theme = ThemeManager().current
        total = sum(self._catalog_state.count_by_kind().values())
        cycles = self._catalog_state.detect_cycles()
        cycle_warning = f" | {len(cycles)} cycles" if cycles else ""

        return Row(
            Button("Reload").on_click(self._on_reload).fixed_width(80),
            Spacer().fixed_width(16),
            Text(self._status_message(), font_size=12),
            Spacer(),
            Text(f"{total} entities{cycle_warning}", font_size=12),
            Spacer().fixed_width(16),
            Text(f"Last: {self._last_reload()}", font_size=12),
            Spacer().fixed_width(8),
        ).fixed_height(32).bg_color(theme.colors.bg_primary)
