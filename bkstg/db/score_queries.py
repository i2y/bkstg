"""SQL queries for scorecard data."""

import json
from typing import Any

import duckdb


class ScoreQueries:
    """SQL queries for scorecard data."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    def get_score_definitions(self) -> list[dict[str, Any]]:
        """Get all score definitions."""
        result = self.conn.execute("""
            SELECT id, name, description, target_kinds, min_value, max_value
            FROM score_definitions
            ORDER BY name
        """).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "target_kinds": row[3] or [],
                "min_value": row[4],
                "max_value": row[5],
            }
            for row in result
        ]

    def get_rank_definitions(self) -> list[dict[str, Any]]:
        """Get all rank definitions."""
        result = self.conn.execute("""
            SELECT id, name, description, target_kinds, score_refs, formula,
                   rules, label_function, entity_refs, thresholds
            FROM rank_definitions
            ORDER BY name
        """).fetchall()
        ranks = []
        for row in result:
            # Parse JSON fields
            rules_data = row[6]
            if isinstance(rules_data, str):
                rules_data = json.loads(rules_data)

            thresholds_data = row[9]
            if isinstance(thresholds_data, str):
                thresholds_data = json.loads(thresholds_data)

            ranks.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "target_kinds": row[3] or [],
                "score_refs": row[4] or [],
                "formula": row[5],
                "rules": rules_data or [],
                "label_function": row[7],
                "entity_refs": row[8] or [],
                "thresholds": thresholds_data or [],
            })
        return ranks

    def get_entity_scores(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all scores for an entity."""
        result = self.conn.execute(
            """
            SELECT es.score_id, es.value, es.reason, es.updated_at,
                   sd.name, sd.min_value, sd.max_value
            FROM entity_scores es
            LEFT JOIN score_definitions sd ON es.score_id = sd.id
            WHERE es.entity_id = ?
            ORDER BY sd.name
        """,
            [entity_id],
        ).fetchall()
        return [
            {
                "score_id": row[0],
                "value": row[1],
                "reason": row[2],
                "updated_at": row[3],
                "name": row[4] or row[0],
                "min_value": row[5] or 0,
                "max_value": row[6] or 100,
            }
            for row in result
        ]

    def get_entity_ranks(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all computed ranks for an entity."""
        result = self.conn.execute(
            """
            SELECT er.rank_id, er.value, er.label, er.computed_at,
                   rd.name, rd.description
            FROM entity_ranks er
            LEFT JOIN rank_definitions rd ON er.rank_id = rd.id
            WHERE er.entity_id = ?
            ORDER BY rd.name
        """,
            [entity_id],
        ).fetchall()
        return [
            {
                "rank_id": row[0],
                "value": row[1],
                "label": row[2],
                "computed_at": row[3],
                "name": row[4] or row[0],
                "description": row[5],
            }
            for row in result
        ]

    def get_all_scores_with_entities(self) -> list[dict[str, Any]]:
        """Get all scores with entity information."""
        result = self.conn.execute("""
            SELECT es.entity_id, es.score_id, es.value, es.reason, es.updated_at,
                   e.name as entity_name, e.title as entity_title, e.kind,
                   sd.name as score_name, sd.max_value
            FROM entity_scores es
            JOIN entities e ON es.entity_id = e.id
            LEFT JOIN score_definitions sd ON es.score_id = sd.id
            ORDER BY es.updated_at DESC
        """).fetchall()
        return [
            {
                "entity_id": row[0],
                "score_id": row[1],
                "value": row[2],
                "reason": row[3],
                "updated_at": row[4],
                "entity_name": row[5],
                "entity_title": row[6],
                "kind": row[7],
                "score_name": row[8] or row[1],
                "max_value": row[9] or 100,
            }
            for row in result
        ]

    def get_leaderboard(self, rank_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get top entities by rank."""
        result = self.conn.execute(
            """
            SELECT er.entity_id, er.value, er.label, e.name, e.title, e.kind
            FROM entity_ranks er
            JOIN entities e ON er.entity_id = e.id
            WHERE er.rank_id = ?
            ORDER BY er.value DESC
            LIMIT ?
        """,
            [rank_id, limit],
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "value": row[1],
                "label": row[2],
                "name": row[3],
                "title": row[4],
                "kind": row[5],
            }
            for row in result
        ]

    def get_dashboard_summary(self) -> dict[str, Any]:
        """Get aggregated scorecard data for dashboard."""
        # Total entities with scores
        scored = self.conn.execute("""
            SELECT COUNT(DISTINCT entity_id) FROM entity_scores
        """).fetchone()[0]

        # Total entities
        total = self.conn.execute("""
            SELECT COUNT(*) FROM entities
        """).fetchone()[0]

        # Average score
        avg_score = self.conn.execute("""
            SELECT AVG(value) FROM entity_scores
        """).fetchone()[0]

        # Score count by kind
        kind_counts = self.conn.execute("""
            SELECT e.kind, COUNT(DISTINCT es.entity_id)
            FROM entity_scores es
            JOIN entities e ON es.entity_id = e.id
            GROUP BY e.kind
        """).fetchall()

        # Recent score updates
        recent = self.conn.execute("""
            SELECT es.entity_id, e.name, e.title, e.kind,
                   es.score_id, sd.name as score_name, es.value, es.updated_at
            FROM entity_scores es
            JOIN entities e ON es.entity_id = e.id
            LEFT JOIN score_definitions sd ON es.score_id = sd.id
            ORDER BY es.updated_at DESC
            LIMIT 10
        """).fetchall()

        return {
            "total_entities": total,
            "scored_entities": scored,
            "avg_score": avg_score or 0,
            "kind_counts": {row[0]: row[1] for row in kind_counts},
            "recent_updates": [
                {
                    "entity_id": row[0],
                    "entity_name": row[1],
                    "entity_title": row[2],
                    "kind": row[3],
                    "score_id": row[4],
                    "score_name": row[5] or row[4],
                    "value": row[6],
                    "updated_at": row[7],
                }
                for row in recent
            ],
        }

    def upsert_score(
        self,
        entity_id: str,
        score_id: str,
        value: float,
        reason: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        """Insert or update a score for an entity."""
        self.conn.execute(
            """
            INSERT INTO entity_scores (id, entity_id, score_id, value, reason, updated_at)
            VALUES (nextval('entity_scores_id_seq'), ?, ?, ?, ?, COALESCE(?, current_timestamp))
            ON CONFLICT (entity_id, score_id) DO UPDATE SET
                value = excluded.value,
                reason = excluded.reason,
                updated_at = excluded.updated_at
        """,
            [entity_id, score_id, value, reason, updated_at],
        )

    def upsert_rank(self, entity_id: str, rank_id: str, value: float, label: str | None = None) -> None:
        """Insert or update a rank for an entity."""
        self.conn.execute(
            """
            INSERT INTO entity_ranks (id, entity_id, rank_id, value, label, computed_at)
            VALUES (nextval('entity_ranks_id_seq'), ?, ?, ?, ?, current_timestamp)
            ON CONFLICT (entity_id, rank_id) DO UPDATE SET
                value = excluded.value,
                label = excluded.label,
                computed_at = current_timestamp
        """,
            [entity_id, rank_id, value, label],
        )

    def insert_score_definition(
        self,
        id: str,
        name: str,
        description: str | None,
        target_kinds: list[str],
        min_value: float,
        max_value: float,
    ) -> None:
        """Insert a score definition."""
        self.conn.execute(
            """
            INSERT INTO score_definitions (id, name, description, target_kinds, min_value, max_value)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                target_kinds = excluded.target_kinds,
                min_value = excluded.min_value,
                max_value = excluded.max_value
        """,
            [id, name, description, target_kinds, min_value, max_value],
        )

    def insert_rank_definition(
        self,
        id: str,
        name: str,
        description: str | None,
        target_kinds: list[str],
        score_refs: list[str],
        formula: str,
    ) -> None:
        """Insert a rank definition."""
        self.conn.execute(
            """
            INSERT INTO rank_definitions (id, name, description, target_kinds, score_refs, formula)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                target_kinds = excluded.target_kinds,
                score_refs = excluded.score_refs,
                formula = excluded.formula
        """,
            [id, name, description, target_kinds, score_refs, formula],
        )

    def clear_scores(self) -> None:
        """Clear all scores and ranks."""
        self.conn.execute("DELETE FROM entity_ranks")
        self.conn.execute("DELETE FROM entity_scores")

    def clear_definitions(self) -> None:
        """Clear all score and rank definitions."""
        self.conn.execute("DELETE FROM rank_definitions")
        self.conn.execute("DELETE FROM score_definitions")

    def get_score_distribution(self) -> list[dict[str, Any]]:
        """Get score distribution by score type (for charts)."""
        result = self.conn.execute("""
            SELECT
                sd.id as score_id,
                sd.name as score_name,
                COUNT(*) as count,
                AVG(es.value) as avg_value,
                MIN(es.value) as min_value,
                MAX(es.value) as max_value
            FROM entity_scores es
            LEFT JOIN score_definitions sd ON es.score_id = sd.id
            GROUP BY sd.id, sd.name
            ORDER BY count DESC
        """).fetchall()
        return [
            {
                "score_id": row[0],
                "score_name": row[1] or row[0],
                "count": row[2],
                "avg_value": row[3] or 0,
                "min_value": row[4] or 0,
                "max_value": row[5] or 0,
            }
            for row in result
        ]

    def get_rank_label_distribution(self, rank_id: str | None = None) -> list[dict[str, Any]]:
        """Get rank label distribution (S/A/B/C/D counts) for charts."""
        if rank_id:
            result = self.conn.execute("""
                SELECT label, COUNT(*) as count
                FROM entity_ranks
                WHERE rank_id = ?
                GROUP BY label
                ORDER BY
                    CASE label
                        WHEN 'S' THEN 1
                        WHEN 'A' THEN 2
                        WHEN 'B' THEN 3
                        WHEN 'C' THEN 4
                        WHEN 'D' THEN 5
                        WHEN 'E' THEN 6
                        WHEN 'F' THEN 7
                        ELSE 8
                    END
            """, [rank_id]).fetchall()
        else:
            result = self.conn.execute("""
                SELECT label, COUNT(*) as count
                FROM entity_ranks
                GROUP BY label
                ORDER BY
                    CASE label
                        WHEN 'S' THEN 1
                        WHEN 'A' THEN 2
                        WHEN 'B' THEN 3
                        WHEN 'C' THEN 4
                        WHEN 'D' THEN 5
                        WHEN 'E' THEN 6
                        WHEN 'F' THEN 7
                        ELSE 8
                    END
            """).fetchall()
        return [
            {"label": row[0] or "Unranked", "count": row[1]}
            for row in result
        ]

    def get_score_trends(self, days: int = 30) -> list[dict[str, Any]]:
        """Get score trends over time (daily aggregates) for charts."""
        result = self.conn.execute(f"""
            SELECT
                DATE_TRUNC('day', updated_at) as date,
                COUNT(*) as update_count,
                AVG(value) as avg_value
            FROM entity_scores
            WHERE updated_at >= CURRENT_DATE - INTERVAL '{days}' DAY
            GROUP BY DATE_TRUNC('day', updated_at)
            ORDER BY date
        """).fetchall()
        return [
            {
                "date": row[0],
                "update_count": row[1],
                "avg_value": row[2] or 0,
            }
            for row in result
        ]

    # ========== Heatmap Queries ==========

    def get_kind_score_average(self) -> list[dict[str, Any]]:
        """Get average scores by Kind × Score Type for heatmap."""
        result = self.conn.execute("""
            SELECT
                e.kind,
                sd.id as score_id,
                sd.name as score_name,
                AVG(es.value) as avg_value,
                COUNT(*) as count
            FROM entity_scores es
            JOIN entities e ON es.entity_id = e.id
            LEFT JOIN score_definitions sd ON es.score_id = sd.id
            GROUP BY e.kind, sd.id, sd.name
            ORDER BY e.kind, sd.name
        """).fetchall()
        return [
            {
                "kind": row[0],
                "score_id": row[1],
                "score_name": row[2] or row[1],
                "avg_value": row[3] or 0,
                "count": row[4],
            }
            for row in result
        ]

    def get_entity_score_matrix(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get entity × score type matrix data for heatmap."""
        result = self.conn.execute(f"""
            SELECT
                es.entity_id,
                e.name as entity_name,
                COALESCE(e.title, e.name) as entity_title,
                e.kind,
                sd.id as score_id,
                sd.name as score_name,
                es.value
            FROM entity_scores es
            JOIN entities e ON es.entity_id = e.id
            LEFT JOIN score_definitions sd ON es.score_id = sd.id
            WHERE es.entity_id IN (
                SELECT DISTINCT entity_id FROM entity_scores
                ORDER BY entity_id
                LIMIT {limit}
            )
            ORDER BY e.kind, e.name, sd.name
        """).fetchall()
        return [
            {
                "entity_id": row[0],
                "entity_name": row[1],
                "entity_title": row[2],
                "kind": row[3],
                "score_id": row[4],
                "score_name": row[5] or row[4],
                "value": row[6],
            }
            for row in result
        ]

    def get_kind_rank_distribution(self, rank_id: str) -> list[dict[str, Any]]:
        """Get Kind × Rank Label distribution for heatmap."""
        result = self.conn.execute("""
            SELECT
                e.kind,
                er.label,
                COUNT(*) as count
            FROM entity_ranks er
            JOIN entities e ON er.entity_id = e.id
            WHERE er.rank_id = ?
            GROUP BY e.kind, er.label
            ORDER BY e.kind,
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
        """, [rank_id]).fetchall()
        return [
            {
                "kind": row[0],
                "label": row[1] or "Unranked",
                "count": row[2],
            }
            for row in result
        ]

    def get_score_trends_by_type(self, days: int = 30) -> list[dict[str, Any]]:
        """Get score trends by score type over time for heatmap."""
        result = self.conn.execute(f"""
            SELECT
                DATE_TRUNC('day', es.updated_at) as date,
                sd.id as score_id,
                sd.name as score_name,
                AVG(es.value) as avg_value,
                COUNT(*) as count
            FROM entity_scores es
            LEFT JOIN score_definitions sd ON es.score_id = sd.id
            WHERE es.updated_at >= CURRENT_DATE - INTERVAL '{days}' DAY
            GROUP BY DATE_TRUNC('day', es.updated_at), sd.id, sd.name
            ORDER BY date, sd.name
        """).fetchall()
        return [
            {
                "date": row[0],
                "score_id": row[1],
                "score_name": row[2] or row[1],
                "avg_value": row[3] or 0,
                "count": row[4],
            }
            for row in result
        ]
