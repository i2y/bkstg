"""Dependency graph visualization with GraphCanvas."""

from castella import (
    Button,
    Column,
    Component,
    Row,
    Spacer,
    State,
    Text,
)
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

from ..state.catalog_state import CatalogState


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


class DependencyGraphView(Component):
    """Visualize entity dependencies with GraphCanvas."""

    def __init__(
        self,
        catalog_state: CatalogState,
        selected_id: str,
        on_node_click,
        transform: CanvasTransform,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._selected_id = selected_id
        self._on_node_click = on_node_click
        self._canvas: GraphCanvas | None = None
        self._transform = transform
        self._zoom_percent = State(transform.zoom_percent)
        self._zoom_percent.attach(self)

    def view(self):
        # Get dependency graph data
        graph_data = self._catalog_state.get_dependency_graph()
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

        # Reuse existing canvas or create new one
        if self._canvas is None:
            canvas = GraphCanvas(
                graph_model, layout_config=layout_config, transform=self._transform
            )
            canvas.on_node_click(self._handle_node_click)
            canvas.on_zoom_change(self._handle_zoom_change)
            self._canvas = canvas
        else:
            canvas = self._canvas

        # Set selected node if it exists in the graph
        if self._selected_id and self._selected_id in connected_node_ids:
            canvas.selected_node_id = self._selected_id

        return Column(
            # Compact header row with zoom controls
            Row(
                Text("Dependency Graph", font_size=18),
                Spacer().fixed_width(16),
                Text(f"{len(nodes_data)} nodes, {len(edges_data)} edges", font_size=12),
                Spacer(),
                self._build_cycle_badge(cycles),
                Spacer().fixed_width(16),
                # Zoom controls
                Button("-").on_click(self._on_zoom_out).fixed_width(32),
                Text(f"{self._zoom_percent()}%", font_size=12).fixed_width(50),
                Button("+").on_click(self._on_zoom_in).fixed_width(32),
                Spacer().fixed_width(8),
                Button("Fit").on_click(self._on_fit).fixed_width(40),
            ).fixed_height(36),
            # Graph canvas - takes remaining space
            canvas,
        )

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
            return Text("No cycles", font_size=12).text_color("#4a9f4a")
        else:
            return Text(f"{len(cycles)} cycle(s)!", font_size=12).text_color("#ff6b6b")

    def _handle_node_click(self, node_id: str):
        """Handle node click from GraphCanvas."""
        # Center on the clicked node while canvas has valid size
        if self._canvas:
            self._canvas.center_on_node(node_id)
        self._on_node_click(node_id)

    def _handle_zoom_change(self, zoom_percent: int):
        """Handle zoom level change from GraphCanvas."""
        self._zoom_percent.set(zoom_percent)

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
