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
    PieChart,
    GaugeChart,
    GaugeChartData,
    GaugeStyle,
    CategoricalChartData,
    CategoricalSeries,
    SeriesStyle,
    HeatmapChart,
    HeatmapChartData,
    ColormapType,
)
from castella.theme import ThemeManager

from ..i18n import t
from ..state.catalog_state import CatalogState
from .group_hierarchy import GroupHierarchyView
from .history_view import EnhancedHistoryView
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
        "teal": "#73daca",                       # teal (Tokyo Night)
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
    value: str = Field(title="Value")  # str to support N/A display
    reason: str | None = Field(default=None, title="Reason")


class LeaderboardRow(BaseModel):
    """Row model for leaderboard table."""

    rank: int = Field(title="#")
    entity_name: str = Field(title="Entity")
    kind: str = Field(title="Kind")
    label: str = Field(title="Rank")
    value: str = Field(title="Score")  # str to support N/A display


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

        # Render trigger for forcing re-renders
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

        # Selected scorecard for filtering (None = "All")
        self._selected_scorecard_id: str | None = None
        # Track if user has made an explicit selection (to allow "All" selection)
        self._scorecard_selection_made: bool = False

        # Compare tab: selected scorecards
        self._compare_scorecard_a: str | None = None
        self._compare_scorecard_b: str | None = None

        # Store current rows for click handling
        self._current_rows: list = []
        self._current_entity_ids: list[str] = []

    def _trigger_render(self):
        """Trigger a re-render."""
        self._render_trigger.set(self._render_trigger() + 1)

    def _get_effective_scorecard_id(self) -> str | None:
        """Get effective scorecard ID, auto-selecting if needed.

        This method does NOT modify state, making it safe to call during render.
        """
        # If user made explicit selection, use that
        if self._scorecard_selection_made:
            return self._selected_scorecard_id

        # Otherwise, auto-select first scorecard (without modifying state)
        scorecards = self._catalog_state.get_scorecards()
        if scorecards:
            return scorecards[0]["id"]
        return None

    def _select_scorecard(self, scorecard_id: str | None):
        """Select a scorecard for filtering."""
        self._selected_scorecard_id = scorecard_id
        self._scorecard_selection_made = True
        self._trigger_render()

    def _build_scorecard_selector(self, include_all: bool = True):
        """Build scorecard selector buttons."""
        theme = ThemeManager().current
        scorecards = self._catalog_state.get_scorecards()

        if not scorecards:
            return Spacer().fixed_height(0)

        buttons = []
        effective_id = self._get_effective_scorecard_id()

        # "All" button
        if include_all:
            # "All" is selected when user explicitly selected it (selection made + None)
            is_all = self._scorecard_selection_made and self._selected_scorecard_id is None
            buttons.append(
                Button(t("dashboard.scorecard.all"))
                .on_click(lambda _: self._select_scorecard(None))
                .bg_color(theme.colors.bg_selected if is_all else theme.colors.bg_secondary)
                .fixed_width(80)
            )

        # Scorecard buttons
        for sc in scorecards:
            is_selected = sc["id"] == effective_id
            buttons.append(
                Button(sc["name"])
                .on_click(lambda _, sid=sc["id"]: self._select_scorecard(sid))
                .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
                .fixed_width(140)
            )

        return Row(
            Spacer().fixed_width(4),  # Left padding
            Text(t("dashboard.scorecard.label"), font_size=14).erase_border().fixed_width(90),
            *buttons,
            Spacer(),
        ).fixed_height(40)

    def view(self):
        active_tab = self._active_tab_value

        tab_items = [
            TabItem(id="overview", label=t("dashboard.tab.overview"), content=Spacer()),
            TabItem(id="charts", label=t("dashboard.tab.charts"), content=Spacer()),
            TabItem(id="heatmaps", label=t("dashboard.tab.heatmaps"), content=Spacer()),
            TabItem(id="groups", label=t("dashboard.tab.groups"), content=Spacer()),
            TabItem(id="history", label=t("dashboard.tab.history"), content=Spacer()),
            TabItem(id="leaderboard", label=t("dashboard.tab.leaderboard"), content=Spacer()),
            TabItem(id="scores", label=t("dashboard.tab.all_scores"), content=Spacer()),
            TabItem(id="compare", label=t("dashboard.tab.compare"), content=Spacer()),
            TabItem(id="settings", label=t("dashboard.tab.settings"), content=Spacer()),
        ]
        tabs_state = TabsState(tabs=tab_items, selected_id=active_tab)

        return Column(
            # Header
            Text(t("dashboard.title"), font_size=24).fixed_height(48),
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
        elif tab == "groups":
            return self._build_groups()
        elif tab == "history":
            return self._build_history()
        elif tab == "leaderboard":
            return self._build_leaderboard()
        elif tab == "scores":
            return self._build_all_scores()
        elif tab == "compare":
            return self._build_compare()
        elif tab == "settings":
            return self._build_settings()
        return Spacer()

    def _build_groups(self):
        """Build groups tab with hierarchy drilldown."""
        return Column(
            # Scorecard selector
            self._build_scorecard_selector(),
            Spacer().fixed_height(16),
            GroupHierarchyView(
                catalog_state=self._catalog_state,
                on_entity_select=self._on_entity_select,
                scorecard_id=self._get_effective_scorecard_id(),
            ).flex(1),
        )

    def _build_history(self):
        """Build history tab with recent changes and definition-centric charts."""
        return Column(
            # Scorecard selector
            self._build_scorecard_selector(),
            Spacer().fixed_height(16),
            Text(t("history.title"), font_size=18).fixed_height(32),
            Spacer().fixed_height(8),
            EnhancedHistoryView(
                self._catalog_state, scorecard_id=self._get_effective_scorecard_id()
            ).flex(1),
        )

    def _build_settings(self):
        """Build settings tab with scorecard configuration."""
        return ScorecardSettingsTab(self._catalog_state)

    def _build_overview(self):
        """Build overview with summary statistics."""
        summary = self._catalog_state.get_dashboard_summary(self._get_effective_scorecard_id())

        total = summary.get("total_entities", 0)
        scored = summary.get("scored_entities", 0)
        avg_score = summary.get("avg_score", 0)
        recent = summary.get("recent_updates", [])

        # Clear entity IDs for this view
        self._current_entity_ids = [r.get("entity_id", "") for r in recent]

        return Column(
            # Scorecard selector
            self._build_scorecard_selector(),
            Spacer().fixed_height(16),
            # Summary cards
            Row(
                self._stat_card(t("dashboard.summary.total_entities"), str(total)),
                Spacer().fixed_width(16),
                self._stat_card(t("dashboard.summary.scored_entities"), str(scored)),
                Spacer().fixed_width(16),
                self._stat_card(t("dashboard.summary.avg_score"), f"{avg_score:.1f}"),
                Spacer(),
            ).fixed_height(100),
            Spacer().fixed_height(24),
            # Recent scores header
            Text(t("dashboard.section.recent_updates"), font_size=18).fixed_height(32),
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
            return Text(t("dashboard.no_scores"), font_size=14).text_color(theme.colors.fg)

        rows = []
        for r in recent:
            value = r.get("value", 0)
            value_str = t("scorecard.na") if value == -1 else str(value)
            rows.append(
                ScoreRow(
                    entity_name=r.get("entity_title") or r.get("entity_name", ""),
                    kind=r.get("kind", ""),
                    score_name=r.get("score_name", ""),
                    value=value_str,
                    reason=None,
                )
            )
        self._current_rows = rows
        table_state = DataTableState.from_pydantic(rows)
        self._select_row_by_entity_id(table_state)
        return DataTable(table_state).on_cell_click(self._on_row_click)

    def _build_leaderboard(self):
        """Build leaderboard view."""
        theme = ThemeManager().current

        # Get rank definitions for selected scorecard
        effective_scorecard_id = self._get_effective_scorecard_id()
        if effective_scorecard_id:
            ranks = self._catalog_state.get_rank_definitions_for_scorecard(
                effective_scorecard_id
            )
        else:
            ranks = self._catalog_state.get_rank_definitions()

        if not ranks:
            return Column(
                self._build_scorecard_selector(),
                Spacer().fixed_height(16),
                Text(t("dashboard.no_rank_definitions"), font_size=14).text_color(theme.colors.fg),
                Spacer().fixed_height(8),
                Text(t("dashboard.create_scorecard_hint"), font_size=12).text_color(theme.colors.border_primary),
            )

        selected = self._selected_rank()
        rank_ids = [r["id"] for r in ranks]
        if not selected or selected not in rank_ids:
            # Use first rank as default (don't call set() during render)
            selected = rank_ids[0]

        limit = self._catalog_state.get_config().settings.leaderboard_limit
        leaderboard = self._catalog_state.get_leaderboard(
            selected, limit=limit, scorecard_id=self._get_effective_scorecard_id()
        )

        # Store entity IDs for click handling
        self._current_entity_ids = [item.get("entity_id", "") for item in leaderboard]

        rows = []
        for i, item in enumerate(leaderboard):
            label = item.get("label") or "-"
            value = item.get("value", 0)
            # Display N/A for negative values or N/A label
            value_str = t("scorecard.na") if value < 0 or label == "N/A" else str(round(value, 1))
            rows.append(
                LeaderboardRow(
                    rank=i + 1,
                    entity_name=item.get("title") or item.get("name", ""),
                    kind=item.get("kind", ""),
                    label=label,
                    value=value_str,
                )
            )
        self._current_rows = rows

        return Column(
            # Scorecard selector
            self._build_scorecard_selector(),
            Spacer().fixed_height(16),
            # Rank selector
            Row(
                Text(t("dashboard.rank_label"), font_size=14).erase_border().fixed_width(60),
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
            return Text(t("dashboard.no_entities_with_rank"), font_size=14).text_color(theme.colors.fg)

        table_state = DataTableState.from_pydantic(rows)
        self._select_row_by_entity_id(table_state)
        return DataTable(table_state).on_cell_click(self._on_row_click)

    def _build_all_scores(self):
        """Build complete scores view."""
        theme = ThemeManager().current
        scores = self._catalog_state.get_all_scores_with_entities(
            self._selected_scorecard_id
        )

        if not scores:
            return Column(
                self._build_scorecard_selector(),
                Spacer().fixed_height(16),
                Text(t("dashboard.no_scores"), font_size=14).text_color(theme.colors.fg),
                Spacer().fixed_height(8),
                Text(t("dashboard.add_scores_hint"), font_size=12).text_color(theme.colors.border_primary),
            )

        # Store entity IDs for click handling
        self._current_entity_ids = [s.get("entity_id", "") for s in scores]

        rows = []
        for s in scores:
            value = s.get("value", 0)
            value_str = t("scorecard.na") if value == -1 else str(value)
            rows.append(
                ScoreRow(
                    entity_name=s.get("entity_title") or s.get("entity_name", ""),
                    kind=s.get("kind", ""),
                    score_name=s.get("score_name", ""),
                    value=value_str,
                    reason=s.get("reason"),
                )
            )
        self._current_rows = rows

        table_state = DataTableState.from_pydantic(rows)
        self._select_row_by_entity_id(table_state)
        return Column(
            self._build_scorecard_selector(),
            Spacer().fixed_height(16),
            Text(t("dashboard.scores_total", count=len(scores)), font_size=13).fixed_height(24),
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
            # Scorecard selector
            self._build_scorecard_selector(),
            Spacer().fixed_height(16),
            # Row 1: Entity Kind Bar Chart + Rank Distribution Pie Chart
            Row(
                Spacer().fixed_width(16),  # Left padding for chart labels
                self._build_entity_kind_chart(),
                Spacer().fixed_width(24),
                self._build_rank_distribution_chart(),
            ).fixed_height(280),
            Spacer().fixed_height(24),
            # Row 2: Score Distribution Bar Chart + Overall Score Gauge
            Row(
                Spacer().fixed_width(16),  # Left padding for chart labels
                self._build_score_distribution_chart(),
                Spacer().fixed_width(24),
                self._build_avg_score_gauge(),
                Spacer(),
            ).fixed_height(280),
            # Absorb remaining space
            Spacer(),
        )

    def _build_entity_kind_chart(self):
        """Build bar chart showing entity count by kind."""
        counts = self._catalog_state.count_by_kind()
        chart_colors = _get_chart_colors()

        if not counts:
            return self._chart_placeholder(t("dashboard.chart.entities_by_kind"), t("status.no_entities"))

        categories = list(counts.keys())
        values = list(counts.values())

        data = CategoricalChartData(title=t("dashboard.chart.entities_by_kind"))
        data.add_series(
            CategoricalSeries.from_values(
                name="Count",
                categories=categories,
                values=values,
                style=SeriesStyle(color=chart_colors["primary"]),
            )
        )

        return Column(
            Text(t("dashboard.chart.entities_by_kind"), font_size=16).fixed_height(28),
            BarChart(
                data,
                horizontal=True,
                show_values=True,
                enable_tooltip=True,
            ).flex(1),
        ).fixed_width(400)

    def _build_rank_distribution_chart(self):
        """Build pie chart showing rank label distribution."""
        # Get rank definitions for selected scorecard
        effective_scorecard_id = self._get_effective_scorecard_id()
        if effective_scorecard_id:
            ranks = self._catalog_state.get_rank_definitions_for_scorecard(
                effective_scorecard_id
            )
        else:
            ranks = self._catalog_state.get_rank_definitions()

        if not ranks:
            return self._chart_placeholder(t("dashboard.chart.rank_distribution", name=""), t("dashboard.no_rank_definitions"))

        # Use first rank definition
        rank_id = ranks[0]["id"]
        distribution = self._catalog_state.get_rank_label_distribution(
            rank_id, self._selected_scorecard_id
        )

        if not distribution:
            return self._chart_placeholder(t("dashboard.chart.rank_distribution", name=ranks[0]["name"]), t("dashboard.no_ranked_entities"))

        categories = [d["label"] for d in distribution]
        values = [d["count"] for d in distribution]

        data = CategoricalChartData(title=t("dashboard.chart.rank_distribution", name=ranks[0]["name"]))
        data.add_series(
            CategoricalSeries.from_values(
                name="Ranks",
                categories=categories,
                values=values,
            )
        )

        return Column(
            Text(t("dashboard.chart.rank_distribution", name=ranks[0]["name"]), font_size=16).fixed_height(28),
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
        distribution = self._catalog_state.get_score_distribution(
            self._get_effective_scorecard_id()
        )
        chart_colors = _get_chart_colors()

        if not distribution:
            return self._chart_placeholder(t("dashboard.chart.avg_scores_by_type"), t("status.no_data"))

        # Filter out entries with None score_name
        valid_distribution = [d for d in distribution if d.get("score_name")]
        if not valid_distribution:
            return self._chart_placeholder(t("dashboard.chart.avg_scores_by_type"), t("status.no_data"))

        categories = [d["score_name"] for d in valid_distribution]
        values = [d["avg_value"] for d in valid_distribution]

        data = CategoricalChartData(title=t("dashboard.chart.avg_scores_by_type"))
        data.add_series(
            CategoricalSeries.from_values(
                name="Avg Score",
                categories=categories,
                values=values,
                style=SeriesStyle(color=chart_colors["secondary"]),
            )
        )

        return Column(
            Text(t("dashboard.chart.avg_scores_by_type"), font_size=16).fixed_height(28),
            BarChart(
                data,
                horizontal=True,
                show_values=True,
                enable_tooltip=True,
            ).flex(1),
        ).fixed_width(400)

    def _build_avg_score_gauge(self):
        """Build gauge chart showing overall average score."""
        theme = ThemeManager().current
        summary = self._catalog_state.get_dashboard_summary(self._get_effective_scorecard_id())
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
            Text(t("dashboard.chart.overall_avg_score"), font_size=16).fixed_height(28),
            GaugeChart(data, style=GaugeStyle.HALF_CIRCLE, arc_width=24, show_value=True).fixed_height(180),
            Text(t("dashboard.chart.overall_avg_score_desc"), font_size=11)
                .text_color(theme.colors.border_primary)
                .fixed_height(36),
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
            # Scorecard selector
            self._build_scorecard_selector(),
            Spacer().fixed_height(16),
            # Row 1: Kind × Score Average
            self._build_kind_score_heatmap().fixed_height(280),
            Spacer().fixed_height(16),
            # Row 2: Kind × Rank + Domain × Rank
            Row(
                self._build_kind_rank_heatmap(),
                Spacer().fixed_width(24),
                self._build_domain_rank_heatmap(),
            ).fixed_height(280),
            Spacer().fixed_height(16),
            # Row 3: Entity × Score Matrix (takes remaining height)
            self._build_entity_score_heatmap(),
        ).flex(1)

    def _build_kind_score_heatmap(self):
        """Build Kind × Score Average heatmap."""
        data = self._catalog_state.get_kind_score_average(self._get_effective_scorecard_id())

        if not data:
            return self._heatmap_placeholder(t("dashboard.chart.kind_score_avg"), t("status.no_data"), height=280)

        # Build matrix: rows = kinds, columns = score types
        kinds = sorted(set(d["kind"] for d in data if d["kind"]))
        score_names = sorted(set(d["score_name"] for d in data if d["score_name"]))

        if not kinds or not score_names:
            return self._heatmap_placeholder(t("dashboard.chart.kind_score_avg"), t("status.no_data"), height=280)

        # Build min/max map for normalization
        minmax_map = {
            d["score_name"]: (d["min_value"], d["max_value"])
            for d in data
            if d["score_name"]
        }

        # Create value matrix with normalized values (0-100 scale)
        value_map = {(d["kind"], d["score_name"]): d["avg_value"] for d in data}
        values = []
        for kind in kinds:
            row = []
            for score in score_names:
                raw_val = value_map.get((kind, score), 0)
                min_val, max_val = minmax_map.get(score, (0.0, 100.0))
                # Normalize to 0-100 scale
                if max_val != min_val:
                    normalized = (raw_val - min_val) / (max_val - min_val) * 100
                else:
                    normalized = 100.0 if raw_val >= max_val else 0.0
                row.append(round(normalized, 1))
            values.append(row)

        # Truncate long score names for display
        def truncate_name(name: str, max_len: int = 12) -> str:
            return name[:max_len - 1] + "…" if len(name) > max_len else name

        short_score_names = [truncate_name(name) for name in score_names]

        heatmap_data = HeatmapChartData.from_2d_array(
            values=values,
            row_labels=kinds,
            column_labels=short_score_names,
            title=t("dashboard.chart.kind_score_avg"),
        )
        heatmap_data.set_range(0, 100)

        return Column(
            Text(t("dashboard.chart.kind_score_avg"), font_size=16).fixed_height(28),
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
        # Get rank definitions for selected scorecard
        effective_scorecard_id = self._get_effective_scorecard_id()
        if effective_scorecard_id:
            ranks = self._catalog_state.get_rank_definitions_for_scorecard(
                effective_scorecard_id
            )
        else:
            ranks = self._catalog_state.get_rank_definitions()

        if not ranks:
            return self._heatmap_placeholder(t("dashboard.chart.kind_rank", name=""), t("dashboard.no_rank_definitions"), height=280)

        rank_def = ranks[0]
        rank_id = rank_def["id"]
        data = self._catalog_state.get_kind_rank_distribution(
            rank_id, self._selected_scorecard_id
        )

        if not data:
            return self._heatmap_placeholder(t("dashboard.chart.kind_rank", name=rank_def["name"]), t("dashboard.no_ranked_entities"), height=280)

        # Get rank labels from thresholds (sorted by min descending for S->A->B->C->D order)
        thresholds = rank_def.get("thresholds") or []
        if thresholds:
            sorted_thresholds = sorted(thresholds, key=lambda x: x.get("min", 0), reverse=True)
            rank_labels = [th.get("label", "") for th in sorted_thresholds if th.get("label")]
        else:
            # Fallback to labels from data
            rank_labels = sorted(set(d["label"] for d in data if d["label"]))

        if not rank_labels:
            return self._heatmap_placeholder(t("dashboard.chart.kind_rank", name=rank_def["name"]), t("dashboard.no_ranked_entities"), height=280)

        # Build matrix: rows = kinds, columns = rank labels
        kinds = sorted(set(d["kind"] for d in data if d["kind"]))

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
            title=t("dashboard.chart.kind_rank", name=rank_def["name"]),
        )
        heatmap_data.set_range(0, max_count)

        return Column(
            Text(t("dashboard.chart.kind_rank", name=rank_def["name"]), font_size=16).fixed_height(28),
            HeatmapChart(
                heatmap_data,
                colormap=ColormapType.PLASMA,
                show_values=True,
                show_colorbar=True,
                cell_gap=2.0,
            ).flex(1),
        ).fixed_width(450)

    def _build_domain_rank_heatmap(self):
        """Build Domain × Rank Distribution heatmap."""
        # Get rank definitions for selected scorecard
        effective_scorecard_id = self._get_effective_scorecard_id()
        if effective_scorecard_id:
            ranks = self._catalog_state.get_rank_definitions_for_scorecard(
                effective_scorecard_id
            )
        else:
            ranks = self._catalog_state.get_rank_definitions()

        if not ranks:
            return self._heatmap_placeholder(t("dashboard.chart.domain_rank", name=""), t("dashboard.no_rank_definitions"), height=280)

        rank_def = ranks[0]
        rank_id = rank_def["id"]
        data = self._catalog_state.get_domain_rank_distribution(
            rank_id, self._selected_scorecard_id
        )

        if not data:
            return self._heatmap_placeholder(t("dashboard.chart.domain_rank", name=rank_def["name"]), t("dashboard.no_ranked_entities"), height=280)

        # Get rank labels from thresholds (sorted by min descending for S->A->B->C->D order)
        thresholds = rank_def.get("thresholds") or []
        if thresholds:
            sorted_thresholds = sorted(thresholds, key=lambda x: x.get("min", 0), reverse=True)
            rank_labels = [th.get("label", "") for th in sorted_thresholds if th.get("label")]
        else:
            # Fallback to labels from data
            rank_labels = sorted(set(d["label"] for d in data if d["label"]))

        if not rank_labels:
            return self._heatmap_placeholder(t("dashboard.chart.domain_rank", name=rank_def["name"]), t("dashboard.no_ranked_entities"), height=280)

        # Build matrix: rows = domains, columns = rank labels
        # Show "unset" label for empty domain
        domains = sorted(set(d["domain"] for d in data))
        domain_labels = [d if d else t("dashboard.unset_domain") for d in domains]

        # Create value matrix (counts)
        value_map = {(d["domain"], d["label"]): d["count"] for d in data}
        values = [
            [value_map.get((domain, label), 0) for label in rank_labels]
            for domain in domains
        ]

        # Find max count for color scaling
        max_count = max(max(row) for row in values) if values and values[0] else 1

        heatmap_data = HeatmapChartData.from_2d_array(
            values=values,
            row_labels=domain_labels,
            column_labels=rank_labels,
            title=t("dashboard.chart.domain_rank", name=rank_def["name"]),
        )
        heatmap_data.set_range(0, max_count)

        return Column(
            Text(t("dashboard.chart.domain_rank", name=rank_def["name"]), font_size=16).fixed_height(28),
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
        data = self._catalog_state.get_entity_score_matrix(
            limit=30, scorecard_id=self._get_effective_scorecard_id()
        )

        if not data:
            return self._heatmap_placeholder(t("dashboard.chart.entity_score_matrix"), t("status.no_data"), use_flex=True)

        # Build matrix: rows = entities, columns = score types + rank labels
        entity_ids = []
        entity_labels = []
        seen_entities = set()
        for d in data:
            if d["entity_id"] not in seen_entities:
                seen_entities.add(d["entity_id"])
                entity_ids.append(d["entity_id"])
                entity_labels.append(d["entity_title"] or d["entity_name"])

        score_names = sorted(set(d["score_name"] for d in data if d["score_name"]))

        if not entity_labels or not score_names:
            return self._heatmap_placeholder(t("dashboard.chart.entity_score_matrix"), t("status.no_data"), use_flex=True)

        # Get rank definitions for selected scorecard
        effective_scorecard_id = self._get_effective_scorecard_id()
        if effective_scorecard_id:
            rank_defs = self._catalog_state.get_rank_definitions_for_scorecard(
                effective_scorecard_id
            )
        else:
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
        columns = [ColumnConfig(name=t("entity.entity"), width=140)]  # "Entity" column
        for score in score_names:
            # Remove "Score" suffix from column name
            display_name = score.replace(" Score", "").replace("Score", "")
            columns.append(ColumnConfig(name=display_name, width=110))
        for rank in rank_names:
            columns.append(ColumnConfig(name=rank, width=120))

        # Create rows: [entity_label, score1, score2, ..., rank1, rank2, ...]
        rows = []
        for i, eid in enumerate(entity_ids):
            row = [entity_labels[i]]
            for score in score_names:
                val = value_map.get((eid, score), 0)
                # Display "N/A" for -1 values
                row.append(t("scorecard.na") if val == -1 else str(round(val, 1)))
            for rank in rank_names:
                row.append(rank_label_map.get((eid, rank), "-"))
            rows.append(row)

        # Create DataTableState
        state = DataTableState(columns=columns, rows=rows)

        # Apply heatmap coloring to score columns (indices 1 to len(score_names))
        heatmap = HeatmapConfig(colormap=ColormapType.VIRIDIS)
        for i in range(1, 1 + len(score_names)):
            state.columns[i].cell_bg_color = heatmap.create_color_fn(col_idx=i, state=state)

        return Column(
            Text(t("dashboard.chart.entity_score_matrix"), font_size=16).fixed_height(28),
            DataTable(state).flex(1),
        ).flex(1)

    def _heatmap_placeholder(self, title: str, message: str, height: int = 280, use_flex: bool = False):
        """Build a placeholder when heatmap data is unavailable."""
        theme = ThemeManager().current
        content = Column(
            Text(title, font_size=16).fixed_height(28),
            Spacer().fixed_height(60),
            Text(message, font_size=14).text_color(theme.colors.fg).fixed_height(24),
            Spacer(),
        ).bg_color(theme.colors.bg_secondary)
        if use_flex:
            return content.flex(1)
        else:
            return content.fixed_width(450).fixed_height(height)

    # ========== Compare Tab ==========

    def _select_compare_scorecard_a(self, scorecard_id: str):
        """Select scorecard A for comparison."""
        self._compare_scorecard_a = scorecard_id
        self._trigger_render()

    def _select_compare_scorecard_b(self, scorecard_id: str):
        """Select scorecard B for comparison."""
        self._compare_scorecard_b = scorecard_id
        self._trigger_render()

    def _get_effective_compare_a(self) -> str | None:
        """Get effective compare scorecard A, auto-selecting if needed."""
        if self._compare_scorecard_a is not None:
            return self._compare_scorecard_a
        scorecards = self._catalog_state.get_scorecards()
        if scorecards:
            return scorecards[0]["id"]
        return None

    def _get_effective_compare_b(self) -> str | None:
        """Get effective compare scorecard B, auto-selecting if needed."""
        if self._compare_scorecard_b is not None:
            return self._compare_scorecard_b
        scorecards = self._catalog_state.get_scorecards()
        if len(scorecards) > 1:
            return scorecards[1]["id"]
        return None

    def _build_compare(self):
        """Build compare tab for scorecard comparison."""
        theme = ThemeManager().current
        scorecards = self._catalog_state.get_scorecards()

        if len(scorecards) < 2:
            return Column(
                Text(t("dashboard.compare.title"), font_size=18).fixed_height(32),
                Spacer().fixed_height(16),
                Text(t("dashboard.compare.need_two_scorecards"), font_size=14).text_color(theme.colors.fg),
            )

        # Get effective scorecard IDs (auto-select without modifying state)
        effective_a = self._get_effective_compare_a()
        effective_b = self._get_effective_compare_b()

        # Get scorecard names
        scorecard_a_name = next(
            (sc["name"] for sc in scorecards if sc["id"] == effective_a),
            ""
        )
        scorecard_b_name = next(
            (sc["name"] for sc in scorecards if sc["id"] == effective_b),
            ""
        )

        return Column(
            # Title
            Text(t("dashboard.compare.title"), font_size=18).fixed_height(32),
            Spacer().fixed_height(16),
            # Scorecard selector row
            self._build_compare_selector(scorecards),
            Spacer().fixed_height(24),
            # Comparison content
            Row(
                # Left: Scorecard A rank distribution
                self._build_compare_rank_chart(
                    effective_a, scorecard_a_name
                ),
                Spacer().fixed_width(24),
                # Right: Scorecard B rank distribution
                self._build_compare_rank_chart(
                    effective_b, scorecard_b_name
                ),
            ).fixed_height(280),
            Spacer().fixed_height(24),
            # Entity comparison table (takes remaining height)
            self._build_entity_comparison_table(),
        )

    def _build_compare_selector(self, scorecards: list):
        """Build scorecard selector for comparison."""
        theme = ThemeManager().current
        effective_a = self._get_effective_compare_a()
        effective_b = self._get_effective_compare_b()

        buttons_a = []
        for sc in scorecards:
            is_selected = sc["id"] == effective_a
            buttons_a.append(
                Button(sc["name"])
                .on_click(lambda _, sid=sc["id"]: self._select_compare_scorecard_a(sid))
                .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
                .fixed_width(120)
            )

        buttons_b = []
        for sc in scorecards:
            is_selected = sc["id"] == effective_b
            buttons_b.append(
                Button(sc["name"])
                .on_click(lambda _, sid=sc["id"]: self._select_compare_scorecard_b(sid))
                .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
                .fixed_width(120)
            )

        return Row(
            Text("A:", font_size=14).erase_border().fixed_width(30),
            *buttons_a,
            Spacer().fixed_width(24),
            Text("vs", font_size=14).erase_border().fixed_width(30),
            Spacer().fixed_width(24),
            Text("B:", font_size=14).erase_border().fixed_width(30),
            *buttons_b,
            Spacer(),
        ).fixed_height(40)

    def _build_compare_rank_chart(self, scorecard_id: str | None, scorecard_name: str):
        """Build rank distribution pie chart for comparison."""
        if not scorecard_id:
            return self._chart_placeholder(
                t("dashboard.compare.rank_distribution", name=""),
                t("dashboard.compare.select_scorecard")
            )

        # Get rank definitions for this scorecard
        ranks = self._catalog_state.get_rank_definitions_for_scorecard(scorecard_id)
        if not ranks:
            return self._chart_placeholder(
                t("dashboard.compare.rank_distribution", name=scorecard_name),
                t("dashboard.no_rank_definitions")
            )

        rank_id = ranks[0]["id"]
        distribution = self._catalog_state.get_rank_label_distribution(
            rank_id, scorecard_id
        )

        if not distribution:
            return self._chart_placeholder(
                t("dashboard.compare.rank_distribution", name=scorecard_name),
                t("dashboard.no_ranked_entities")
            )

        categories = [d["label"] for d in distribution]
        values = [d["count"] for d in distribution]

        data = CategoricalChartData(title=scorecard_name)
        data.add_series(
            CategoricalSeries.from_values(
                name="Ranks",
                categories=categories,
                values=values,
            )
        )

        return Column(
            Text(
                t("dashboard.compare.rank_distribution", name=scorecard_name),
                font_size=16
            ).fixed_height(28),
            PieChart(
                data,
                donut=True,
                inner_radius_ratio=0.5,
                show_labels=True,
                show_percentages=True,
                enable_tooltip=True,
            ).flex(1),
        ).fixed_width(400)

    def _build_entity_comparison_table(self):
        """Build entity comparison table showing rank changes."""
        theme = ThemeManager().current
        effective_a = self._get_effective_compare_a()
        effective_b = self._get_effective_compare_b()

        if not effective_a or not effective_b:
            return Spacer().flex(1)

        comparison = self._catalog_state.get_entities_comparison(
            effective_a, effective_b
        )

        if not comparison:
            return Column(
                Text(t("dashboard.compare.entity_comparison"), font_size=16).fixed_height(28),
                Spacer().fixed_height(8),
                Text(t("dashboard.compare.no_common_entities"), font_size=14).text_color(theme.colors.fg),
                Spacer(),
            ).flex(1)

        # Get scorecard names
        scorecards = self._catalog_state.get_scorecards()
        scorecard_a_name = next(
            (sc["name"] for sc in scorecards if sc["id"] == effective_a),
            "A"
        )
        scorecard_b_name = next(
            (sc["name"] for sc in scorecards if sc["id"] == effective_b),
            "B"
        )

        # Build DataTable
        columns = [
            ColumnConfig(name=t("entity.entity"), width=180),
            ColumnConfig(name=t("entity.field.kind"), width=80),
            ColumnConfig(name=scorecard_a_name, width=120),
            ColumnConfig(name=scorecard_b_name, width=120),
            ColumnConfig(name=t("dashboard.compare.change"), width=80),
        ]

        rows = []
        rank_order = {"S": 1, "A": 2, "B": 3, "C": 4, "D": 5, "E": 6, "F": 7, "-": 99}

        for item in comparison:
            label_a = item["label_a"]
            label_b = item["label_b"]

            # Calculate change indicator
            order_a = rank_order.get(label_a, 50)
            order_b = rank_order.get(label_b, 50)

            if order_a < order_b:
                change = "↓"  # Worsened (higher order = worse rank)
            elif order_a > order_b:
                change = "↑"  # Improved
            else:
                change = "="

            rows.append([
                item["entity_title"],
                item["kind"],
                label_a,
                label_b,
                change,
            ])

        state = DataTableState(columns=columns, rows=rows)

        return Column(
            Text(t("dashboard.compare.entity_comparison"), font_size=16).fixed_height(28),
            Spacer().fixed_height(8),
            DataTable(state).flex(1),
        ).flex(1)
