"""Scorecard Dashboard UI."""

from pydantic import BaseModel, Field

from castella import (
    Button,
    Column,
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
)

from ..state.catalog_state import CatalogState
from .scorecard_settings import ScorecardSettingsTab

# Chart colors
CHART_COLORS = {
    "primary": "#3b82f6",
    "secondary": "#22c55e",
    "accent": "#f59e0b",
    "purple": "#8b5cf6",
    "pink": "#ec4899",
    "cyan": "#06b6d4",
    "orange": "#f97316",
}

RANK_COLORS = {
    "S": "#fbbf24",
    "A": "#22c55e",
    "B": "#3b82f6",
    "C": "#f59e0b",
    "D": "#f97316",
    "E": "#ef4444",
    "F": "#dc2626",
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
        return Column(
            Spacer().fixed_height(16),
            Text(value, font_size=32),
            Spacer().fixed_height(4),
            Text(label, font_size=14).text_color("#9ca3af"),
            Spacer().fixed_height(16),
        ).bg_color("#374151").fixed_width(180)

    def _build_recent_scores_table(self, recent: list):
        """Build table of recent score updates."""
        if not recent:
            return Text("No scores recorded yet", font_size=14).text_color("#9ca3af")

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
        ranks = self._catalog_state.get_rank_definitions()

        if not ranks:
            return Column(
                Text("No rank definitions found", font_size=14).text_color("#9ca3af"),
                Spacer().fixed_height(8),
                Text("Create a scorecard definition file in catalogs/scorecards/", font_size=12).text_color("#6b7280"),
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
        is_selected = rank_id == selected
        return (
            Button(name)
            .on_click(lambda _, rid=rank_id: self._selected_rank.set(rid))
            .bg_color("#3b82f6" if is_selected else "#374151")
            .fixed_width(140)
        )

    def _build_leaderboard_table(self, rows: list[LeaderboardRow]):
        """Build leaderboard table."""
        if not rows:
            return Text("No entities with this rank yet", font_size=14).text_color("#9ca3af")

        table_state = DataTableState.from_pydantic(rows)
        self._select_row_by_entity_id(table_state)
        return DataTable(table_state).on_cell_click(self._on_row_click)

    def _build_all_scores(self):
        """Build complete scores view."""
        scores = self._catalog_state.get_all_scores_with_entities()

        if not scores:
            return Column(
                Text("No scores recorded yet", font_size=14).text_color("#9ca3af"),
                Spacer().fixed_height(8),
                Text("Add scores to entities in their YAML files under metadata.scores", font_size=12).text_color("#6b7280"),
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

        if not counts:
            return self._chart_placeholder("Entities by Kind", "No entities found")

        # Define colors for each kind
        kind_colors = {
            "Component": CHART_COLORS["primary"],
            "API": CHART_COLORS["secondary"],
            "Resource": CHART_COLORS["accent"],
            "System": CHART_COLORS["purple"],
            "Domain": CHART_COLORS["pink"],
            "User": CHART_COLORS["cyan"],
            "Group": CHART_COLORS["orange"],
        }

        categories = list(counts.keys())
        values = list(counts.values())
        colors = [kind_colors.get(k, CHART_COLORS["primary"]) for k in categories]

        data = CategoricalChartData(title="Entities by Kind")
        data.add_series(
            CategoricalSeries.from_values(
                name="Count",
                categories=categories,
                values=values,
                style=SeriesStyle(color=CHART_COLORS["primary"]),
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
                style=SeriesStyle(color=CHART_COLORS["secondary"]),
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

        if not trends or len(trends) < 2:
            return self._chart_placeholder("Score Trends", "Not enough data for trends")

        # Convert to numeric series
        y_values = [t["avg_value"] for t in trends]

        data = NumericChartData(title="Score Trends (30 days)")
        data.add_series(
            NumericSeries.from_y_values(
                name="Avg Score",
                y_values=y_values,
                style=SeriesStyle(color=CHART_COLORS["accent"]),
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
        summary = self._catalog_state.get_dashboard_summary()
        avg_score = summary.get("avg_score", 0)

        data = GaugeChartData(
            value=avg_score,
            min_value=0,
            max_value=100,
            thresholds=[
                (0.0, "#ef4444"),    # Red for low
                (0.4, "#f59e0b"),    # Yellow for medium-low
                (0.6, "#3b82f6"),    # Blue for medium
                (0.8, "#22c55e"),    # Green for high
            ],
        )

        return Column(
            Text("Overall Average Score", font_size=16).fixed_height(28),
            GaugeChart(data, style=GaugeStyle.HALF_CIRCLE, arc_width=24, show_value=True).fixed_height(220),
        ).fixed_width(280)

    def _chart_placeholder(self, title: str, message: str):
        """Build a placeholder when chart data is unavailable."""
        return Column(
            Text(title, font_size=16).fixed_height(28),
            Spacer().fixed_height(60),
            Text(message, font_size=14).text_color("#9ca3af"),
            Spacer(),
        ).fixed_width(400).bg_color("#1f2937")
