"""Dependency graph visualization with GraphCanvas."""

from castella import (
    Button,
    CheckBox,
    Column,
    Component,
    Row,
    Spacer,
    State,
    Text,
)
from castella.core import Painter, Style, FillStyle, StrokeStyle
from castella.graph import (
    GraphCanvas,
    GraphModel,
    NodeModel,
    EdgeModel,
    NodeType,
    EdgeType,
    LayoutConfig,
)
from castella.graph.transform import CanvasTransform
from castella.models.geometry import Point, Size, Rect
from castella.models.font import Font
from ..i18n import t
from ..state.catalog_state import CatalogState


# All available relation types
ALL_RELATION_TYPES = [
    "dependsOn",
    "providesApi",
    "consumesApi",
    "ownedBy",
    "partOf",
    "partOfDomain",
    "memberOf",
    "childOf",
    "parentOf",
    "hasMember",
    "subdomainOf",
    "subcomponentOf",
]

# Default relation types (technical dependencies)
DEFAULT_RELATION_TYPES = {"dependsOn", "providesApi", "consumesApi"}

# All available entity kinds
ALL_KINDS = ["Component", "API", "Resource", "System", "Domain", "User", "Group"]


# Glow effect configuration for selected nodes
GLOW_LAYERS = [
    (12, 0.15),  # (expand_px, alpha)
    (8, 0.25),
    (4, 0.40),
]


class HighlightGraphCanvas(GraphCanvas):
    """GraphCanvas with enhanced selection highlighting.

    Overrides _draw_node to provide glow effect, fill color,
    and thicker border for selected nodes.
    """

    def _draw_node(self, p: Painter, node: NodeModel) -> None:
        """Draw a node with enhanced selection highlighting."""
        theme = self._theme
        scale = self._transform.scale

        is_hovered = self._hovered_node_id == node.id
        is_selected = self._selected_node_id == node.id

        node_color = theme.get_node_color(node.node_type)

        pos = Point(x=node.position.x * scale, y=node.position.y * scale)
        node_size = Size(width=node.size.width * scale, height=node.size.height * scale)
        node_rect = Rect(origin=pos, size=node_size)

        # Glow effect for selected node (uses lightened node color)
        if is_selected:
            glow_base_color = theme.lighten_color(node_color, 0.5)
            for expand, alpha in GLOW_LAYERS:
                glow_color = self._color_with_alpha(glow_base_color, alpha)
                glow_rect = Rect(
                    origin=Point(
                        x=pos.x - expand * scale,
                        y=pos.y - expand * scale
                    ),
                    size=Size(
                        width=node_size.width + expand * 2 * scale,
                        height=node_size.height + expand * 2 * scale
                    )
                )
                p.style(Style(
                    fill=FillStyle(color=glow_color),
                    border_radius=(theme.node_border_radius + expand) * scale,
                ))
                p.fill_rect(glow_rect)

        # Shadow (only for non-selected nodes)
        if not is_selected:
            shadow_offset = theme.node_shadow_offset * scale
            p.style(Style(
                fill=FillStyle(color=theme.node_shadow_color),
                border_radius=theme.node_border_radius * scale,
            ))
            p.fill_rect(Rect(
                origin=Point(x=pos.x + shadow_offset, y=pos.y + shadow_offset),
                size=node_size,
            ))

        # Background fill
        if is_selected:
            fill_color = self._color_with_alpha(node_color, 0.20)
        else:
            fill_color = theme.background_color

        p.style(Style(
            fill=FillStyle(color=fill_color),
            border_radius=theme.node_border_radius * scale,
        ))
        p.fill_rect(node_rect)

        # Border
        if is_selected:
            border_color = theme.lighten_color(node_color, 0.5)
            stroke_width = theme.node_border_width * 3 * scale
        elif is_hovered:
            border_color = theme.lighten_color(node_color, theme.hover_lighten_amount)
            stroke_width = theme.node_border_width * scale
        else:
            border_color = node_color
            stroke_width = theme.node_border_width * scale

        p.style(Style(
            stroke=StrokeStyle(color=border_color, width=stroke_width),
            border_radius=theme.node_border_radius * scale,
        ))
        p.stroke_rect(node_rect)

        # Label
        font_size = max(10, int(theme.font_size * scale))
        label_color = "#ffffff" if is_selected else node_color
        p.style(Style(
            fill=FillStyle(color=label_color),
            font=Font(size=font_size),
        ))

        # Truncate label if needed
        text_width = p.measure_text(node.label)
        max_text_width = node_size.width - 16 * scale
        display_text = node.label
        if text_width > max_text_width:
            while text_width > max_text_width and len(display_text) > 3:
                display_text = display_text[:-4] + "..."
                text_width = p.measure_text(display_text)

        text_x = pos.x + (node_size.width - p.measure_text(display_text)) / 2
        text_y = pos.y + node_size.height / 2 + font_size / 3
        p.fill_text(display_text, Point(x=text_x, y=text_y), None)

    @staticmethod
    def _color_with_alpha(hex_color: str, alpha: float) -> str:
        """Add alpha value to hex color.

        Args:
            hex_color: Hex color string (e.g., "#00ffff").
            alpha: Alpha value (0.0 to 1.0).

        Returns:
            Hex color with alpha (e.g., "#00ffff40").
        """
        hex_color = hex_color.lstrip("#")
        alpha_hex = format(int(alpha * 255), "02x")
        return f"#{hex_color}{alpha_hex}"


