"""Group hierarchy queries for bkstg."""

from typing import Any

import duckdb


class GroupHierarchyQueries:
    """SQL queries for group hierarchy traversal and aggregation."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    def get_root_groups(self) -> list[dict[str, Any]]:
        """Get all groups with no parent (top-level groups).

        Returns:
            List of group dicts with id, name, title, description, type
        """
        result = self.conn.execute(
            """
            SELECT
                e.id,
                e.name,
                e.title,
                e.description,
                e.type
            FROM entities e
            WHERE e.kind = 'Group'
              AND NOT EXISTS (
                  SELECT 1 FROM relations r
                  WHERE r.source_id = e.id AND r.relation_type = 'childOf'
              )
            ORDER BY e.name
            """
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "title": row[2],
                "description": row[3],
                "type": row[4],
            }
            for row in result
        ]

    def get_child_groups(self, group_id: str) -> list[dict[str, Any]]:
        """Get direct child groups of a group.

        Args:
            group_id: The parent group ID (e.g., "Group:default/platform-team")

        Returns:
            List of child group dicts
        """
        result = self.conn.execute(
            """
            SELECT
                e.id,
                e.name,
                e.title,
                e.description,
                e.type
            FROM entities e
            JOIN relations r ON e.id = r.source_id
            WHERE r.target_id = ? AND r.relation_type = 'childOf'
            ORDER BY e.name
            """,
            [group_id],
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "title": row[2],
                "description": row[3],
                "type": row[4],
            }
            for row in result
        ]

    def get_all_descendants(
        self, group_id: str, max_depth: int = 10
    ) -> list[dict[str, Any]]:
        """Get all descendant groups recursively using CTE.

        Args:
            group_id: The ancestor group ID
            max_depth: Maximum recursion depth (default: 10)

        Returns:
            List of descendant group dicts with depth
        """
        result = self.conn.execute(
            """
            WITH RECURSIVE group_hierarchy AS (
                -- Base case: direct children
                SELECT r.source_id as group_id, 1 as depth
                FROM relations r
                WHERE r.target_id = ? AND r.relation_type = 'childOf'

                UNION

                -- Recursive case: children of children
                SELECT r.source_id, gh.depth + 1
                FROM relations r
                JOIN group_hierarchy gh ON r.target_id = gh.group_id
                WHERE r.relation_type = 'childOf' AND gh.depth < ?
            )
            SELECT DISTINCT
                gh.group_id,
                gh.depth,
                e.name,
                e.title,
                e.description,
                e.type
            FROM group_hierarchy gh
            JOIN entities e ON e.id = gh.group_id
            ORDER BY gh.depth, e.name
            """,
            [group_id, max_depth],
        ).fetchall()
        return [
            {
                "id": row[0],
                "depth": row[1],
                "name": row[2],
                "title": row[3],
                "description": row[4],
                "type": row[5],
            }
            for row in result
        ]

    def get_group_and_descendants(
        self, group_id: str, max_depth: int = 10
    ) -> list[str]:
        """Get a group and all its descendant group IDs.

        Args:
            group_id: The group ID
            max_depth: Maximum recursion depth

        Returns:
            List of group IDs (including the original group)
        """
        descendants = self.get_all_descendants(group_id, max_depth)
        return [group_id] + [d["id"] for d in descendants]

    def get_owned_entities(
        self, group_id: str, include_descendants: bool = True, max_depth: int = 10
    ) -> list[dict[str, Any]]:
        """Get all entities owned by a group (and optionally its descendants).

        Args:
            group_id: The group ID
            include_descendants: Whether to include entities owned by child groups
            max_depth: Maximum recursion depth for descendants

        Returns:
            List of entity dicts with id, kind, name, title, owner
        """
        if include_descendants:
            group_ids = self.get_group_and_descendants(group_id, max_depth)
        else:
            group_ids = [group_id]

        if not group_ids:
            return []

        # Use relations table (ownedBy) which has normalized references
        placeholders = ", ".join(["?"] * len(group_ids))
        result = self.conn.execute(
            f"""
            SELECT
                e.id,
                e.kind,
                e.name,
                e.title,
                e.description,
                e.owner,
                e.type,
                e.lifecycle
            FROM entities e
            JOIN relations r ON r.source_id = e.id
            WHERE r.target_id IN ({placeholders})
              AND r.relation_type = 'ownedBy'
              AND e.kind != 'Group'
            ORDER BY e.kind, e.name
            """,
            group_ids,
        ).fetchall()
        return [
            {
                "id": row[0],
                "kind": row[1],
                "name": row[2],
                "title": row[3],
                "description": row[4],
                "owner": row[5],
                "type": row[6],
                "lifecycle": row[7],
            }
            for row in result
        ]

    def get_group_entity_count(
        self, group_id: str, include_descendants: bool = True, max_depth: int = 10
    ) -> dict[str, int]:
        """Get entity count by kind for a group.

        Args:
            group_id: The group ID
            include_descendants: Whether to include child groups
            max_depth: Maximum recursion depth

        Returns:
            Dict mapping kind to count
        """
        if include_descendants:
            group_ids = self.get_group_and_descendants(group_id, max_depth)
        else:
            group_ids = [group_id]

        if not group_ids:
            return {}

        # Use relations table (ownedBy) which has normalized references
        placeholders = ", ".join(["?"] * len(group_ids))
        result = self.conn.execute(
            f"""
            SELECT e.kind, COUNT(*) as count
            FROM entities e
            JOIN relations r ON r.source_id = e.id
            WHERE r.target_id IN ({placeholders})
              AND r.relation_type = 'ownedBy'
              AND e.kind != 'Group'
            GROUP BY e.kind
            ORDER BY e.kind
            """,
            group_ids,
        ).fetchall()
        return {row[0]: row[1] for row in result}

    def get_group_score_aggregation(
        self, group_id: str, include_descendants: bool = True, max_depth: int = 10
    ) -> list[dict[str, Any]]:
        """Aggregate scores for entities owned by a group.

        Args:
            group_id: The group ID
            include_descendants: Whether to include child groups
            max_depth: Maximum recursion depth

        Returns:
            List of score aggregation dicts with score_id, name, avg, min, max, count
        """
        if include_descendants:
            group_ids = self.get_group_and_descendants(group_id, max_depth)
        else:
            group_ids = [group_id]

        if not group_ids:
            return []

        # Use relations table (ownedBy) which has normalized references
        placeholders = ", ".join(["?"] * len(group_ids))
        result = self.conn.execute(
            f"""
            SELECT
                sd.id as score_id,
                sd.name,
                AVG(es.value) as avg_value,
                MIN(es.value) as min_value,
                MAX(es.value) as max_value,
                COUNT(*) as entity_count
            FROM entity_scores es
            JOIN entities e ON e.id = es.entity_id
            JOIN relations r ON r.source_id = e.id
            JOIN score_definitions sd ON sd.id = es.score_id
            WHERE r.target_id IN ({placeholders})
              AND r.relation_type = 'ownedBy'
            GROUP BY sd.id, sd.name
            ORDER BY sd.name
            """,
            group_ids,
        ).fetchall()
        return [
            {
                "score_id": row[0],
                "name": row[1],
                "avg": row[2],
                "min": row[3],
                "max": row[4],
                "count": row[5],
            }
            for row in result
        ]

    def get_group_rank_distribution(
        self,
        group_id: str,
        rank_id: str,
        include_descendants: bool = True,
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        """Get rank label distribution for entities owned by a group.

        Args:
            group_id: The group ID
            rank_id: The rank definition ID
            include_descendants: Whether to include child groups
            max_depth: Maximum recursion depth

        Returns:
            List of dicts with label and count
        """
        if include_descendants:
            group_ids = self.get_group_and_descendants(group_id, max_depth)
        else:
            group_ids = [group_id]

        if not group_ids:
            return []

        # Use relations table (ownedBy) which has normalized references
        placeholders = ", ".join(["?"] * len(group_ids))
        result = self.conn.execute(
            f"""
            SELECT
                er.label,
                COUNT(*) as count
            FROM entity_ranks er
            JOIN entities e ON e.id = er.entity_id
            JOIN relations r ON r.source_id = e.id
            WHERE r.target_id IN ({placeholders})
              AND r.relation_type = 'ownedBy'
              AND er.rank_id = ?
            GROUP BY er.label
            ORDER BY
                CASE er.label
                    WHEN 'S' THEN 1
                    WHEN 'A' THEN 2
                    WHEN 'B' THEN 3
                    WHEN 'C' THEN 4
                    WHEN 'D' THEN 5
                    WHEN 'E' THEN 6
                    WHEN 'F' THEN 7
                    ELSE 8
                END
            """,
            group_ids + [rank_id],
        ).fetchall()
        return [{"label": row[0], "count": row[1]} for row in result]

    def get_group_average_rank(
        self,
        group_id: str,
        rank_id: str,
        include_descendants: bool = True,
        max_depth: int = 10,
    ) -> dict[str, Any] | None:
        """Get average rank value for entities owned by a group.

        Args:
            group_id: The group ID
            rank_id: The rank definition ID
            include_descendants: Whether to include child groups
            max_depth: Maximum recursion depth

        Returns:
            Dict with avg_value, entity_count, or None if no data
        """
        if include_descendants:
            group_ids = self.get_group_and_descendants(group_id, max_depth)
        else:
            group_ids = [group_id]

        if not group_ids:
            return None

        # Use relations table (ownedBy) which has normalized references
        placeholders = ", ".join(["?"] * len(group_ids))
        result = self.conn.execute(
            f"""
            SELECT
                AVG(er.value) as avg_value,
                COUNT(*) as entity_count
            FROM entity_ranks er
            JOIN entities e ON e.id = er.entity_id
            JOIN relations r ON r.source_id = e.id
            WHERE r.target_id IN ({placeholders})
              AND r.relation_type = 'ownedBy'
              AND er.rank_id = ?
            """,
            group_ids + [rank_id],
        ).fetchone()

        if result and result[1] > 0:
            return {"avg_value": result[0], "entity_count": result[1]}
        return None

    def get_groups_comparison(
        self,
        group_ids: list[str],
        include_descendants: bool = True,
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        """Compare multiple groups by their score/rank aggregations.

        Args:
            group_ids: List of group IDs to compare
            include_descendants: Whether to include child groups
            max_depth: Maximum recursion depth

        Returns:
            List of group comparison dicts
        """
        comparisons = []
        for group_id in group_ids:
            # Get group info
            group_info = self.conn.execute(
                "SELECT id, name, title FROM entities WHERE id = ?", [group_id]
            ).fetchone()
            if not group_info:
                continue

            # Get entity count
            entity_counts = self.get_group_entity_count(
                group_id, include_descendants, max_depth
            )
            total_entities = sum(entity_counts.values())

            # Get score aggregations
            score_aggs = self.get_group_score_aggregation(
                group_id, include_descendants, max_depth
            )

            comparisons.append(
                {
                    "id": group_info[0],
                    "name": group_info[1],
                    "title": group_info[2],
                    "entity_count": total_entities,
                    "entity_counts_by_kind": entity_counts,
                    "score_aggregations": score_aggs,
                }
            )

        return comparisons

    def get_group_hierarchy_tree(
        self, root_group_id: str | None = None, max_depth: int = 10
    ) -> list[dict[str, Any]]:
        """Build a hierarchical tree structure of groups.

        Args:
            root_group_id: Starting group ID, or None for all root groups
            max_depth: Maximum tree depth

        Returns:
            List of group tree nodes with children
        """
        if root_group_id:
            # Get specific group and its children
            groups = [self._get_group_info(root_group_id)]
            if groups[0] is None:
                return []
            groups[0]["children"] = self._get_children_recursive(
                root_group_id, 1, max_depth
            )
            return groups
        else:
            # Get all root groups
            root_groups = self.get_root_groups()
            for group in root_groups:
                group["children"] = self._get_children_recursive(
                    group["id"], 1, max_depth
                )
            return root_groups

    def _get_group_info(self, group_id: str) -> dict[str, Any] | None:
        """Get basic info for a single group."""
        result = self.conn.execute(
            """
            SELECT id, name, title, description, type
            FROM entities WHERE id = ? AND kind = 'Group'
            """,
            [group_id],
        ).fetchone()
        if result:
            return {
                "id": result[0],
                "name": result[1],
                "title": result[2],
                "description": result[3],
                "type": result[4],
            }
        return None

    def _get_children_recursive(
        self, group_id: str, depth: int, max_depth: int
    ) -> list[dict[str, Any]]:
        """Recursively get children of a group."""
        if depth >= max_depth:
            return []

        children = self.get_child_groups(group_id)
        for child in children:
            child["children"] = self._get_children_recursive(
                child["id"], depth + 1, max_depth
            )
        return children
