"""History view components for score and rank tracking."""

from datetime import datetime
from typing import Any, Callable

from castella import (
    Button,
    Column,
    Component,
    Row,
    Spacer,
    State,
    Text,
)
from castella.chart import LineChart, NumericChartData, NumericSeries, SeriesStyle
from castella.chart.models.data_points import NumericDataPoint
from castella.theme import ThemeManager

from ..state.catalog_state import CatalogState


def _parse_timestamp(timestamp: str | Any) -> datetime | None:
    """Parse timestamp string to datetime."""
    if timestamp is None:
        return None
    ts_str = str(timestamp)
    # Handle common formats
    try:
        # Remove timezone suffix for simpler parsing
        clean = ts_str.replace("Z", "").replace("+00:00", "")
        if "T" in clean:
            return datetime.fromisoformat(clean)
        elif " " in clean:
            return datetime.strptime(clean.split(".")[0], "%Y-%m-%d %H:%M:%S")
        else:
            return datetime.strptime(clean[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _format_timestamp(timestamp: str | Any) -> str:
    """Format timestamp for display."""
    if timestamp is None:
        return "-"
    ts_str = str(timestamp)
    # Handle different formats
    if "T" in ts_str:
        return ts_str.split("T")[0]
    if " " in ts_str:
        return ts_str.split(" ")[0]
    return ts_str[:10] if len(ts_str) > 10 else ts_str


class ScoreHistoryChart(Component):
    """Line chart showing score history over time."""

    def __init__(
        self,
        catalog_state: CatalogState,
        entity_id: str,
        score_id: str,
        height: int = 200,
        show_definition_changes: bool = False,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._entity_id = entity_id
        self._score_id = score_id
        self._height = height
        self._show_definition_changes = show_definition_changes

    def view(self):
        theme = ThemeManager().current
        history = self._catalog_state.get_entity_score_history(
            self._entity_id, self._score_id
        )

        if not history or len(history) < 2:
            return Column(
                Text("Score History", font_size=14).text_color(
                    theme.colors.text_primary
                ),
                Spacer().fixed_height(8),
                Text("Not enough data for chart", font_size=12).text_color(
                    theme.colors.fg
                ),
            ).fixed_height(self._height)

        # Sort by timestamp (oldest first for chart)
        sorted_history = sorted(history, key=lambda x: x.get("recorded_at", ""))

        # Extract values
        y_values = [h.get("value", 0) for h in sorted_history]

        data = NumericChartData(title=f"Score History: {self._score_id}")
        data.add_series(
            NumericSeries.from_y_values(
                name="Value",
                y_values=y_values,
                style=SeriesStyle(color=theme.colors.text_info),
            )
        )

        # Get definition change info if requested
        if self._show_definition_changes:
            definition_changes = self._catalog_state.get_definition_change_timestamps(
                "score", self._score_id
            )
            if definition_changes:
                change_dates = [
                    _format_timestamp(c.get("recorded_at")) for c in definition_changes
                ]
                change_info = Text(
                    f"Definition changes: {', '.join(change_dates[:5])}",
                    font_size=10,
                ).text_color(theme.colors.text_warning)
            else:
                change_info = Spacer().fixed_height(0)
        else:
            change_info = Spacer().fixed_height(0)

        chart_height = self._height - 30 if not self._show_definition_changes else self._height - 50

        return Column(
            Text(f"Score History: {self._score_id}", font_size=14).text_color(
                theme.colors.text_primary
            ),
            Spacer().fixed_height(8),
            LineChart(
                data,
                show_points=True,
                smooth=True,
                enable_tooltip=True,
            ).fixed_height(chart_height),
            change_info,
        ).fixed_height(self._height)


class ScoreHistoryTable(Component):
    """Table showing score history entries."""

    def __init__(
        self,
        catalog_state: CatalogState,
        entity_id: str,
        score_id: str | None = None,
        limit: int = 20,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._entity_id = entity_id
        self._score_id = score_id
        self._limit = limit

    def view(self):
        theme = ThemeManager().current
        history = self._catalog_state.get_entity_score_history(
            self._entity_id, self._score_id, self._limit
        )

        if not history:
            return Text("No history data", font_size=12).text_color(theme.colors.fg)

        # Header
        header = Row(
            Text("Date", font_size=12).text_color(theme.colors.fg).fixed_width(100),
            Text("Score", font_size=12).text_color(theme.colors.fg).fixed_width(80)
            if not self._score_id
            else Spacer().fixed_width(0),
            Text("Value", font_size=12).text_color(theme.colors.fg).fixed_width(60),
            Text("Reason", font_size=12).text_color(theme.colors.fg).flex(1),
        ).fixed_height(24).bg_color(theme.colors.bg_tertiary)

        # Rows
        rows = [header]
        for entry in history:
            rows.append(
                Row(
                    Text(_format_timestamp(entry.get("recorded_at")), font_size=12)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(100),
                    Text(entry.get("score_id", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(80)
                    if not self._score_id
                    else Spacer().fixed_width(0),
                    Text(f"{entry.get('value', 0):.0f}", font_size=12)
                    .text_color(theme.colors.text_success)
                    .fixed_width(60),
                    Text(entry.get("reason") or "-", font_size=12)
                    .text_color(theme.colors.fg)
                    .flex(1),
                ).fixed_height(24)
            )
            rows.append(Spacer().fixed_height(2))

        return Column(*rows, scrollable=True)


class RankHistoryTable(Component):
    """Table showing rank history entries."""

    def __init__(
        self,
        catalog_state: CatalogState,
        entity_id: str,
        rank_id: str | None = None,
        limit: int = 20,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._entity_id = entity_id
        self._rank_id = rank_id
        self._limit = limit

    def _label_color(self, label: str | None):
        """Get color for rank label."""
        theme = ThemeManager().current
        if not label:
            return theme.colors.fg
        label = label.upper()
        if label in ("S", "SS", "SSS"):
            return "#FFD700"  # Gold
        elif label == "A":
            return theme.colors.text_success
        elif label == "B":
            return theme.colors.text_info
        elif label == "C":
            return "#FFFF00"  # Yellow
        elif label == "D":
            return "#FFA500"  # Orange
        else:
            return theme.colors.text_danger

    def view(self):
        theme = ThemeManager().current
        history = self._catalog_state.get_entity_rank_history(
            self._entity_id, self._rank_id, self._limit
        )

        if not history:
            return Text("No history data", font_size=12).text_color(theme.colors.fg)

        # Header
        header = Row(
            Text("Date", font_size=12).text_color(theme.colors.fg).fixed_width(100),
            Text("Rank", font_size=12).text_color(theme.colors.fg).fixed_width(100)
            if not self._rank_id
            else Spacer().fixed_width(0),
            Text("Label", font_size=12).text_color(theme.colors.fg).fixed_width(60),
            Text("Value", font_size=12).text_color(theme.colors.fg).fixed_width(60),
        ).fixed_height(24).bg_color(theme.colors.bg_tertiary)

        # Rows
        rows = [header]
        for entry in history:
            label = entry.get("label", "-")
            rows.append(
                Row(
                    Text(_format_timestamp(entry.get("recorded_at")), font_size=12)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(100),
                    Text(entry.get("rank_id", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(100)
                    if not self._rank_id
                    else Spacer().fixed_width(0),
                    Text(label or "-", font_size=14)
                    .text_color(self._label_color(label))
                    .fixed_width(60),
                    Text(f"{entry.get('value', 0):.1f}", font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(60),
                ).fixed_height(24)
            )
            rows.append(Spacer().fixed_height(2))

        return Column(*rows, scrollable=True)


class DefinitionHistoryView(Component):
    """View for definition change history."""

    def __init__(
        self,
        catalog_state: CatalogState,
        definition_type: str | None = None,
        definition_id: str | None = None,
        limit: int = 50,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._definition_type = definition_type
        self._definition_id = definition_id
        self._limit = limit

    def _change_type_color(self, change_type: str):
        """Get color for change type."""
        theme = ThemeManager().current
        if change_type == "created":
            return theme.colors.text_success
        elif change_type == "deleted":
            return theme.colors.text_danger
        elif change_type == "updated":
            return theme.colors.text_info
        return theme.colors.fg

    def view(self):
        theme = ThemeManager().current
        history = self._catalog_state.get_definition_history(
            self._definition_type, self._definition_id, self._limit
        )

        if not history:
            return Text("No definition changes", font_size=12).text_color(
                theme.colors.fg
            )

        # Header
        header = Row(
            Text("Date", font_size=12).text_color(theme.colors.fg).fixed_width(100),
            Text("Type", font_size=12).text_color(theme.colors.fg).fixed_width(60),
            Text("ID", font_size=12).text_color(theme.colors.fg).fixed_width(120),
            Text("Change", font_size=12).text_color(theme.colors.fg).fixed_width(80),
            Text("Fields", font_size=12).text_color(theme.colors.fg).flex(1),
        ).fixed_height(24).bg_color(theme.colors.bg_tertiary)

        # Rows
        rows = [header]
        for entry in history:
            change_type = entry.get("change_type", "")
            changed_fields = entry.get("changed_fields", [])
            fields_str = ", ".join(changed_fields) if changed_fields else "-"

            rows.append(
                Row(
                    Text(_format_timestamp(entry.get("recorded_at")), font_size=12)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(100),
                    Text(entry.get("definition_type", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(60),
                    Text(entry.get("definition_id", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(120),
                    Text(change_type, font_size=12)
                    .text_color(self._change_type_color(change_type))
                    .fixed_width(80),
                    Text(fields_str, font_size=12).text_color(theme.colors.fg).flex(1),
                ).fixed_height(24)
            )
            rows.append(Spacer().fixed_height(2))

        return Column(*rows, scrollable=True)


class RecentChangesView(Component):
    """View for recent score/rank changes (for dashboard)."""

    def __init__(self, catalog_state: CatalogState, limit: int = 10):
        super().__init__()
        self._catalog_state = catalog_state
        self._limit = limit
        self._active_tab = State("scores")
        self._active_tab.attach(self)

    def view(self):
        theme = ThemeManager().current
        active = self._active_tab()

        # Tabs
        tabs = Row(
            Button("Score Changes")
            .on_click(lambda _: self._active_tab.set("scores"))
            .bg_color(
                theme.colors.bg_selected if active == "scores" else theme.colors.bg_secondary
            )
            .fixed_height(32),
            Spacer().fixed_width(8),
            Button("Rank Changes")
            .on_click(lambda _: self._active_tab.set("ranks"))
            .bg_color(
                theme.colors.bg_selected if active == "ranks" else theme.colors.bg_secondary
            )
            .fixed_height(32),
            Spacer().fixed_width(8),
            Button("Definition Changes")
            .on_click(lambda _: self._active_tab.set("definitions"))
            .bg_color(
                theme.colors.bg_selected
                if active == "definitions"
                else theme.colors.bg_secondary
            )
            .fixed_height(32),
            Spacer(),
        ).fixed_height(40)

        # Content
        if active == "scores":
            content = self._build_score_changes()
        elif active == "ranks":
            content = self._build_rank_changes()
        else:
            content = DefinitionHistoryView(self._catalog_state, limit=self._limit)

        return Column(
            tabs,
            Spacer().fixed_height(8),
            content,
        )

    def _build_score_changes(self):
        theme = ThemeManager().current
        changes = self._catalog_state.get_recent_score_changes(self._limit)

        if not changes:
            return Text("No recent score changes", font_size=12).text_color(
                theme.colors.fg
            )

        # Header
        header = Row(
            Text("Date", font_size=12).text_color(theme.colors.fg).fixed_width(100),
            Text("Entity", font_size=12).text_color(theme.colors.fg).fixed_width(150),
            Text("Score", font_size=12).text_color(theme.colors.fg).fixed_width(100),
            Text("Old", font_size=12).text_color(theme.colors.fg).fixed_width(50),
            Text("New", font_size=12).text_color(theme.colors.fg).fixed_width(50),
        ).fixed_height(24).bg_color(theme.colors.bg_tertiary)

        rows = [header]
        for change in changes:
            old_val = change.get("prev_value", 0)
            new_val = change.get("value", 0)
            diff_color = (
                theme.colors.text_success
                if new_val > old_val
                else theme.colors.text_danger
            )

            rows.append(
                Row(
                    Text(_format_timestamp(change.get("recorded_at")), font_size=12)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(100),
                    Text(change.get("entity_name", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(150),
                    Text(change.get("score_name", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(100),
                    Text(f"{old_val:.0f}", font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(50),
                    Text(f"{new_val:.0f}", font_size=12)
                    .text_color(diff_color)
                    .fixed_width(50),
                ).fixed_height(24)
            )
            rows.append(Spacer().fixed_height(2))

        return Column(*rows, scrollable=True)

    def _build_rank_changes(self):
        theme = ThemeManager().current
        changes = self._catalog_state.get_recent_rank_changes(self._limit)

        if not changes:
            return Text("No recent rank changes", font_size=12).text_color(
                theme.colors.fg
            )

        # Header
        header = Row(
            Text("Date", font_size=12).text_color(theme.colors.fg).fixed_width(100),
            Text("Entity", font_size=12).text_color(theme.colors.fg).fixed_width(150),
            Text("Rank", font_size=12).text_color(theme.colors.fg).fixed_width(100),
            Text("Old", font_size=12).text_color(theme.colors.fg).fixed_width(50),
            Text("New", font_size=12).text_color(theme.colors.fg).fixed_width(50),
        ).fixed_height(24).bg_color(theme.colors.bg_tertiary)

        rows = [header]
        for change in changes:
            old_label = change.get("prev_label", "-")
            new_label = change.get("label", "-")

            rows.append(
                Row(
                    Text(_format_timestamp(change.get("recorded_at")), font_size=12)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(100),
                    Text(change.get("entity_name", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(150),
                    Text(change.get("rank_name", ""), font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(100),
                    Text(old_label or "-", font_size=12)
                    .text_color(theme.colors.fg)
                    .fixed_width(50),
                    Text(new_label or "-", font_size=12)
                    .text_color(theme.colors.text_info)
                    .fixed_width(50),
                ).fixed_height(24)
            )
            rows.append(Spacer().fixed_height(2))

        return Column(*rows, scrollable=True)


# Tokyo Night inspired color palette for multi-series charts
CHART_COLORS = [
    "#7aa2f7",  # Blue
    "#9ece6a",  # Green
    "#bb9af7",  # Purple
    "#e0af68",  # Yellow/Orange
    "#f7768e",  # Red/Pink
    "#7dcfff",  # Cyan
    "#c0caf5",  # Light blue-gray
    "#ff9e64",  # Orange
]


class DefinitionHistoryChartView(Component):
    """Multi-entity time series chart for a specific definition."""

    def __init__(
        self,
        catalog_state: CatalogState,
        definition_type: str,  # "score" or "rank"
        definition_id: str,
        entity_ids: list[str] | None = None,
        days: int = 90,
        height: int = 350,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._definition_type = definition_type
        self._definition_id = definition_id
        self._entity_ids = entity_ids
        self._days = days
        self._height = height

    def view(self):
        theme = ThemeManager().current

        # Get history data grouped by entity
        if self._definition_type == "score":
            history = self._catalog_state.get_score_history_for_definition(
                self._definition_id, self._entity_ids, self._days
            )
        else:
            history = self._catalog_state.get_rank_history_for_definition(
                self._definition_id, self._entity_ids, self._days
            )

        if not history:
            return Column(
                Text(
                    f"{self._definition_type.title()} History: {self._definition_id}",
                    font_size=14,
                ).text_color(theme.colors.text_primary),
                Spacer().fixed_height(8),
                Text("No history data", font_size=12).text_color(theme.colors.fg),
            ).fixed_height(self._height)

        # Group by entity_id and parse timestamps
        grouped: dict[str, list[dict]] = {}
        entity_names: dict[str, str] = {}
        all_timestamps: list[datetime] = []

        for entry in history:
            entity_id = entry["entity_id"]
            if entity_id not in grouped:
                grouped[entity_id] = []
                entity_names[entity_id] = entry.get("entity_name", entity_id)
            # Parse timestamp
            ts = _parse_timestamp(entry.get("recorded_at"))
            if ts:
                entry["_parsed_ts"] = ts
                all_timestamps.append(ts)
            grouped[entity_id].append(entry)

        # Find the earliest timestamp as reference point for X axis
        if not all_timestamps:
            return Column(
                Text("No valid timestamps in data", font_size=12).text_color(
                    theme.colors.fg
                ),
            ).fixed_height(self._height)

        min_ts = min(all_timestamps)

        # Get definition change timestamps for markers
        definition_changes = self._catalog_state.get_definition_change_timestamps(
            self._definition_type, self._definition_id
        )

        # Create chart data
        data = NumericChartData(
            title=f"{self._definition_type.title()} History: {self._definition_id}"
        )

        # Add a series for each entity with proper X coordinates (days since min_ts)
        for i, (entity_id, entries) in enumerate(grouped.items()):
            # Filter entries with valid timestamps and sort
            valid_entries = [e for e in entries if "_parsed_ts" in e]
            sorted_entries = sorted(valid_entries, key=lambda x: x["_parsed_ts"])

            if len(sorted_entries) < 2:
                continue

            color = CHART_COLORS[i % len(CHART_COLORS)]
            entity_name = entity_names.get(entity_id, entity_id)

            # Create data points with X = days since min_ts
            points = []
            for entry in sorted_entries:
                ts = entry["_parsed_ts"]
                x_days = (ts - min_ts).total_seconds() / 86400.0  # Convert to days
                y_value = float(entry.get("value", 0))
                label = _format_timestamp(entry.get("recorded_at"))
                points.append(NumericDataPoint(x=x_days, y=y_value, label=label))

            data.add_series(
                NumericSeries(
                    name=entity_name,
                    data=tuple(points),
                    style=SeriesStyle(color=color),
                )
            )

        # Build legend
        legend_items = []
        for i, (entity_id, _) in enumerate(grouped.items()):
            color = CHART_COLORS[i % len(CHART_COLORS)]
            entity_name = entity_names.get(entity_id, entity_id)
            legend_items.append(
                Row(
                    Column().bg_color(color).fixed_width(12).fixed_height(12),
                    Spacer().fixed_width(4),
                    Text(entity_name, font_size=11).text_color(theme.colors.fg),
                    Spacer().fixed_width(16),
                )
            )

        legend_row = Row(*legend_items, Spacer()).fixed_height(20)

        # Build definition change info text
        if definition_changes:
            change_dates = [
                _format_timestamp(c.get("recorded_at")) for c in definition_changes
            ]
            change_info = Text(
                f"Definition changes: {', '.join(change_dates[:5])}",
                font_size=10,
            ).text_color(theme.colors.fg)
        else:
            change_info = Spacer().fixed_height(0)

        return Column(
            Text(
                f"{self._definition_type.title()} History: {self._definition_id}",
                font_size=14,
            ).text_color(theme.colors.text_primary),
            Spacer().fixed_height(8),
            LineChart(
                data,
                show_points=True,
                smooth=False,
                enable_tooltip=True,
            ).fixed_height(self._height - 80),
            Spacer().fixed_height(8),
            legend_row,
            change_info,
        ).fixed_height(self._height)


class EnhancedHistoryView(Component):
    """Enhanced history view with definition-centric charts."""

    def __init__(self, catalog_state: CatalogState):
        super().__init__()
        self._catalog_state = catalog_state

        # View mode: "recent", "by_score", "by_rank"
        self._view_mode = State("recent")
        self._view_mode.attach(self)

        # Selected definition for chart view
        self._selected_definition = State("")
        self._selected_definition.attach(self)

    def view(self):
        theme = ThemeManager().current
        mode = self._view_mode()

        # View mode selector buttons
        mode_buttons = Row(
            Button("Recent Changes")
            .on_click(lambda _: self._set_mode("recent"))
            .bg_color(
                theme.colors.bg_selected if mode == "recent" else theme.colors.bg_secondary
            )
            .fixed_height(32),
            Spacer().fixed_width(8),
            Button("By Score")
            .on_click(lambda _: self._set_mode("by_score"))
            .bg_color(
                theme.colors.bg_selected if mode == "by_score" else theme.colors.bg_secondary
            )
            .fixed_height(32),
            Spacer().fixed_width(8),
            Button("By Rank")
            .on_click(lambda _: self._set_mode("by_rank"))
            .bg_color(
                theme.colors.bg_selected if mode == "by_rank" else theme.colors.bg_secondary
            )
            .fixed_height(32),
            Spacer(),
        ).fixed_height(40)

        # Content based on mode
        if mode == "recent":
            content = RecentChangesView(self._catalog_state, limit=20)
        elif mode == "by_score":
            content = self._build_by_score_view()
        else:  # by_rank
            content = self._build_by_rank_view()

        return Column(
            mode_buttons,
            Spacer().fixed_height(16),
            content,
        )

    def _set_mode(self, mode: str):
        self._view_mode.set(mode)
        self._selected_definition.set("")

    def _build_by_score_view(self):
        """Build view for score history by definition."""
        theme = ThemeManager().current
        score_defs = self._catalog_state.get_score_definitions()

        if not score_defs:
            return Text("No score definitions found", font_size=14).text_color(
                theme.colors.fg
            )

        selected = self._selected_definition()
        score_ids = [s["id"] for s in score_defs]

        # Auto-select first if not selected
        if not selected or selected not in score_ids:
            selected = score_ids[0]

        # Definition selector buttons
        def_buttons = []
        for s in score_defs:
            sid = s["id"]
            name = s["name"]
            is_selected = sid == selected
            def_buttons.append(
                Button(name)
                .on_click(lambda _, sid=sid: self._selected_definition.set(sid))
                .bg_color(
                    theme.colors.bg_selected if is_selected else theme.colors.bg_tertiary
                )
                .fixed_height(28)
            )
            def_buttons.append(Spacer().fixed_width(8))

        selector_row = Row(*def_buttons, Spacer()).fixed_height(36)

        # Chart view
        chart = DefinitionHistoryChartView(
            self._catalog_state,
            definition_type="score",
            definition_id=selected,
            days=90,
            height=400,
        )

        return Column(
            Text("Select Score Definition:", font_size=14).fixed_height(24),
            selector_row,
            Spacer().fixed_height(16),
            chart,
            Spacer(),
        )

    def _build_by_rank_view(self):
        """Build view for rank history by definition."""
        theme = ThemeManager().current
        rank_defs = self._catalog_state.get_rank_definitions()

        if not rank_defs:
            return Text("No rank definitions found", font_size=14).text_color(
                theme.colors.fg
            )

        selected = self._selected_definition()
        rank_ids = [r["id"] for r in rank_defs]

        # Auto-select first if not selected
        if not selected or selected not in rank_ids:
            selected = rank_ids[0]

        # Definition selector buttons
        def_buttons = []
        for r in rank_defs:
            rid = r["id"]
            name = r["name"]
            is_selected = rid == selected
            def_buttons.append(
                Button(name)
                .on_click(lambda _, rid=rid: self._selected_definition.set(rid))
                .bg_color(
                    theme.colors.bg_selected if is_selected else theme.colors.bg_tertiary
                )
                .fixed_height(28)
            )
            def_buttons.append(Spacer().fixed_width(8))

        selector_row = Row(*def_buttons, Spacer()).fixed_height(36)

        # Chart view
        chart = DefinitionHistoryChartView(
            self._catalog_state,
            definition_type="rank",
            definition_id=selected,
            days=90,
            height=400,
        )

        return Column(
            Text("Select Rank Definition:", font_size=14).fixed_height(24),
            selector_row,
            Spacer().fixed_height(16),
            chart,
            Spacer(),
        )
