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
                   sd.name, sd.min_value, sd.max_value, es.scorecard_id
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
                "scorecard_id": row[7],
            }
            for row in result
        ]

    def get_entity_ranks(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all computed ranks for an entity."""
        result = self.conn.execute(
            """
            SELECT er.rank_id, er.value, er.label, er.computed_at,
                   rd.name, rd.description, er.scorecard_id
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
                "scorecard_id": row[6],
            }
            for row in result
        ]

    def get_all_ranks_for_definition(
        self, rank_id: str, scorecard_id: str
    ) -> list[dict[str, Any]]:
        """Get all entity ranks for a specific rank definition.

        Args:
            rank_id: The rank definition ID
            scorecard_id: Scorecard ID (required - all ranks belong to a scorecard)

        Returns:
            List of dicts with entity_id, value, label
        """
        result = self.conn.execute(
            """
            SELECT er.entity_id, er.value, er.label, e.name, e.kind
            FROM entity_ranks er
            LEFT JOIN entities e ON er.entity_id = e.id
            WHERE er.rank_id = ? AND er.scorecard_id = ?
            ORDER BY er.value DESC
        """,
            [rank_id, scorecard_id],
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "value": row[1],
                "label": row[2],
                "entity_name": row[3],
                "kind": row[4],
            }
            for row in result
        ]

    def get_all_scores_with_entities(
        self, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all scores with entity information.

        Args:
            scorecard_id: Filter by scorecard ID. If None, returns all scores.
        """
        if scorecard_id:
            result = self.conn.execute("""
                SELECT es.entity_id, es.score_id, es.value, es.reason, es.updated_at,
                       e.name as entity_name, e.title as entity_title, e.kind,
                       sd.name as score_name, sd.max_value
                FROM entity_scores es
                JOIN entities e ON es.entity_id = e.id
                LEFT JOIN score_definitions sd ON es.score_id = sd.id
                WHERE es.scorecard_id = ?
                ORDER BY es.updated_at DESC
            """, [scorecard_id]).fetchall()
        else:
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

    def get_leaderboard(
        self, rank_id: str, limit: int = 100, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get top entities by rank.

        Args:
            rank_id: Rank definition ID
            limit: Maximum number of results
            scorecard_id: Filter by scorecard ID. If None, returns all ranks for the given rank_id.
        """
        if scorecard_id:
            result = self.conn.execute(
                """
                SELECT er.entity_id, er.value, er.label, e.name, e.title, e.kind
                FROM entity_ranks er
                JOIN entities e ON er.entity_id = e.id
                WHERE er.rank_id = ? AND er.scorecard_id = ?
                ORDER BY er.value DESC
                LIMIT ?
            """,
                [rank_id, scorecard_id, limit],
            ).fetchall()
        else:
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

    def get_dashboard_summary(
        self, scorecard_id: str | None = None
    ) -> dict[str, Any]:
        """Get aggregated scorecard data for dashboard.

        Args:
            scorecard_id: Filter by scorecard ID. If None, returns summary for all scores.
        """
        # Total entities
        total = self.conn.execute("""
            SELECT COUNT(*) FROM entities
        """).fetchone()[0]

        if scorecard_id:
            # Total entities with scores for this scorecard
            scored = self.conn.execute("""
                SELECT COUNT(DISTINCT entity_id) FROM entity_scores
                WHERE scorecard_id = ?
            """, [scorecard_id]).fetchone()[0]

            # Average score (excluding N/A values where value == -1)
            avg_score = self.conn.execute("""
                SELECT AVG(value) FROM entity_scores
                WHERE value != -1 AND scorecard_id = ?
            """, [scorecard_id]).fetchone()[0]

            # Score count by kind
            kind_counts = self.conn.execute("""
                SELECT e.kind, COUNT(DISTINCT es.entity_id)
                FROM entity_scores es
                JOIN entities e ON es.entity_id = e.id
                WHERE es.scorecard_id = ?
                GROUP BY e.kind
            """, [scorecard_id]).fetchall()

            # Recent score updates
            recent = self.conn.execute("""
                SELECT es.entity_id, e.name, e.title, e.kind,
                       es.score_id, sd.name as score_name, es.value, es.updated_at
                FROM entity_scores es
                JOIN entities e ON es.entity_id = e.id
                LEFT JOIN score_definitions sd ON es.score_id = sd.id
                WHERE es.scorecard_id = ?
                ORDER BY es.updated_at DESC
                LIMIT 10
            """, [scorecard_id]).fetchall()
        else:
            # Total entities with scores
            scored = self.conn.execute("""
                SELECT COUNT(DISTINCT entity_id) FROM entity_scores
            """).fetchone()[0]

            # Average score (excluding N/A values where value == -1)
            avg_score = self.conn.execute("""
                SELECT AVG(value) FROM entity_scores WHERE value != -1
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

    def get_score_distribution(
        self, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get score distribution by score type (for charts).

        Args:
            scorecard_id: Filter by scorecard ID. If None, returns distribution for all scores.
        """
        # Exclude N/A values (value == -1) from AVG/MIN/MAX calculations
        if scorecard_id:
            result = self.conn.execute("""
                SELECT
                    sd.id as score_id,
                    sd.name as score_name,
                    COUNT(*) as count,
                    AVG(CASE WHEN es.value != -1 THEN es.value END) as avg_value,
                    MIN(CASE WHEN es.value != -1 THEN es.value END) as min_value,
                    MAX(CASE WHEN es.value != -1 THEN es.value END) as max_value
                FROM entity_scores es
                LEFT JOIN score_definitions sd ON es.score_id = sd.id
                WHERE es.scorecard_id = ?
                GROUP BY sd.id, sd.name
                ORDER BY count DESC
            """, [scorecard_id]).fetchall()
        else:
            result = self.conn.execute("""
                SELECT
                    sd.id as score_id,
                    sd.name as score_name,
                    COUNT(*) as count,
                    AVG(CASE WHEN es.value != -1 THEN es.value END) as avg_value,
                    MIN(CASE WHEN es.value != -1 THEN es.value END) as min_value,
                    MAX(CASE WHEN es.value != -1 THEN es.value END) as max_value
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

    def get_rank_label_distribution(
        self, rank_id: str | None = None, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get rank label distribution (S/A/B/C/D counts) for charts.

        Args:
            rank_id: Filter by rank definition ID.
            scorecard_id: Filter by scorecard ID.
        """
        if rank_id and scorecard_id:
            result = self.conn.execute("""
                SELECT label, COUNT(*) as count
                FROM entity_ranks
                WHERE rank_id = ? AND scorecard_id = ?
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
            """, [rank_id, scorecard_id]).fetchall()
        elif rank_id:
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
        elif scorecard_id:
            result = self.conn.execute("""
                SELECT label, COUNT(*) as count
                FROM entity_ranks
                WHERE scorecard_id = ?
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
            """, [scorecard_id]).fetchall()
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
        # Exclude N/A values (value == -1) from average calculation
        result = self.conn.execute(f"""
            SELECT
                DATE_TRUNC('day', updated_at) as date,
                COUNT(*) as update_count,
                AVG(CASE WHEN value != -1 THEN value END) as avg_value
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

    def get_kind_score_average(
        self, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get average scores by Kind × Score Type for heatmap.

        Args:
            scorecard_id: Filter by scorecard ID. If None, returns averages for all scores.
        """
        # Exclude N/A values (value == -1) from average calculation
        if scorecard_id:
            result = self.conn.execute("""
                SELECT
                    e.kind,
                    sd.id as score_id,
                    sd.name as score_name,
                    AVG(CASE WHEN es.value != -1 THEN es.value END) as avg_value,
                    COUNT(CASE WHEN es.value != -1 THEN 1 END) as count
                FROM entity_scores es
                JOIN entities e ON es.entity_id = e.id
                LEFT JOIN score_definitions sd ON es.score_id = sd.id
                WHERE es.scorecard_id = ?
                GROUP BY e.kind, sd.id, sd.name
                ORDER BY e.kind, sd.name
            """, [scorecard_id]).fetchall()
        else:
            result = self.conn.execute("""
                SELECT
                    e.kind,
                    sd.id as score_id,
                    sd.name as score_name,
                    AVG(CASE WHEN es.value != -1 THEN es.value END) as avg_value,
                    COUNT(CASE WHEN es.value != -1 THEN 1 END) as count
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

    def get_entity_score_matrix(
        self, limit: int = 50, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get entity × score type matrix data for heatmap.

        Args:
            limit: Maximum number of entities to include.
            scorecard_id: Filter by scorecard ID. If None, returns matrix for all scores.
        """
        if scorecard_id:
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
                WHERE es.scorecard_id = ? AND es.entity_id IN (
                    SELECT DISTINCT entity_id FROM entity_scores
                    WHERE scorecard_id = ?
                    ORDER BY entity_id
                    LIMIT {limit}
                )
                ORDER BY e.kind, e.name, sd.name
            """, [scorecard_id, scorecard_id]).fetchall()
        else:
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

    def get_kind_rank_distribution(
        self, rank_id: str, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get Kind × Rank Label distribution for heatmap.

        Args:
            rank_id: Rank definition ID.
            scorecard_id: Filter by scorecard ID. If None, returns distribution for all ranks.
        """
        if scorecard_id:
            result = self.conn.execute("""
                SELECT
                    e.kind,
                    er.label,
                    COUNT(*) as count
                FROM entity_ranks er
                JOIN entities e ON er.entity_id = e.id
                WHERE er.rank_id = ? AND er.scorecard_id = ?
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
            """, [rank_id, scorecard_id]).fetchall()
        else:
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
        # Exclude N/A values (value == -1) from average calculation
        result = self.conn.execute(f"""
            SELECT
                DATE_TRUNC('day', es.updated_at) as date,
                sd.id as score_id,
                sd.name as score_name,
                AVG(CASE WHEN es.value != -1 THEN es.value END) as avg_value,
                COUNT(CASE WHEN es.value != -1 THEN 1 END) as count
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

    # ========== Multi-Scorecard Queries ==========

    def get_scorecards(self) -> list[dict[str, Any]]:
        """Get all registered scorecards."""
        result = self.conn.execute("""
            SELECT id, name, description, status, created_at, updated_at
            FROM scorecards
            ORDER BY name
        """).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in result
        ]

    def get_active_scorecards(self) -> list[dict[str, Any]]:
        """Get all active scorecards."""
        result = self.conn.execute("""
            SELECT id, name, description, status, created_at, updated_at
            FROM scorecards
            WHERE status = 'active'
            ORDER BY name
        """).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in result
        ]

    def get_scorecard(self, scorecard_id: str) -> dict[str, Any] | None:
        """Get a specific scorecard by ID."""
        result = self.conn.execute(
            """
            SELECT id, name, description, status, created_at, updated_at
            FROM scorecards
            WHERE id = ?
        """,
            [scorecard_id],
        ).fetchone()
        if not result:
            return None
        return {
            "id": result[0],
            "name": result[1],
            "description": result[2],
            "status": result[3],
            "created_at": result[4],
            "updated_at": result[5],
        }

    def update_scorecard_status(self, scorecard_id: str, status: str) -> None:
        """Update a scorecard's status."""
        from datetime import datetime

        now = datetime.utcnow().isoformat() + "Z"
        self.conn.execute(
            """
            UPDATE scorecards
            SET status = ?, updated_at = ?
            WHERE id = ?
        """,
            [status, now, scorecard_id],
        )

    def delete_scorecard(self, scorecard_id: str) -> None:
        """Delete a scorecard and all its related data."""
        # Delete related data
        self.conn.execute(
            "DELETE FROM entity_ranks WHERE scorecard_id = ?", [scorecard_id]
        )
        self.conn.execute(
            "DELETE FROM entity_scores WHERE scorecard_id = ?", [scorecard_id]
        )
        self.conn.execute(
            "DELETE FROM rank_definitions WHERE scorecard_id = ?", [scorecard_id]
        )
        self.conn.execute(
            "DELETE FROM score_definitions WHERE scorecard_id = ?", [scorecard_id]
        )
        # Delete scorecard
        self.conn.execute("DELETE FROM scorecards WHERE id = ?", [scorecard_id])

    def get_score_definitions_for_scorecard(
        self, scorecard_id: str
    ) -> list[dict[str, Any]]:
        """Get score definitions for a specific scorecard.

        Args:
            scorecard_id: Scorecard ID (required - all scores belong to a scorecard)
        """
        result = self.conn.execute(
            """
            SELECT id, name, description, target_kinds, min_value, max_value, scorecard_id
            FROM score_definitions
            WHERE scorecard_id = ?
            ORDER BY name
        """,
            [scorecard_id],
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "target_kinds": row[3] or [],
                "min_value": row[4],
                "max_value": row[5],
                "scorecard_id": row[6],
            }
            for row in result
        ]

    def get_rank_definitions_for_scorecard(
        self, scorecard_id: str
    ) -> list[dict[str, Any]]:
        """Get rank definitions for a specific scorecard.

        Args:
            scorecard_id: Scorecard ID (required - all ranks belong to a scorecard)
        """
        result = self.conn.execute(
            """
            SELECT id, name, description, target_kinds, score_refs, formula,
                   rules, label_function, entity_refs, thresholds, scorecard_id
            FROM rank_definitions
            WHERE scorecard_id = ?
            ORDER BY name
        """,
            [scorecard_id],
        ).fetchall()
        ranks = []
        for row in result:
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
                "scorecard_id": row[10],
            })
        return ranks

    def get_entities_comparison(
        self, scorecard_a: str, scorecard_b: str
    ) -> list[dict[str, Any]]:
        """Get entities with ranks from both scorecards for comparison.

        Args:
            scorecard_a: First scorecard ID
            scorecard_b: Second scorecard ID

        Returns:
            List of entities with rank labels from both scorecards.
        """
        # Get entities that have ranks in both scorecards
        # Join on rank_id to compare the same rank definition between scorecards
        result = self.conn.execute("""
            SELECT
                e.id as entity_id,
                e.name as entity_name,
                COALESCE(e.title, e.name) as entity_title,
                e.kind,
                era.label as label_a,
                era.value as value_a,
                erb.label as label_b,
                erb.value as value_b,
                era.rank_id as rank_id,
                rd.name as rank_name
            FROM entities e
            INNER JOIN entity_ranks era ON e.id = era.entity_id AND era.scorecard_id = ?
            INNER JOIN entity_ranks erb ON e.id = erb.entity_id AND erb.scorecard_id = ?
                AND era.rank_id = erb.rank_id
            LEFT JOIN rank_definitions rd ON era.rank_id = rd.id
            ORDER BY e.kind, e.name, rd.name
        """, [scorecard_a, scorecard_b]).fetchall()
        return [
            {
                "entity_id": row[0],
                "entity_name": row[1],
                "entity_title": row[2],
                "kind": row[3],
                "label_a": row[4] or "-",
                "value_a": row[5] or 0,
                "label_b": row[6] or "-",
                "value_b": row[7] or 0,
                "rank_id": row[8],
                "rank_name": row[9],
            }
            for row in result
        ]