# Map EntityKind to NodeType for color coding
KIND_TO_NODE_TYPE = {
    "Component": NodeType.PROCESS,    # Blue
    "API": NodeType.TOOL,             # Amber
    "Resource": NodeType.DEFAULT,     # Gray
    "System": NodeType.AGENT,         # Blue
    "Domain": NodeType.DECISION,      # Purple
    "User": NodeType.DEFAULT,         # Gray
    "Group": NodeType.DEFAULT,        # Gray
}

# Map relation type to EdgeType
RELATION_TO_EDGE_TYPE = {
    "dependsOn": EdgeType.NORMAL,
    "providesApi": EdgeType.NORMAL,
    "consumesApi": EdgeType.NORMAL,
}


class ZoomDisplay(Component):
    """Small component for zoom percentage display.

    Isolated to avoid full graph re-render on zoom changes.
    """

    def __init__(self, zoom_state: State):
        super().__init__()
        self._zoom_state = zoom_state
        self._zoom_state.attach(self)

    def view(self):
        return Text(t("graph.zoom", percent=self._zoom_state()), font_size=12).fixed_width(50)


class DependencyGraphView(Component):
    """Visualize entity dependencies with GraphCanvas."""

    def __init__(
        self,
        catalog_state: CatalogState,
        selected_id: str,
        on_node_click,
        transform: CanvasTransform,
        selected_relations: set[str],
        selected_kinds: set[str],
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._selected_id = selected_id
        self._on_node_click = on_node_click
        self._canvas: GraphCanvas | None = None
        self._transform = transform

        # Zoom state - attached to ZoomDisplay component only, not self
        self._zoom_state = State(transform.zoom_percent)
        self._zoom_display = ZoomDisplay(self._zoom_state)

        # Filter states (shared with parent to persist across re-renders)
        self._selected_relations = selected_relations
        self._selected_kinds = selected_kinds
        self._filter_trigger = State(0)
        self._filter_trigger.attach(self)

    def view(self):
        # Get dependency graph data with filters
        relation_types = list(self._selected_relations) if self._selected_relations else None
        kind_filter = list(self._selected_kinds) if self._selected_kinds else None
        graph_data = self._catalog_state.get_dependency_graph(
            relation_types=relation_types,
            kind_filter=kind_filter,
        )
        nodes_data = graph_data["nodes"]
        edges_data = graph_data["edges"]

        # Detect cycles
        cycles = self._catalog_state.detect_cycles()

        # Build a mapping from short names to full IDs
        # Some edge targets use short names like "gateway-api" instead of "API:default/gateway-api"
        name_to_full_id = {}
        for node in nodes_data:
            full_id = node["id"]
            name = node["name"]
            name_to_full_id[name] = full_id
            name_to_full_id[full_id] = full_id  # Also map full ID to itself

        # Find connected node IDs (using full IDs)
        connected_node_ids = set()
        for edge in edges_data:
            source = edge["source"]
            target = edge["target"]
            # Resolve to full IDs
            connected_node_ids.add(name_to_full_id.get(source, source))
            connected_node_ids.add(name_to_full_id.get(target, target))

        # Build GraphModel for visualization
        graph_model = self._build_graph_model(
            nodes_data, edges_data, cycles, connected_node_ids, name_to_full_id
        )

        # Layout configuration - left to right
        layout_config = LayoutConfig(
            direction="LR",
            layer_spacing=280,
            node_spacing=120,
            crossing_reduction_passes=8,
        )

        # Recreate canvas when filters change
        canvas = HighlightGraphCanvas(
            graph_model, layout_config=layout_config, transform=self._transform
        )
        canvas.on_node_click(self._handle_node_click)
        canvas.on_zoom_change(self._handle_zoom_change)
        self._canvas = canvas

        # Set selected node if it exists in the graph
        if self._selected_id and self._selected_id in connected_node_ids:
            canvas.selected_node_id = self._selected_id

        # Build inline filter checkboxes
        filter_panel = self._build_filter_panel()

        return Column(
            # Compact header row with zoom controls
            Row(
                Text(t("graph.title"), font_size=18),
                Spacer().fixed_width(16),
                Text(t("graph.stats", nodes=len(nodes_data), edges=len(edges_data)), font_size=12),
                Spacer(),
                self._build_cycle_badge(cycles),
                Spacer().fixed_width(16),
                # Zoom controls
                Button(t("common.minus")).on_click(self._on_zoom_out).fixed_width(32),
                self._zoom_display,
                Button(t("common.plus")).on_click(self._on_zoom_in).fixed_width(32),
                Spacer().fixed_width(8),
                Button(t("common.fit")).on_click(self._on_fit).fixed_width(40),
            ).fixed_height(36),
            # Filter panel with checkboxes
            filter_panel,
            # Graph canvas - takes remaining space
            canvas,
        )

    def _build_filter_panel(self):
        """Build inline filter checkboxes panel."""
        # Relation type checkboxes (split into 2 rows)
        relation_row1 = []
        relation_row2 = []
        for i, rel in enumerate(ALL_RELATION_TYPES):
            is_checked = rel in self._selected_relations
            checkbox = Row(
                CheckBox(is_checked)
                .on_click(lambda _, r=rel: self._toggle_relation(r))
                .fixed_width(16)
                .fixed_height(16),
                Spacer().fixed_width(4),
                Text(t(f"graph.relation.{rel}"), font_size=11).erase_border().fit_content_width(),
            ).fit_content_width().fixed_height(20)
            relation_row1.append(checkbox) if i < 6 else relation_row2.append(checkbox)
            # Add spacing between items
            spacer = Spacer().fixed_width(16)
            relation_row1.append(spacer) if i < 6 else relation_row2.append(spacer)

        # Kind checkboxes (single row)
        kind_items = []
        for kind in ALL_KINDS:
            is_checked = kind in self._selected_kinds
            kind_items.append(
                Row(
                    CheckBox(is_checked)
                    .on_click(lambda _, k=kind: self._toggle_kind(k))
                    .fixed_width(16)
                    .fixed_height(16),
                    Spacer().fixed_width(4),
                    Text(t(f"entity.kind.{kind.lower()}"), font_size=11).erase_border().fit_content_width(),
                ).fit_content_width().fixed_height(20)
            )
            kind_items.append(Spacer().fixed_width(16))

        return Column(
            # Relations filter
            Row(
                Text(t("graph.filter.relations") + ":", font_size=11).erase_border().fixed_width(80).fixed_height(20),
                *relation_row1,
                Spacer(),
            ).fixed_height(22),
            Row(
                Spacer().fixed_width(80),
                *relation_row2,
                Spacer(),
            ).fixed_height(22),
            # Kinds filter
            Row(
                Text(t("graph.filter.kinds") + ":", font_size=11).erase_border().fixed_width(80).fixed_height(20),
                *kind_items,
                Spacer(),
            ).fixed_height(22),
        ).fixed_height(70)

    def _toggle_relation(self, relation: str):
        """Toggle a relation type in the filter."""
        if relation in self._selected_relations:
            self._selected_relations.discard(relation)
        else:
            self._selected_relations.add(relation)
        self._filter_trigger.set(self._filter_trigger() + 1)

    def _toggle_kind(self, kind: str):
        """Toggle a kind in the filter."""
        if kind in self._selected_kinds:
            self._selected_kinds.discard(kind)
        else:
            self._selected_kinds.add(kind)
        self._filter_trigger.set(self._filter_trigger() + 1)

    def _build_graph_model(
        self,
        nodes_data: list,
        edges_data: list,
        cycles: list,
        connected_node_ids: set,
        name_to_full_id: dict,
    ) -> GraphModel:
        """Convert catalog data to GraphModel."""
        # Create set of edges involved in cycles (using full IDs)
        cycle_edges = set()
        for cycle in cycles:
            for i in range(len(cycle) - 1):
                src = name_to_full_id.get(cycle[i], cycle[i])
                tgt = name_to_full_id.get(cycle[i + 1], cycle[i + 1])
                cycle_edges.add((src, tgt))

        # Build nodes - only include connected nodes
        nodes = []
        for node in nodes_data:
            entity_id = node["id"]
            if entity_id not in connected_node_ids:
                continue  # Skip disconnected nodes

            label = node["name"]
            kind = node["kind"]

            node_type = KIND_TO_NODE_TYPE.get(kind, NodeType.DEFAULT)

            nodes.append(
                NodeModel(
                    id=entity_id,
                    label=label,
                    node_type=node_type,
                    metadata={"kind": kind},
                )
            )

        # Build edges (using full IDs)
        edges = []
        for i, edge in enumerate(edges_data):
            source_id = name_to_full_id.get(edge["source"], edge["source"])
            target_id = name_to_full_id.get(edge["target"], edge["target"])
            rel_type = edge["type"]

            # Skip edges where source or target is not in connected nodes
            if source_id not in connected_node_ids or target_id not in connected_node_ids:
                continue

            # Check if edge is in a cycle
            is_cycle_edge = (source_id, target_id) in cycle_edges

            if is_cycle_edge:
                edge_type = EdgeType.BACK  # Amber warning color
            else:
                edge_type = RELATION_TO_EDGE_TYPE.get(rel_type, EdgeType.NORMAL)

            edges.append(
                EdgeModel(
                    id=f"e{i}",
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=edge_type,
                    label=rel_type if rel_type != "dependsOn" else None,
                )
            )

        return GraphModel(
            name="Dependencies",
            nodes=nodes,
            edges=edges,
            direction="LR",
        )

    def _build_cycle_badge(self, cycles: list):
        """Build a compact cycle indicator badge."""
        if not cycles:
            return Text(t("graph.no_cycles"), font_size=12).text_color("#4a9f4a")
        else:
            return Text(t("graph.cycles_found", count=len(cycles)), font_size=12).text_color("#ff6b6b")

    def _handle_node_click(self, node_id: str):
        """Handle node click from GraphCanvas."""
        # Center on the clicked node while canvas has valid size
        if self._canvas:
            self._canvas.center_on_node(node_id)
        self._on_node_click(node_id)

    def _handle_zoom_change(self, zoom_percent: int):
        """Handle zoom level change from GraphCanvas.

        Updates ZoomDisplay component only, not the full DependencyGraphView.
        """
        self._zoom_state.set(zoom_percent)

    def _on_zoom_in(self, _):
        """Handle zoom in button click."""
        if self._canvas:
            self._canvas.zoom_in()

    def _on_zoom_out(self, _):
        """Handle zoom out button click."""
        if self._canvas:
            self._canvas.zoom_out()

    def _on_fit(self, _):
        """Handle fit to content button click."""
        if self._canvas:
            self._canvas.fit_to_content()
