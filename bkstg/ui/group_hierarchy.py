"""Group Hierarchy Drilldown UI component."""

from pydantic import BaseModel, Field

from castella import (
    Button,
    CheckBox,
    Column,
    ColumnConfig,
    Component,
    DataTable,
    DataTableState,
    Row,
    Spacer,
    State,
    Tabs,
    TabItem,
    TabsState,
    Text,
)
from castella.chart import (
    BarChart,
    PieChart,
    CategoricalChartData,
    CategoricalSeries,
    SeriesStyle,
)
from castella.theme import ThemeManager

from ..i18n import t
from ..state.catalog_state import CatalogState


def _get_rank_colors():
    """Get rank colors from theme."""
    theme = ThemeManager().current
    return {
        "S": theme.colors.text_warning,
        "A": theme.colors.text_success,
        "B": theme.colors.text_info,
        "C": "#ff9e64",
        "D": theme.colors.text_danger,
        "E": theme.colors.text_danger,
        "F": theme.colors.text_danger,
    }


class GroupRow(BaseModel):
    """Row model for group table."""

    id: str = Field(title="ID")
    name: str = Field(title="Name")
    title: str | None = Field(default=None, title="Title")
    type: str | None = Field(default=None, title="Type")
    child_count: int = Field(default=0, title="Subgroups")
    entity_count: int = Field(default=0, title="Entities")


class EntityRow(BaseModel):
    """Row model for entity table."""

    id: str = Field(title="ID")
    kind: str = Field(title="Kind")
    name: str = Field(title="Name")
    title: str | None = Field(default=None, title="Title")
    type: str | None = Field(default=None, title="Type")
    lifecycle: str | None = Field(default=None, title="Lifecycle")


