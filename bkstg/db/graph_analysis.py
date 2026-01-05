"""Analyze entity dependencies using DuckDB."""

from typing import Any

import duckdb


class DependencyAnalyzer:
    """Analyze entity dependencies using DuckDB."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    def get_dependencies(
        self, entity_id: str, relation_type: str = "dependsOn"
    ) -> list[str]:
        """Get direct dependencies of an entity."""
        result = self.conn.execute(
            """
            SELECT target_id FROM relations
            WHERE source_id = ? AND relation_type = ?
            """,
            [entity_id, relation_type],
        ).fetchall()
        return [row[0] for row in result]

    def get_dependents(
        self, entity_id: str, relation_type: str = "dependsOn"
    ) -> list[str]:
        """Get entities that depend on this entity."""
        result = self.conn.execute(
            """
            SELECT source_id FROM relations
            WHERE target_id = ? AND relation_type = ?
            """,
            [entity_id, relation_type],
        ).fetchall()
        return [row[0] for row in result]

    def find_all_dependencies(
        self,
        entity_id: str,
        relation_type: str = "dependsOn",
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        """Find transitive dependencies using recursive CTE."""
        result = self.conn.execute(
            """
            WITH RECURSIVE deps AS (
                SELECT target_id, 1 as depth
                FROM relations
                WHERE source_id = ? AND relation_type = ?

                UNION

                SELECT r.target_id, d.depth + 1
                FROM relations r
                JOIN deps d ON r.source_id = d.target_id
                WHERE r.relation_type = ? AND d.depth < ?
            )
            SELECT DISTINCT target_id, MIN(depth) as depth
            FROM deps
            GROUP BY target_id
            ORDER BY depth, target_id
            """,
            [entity_id, relation_type, relation_type, max_depth],
        ).fetchall()
        return [{"entity_id": row[0], "depth": row[1]} for row in result]

    def find_all_dependents(
        self,
        entity_id: str,
        relation_type: str = "dependsOn",
        max_depth: int = 10,
    ) -> list[dict[str, Any]]:
        """Find all entities that transitively depend on this entity."""
        result = self.conn.execute(
            """
            WITH RECURSIVE deps AS (
                SELECT source_id, 1 as depth
                FROM relations
                WHERE target_id = ? AND relation_type = ?

                UNION

                SELECT r.source_id, d.depth + 1
                FROM relations r
                JOIN deps d ON r.target_id = d.source_id
                WHERE r.relation_type = ? AND d.depth < ?
            )
            SELECT DISTINCT source_id, MIN(depth) as depth
            FROM deps
            GROUP BY source_id
            ORDER BY depth, source_id
            """,
            [entity_id, relation_type, relation_type, max_depth],
        ).fetchall()
        return [{"entity_id": row[0], "depth": row[1]} for row in result]

    def detect_cycles(self, relation_type: str = "dependsOn") -> list[list[str]]:
        """Detect dependency cycles in the graph."""
        result = self.conn.execute(
            """
            WITH RECURSIVE path AS (
                SELECT
                    source_id,
                    target_id,
                    [source_id, target_id] as nodes,
                    source_id = target_id as is_cycle
                FROM relations
                WHERE relation_type = ?

                UNION ALL

                SELECT
                    p.source_id,
                    r.target_id,
                    list_append(p.nodes, r.target_id),
                    p.source_id = r.target_id
                FROM path p
                JOIN relations r ON p.target_id = r.source_id
                WHERE r.relation_type = ?
                  AND NOT list_contains(p.nodes[:-1], r.target_id)
                  AND len(p.nodes) < 20
                  AND NOT p.is_cycle
            )
            SELECT DISTINCT nodes
            FROM path
            WHERE is_cycle
            ORDER BY len(nodes)
            """,
            [relation_type, relation_type],
        ).fetchall()
        return [list(row[0]) for row in result]

    def get_dependency_graph(
        self, relation_types: list[str] | None = None
    ) -> dict[str, Any]:
        """Get the full dependency graph for visualization."""
        if relation_types is None:
            relation_types = ["dependsOn", "providesApi", "consumesApi"]

        # Get all entities
        entities = self.conn.execute(
            "SELECT id, kind, name, title FROM entities"
        ).fetchall()

        nodes = [
            {
                "id": row[0],
                "kind": row[1],
                "name": row[2],
                "title": row[3],
            }
            for row in entities
        ]

        # Get relations
        placeholders = ", ".join(["?"] * len(relation_types))
        relations = self.conn.execute(
            f"""
            SELECT source_id, target_id, relation_type
            FROM relations
            WHERE relation_type IN ({placeholders})
            """,
            relation_types,
        ).fetchall()

        edges = [
            {
                "source": row[0],
                "target": row[1],
                "type": row[2],
            }
            for row in relations
        ]

        return {"nodes": nodes, "edges": edges}

    def get_impact_analysis(
        self, entity_id: str, relation_type: str = "dependsOn"
    ) -> dict[str, Any]:
        """Analyze the impact of changing an entity."""
        direct_deps = self.get_dependents(entity_id, relation_type)
        all_deps = self.find_all_dependents(entity_id, relation_type)

        return {
            "entity_id": entity_id,
            "direct_dependents": direct_deps,
            "direct_count": len(direct_deps),
            "transitive_dependents": [d["entity_id"] for d in all_deps],
            "transitive_count": len(all_deps),
            "impact_depth": max((d["depth"] for d in all_deps), default=0),
        }
