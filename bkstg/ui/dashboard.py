"""Scorecard Dashboard UI."""

from pydantic import BaseModel, Field

from castella import (
    Button,
    Column,
    ColumnConfig,
    Component,
    DataTable,
    DataTableState,
    HeatmapConfig,
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
    LineChart,
    PieChart,
    GaugeChart,
    GaugeChartData,
    GaugeStyle,
    CategoricalChartData,
    NumericChartData,
    CategoricalSeries,
    NumericSeries,
    SeriesStyle,
    HeatmapChart,
    HeatmapChartData,
    ColormapType,
)
from castella.theme import ThemeManager

from ..state.catalog_state import CatalogState
from .scorecard_settings import ScorecardSettingsTab


def _get_chart_colors():
    """Get chart colors from theme."""
    theme = ThemeManager().current
    return {
        "primary": theme.colors.text_info,       # cyan
        "secondary": theme.colors.text_success,  # green
        "accent": theme.colors.text_warning,     # yellow
        "purple": "#bb9af7",                     # magenta (Tokyo Night)
        "pink": theme.colors.text_danger,        # red
        "cyan": theme.colors.text_info,          # cyan
        "orange": "#ff9e64",                     # orange (Tokyo Night)
    }


def _get_rank_colors():
    """Get rank colors from theme."""
    theme = ThemeManager().current
    return {
        "S": theme.colors.text_warning,   # gold/yellow
        "A": theme.colors.text_success,   # green
        "B": theme.colors.text_info,      # blue/cyan
        "C": "#ff9e64",                   # orange
        "D": theme.colors.text_danger,    # red
        "E": theme.colors.text_danger,    # red
        "F": theme.colors.text_danger,    # red
    }


class ScoreRow(BaseModel):
    """Row model for score table."""

    entity_name: str = Field(title="Entity")
    kind: str = Field(title="Kind")
    score_name: str = Field(title="Score")
    value: float = Field(title="Value")
    reason: str | None = Field(default=None, title="Reason")


class LeaderboardRow(BaseModel):
    """Row model for leaderboard table."""

    rank: int = Field(title="#")
    entity_name: str = Field(title="Entity")
    kind: str = Field(title="Kind")
    label: str = Field(title="Rank")
    value: float = Field(title="Score")