class GroupHierarchyView(Component):
    """Group hierarchy drilldown view."""

    def __init__(
        self,
        catalog_state: CatalogState,
        on_entity_select,
        active_tab: str = "tree",
        on_tab_change=None,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._on_entity_select = on_entity_select
        self._on_tab_change = on_tab_change

        # Internal tab state
        self._active_tab = State(active_tab)
        self._active_tab.attach(self)

        # Selected group for drilldown (empty = root level)
        self._selected_group = State("")
        self._selected_group.attach(self)

        # Breadcrumb path: list of (group_id, group_name) tuples
        self._breadcrumb_path: list[tuple[str, str]] = []

        # Include descendants toggle
        self._include_descendants = State(True)
        self._include_descendants.attach(self)

        # Store current rows for click handling
        self._current_group_rows: list[GroupRow] = []
        self._current_entity_rows: list[EntityRow] = []

    def view(self):
        theme = ThemeManager().current
        active_tab = self._active_tab()

        tab_items = [
            TabItem(id="tree", label=t("group.tab.hierarchy"), content=Spacer()),
            TabItem(id="entities", label=t("group.tab.entities"), content=Spacer()),
            TabItem(id="scores", label=t("group.tab.scores"), content=Spacer()),
            TabItem(id="compare", label=t("group.tab.compare"), content=Spacer()),
        ]
        tabs_state = TabsState(tabs=tab_items, selected_id=active_tab)

        return Column(
            self._build_breadcrumb(),
            Spacer().fixed_height(8),
            Tabs(tabs_state).on_change(self._handle_tab_change).fixed_height(44),
            Spacer().fixed_height(8),
            self._build_content(active_tab),
        )

    def _build_breadcrumb(self):
        """Build breadcrumb navigation."""
        theme = ThemeManager().current

        items = [
            Button(t("group.all_groups"))
            .on_click(lambda _: self._navigate_to_root())
            .fixed_height(28)
        ]

        for i, (group_id, group_name) in enumerate(self._breadcrumb_path):
            items.append(Text(" > ", font_size=14))
            items.append(
                Button(group_name)
                .on_click(lambda _, idx=i: self._navigate_to_breadcrumb(idx))
                .fixed_height(28)
            )

        return Row(*items, Spacer()).fixed_height(36)

    def _build_content(self, tab: str):
        if tab == "tree":
            return self._build_tree_view()
        elif tab == "entities":
            return self._build_entities_view()
        elif tab == "scores":
            return self._build_scores_view()
        elif tab == "compare":
            return self._build_comparison_view()
        return Spacer()

    def _build_tree_view(self):
        """Build hierarchical tree view of groups."""
        theme = ThemeManager().current
        selected = self._selected_group()

        # Get groups to display
        if selected:
            groups = self._catalog_state.get_child_groups(selected)
        else:
            groups = self._catalog_state.get_root_groups()

        if not groups:
            msg = (
                t("group.no_subgroups")
                if selected
                else t("group.no_groups")
            )
            self._current_group_rows = []
            return Column(
                Text(msg, font_size=14).text_color(theme.colors.fg),
                Spacer(),
            )

        # Build group rows with counts
        self._current_group_rows = []
        table_rows = []
        for group in groups:
            group_id = group["id"]
            child_count = len(self._catalog_state.get_child_groups(group_id))
            entity_count = sum(
                self._catalog_state.get_group_entity_count(group_id, False).values()
            )
            self._current_group_rows.append(
                GroupRow(
                    id=group_id,
                    name=group.get("name", ""),
                    title=group.get("title"),
                    type=group.get("type"),
                    child_count=child_count,
                    entity_count=entity_count,
                )
            )
            table_rows.append([
                group.get("name", ""),
                group.get("title") or "",
                group.get("type") or "",
                child_count,
                entity_count,
            ])

        # Create DataTable
        columns = [
            ColumnConfig(name=t("entity.field.name"), width=200),
            ColumnConfig(name=t("entity.field.title"), width=200),
            ColumnConfig(name=t("entity.field.type"), width=100),
            ColumnConfig(name=t("group.subgroups"), width=100),
            ColumnConfig(name=t("group.entities"), width=100),
        ]
        table_state = DataTableState(rows=table_rows, columns=columns)

        return Column(
            Text(t("group.click_to_drill_down"), font_size=12).text_color(theme.colors.fg),
            Spacer().fixed_height(8),
            DataTable(table_state).on_cell_click(self._on_group_click),
            Spacer(),
        )

    def _build_entities_view(self):
        """Build entity list for selected group."""
        theme = ThemeManager().current
        selected = self._selected_group()
        include_desc = self._include_descendants()

        if not selected:
            return Column(
                Text(t("group.select_group_first"), font_size=14).text_color(theme.colors.fg),
                Spacer(),
            )

        entities = self._catalog_state.get_group_owned_entities(selected, include_desc)

        # Build entity rows
        self._current_entity_rows = []
        table_rows = []
        for e in entities:
            self._current_entity_rows.append(
                EntityRow(
                    id=e["id"],
                    kind=e["kind"],
                    name=e["name"],
                    title=e.get("title"),
                    type=e.get("type"),
                    lifecycle=e.get("lifecycle"),
                )
            )
            table_rows.append([
                e["kind"],
                e["name"],
                e.get("title") or "",
                e.get("type") or "",
                e.get("lifecycle") or "",
            ])

        # Create DataTable
        columns = [
            ColumnConfig(name=t("entity.field.kind"), width=100),
            ColumnConfig(name=t("entity.field.name"), width=200),
            ColumnConfig(name=t("entity.field.title"), width=200),
            ColumnConfig(name=t("entity.field.type"), width=100),
            ColumnConfig(name=t("entity.field.lifecycle"), width=100),
        ]
        table_state = DataTableState(rows=table_rows, columns=columns)

        return Column(
            Row(
                CheckBox(self._include_descendants()).on_click(self._toggle_descendants).fixed_width(24),
                Spacer().fixed_width(8),
                Text(t("group.include_descendants"), font_size=13),
                Spacer(),
                Text(f"{len(entities)} {t('group.entities')}", font_size=12).text_color(theme.colors.fg),
            ).fixed_height(32),
            Spacer().fixed_height(8),
            DataTable(table_state).on_cell_click(self._on_entity_click),
            Spacer(),
        )

    def _build_scores_view(self):
        """Build aggregated scores view for selected group."""
        theme = ThemeManager().current
        selected = self._selected_group()
        include_desc = self._include_descendants()

        if not selected:
            return Column(
                Text(t("group.select_group_first"), font_size=14).text_color(theme.colors.fg),
                Spacer(),
            )

        # Get score aggregation
        score_aggs = self._catalog_state.get_group_score_summary(selected, include_desc)

        if not score_aggs:
            return Column(
                Row(
                    CheckBox(self._include_descendants()).on_click(self._toggle_descendants).fixed_width(24),
                    Spacer().fixed_width(8),
                    Text(t("group.include_descendants"), font_size=13),
                    Spacer(),
                ).fixed_height(32),
                Spacer().fixed_height(16),
                Text(t("group.no_scores"), font_size=14).text_color(theme.colors.fg),
                Spacer(),
            )

        # Build score rows
        table_rows = [
            [
                agg["name"],
                round(agg["avg"], 2) if agg["avg"] else 0,
                agg["min"] or 0,
                agg["max"] or 0,
                agg["count"],
            ]
            for agg in score_aggs
        ]

        # Create table
        columns = [
            ColumnConfig(name=t("group.score_name"), width=150),
            ColumnConfig(name=t("group.avg_score"), width=100),
            ColumnConfig(name=t("group.min_score"), width=80),
            ColumnConfig(name=t("group.max_score"), width=80),
            ColumnConfig(name=t("group.entity_count"), width=80),
        ]
        table_state = DataTableState(rows=table_rows, columns=columns)

        # Build bar chart
        chart_data = CategoricalChartData(
            labels=[agg["name"] for agg in score_aggs],
            series=[
                CategoricalSeries(
                    name=t("group.avg_score"),
                    values=[agg["avg"] or 0 for agg in score_aggs],
                    style=SeriesStyle(color=theme.colors.text_info),
                )
            ],
        )

        # Get rank distribution if available
        rank_defs = self._catalog_state.get_rank_definitions()
        rank_charts = []
        if rank_defs:
            for rank_def in rank_defs[:2]:  # Limit to first 2 ranks
                rank_dist = self._catalog_state.get_group_rank_distribution(
                    selected, rank_def["id"], include_desc
                )
                if rank_dist:
                    rank_colors = _get_rank_colors()
                    pie_data = CategoricalChartData(
                        labels=[d["label"] for d in rank_dist],
                        series=[
                            CategoricalSeries(
                                name=rank_def["name"],
                                values=[d["count"] for d in rank_dist],
                                style=SeriesStyle(
                                    colors=[
                                        rank_colors.get(d["label"], "#888888")
                                        for d in rank_dist
                                    ]
                                ),
                            )
                        ],
                    )
                    rank_charts.append(
                        Column(
                            Text(
                                f"{rank_def['name']} {t('group.rank_distribution')}",
                                font_size=14,
                            ),
                            Spacer().fixed_height(8),
                            PieChart(pie_data).fixed_height(200).fixed_width(250),
                        )
                    )

        return Column(
            Row(
                CheckBox(self._include_descendants()).on_click(self._toggle_descendants).fixed_width(24),
                Spacer().fixed_width(8),
                Text(t("group.include_descendants"), font_size=13),
                Spacer(),
            ).fixed_height(32),
            Spacer().fixed_height(16),
            Text(t("group.score_summary"), font_size=16),
            Spacer().fixed_height(8),
            Row(
                Column(
                    DataTable(table_state).fixed_height(200),
                ).fixed_width(550),
                Spacer().fixed_width(32),
                Column(
                    BarChart(chart_data).fixed_height(200).fixed_width(400),
                ),
            ),
            Spacer().fixed_height(24),
            Row(*rank_charts, Spacer()) if rank_charts else Spacer(),
            Spacer(),
        )

    def _build_comparison_view(self):
        """Build group comparison view."""
        theme = ThemeManager().current
        selected = self._selected_group()

        # Determine which groups to compare based on current selection
        if selected:
            # If a group is selected, compare its children
            child_groups = self._catalog_state.get_child_groups(selected)
            if len(child_groups) >= 2:
                groups_to_compare = child_groups
                comparison_context = t("group.comparing_children")
            else:
                # No children or only 1 child - compare siblings (same level)
                # Find parent and get siblings
                parent_id = self._get_parent_group_id(selected)
                if parent_id:
                    siblings = self._catalog_state.get_child_groups(parent_id)
                else:
                    siblings = self._catalog_state.get_root_groups()
                groups_to_compare = siblings
                comparison_context = t("group.comparing_siblings")
        else:
            # At root level, compare root groups
            groups_to_compare = self._catalog_state.get_root_groups()
            comparison_context = t("group.comparing_root_groups")

        if len(groups_to_compare) < 2:
            return Column(
                Text(t("group.need_multiple_groups_for_comparison"), font_size=14).text_color(theme.colors.fg),
                Spacer(),
            )

        # Compare groups
        group_ids = [g["id"] for g in groups_to_compare[:5]]  # Limit to 5 groups
        comparisons = self._catalog_state.get_groups_comparison(
            group_ids, include_descendants=True
        )

        if not comparisons:
            return Column(
                Text(t("group.no_data_for_comparison"), font_size=14),
                Spacer(),
            )

        # Build comparison table first (always visible)
        table_columns = [
            ColumnConfig(name=t("group.group_name"), width=200),
            ColumnConfig(name=t("group.entity_count"), width=100),
        ]
        # Add score columns
        score_ids_list = []
        if comparisons and comparisons[0].get("score_aggregations"):
            for agg in comparisons[0]["score_aggregations"][:3]:
                score_ids_list.append((agg["score_id"], agg["name"]))
                table_columns.append(ColumnConfig(name=agg["name"], width=120))

        table_rows = []
        for c in comparisons:
            row = [
                c.get("title") or c["name"],
                c["entity_count"],
            ]
            for score_id, _ in score_ids_list:
                avg_val = 0
                for agg in c.get("score_aggregations", []):
                    if agg["score_id"] == score_id:
                        avg_val = round(agg["avg"] or 0, 1)
                        break
                row.append(avg_val)
            table_rows.append(row)

        comparison_table = DataTable(
            DataTableState(rows=table_rows, columns=table_columns)
        ).fixed_height(120)

        # Build comparison chart: group names vs entity counts
        group_labels = [c.get("title") or c["name"] for c in comparisons]
        entity_counts = [c["entity_count"] for c in comparisons]

        entity_count_data = CategoricalChartData(title=t("group.entity_count"))
        entity_count_data.add_series(
            CategoricalSeries.from_values(
                name=t("group.entity_count"),
                categories=group_labels,
                values=entity_counts,
                style=SeriesStyle(color=theme.colors.text_success),
            )
        )

        # Build score comparison charts if available
        score_charts = []
        if comparisons and comparisons[0].get("score_aggregations"):
            score_ids = set()
            for c in comparisons:
                for agg in c.get("score_aggregations", []):
                    score_ids.add((agg["score_id"], agg["name"]))

            for score_id, score_name in list(score_ids)[:3]:  # Limit to 3 scores
                values = []
                for c in comparisons:
                    agg_val = 0
                    for agg in c.get("score_aggregations", []):
                        if agg["score_id"] == score_id:
                            agg_val = agg["avg"] or 0
                            break
                    values.append(round(agg_val, 1))

                score_data = CategoricalChartData(title=score_name)
                score_data.add_series(
                    CategoricalSeries.from_values(
                        name=score_name,
                        categories=group_labels,
                        values=values,
                        style=SeriesStyle(color=theme.colors.text_info),
                    )
                )
                score_charts.append(
                    Column(
                        Text(f"{score_name} {t('group.avg_score')}", font_size=14).fixed_height(20),
                        Spacer().fixed_height(8),
                        BarChart(score_data, show_values=True, enable_tooltip=True).fixed_height(200).fixed_width(500),
                    ).fixed_height(240)
                )

        return Column(
            Text(f"{t('group.comparison_title')} ({comparison_context})", font_size=16).fixed_height(24),
            Spacer().fixed_height(16),
            comparison_table,
            Spacer().fixed_height(24),
            Text(t("group.entity_count"), font_size=14).fixed_height(20),
            Spacer().fixed_height(8),
            BarChart(entity_count_data, show_values=True, enable_tooltip=True).fixed_height(200).fixed_width(500),
            Spacer().fixed_height(24),
            *score_charts,
            Spacer().fixed_height(24),
            scrollable=True,
        )

    def _handle_tab_change(self, tab_id: str):
        """Handle tab change."""
        self._active_tab.set(tab_id)
        if self._on_tab_change:
            self._on_tab_change(tab_id)

    def _navigate_to_root(self):
        """Navigate to root level (all top-level groups)."""
        self._selected_group.set("")
        self._breadcrumb_path = []

    def _navigate_to_breadcrumb(self, idx: int):
        """Navigate to a specific point in the breadcrumb."""
        if idx < len(self._breadcrumb_path):
            group_id, _ = self._breadcrumb_path[idx]
            self._selected_group.set(group_id)
            self._breadcrumb_path = self._breadcrumb_path[: idx + 1]

    def _on_group_click(self, event):
        """Handle group row click - drill down."""
        row_idx = event.row
        if 0 <= row_idx < len(self._current_group_rows):
            group = self._current_group_rows[row_idx]
            group_name = group.title or group.name
            self._breadcrumb_path.append((group.id, group_name))
            self._selected_group.set(group.id)

    def _on_entity_click(self, event):
        """Handle entity row click - open entity details."""
        row_idx = event.row
        if 0 <= row_idx < len(self._current_entity_rows):
            entity = self._current_entity_rows[row_idx]
            if self._on_entity_select:
                self._on_entity_select(entity.id)

    def _toggle_descendants(self, _):
        """Toggle include descendants checkbox."""
        self._include_descendants.set(not self._include_descendants())

    def _get_parent_group_id(self, group_id: str) -> str | None:
        """Get the parent group ID from breadcrumb path."""
        # Find the group in breadcrumb and return the previous one
        for i, (gid, _) in enumerate(self._breadcrumb_path):
            if gid == group_id and i > 0:
                return self._breadcrumb_path[i - 1][0]
        return None
