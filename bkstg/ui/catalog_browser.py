"""Catalog browser with DataTable."""

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
    Tabs,
    TabItem,
    TabsState,
    Text,
)

from ..i18n import t
from ..state.catalog_state import CatalogState


class EntityRow(BaseModel):
    """Row model for entity table."""

    id: str = Field(title="ID", description="Entity ID")
    kind: str = Field(title="Kind", description="Entity kind")
    name: str = Field(title="Name", description="Entity name")
    title: str | None = Field(default=None, title="Title", description="Display title")
    type: str | None = Field(default=None, title="Type", description="Entity type")
    owner: str | None = Field(default=None, title="Owner", description="Owner reference")
    lifecycle: str | None = Field(
        default=None, title="Lifecycle", description="Lifecycle stage"
    )


class CatalogBrowser(Component):
    """Browse catalog entities with DataTable."""

    KINDS = ["All", "Component", "API", "Resource", "System", "Domain", "User", "Group"]
    MAX_DISPLAY_ROWS = 200  # Limit rows for performance

    def __init__(
        self,
        catalog_state: CatalogState,
        selected_id: str,
        on_select,
        search_input_state: InputState,
        active_tab: str = "All",
        on_tab_change=None,
        on_new=None,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._selected_id = selected_id
        self._on_select = on_select

        # Tab state managed by parent (persists across re-renders)
        self._active_tab = active_tab
        self._on_tab_change = on_tab_change
        self._on_new = on_new

        # Search input state (passed from parent, NOT attached to avoid re-render on typing)
        self._search_input_state = search_input_state

        # Committed search query (only updates on Search button click)
        self._committed_query = State("")
        self._committed_query.attach(self)

        # Store current entity rows for click handling
        self._current_rows: list[EntityRow] = []

    def view(self):
        selected_kind = self._active_tab
        # Use committed query for filtering (not InputState, to avoid re-render on typing)
        current_query = self._committed_query()

        # Create tab items
        tab_items = [
            TabItem(id=kind, label=kind, content=Spacer()) for kind in self.KINDS
        ]
        tabs_state = TabsState(tabs=tab_items, selected_id=selected_kind)

        # Get filtered entities
        kind = None if selected_kind == "All" else selected_kind
        entities = self._catalog_state.search(current_query, kind)
        total_count = len(entities)

        # Limit rows for performance
        is_truncated = total_count > self.MAX_DISPLAY_ROWS
        if is_truncated:
            entities = entities[: self.MAX_DISPLAY_ROWS]

        # Convert to table rows and store for click handling
        self._current_rows = [
            EntityRow(
                id=e["id"],
                kind=e["kind"],
                name=e["name"],
                title=e.get("title"),
                type=e.get("type"),
                owner=e.get("owner"),
                lifecycle=e.get("lifecycle"),
            )
            for e in entities
        ]

        # Create DataTableState
        if self._current_rows:
            table_state = DataTableState.from_pydantic(self._current_rows)
            # Find and select the row matching selected_id
            if self._selected_id:
                for i, row in enumerate(self._current_rows):
                    if row.id == self._selected_id:
                        table_state.select_row(i)
                        break
        else:
            table_state = DataTableState(columns=[], rows=[])

        return Column(
            # Search bar (Search button to execute search)
            Row(
                Input(self._search_input_state).flex(1),
                Spacer().fixed_width(4),
                Button(t("common.search")).on_click(self._on_search_click).fixed_width(80),
                Spacer().fixed_width(4),
                Button(t("common.clear")).on_click(self._clear_search).fixed_width(80),
                Spacer().fixed_width(16),
                Button(t("common.plus") + " " + t("common.new"))
                .on_click(self._handle_new_click)
                .fixed_width(80)
                if self._on_new
                else Spacer().fixed_width(0),
            ).fixed_height(44),
            Spacer().fixed_height(8),
            # Kind tabs
            Tabs(tabs_state).on_change(self._handle_tab_change).fixed_height(44),
            Spacer().fixed_height(8),
            # Results count (with truncation warning if needed)
            self._build_results_text(total_count, is_truncated),
            # Data table
            DataTable(table_state).on_cell_click(self._handle_row_click),
        )

    def _on_search_click(self, _):
        """Execute search on Search button click."""
        self._committed_query.set(self._search_input_state.value())

    def _clear_search(self, _):
        """Clear search input and results."""
        self._search_input_state.set("")
        self._committed_query.set("")

    def _handle_tab_change(self, tab_id: str):
        if self._on_tab_change:
            self._on_tab_change(tab_id)

    def _build_results_text(self, total_count: int, is_truncated: bool):
        """Build the results count text with optional truncation warning."""
        if is_truncated:
            return Row(
                Text(
                    t("status.showing", count=self.MAX_DISPLAY_ROWS, total=total_count),
                    font_size=13,
                ),
                Spacer().fixed_width(8),
                Text(
                    t("status.use_search"),
                    font_size=12,
                ).text_color("#f59e0b"),
            ).fixed_height(24)
        else:
            return Text(t("status.found", count=total_count), font_size=13).fixed_height(24)

    def _handle_row_click(self, event):
        # Get the entity ID from stored rows
        if 0 <= event.row < len(self._current_rows):
            entity_id = self._current_rows[event.row].id
            self._on_select(entity_id)

    def _handle_new_click(self, _):
        """Handle new entity button click."""
        if self._on_new:
            self._on_new()