class Dashboard(Component):
    """Scorecard dashboard view with multiple tabs."""

    def __init__(
        self,
        catalog_state: CatalogState,
        on_entity_select,
        active_tab: str = "overview",
        on_tab_change=None,
        selected_entity_id: str = "",
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._on_entity_select = on_entity_select

        # Tab state (managed by parent)
        self._active_tab_value = active_tab
        self._on_tab_change = on_tab_change
        self._selected_entity_id = selected_entity_id

        # Selected rank for leaderboard
        self._selected_rank = State("")
        self._selected_rank.attach(self)

        # Store current rows for click handling
        self._current_rows: list = []
        self._current_entity_ids: list[str] = []

    def view(self):
        active_tab = self._active_tab_value

        tab_items = [
            TabItem(id="overview", label="Overview", content=Spacer()),
            TabItem(id="charts", label="Charts", content=Spacer()),
            TabItem(id="heatmaps", label="Heatmaps", content=Spacer()),
            TabItem(id="leaderboard", label="Leaderboard", content=Spacer()),
            TabItem(id="scores", label="All Scores", content=Spacer()),
            TabItem(id="settings", label="Settings", content=Spacer()),
        ]
        tabs_state = TabsState(tabs=tab_items, selected_id=active_tab)

        return Column(
            # Header
            Text("Scorecard Dashboard", font_size=24).fixed_height(48),
            Spacer().fixed_height(8),
            # Tabs
            Tabs(tabs_state).on_change(self._handle_tab_change).fixed_height(44),
            Spacer().fixed_height(16),
            # Content
            self._build_content(active_tab),
        )

    def _build_content(self, tab: str):
        if tab == "overview":
            return self._build_overview()
        elif tab == "charts":
            return self._build_charts()
        elif tab == "heatmaps":
            return self._build_heatmaps()
        elif tab == "leaderboard":
            return self._build_leaderboard()
        elif tab == "scores":
            return self._build_all_scores()
        elif tab == "settings":
            return self._build_settings()
        return Spacer()

    def _build_settings(self):
        """Build settings tab with scorecard configuration."""
        return ScorecardSettingsTab(self._catalog_state)

    def _build_overview(self):
        """Build overview with summary statistics."""
        summary = self._catalog_state.get_dashboard_summary()

        total = summary.get("total_entities", 0)
        scored = summary.get("scored_entities", 0)
        avg_score = summary.get("avg_score", 0)
        recent = summary.get("recent_updates", [])

        # Clear entity IDs for this view
        self._current_entity_ids = [r.get("entity_id", "") for r in recent]

        return Column(
            # Summary cards
            Row(
                self._stat_card("Total Entities", str(total)),
                Spacer().fixed_width(16),
                self._stat_card("Scored Entities", str(scored)),
                Spacer().fixed_width(16),
                self._stat_card("Avg Score", f"{avg_score:.1f}"),
                Spacer(),
            ).fixed_height(100),
            Spacer().fixed_height(24),
            # Recent scores header
            Text("Recent Score Updates", font_size=18).fixed_height(32),
            Spacer().fixed_height(8),
            # Recent scores table
            self._build_recent_scores_table(recent),
        )

    def _stat_card(self, label: str, value: str):
        """Build a statistics card."""
        theme = ThemeManager().current
        return Column(
            Spacer().fixed_height(16),
            Text(value, font_size=32),
            Spacer().fixed_height(4),
            Text(label, font_size=14).text_color(theme.colors.fg),
            Spacer().fixed_height(16),
        ).bg_color(theme.colors.bg_secondary).fixed_width(180)

    def _build_recent_scores_table(self, recent: list):
        """Build table of recent score updates."""
        theme = ThemeManager().current
        if not recent:
            return Text("No scores recorded yet", font_size=14).text_color(theme.colors.fg)

        rows = [
            ScoreRow(
                entity_name=r.get("entity_title") or r.get("entity_name", ""),
                kind=r.get("kind", ""),
                score_name=r.get("score_name", ""),
                value=r.get("value", 0),
                reason=None,
            )
            for r in recent
        ]
        self._current_rows = rows
        table_state = DataTableState.from_pydantic(rows)
        self._select_row_by_entity_id(table_state)
        return DataTable(table_state).on_cell_click(self._on_row_click)

    def _build_leaderboard(self):
        """Build leaderboard view."""
        theme = ThemeManager().current
        ranks = self._catalog_state.get_rank_definitions()

        if not ranks:
            return Column(
                Text("No rank definitions found", font_size=14).text_color(theme.colors.fg),
                Spacer().fixed_height(8),
                Text("Create a scorecard definition file in catalogs/scorecards/", font_size=12).text_color(theme.colors.border_primary),
            )

        selected = self._selected_rank()
        rank_ids = [r["id"] for r in ranks]
        if not selected or selected not in rank_ids:
            # Use first rank as default (don't call set() during render)
            selected = rank_ids[0]

        leaderboard = self._catalog_state.get_leaderboard(selected)

        # Store entity IDs for click handling
        self._current_entity_ids = [item.get("entity_id", "") for item in leaderboard]

        rows = [
            LeaderboardRow(
                rank=i + 1,
                entity_name=item.get("title") or item.get("name", ""),
                kind=item.get("kind", ""),
                label=item.get("label") or "-",
                value=round(item.get("value", 0), 1),
            )
            for i, item in enumerate(leaderboard)
        ]
        self._current_rows = rows

        return Column(
            # Rank selector
            Row(
                Text("Rank:", font_size=14).fixed_width(50),
                *[self._rank_button(r["id"], r["name"], selected) for r in ranks],
                Spacer(),
            ).fixed_height(40),
            Spacer().fixed_height(16),
            # Leaderboard table
            self._build_leaderboard_table(rows),
        )

    def _rank_button(self, rank_id: str, name: str, selected: str):
        """Build a rank selector button."""
        theme = ThemeManager().current
        is_selected = rank_id == selected
        return (
            Button(name)
            .on_click(lambda _, rid=rank_id: self._selected_rank.set(rid))
            .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
            .fixed_width(140)
        )

    def _build_leaderboard_table(self, rows: list[LeaderboardRow]):
        """Build leaderboard table."""
        theme = ThemeManager().current
        if not rows:
            return Text("No entities with this rank yet", font_size=14).text_color(theme.colors.fg)

        table_state = DataTableState.from_pydantic(rows)
        self._select_row_by_entity_id(table_state)
        return DataTable(table_state).on_cell_click(self._on_row_click)

    def _build_all_scores(self):
        """Build complete scores view."""
        theme = ThemeManager().current
        scores = self._catalog_state.get_all_scores_with_entities()

        if not scores:
            return Column(
                Text("No scores recorded yet", font_size=14).text_color(theme.colors.fg),
                Spacer().fixed_height(8),
                Text("Add scores to entities in their YAML files under metadata.scores", font_size=12).text_color(theme.colors.border_primary),
            )

        # Store entity IDs for click handling
        self._current_entity_ids = [s.get("entity_id", "") for s in scores]

        rows = [
            ScoreRow(
                entity_name=s.get("entity_title") or s.get("entity_name", ""),
                kind=s.get("kind", ""),
                score_name=s.get("score_name", ""),
                value=s.get("value", 0),
                reason=s.get("reason"),
            )
            for s in scores
        ]
        self._current_rows = rows

        table_state = DataTableState.from_pydantic(rows)
        self._select_row_by_entity_id(table_state)
        return Column(
            Text(f"{len(scores)} scores total", font_size=13).fixed_height(24),
            DataTable(table_state).on_cell_click(self._on_row_click),
        )

    def _select_row_by_entity_id(self, table_state: DataTableState):
        """Select the row corresponding to the selected entity ID."""
        if self._selected_entity_id and self._selected_entity_id in self._current_entity_ids:
            row_index = self._current_entity_ids.index(self._selected_entity_id)
            table_state.select_row(row_index)

    def _handle_tab_change(self, tab_id: str):
        if self._on_tab_change:
            self._on_tab_change(tab_id)

    def _on_row_click(self, event):
        """Handle row click to navigate to entity detail."""
        if 0 <= event.row < len(self._current_entity_ids):
            entity_id = self._current_entity_ids[event.row]
            if entity_id:
                self._on_entity_select(entity_id)

    # ========== Charts Tab ==========

    def _build_charts(self):
        """Build charts analytics view."""
        return Column(
            # Row 1: Entity Kind Bar Chart + Rank Distribution Pie Chart
            Row(
                self._build_entity_kind_chart(),
                Spacer().fixed_width(24),
                self._build_rank_distribution_chart(),
            ).fixed_height(280),
            Spacer().fixed_height(24),
            # Row 2: Score Distribution Bar Chart + Overall Score Gauge + Score Trends
            Row(
                self._build_score_distribution_chart(),
                Spacer().fixed_width(24),
                self._build_avg_score_gauge(),
                Spacer().fixed_width(24),
                self._build_score_trends_chart(),
            ).fixed_height(280),
            # Absorb remaining space
            Spacer(),
        )

    def _build_entity_kind_chart(self):
        """Build bar chart showing entity count by kind."""
        counts = self._catalog_state.count_by_kind()
        chart_colors = _get_chart_colors()

        if not counts:
            return self._chart_placeholder("Entities by Kind", "No entities found")

        # Define colors for each kind
        kind_colors = {
            "Component": chart_colors["primary"],
            "API": chart_colors["secondary"],
            "Resource": chart_colors["accent"],
            "System": chart_colors["purple"],
            "Domain": chart_colors["pink"],
            "User": chart_colors["cyan"],
            "Group": chart_colors["orange"],
        }

        categories = list(counts.keys())
        values = list(counts.values())
        colors = [kind_colors.get(k, chart_colors["primary"]) for k in categories]

        data = CategoricalChartData(title="Entities by Kind")
        data.add_series(
            CategoricalSeries.from_values(
                name="Count",
                categories=categories,
                values=values,
                style=SeriesStyle(color=chart_colors["primary"]),
            )
        )

        return Column(
            Text("Entities by Kind", font_size=16).fixed_height(28),
            BarChart(
                data,
                show_values=True,
                enable_tooltip=True,
            ).flex(1),
        ).fixed_width(400)

    def _build_rank_distribution_chart(self):
        """Build pie chart showing rank label distribution."""
        ranks = self._catalog_state.get_rank_definitions()
        if not ranks:
            return self._chart_placeholder("Rank Distribution", "No rank definitions found")

        # Use first rank definition
        rank_id = ranks[0]["id"]
        distribution = self._catalog_state.get_rank_label_distribution(rank_id)

        if not distribution:
            return self._chart_placeholder("Rank Distribution", "No ranked entities yet")

        categories = [d["label"] for d in distribution]
        values = [d["count"] for d in distribution]

        data = CategoricalChartData(title=f"Rank Distribution ({ranks[0]['name']})")
        data.add_series(
            CategoricalSeries.from_values(
                name="Ranks",
                categories=categories,
                values=values,
            )
        )

        return Column(
            Text(f"Rank Distribution: {ranks[0]['name']}", font_size=16).fixed_height(28),
            PieChart(
                data,
                donut=True,
                inner_radius_ratio=0.5,
                show_labels=True,
                show_percentages=True,
                enable_tooltip=True,
            ).flex(1),
        ).fixed_width(400)

    def _build_score_distribution_chart(self):
        """Build bar chart showing score distribution by type."""
        distribution = self._catalog_state.get_score_distribution()
        chart_colors = _get_chart_colors()

        if not distribution:
            return self._chart_placeholder("Scores by Type", "No score data available")

        categories = [d["score_name"] for d in distribution]
        values = [d["avg_value"] for d in distribution]

        data = CategoricalChartData(title="Average Scores by Type")
        data.add_series(
            CategoricalSeries.from_values(
                name="Avg Score",
                categories=categories,
                values=values,
                style=SeriesStyle(color=chart_colors["secondary"]),
            )
        )

        return Column(
            Text("Average Scores by Type", font_size=16).fixed_height(28),
            BarChart(
                data,
                show_values=True,
                enable_tooltip=True,
            ).flex(1),
        ).fixed_width(400)

    def _build_score_trends_chart(self):
        """Build line chart showing score trends over time."""
        trends = self._catalog_state.get_score_trends(days=30)
        chart_colors = _get_chart_colors()

        if not trends or len(trends) < 2:
            return self._chart_placeholder("Score Trends", "Not enough data for trends")

        # Convert to numeric series
        y_values = [t["avg_value"] for t in trends]

        data = NumericChartData(title="Score Trends (30 days)")
        data.add_series(
            NumericSeries.from_y_values(
                name="Avg Score",
                y_values=y_values,
                style=SeriesStyle(color=chart_colors["accent"]),
            )
        )

        return Column(
            Text("Score Trends (30 days)", font_size=16).fixed_height(28),
            LineChart(
                data,
                show_points=True,
                smooth=True,
                enable_tooltip=True,
            ).flex(1),
        ).fixed_width(400)

    def _build_avg_score_gauge(self):
        """Build gauge chart showing overall average score."""
        theme = ThemeManager().current
        summary = self._catalog_state.get_dashboard_summary()
        avg_score = summary.get("avg_score", 0)

        data = GaugeChartData(
            value=avg_score,
            min_value=0,
            max_value=100,
            thresholds=[
                (0.0, theme.colors.text_danger),   # Red for low
                (0.4, theme.colors.text_warning),  # Yellow for medium-low
                (0.6, theme.colors.text_info),     # Blue for medium
                (0.8, theme.colors.text_success),  # Green for high
            ],
        )

        return Column(
            Text("Overall Average Score", font_size=16).fixed_height(28),
            GaugeChart(data, style=GaugeStyle.HALF_CIRCLE, arc_width=24, show_value=True).fixed_height(220),
        ).fixed_width(280)

    def _chart_placeholder(self, title: str, message: str):
        """Build a placeholder when chart data is unavailable."""
        theme = ThemeManager().current
        return Column(
            Text(title, font_size=16).fixed_height(28),
            Spacer().fixed_height(60),
            Text(message, font_size=14).text_color(theme.colors.fg),
            Spacer(),
        ).fixed_width(400).bg_color(theme.colors.bg_secondary)

    # ========== Heatmaps Tab ==========

    def _build_heatmaps(self):
        """Build heatmaps analytics view."""
        return Column(
            # Row 1: Kind × Score Average + Kind × Rank Distribution
            Row(
                self._build_kind_score_heatmap(),
                Spacer().fixed_width(24),
                self._build_kind_rank_heatmap(),
            ).fixed_height(320),
            Spacer().fixed_height(24),
            # Row 2: Entity × Score Matrix
            self._build_entity_score_heatmap(),
            Spacer().fixed_height(24),
            # Row 3: Time × Score Trends
            self._build_score_trends_heatmap(),
            Spacer().fixed_height(24),
            scrollable=True,
        )

    def _build_kind_score_heatmap(self):
        """Build Kind × Score Average heatmap."""
        data = self._catalog_state.get_kind_score_average()

        if not data:
            return self._heatmap_placeholder("Kind × Score Average", "No score data available", height=280)

        # Build matrix: rows = kinds, columns = score types
        kinds = sorted(set(d["kind"] for d in data))
        score_names = sorted(set(d["score_name"] for d in data))

        if not kinds or not score_names:
            return self._heatmap_placeholder("Kind × Score Average", "No score data available", height=280)

        # Create value matrix
        value_map = {(d["kind"], d["score_name"]): d["avg_value"] for d in data}
        values = [
            [value_map.get((kind, score), 0) for score in score_names]
            for kind in kinds
        ]

        heatmap_data = HeatmapChartData.from_2d_array(
            values=values,
            row_labels=kinds,
            column_labels=score_names,
            title="Kind × Score Average",
        )
        heatmap_data.set_range(0, 100)

        return Column(
            Text("Kind × Score Average", font_size=16).fixed_height(28),
            HeatmapChart(
                heatmap_data,
                colormap=ColormapType.VIRIDIS,
                show_values=True,
                show_colorbar=True,
                cell_gap=2.0,
            ).flex(1),
        ).fixed_width(500)

    def _build_kind_rank_heatmap(self):
        """Build Kind × Rank Distribution heatmap."""
        ranks = self._catalog_state.get_rank_definitions()
        if not ranks:
            return self._heatmap_placeholder("Kind × Rank Distribution", "No rank definitions found", height=280)

        rank_id = ranks[0]["id"]
        data = self._catalog_state.get_kind_rank_distribution(rank_id)

        if not data:
            return self._heatmap_placeholder("Kind × Rank Distribution", "No ranked entities yet", height=280)

        # Build matrix: rows = kinds, columns = rank labels
        kinds = sorted(set(d["kind"] for d in data))
        rank_labels = ["S", "A", "B", "C", "D"]  # Standard order

        # Create value matrix (counts)
        value_map = {(d["kind"], d["label"]): d["count"] for d in data}
        values = [
            [value_map.get((kind, label), 0) for label in rank_labels]
            for kind in kinds
        ]

        # Find max count for color scaling
        max_count = max(max(row) for row in values) if values and values[0] else 1

        heatmap_data = HeatmapChartData.from_2d_array(
            values=values,
            row_labels=kinds,
            column_labels=rank_labels,
            title=f"Kind × Rank ({ranks[0]['name']})",
        )
        heatmap_data.set_range(0, max_count)

        return Column(
            Text(f"Kind × Rank: {ranks[0]['name']}", font_size=16).fixed_height(28),
            HeatmapChart(
                heatmap_data,
                colormap=ColormapType.PLASMA,
                show_values=True,
                show_colorbar=True,
                cell_gap=2.0,
            ).flex(1),
        ).fixed_width(450)

    def _build_entity_score_heatmap(self):
        """Build Entity × Score Matrix table with heatmap coloring and Rank labels."""
        data = self._catalog_state.get_entity_score_matrix(limit=30)

        if not data:
            return self._heatmap_placeholder("Entity × Score Matrix", "No score data available", height=300)

        # Build matrix: rows = entities, columns = score types + rank labels
        entity_ids = []
        entity_labels = []
        seen_entities = set()
        for d in data:
            if d["entity_id"] not in seen_entities:
                seen_entities.add(d["entity_id"])
                entity_ids.append(d["entity_id"])
                entity_labels.append(d["entity_title"] or d["entity_name"])

        score_names = sorted(set(d["score_name"] for d in data))

        if not entity_labels or not score_names:
            return self._heatmap_placeholder("Entity × Score Matrix", "No score data available", height=300)

        # Get rank definitions and entity ranks (with labels)
        rank_defs = self._catalog_state.get_rank_definitions()
        rank_names = [r["name"] for r in rank_defs]

        # Build rank label map: {(entity_id, rank_name): label}
        rank_label_map = {}
        for eid in entity_ids:
            entity_ranks = self._catalog_state.get_entity_ranks(eid)
            for r in entity_ranks:
                rank_label_map[(eid, r["name"])] = r["label"] or "-"

        # Build score value map
        value_map = {(d["entity_id"], d["score_name"]): d["value"] for d in data}

        # Create DataTable columns: Entity + scores + ranks
        columns = [ColumnConfig(name="Entity", width=140)]
        for score in score_names:
            # Remove "Score" suffix from column name
            display_name = score.replace(" Score", "").replace("Score", "")
            columns.append(ColumnConfig(name=display_name, width=110))
        for rank in rank_names:
            columns.append(ColumnConfig(name=f"Rank", width=120))

        # Create rows: [entity_label, score1, score2, ..., rank1, rank2, ...]
        rows = []
        for i, eid in enumerate(entity_ids):
            row = [entity_labels[i]]
            for score in score_names:
                row.append(round(value_map.get((eid, score), 0), 1))
            for rank in rank_names:
                row.append(rank_label_map.get((eid, rank), "-"))
            rows.append(row)

        # Create DataTableState
        state = DataTableState(columns=columns, rows=rows)

        # Apply heatmap coloring to score columns (indices 1 to len(score_names))
        heatmap = HeatmapConfig(colormap=ColormapType.VIRIDIS)
        for i in range(1, 1 + len(score_names)):
            state.columns[i].cell_bg_color = heatmap.create_color_fn(col_idx=i, state=state)

        # Calculate dynamic height based on entity count
        row_height = 32
        header_height = 80
        height = min(450, header_height + len(entity_labels) * row_height)

        return Column(
            Text("Entity × Score Matrix", font_size=16).fixed_height(28),
            DataTable(state).flex(1),
        ).fixed_height(height)

    def _build_score_trends_heatmap(self):
        """Build Time × Score Trends heatmap."""
        data = self._catalog_state.get_score_trends_by_type(days=30)

        if not data or len(data) < 2:
            return self._heatmap_placeholder("Score Trends (30 days)", "Not enough trend data", height=250)

        # Build matrix: rows = dates, columns = score types
        dates = sorted(set(d["date"] for d in data))
        score_names = sorted(set(d["score_name"] for d in data))

        if not dates or not score_names:
            return self._heatmap_placeholder("Score Trends (30 days)", "Not enough trend data", height=250)

        # Format dates as short strings
        date_labels = [d.strftime("%m/%d") if hasattr(d, "strftime") else str(d)[:5] for d in dates]

        # Create value matrix
        value_map = {(d["date"], d["score_name"]): d["avg_value"] for d in data}
        values = [
            [value_map.get((date, score), 0) for score in score_names]
            for date in dates
        ]

        heatmap_data = HeatmapChartData.from_2d_array(
            values=values,
            row_labels=date_labels,
            column_labels=score_names,
            title="Score Trends (30 days)",
        )
        heatmap_data.set_range(0, 100)

        # Calculate dynamic height based on date count
        row_height = 20
        header_height = 80
        height = min(350, header_height + len(dates) * row_height)

        return Column(
            Text("Score Trends (30 days)", font_size=16).fixed_height(28),
            HeatmapChart(
                heatmap_data,
                colormap=ColormapType.INFERNO,
                show_values=False,
                show_colorbar=True,
                cell_gap=1.0,
            ).flex(1),
        ).fixed_height(height)

    def _heatmap_placeholder(self, title: str, message: str, height: int = 280):
        """Build a placeholder when heatmap data is unavailable."""
        theme = ThemeManager().current
        return Column(
            Text(title, font_size=16).fixed_height(28),
            Spacer().fixed_height(60),
            Text(message, font_size=14).text_color(theme.colors.fg).fixed_height(24),
            Spacer().fixed_height(height - 112),
        ).fixed_width(450).fixed_height(height).bg_color(theme.colors.bg_secondary)
