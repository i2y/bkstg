"""Entity detail view component."""

from castella import (
    Button,
    Column,
    Component,
    MultilineText,
    Row,
    Spacer,
    Text,
    Tree,
    TreeNode,
    TreeState,
)
from castella.theme import ThemeManager

from ..models import Entity


class EntityDetail(Component):
    """Display entity details with metadata and relations."""

    def __init__(
        self,
        entity: Entity,
        relations: list,
        on_edit,
        on_navigate,
        scores: list | None = None,
        ranks: list | None = None,
    ):
        super().__init__()
        self._entity = entity
        self._relations = relations
        self._on_edit = on_edit
        self._on_navigate = on_navigate
        self._scores = scores or []
        self._ranks = ranks or []

    def view(self):
        theme = ThemeManager().current
        e = self._entity
        meta = e.metadata

        return Column(
            # Header
            Row(
                Text(
                    meta.title or meta.name, font_size=20
                ).flex(1),
                Button("Edit").on_click(lambda _: self._on_edit()).fixed_width(70),
            ).fixed_height(44),
            # Kind badge
            Row(
                Text(f"Kind: {e.kind.value}", font_size=14),
                Spacer().fixed_width(16),
                Text(f"Namespace: {meta.namespace}", font_size=14),
            ).fixed_height(28),
            # Description
            self._build_description(),
            Spacer().fixed_height(16),
            # Scores section (bkstg extension)
            self._build_scores_section(),
            # Spec details
            Text("Spec", font_size=16).fixed_height(28),
            self._build_spec_section(),
            Spacer().fixed_height(16),
            # Relations
            Text("Relations", font_size=16).fixed_height(28),
            self._build_relations_tree(),
            Spacer().fixed_height(16),
            # Tags
            self._build_tags_section(),
            Spacer(),
        ).bg_color(theme.colors.bg_secondary)

    def _build_description(self):
        desc = self._entity.metadata.description
        if not desc:
            return Spacer().fixed_height(0)

        return Column(
            Spacer().fixed_height(8),
            MultilineText(desc, font_size=14, wrap=True),
        )

    def _build_scores_section(self):
        """Build scores display section (bkstg extension)."""
        if not self._scores and not self._ranks:
            return Spacer().fixed_height(0)

        items = []

        # Scores
        if self._scores:
            items.append(Text("Scores", font_size=16).fixed_height(28))
            for score in self._scores:
                items.append(self._score_bar(score))
            items.append(Spacer().fixed_height(8))

        # Ranks
        if self._ranks:
            items.append(Text("Ranks", font_size=16).fixed_height(28))
            for rank in self._ranks:
                items.append(self._rank_row(rank))
            items.append(Spacer().fixed_height(8))

        items.append(Spacer().fixed_height(8))
        return Column(*items)

    def _score_bar(self, score: dict):
        """Build a visual score bar."""
        theme = ThemeManager().current
        name = score.get("name", score.get("score_id", ""))
        # Remove redundant "Score" suffix
        name = name.replace(" Score", "").replace("Score", "")
        value = score.get("value", 0)
        max_value = score.get("max_value", 100)
        reason = score.get("reason")

        percentage = (value / max_value) * 100 if max_value > 0 else 0
        color = self._score_color(percentage)
        bar_width = min(int(percentage * 1.5), 150)

        row_items = [
            Text(name, font_size=13).fixed_width(120),
            # Progress bar background
            Row(
                Column().bg_color(color).fixed_width(bar_width).fixed_height(12),
                Spacer(),
            ).bg_color(theme.colors.bg_tertiary).fixed_width(150).fixed_height(16),
            Spacer().fixed_width(8),
            Text(f"{value:.0f}", font_size=13).fixed_width(40),
        ]

        if reason:
            row_items.append(Text(f"({reason})", font_size=11).text_color(theme.colors.fg))

        return Row(*row_items).fixed_height(26)

    def _rank_row(self, rank: dict):
        """Build a rank display row."""
        theme = ThemeManager().current
        name = rank.get("name", rank.get("rank_id", ""))
        # Remove redundant "Rank" suffix
        name = name.replace(" Rank", "").replace("Rank", "")
        value = rank.get("value", 0)
        label = rank.get("label")

        row_items = [
            Text(name, font_size=13).fixed_width(120),
        ]

        if label:
            # Show label prominently with color
            label_color = self._label_color(label)
            row_items.append(
                Text(label, font_size=16).text_color(label_color).fixed_width(40)
            )
            row_items.append(
                Text(f"({value:.1f})", font_size=12).text_color(theme.colors.fg)
            )
        else:
            row_items.append(Text(f"{value:.1f}", font_size=14))

        return Row(*row_items).fixed_height(26)

    def _label_color(self, label: str) -> str:
        """Get color for rank label."""
        theme = ThemeManager().current
        label_upper = label.upper()
        if label_upper in ("S", "SS", "SSS"):
            return theme.colors.text_warning  # Gold
        elif label_upper == "A":
            return theme.colors.text_success  # Green
        elif label_upper == "B":
            return theme.colors.text_info  # Blue
        elif label_upper == "C":
            return theme.colors.text_warning  # Yellow
        elif label_upper == "D":
            return "#ff9e64"  # Orange (Tokyo Night)
        elif label_upper in ("E", "F"):
            return theme.colors.text_danger  # Red
        else:
            return theme.colors.fg  # Gray

    def _score_color(self, percentage: float) -> str:
        """Get color based on score percentage."""
        theme = ThemeManager().current
        if percentage >= 80:
            return theme.colors.text_success  # Green
        elif percentage >= 60:
            return theme.colors.text_warning  # Yellow
        elif percentage >= 40:
            return "#ff9e64"  # Orange (Tokyo Night)
        else:
            return theme.colors.text_danger  # Red

    def _build_spec_section(self):
        spec = self._entity.spec
        items = []

        # Common spec fields - some are navigable (owner, system, domain)
        spec_fields = [
            ("type", "Type", False),
            ("lifecycle", "Lifecycle", False),
            ("owner", "Owner", True),
            ("system", "System", True),
            ("domain", "Domain", True),
        ]

        for field, label, navigable in spec_fields:
            value = getattr(spec, field, None)
            if value:
                items.append(self._spec_row(label, value, navigable))

        if not items:
            return Text("No spec fields", font_size=13).fixed_height(24)

        return Column(*items)

    def _spec_row(self, label: str, value: str, navigable: bool = False):
        if navigable:
            # Make it a clickable button-like text
            return Row(
                Text(f"{label}:", font_size=13).fixed_width(80),
                Button(str(value))
                .on_click(lambda _, v=value: self._navigate_to_ref(v))
                .flex(1),
            ).fixed_height(30)
        else:
            return Row(
                Text(f"{label}:", font_size=13).fixed_width(80),
                Text(str(value), font_size=13).flex(1),
            ).fixed_height(26)

    def _navigate_to_ref(self, ref: str):
        """Navigate to a referenced entity."""
        # Entity refs can be:
        # - "name" (same namespace/kind inferred)
        # - "kind:name" (same namespace)
        # - "kind:namespace/name" (fully qualified)
        # For simplicity, try exact match first, then search
        self._on_navigate(ref)

    def _build_relations_tree(self):
        if not self._relations:
            return Text("No relations", font_size=13).fixed_height(24)

        # Group relations by type
        by_type: dict[str, list] = {}
        for rel in self._relations:
            rel_type = rel["type"]
            if rel_type not in by_type:
                by_type[rel_type] = []
            by_type[rel_type].append(rel)

        # Build tree nodes
        nodes = []
        for rel_type, rels in by_type.items():
            children = [
                TreeNode(
                    id=f"{rel_type}-{rel['entity_id']}",
                    label=rel["entity_id"],
                    icon="",
                )
                for rel in rels
            ]

            direction = rels[0]["direction"] if rels else ""
            icon = "" if direction == "outgoing" else ""

            nodes.append(
                TreeNode(
                    id=rel_type,
                    label=f"{rel_type} ({len(rels)})",
                    icon=icon,
                    children=children,
                )
            )

        state = TreeState(nodes)
        return Tree(state).on_select(self._handle_relation_click)

    def _handle_relation_click(self, node: TreeNode):
        # Extract entity ID from node ID
        node_id = node.id
        if "-" in node_id:
            parts = node_id.split("-", 1)
            if len(parts) == 2:
                entity_id = parts[1]
                self._on_navigate(entity_id)

    def _build_tags_section(self):
        tags = self._entity.metadata.tags
        if not tags:
            return Spacer().fixed_height(0)

        return Column(
            Text("Tags", font_size=16).fixed_height(28),
            Text(", ".join(tags), font_size=13),
        )
