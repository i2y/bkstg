"""SQL queries for history data."""

import json
from datetime import datetime
from typing import Any

import duckdb


class HistoryQueries:
    """SQL queries for score/rank history data."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    # ========== Score History ==========

    def insert_score_history(
        self,
        entity_id: str,
        score_id: str,
        value: float,
        reason: str | None = None,
        source: str | None = None,
        recorded_at: str | None = None,
    ) -> None:
        """Insert a score history entry."""
        if recorded_at is None:
            recorded_at = datetime.utcnow().isoformat() + "Z"
        self.conn.execute(
            """
            INSERT INTO score_history (id, entity_id, score_id, value, reason, source, recorded_at)
            VALUES (nextval('score_history_id_seq'), ?, ?, ?, ?, ?, ?)
        """,
            [entity_id, score_id, value, reason, source, recorded_at],
        )

    def get_entity_score_history(
        self, entity_id: str, score_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get score history for an entity, optionally filtered by score_id."""
        if score_id:
            result = self.conn.execute(
                """
                SELECT score_id, value, reason, source, recorded_at
                FROM score_history
                WHERE entity_id = ? AND score_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [entity_id, score_id, limit],
            ).fetchall()
        else:
            result = self.conn.execute(
                """
                SELECT score_id, value, reason, source, recorded_at
                FROM score_history
                WHERE entity_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [entity_id, limit],
            ).fetchall()
        return [
            {
                "score_id": row[0],
                "value": row[1],
                "reason": row[2],
                "source": row[3],
                "recorded_at": row[4],
            }
            for row in result
        ]

    def get_all_score_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get all score history entries."""
        result = self.conn.execute(
            """
            SELECT sh.entity_id, sh.score_id, sh.value, sh.reason, sh.source, sh.recorded_at,
                   e.name as entity_name, e.kind, sd.name as score_name
            FROM score_history sh
            LEFT JOIN entities e ON sh.entity_id = e.id
            LEFT JOIN score_definitions sd ON sh.score_id = sd.id
            ORDER BY sh.recorded_at DESC
            LIMIT ?
        """,
            [limit],
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "score_id": row[1],
                "value": row[2],
                "reason": row[3],
                "source": row[4],
                "recorded_at": row[5],
                "entity_name": row[6],
                "kind": row[7],
                "score_name": row[8] or row[1],
            }
            for row in result
        ]

    def get_score_history_by_score(
        self, score_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get history for a specific score across all entities."""
        result = self.conn.execute(
            """
            SELECT sh.entity_id, sh.value, sh.reason, sh.source, sh.recorded_at,
                   e.name as entity_name, e.kind
            FROM score_history sh
            LEFT JOIN entities e ON sh.entity_id = e.id
            WHERE sh.score_id = ?
            ORDER BY sh.recorded_at DESC
            LIMIT ?
        """,
            [score_id, limit],
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "value": row[1],
                "reason": row[2],
                "source": row[3],
                "recorded_at": row[4],
                "entity_name": row[5],
                "kind": row[6],
            }
            for row in result
        ]

    def get_score_history_for_definition(
        self,
        score_id: str,
        entity_ids: list[str] | None = None,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get score history for a definition, grouped by entity for charting."""
        if entity_ids:
            placeholders = ", ".join(["?" for _ in entity_ids])
            result = self.conn.execute(
                f"""
                SELECT sh.entity_id, sh.value, sh.recorded_at,
                       e.name as entity_name, e.kind
                FROM score_history sh
                LEFT JOIN entities e ON sh.entity_id = e.id
                WHERE sh.score_id = ?
                  AND sh.entity_id IN ({placeholders})
                  AND sh.recorded_at >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
                ORDER BY sh.entity_id, sh.recorded_at ASC
            """,
                [score_id, *entity_ids],
            ).fetchall()
        else:
            result = self.conn.execute(
                f"""
                SELECT sh.entity_id, sh.value, sh.recorded_at,
                       e.name as entity_name, e.kind
                FROM score_history sh
                LEFT JOIN entities e ON sh.entity_id = e.id
                WHERE sh.score_id = ?
                  AND sh.recorded_at >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
                ORDER BY sh.entity_id, sh.recorded_at ASC
            """,
                [score_id],
            ).fetchall()
        return [
            {
                "entity_id": row[0],
                "value": row[1],
                "recorded_at": row[2],
                "entity_name": row[3] or row[0],
                "kind": row[4],
            }
            for row in result
        ]

    # ========== Rank History ==========

    def insert_rank_history(
        self,
        entity_id: str,
        rank_id: str,
        value: float,
        label: str | None = None,
        score_snapshot: dict[str, float] | None = None,
        recorded_at: str | None = None,
    ) -> None:
        """Insert a rank history entry."""
        if recorded_at is None:
            recorded_at = datetime.utcnow().isoformat() + "Z"
        snapshot_json = json.dumps(score_snapshot) if score_snapshot else None
        self.conn.execute(
            """
            INSERT INTO rank_history (id, entity_id, rank_id, value, label, score_snapshot, recorded_at)
            VALUES (nextval('rank_history_id_seq'), ?, ?, ?, ?, ?, ?)
        """,
            [entity_id, rank_id, value, label, snapshot_json, recorded_at],
        )

    def get_entity_rank_history(
        self, entity_id: str, rank_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get rank history for an entity, optionally filtered by rank_id."""
        if rank_id:
            result = self.conn.execute(
                """
                SELECT rank_id, value, label, score_snapshot, recorded_at
                FROM rank_history
                WHERE entity_id = ? AND rank_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [entity_id, rank_id, limit],
            ).fetchall()
        else:
            result = self.conn.execute(
                """
                SELECT rank_id, value, label, score_snapshot, recorded_at
                FROM rank_history
                WHERE entity_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [entity_id, limit],
            ).fetchall()
        return [
            {
                "rank_id": row[0],
                "value": row[1],
                "label": row[2],
                "score_snapshot": json.loads(row[3]) if row[3] else {},
                "recorded_at": row[4],
            }
            for row in result
        ]

    def get_all_rank_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get all rank history entries."""
        result = self.conn.execute(
            """
            SELECT rh.entity_id, rh.rank_id, rh.value, rh.label, rh.score_snapshot, rh.recorded_at,
                   e.name as entity_name, e.kind, rd.name as rank_name
            FROM rank_history rh
            LEFT JOIN entities e ON rh.entity_id = e.id
            LEFT JOIN rank_definitions rd ON rh.rank_id = rd.id
            ORDER BY rh.recorded_at DESC
            LIMIT ?
        """,
            [limit],
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "rank_id": row[1],
                "value": row[2],
                "label": row[3],
                "score_snapshot": json.loads(row[4]) if row[4] else {},
                "recorded_at": row[5],
                "entity_name": row[6],
                "kind": row[7],
                "rank_name": row[8] or row[1],
            }
            for row in result
        ]

    def get_rank_history_by_rank(
        self, rank_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get history for a specific rank across all entities."""
        result = self.conn.execute(
            """
            SELECT rh.entity_id, rh.value, rh.label, rh.score_snapshot, rh.recorded_at,
                   e.name as entity_name, e.kind
            FROM rank_history rh
            LEFT JOIN entities e ON rh.entity_id = e.id
            WHERE rh.rank_id = ?
            ORDER BY rh.recorded_at DESC
            LIMIT ?
        """,
            [rank_id, limit],
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "value": row[1],
                "label": row[2],
                "score_snapshot": json.loads(row[3]) if row[3] else {},
                "recorded_at": row[4],
                "entity_name": row[5],
                "kind": row[6],
            }
            for row in result
        ]

    def get_rank_history_for_definition(
        self,
        rank_id: str,
        entity_ids: list[str] | None = None,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get rank history for a definition, grouped by entity for charting."""
        if entity_ids:
            placeholders = ", ".join(["?" for _ in entity_ids])
            result = self.conn.execute(
                f"""
                SELECT rh.entity_id, rh.value, rh.label, rh.recorded_at,
                       e.name as entity_name, e.kind
                FROM rank_history rh
                LEFT JOIN entities e ON rh.entity_id = e.id
                WHERE rh.rank_id = ?
                  AND rh.entity_id IN ({placeholders})
                  AND rh.recorded_at >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
                ORDER BY rh.entity_id, rh.recorded_at ASC
            """,
                [rank_id, *entity_ids],
            ).fetchall()
        else:
            result = self.conn.execute(
                f"""
                SELECT rh.entity_id, rh.value, rh.label, rh.recorded_at,
                       e.name as entity_name, e.kind
                FROM rank_history rh
                LEFT JOIN entities e ON rh.entity_id = e.id
                WHERE rh.rank_id = ?
                  AND rh.recorded_at >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
                ORDER BY rh.entity_id, rh.recorded_at ASC
            """,
                [rank_id],
            ).fetchall()
        return [
            {
                "entity_id": row[0],
                "value": row[1],
                "label": row[2],
                "recorded_at": row[3],
                "entity_name": row[4] or row[0],
                "kind": row[5],
            }
            for row in result
        ]

    # ========== Definition History ==========

    def insert_definition_history(
        self,
        definition_type: str,  # "score" or "rank"
        definition_id: str,
        change_type: str,  # "created", "updated", "deleted"
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        changed_fields: list[str] | None = None,
        recorded_at: str | None = None,
    ) -> None:
        """Insert a definition change history entry."""
        if recorded_at is None:
            recorded_at = datetime.utcnow().isoformat() + "Z"
        old_json = json.dumps(old_value) if old_value else None
        new_json = json.dumps(new_value) if new_value else None
        fields_json = json.dumps(changed_fields) if changed_fields else None
        self.conn.execute(
            """
            INSERT INTO definition_history
            (id, definition_type, definition_id, change_type, old_value, new_value, changed_fields, recorded_at)
            VALUES (nextval('definition_history_id_seq'), ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                definition_type,
                definition_id,
                change_type,
                old_json,
                new_json,
                fields_json,
                recorded_at,
            ],
        )

    def get_definition_history(
        self,
        definition_type: str | None = None,
        definition_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get definition change history."""
        if definition_type and definition_id:
            result = self.conn.execute(
                """
                SELECT definition_type, definition_id, change_type, old_value, new_value, changed_fields, recorded_at
                FROM definition_history
                WHERE definition_type = ? AND definition_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [definition_type, definition_id, limit],
            ).fetchall()
        elif definition_type:
            result = self.conn.execute(
                """
                SELECT definition_type, definition_id, change_type, old_value, new_value, changed_fields, recorded_at
                FROM definition_history
                WHERE definition_type = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [definition_type, limit],
            ).fetchall()
        else:
            result = self.conn.execute(
                """
                SELECT definition_type, definition_id, change_type, old_value, new_value, changed_fields, recorded_at
                FROM definition_history
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [limit],
            ).fetchall()
        return [
            {
                "definition_type": row[0],
                "definition_id": row[1],
                "change_type": row[2],
                "old_value": json.loads(row[3]) if row[3] else None,
                "new_value": json.loads(row[4]) if row[4] else None,
                "changed_fields": json.loads(row[5]) if row[5] else [],
                "recorded_at": row[6],
            }
            for row in result
        ]

    def get_definition_change_timestamps(
        self,
        definition_type: str,
        definition_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get timestamps when a definition was changed (for chart markers)."""
        if start_date and end_date:
            result = self.conn.execute(
                """
                SELECT recorded_at, change_type, changed_fields
                FROM definition_history
                WHERE definition_type = ? AND definition_id = ?
                  AND recorded_at >= ? AND recorded_at <= ?
                ORDER BY recorded_at ASC
            """,
                [definition_type, definition_id, start_date, end_date],
            ).fetchall()
        elif start_date:
            result = self.conn.execute(
                """
                SELECT recorded_at, change_type, changed_fields
                FROM definition_history
                WHERE definition_type = ? AND definition_id = ?
                  AND recorded_at >= ?
                ORDER BY recorded_at ASC
            """,
                [definition_type, definition_id, start_date],
            ).fetchall()
        else:
            result = self.conn.execute(
                """
                SELECT recorded_at, change_type, changed_fields
                FROM definition_history
                WHERE definition_type = ? AND definition_id = ?
                ORDER BY recorded_at ASC
            """,
                [definition_type, definition_id],
            ).fetchall()
        return [
            {
                "recorded_at": row[0],
                "change_type": row[1],
                "changed_fields": json.loads(row[2]) if row[2] else [],
            }
            for row in result
        ]

    # ========== Trend Queries ==========

    def get_entity_score_trend(
        self, entity_id: str, score_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get score trend for an entity over time."""
        result = self.conn.execute(
            f"""
            SELECT DATE_TRUNC('day', recorded_at) as date, AVG(value) as avg_value, COUNT(*) as count
            FROM score_history
            WHERE entity_id = ? AND score_id = ?
              AND recorded_at >= CURRENT_DATE - INTERVAL '{days}' DAY
            GROUP BY DATE_TRUNC('day', recorded_at)
            ORDER BY date
        """,
            [entity_id, score_id],
        ).fetchall()
        return [
            {"date": row[0], "avg_value": row[1], "count": row[2]} for row in result
        ]

    def get_entity_rank_trend(
        self, entity_id: str, rank_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get rank trend for an entity over time."""
        result = self.conn.execute(
            f"""
            SELECT DATE_TRUNC('day', recorded_at) as date, AVG(value) as avg_value,
                   MAX(label) as label, COUNT(*) as count
            FROM rank_history
            WHERE entity_id = ? AND rank_id = ?
              AND recorded_at >= CURRENT_DATE - INTERVAL '{days}' DAY
            GROUP BY DATE_TRUNC('day', recorded_at)
            ORDER BY date
        """,
            [entity_id, rank_id],
        ).fetchall()
        return [
            {"date": row[0], "avg_value": row[1], "label": row[2], "count": row[3]}
            for row in result
        ]

    def get_recent_score_changes(
        self, limit: int = 20, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent score changes for dashboard.

        Args:
            limit: Maximum number of results
            scorecard_id: Filter by scorecard ID (via score_definitions)
        """
        if scorecard_id:
            result = self.conn.execute(
                """
                WITH ranked AS (
                    SELECT sh.*, e.name as entity_name, e.kind, sd.name as score_name,
                           LAG(sh.value) OVER (PARTITION BY sh.entity_id, sh.score_id ORDER BY sh.recorded_at) as prev_value,
                           ROW_NUMBER() OVER (PARTITION BY sh.entity_id, sh.score_id ORDER BY sh.recorded_at DESC) as rn
                    FROM score_history sh
                    LEFT JOIN entities e ON sh.entity_id = e.id
                    LEFT JOIN score_definitions sd ON sh.score_id = sd.id
                    WHERE sd.scorecard_id = ?
                )
                SELECT entity_id, entity_name, kind, score_id, score_name, value, prev_value, recorded_at
                FROM ranked
                WHERE rn = 1 AND prev_value IS NOT NULL AND value != prev_value
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [scorecard_id, limit],
            ).fetchall()
        else:
            result = self.conn.execute(
                """
                WITH ranked AS (
                    SELECT sh.*, e.name as entity_name, e.kind, sd.name as score_name,
                           LAG(sh.value) OVER (PARTITION BY sh.entity_id, sh.score_id ORDER BY sh.recorded_at) as prev_value,
                           ROW_NUMBER() OVER (PARTITION BY sh.entity_id, sh.score_id ORDER BY sh.recorded_at DESC) as rn
                    FROM score_history sh
                    LEFT JOIN entities e ON sh.entity_id = e.id
                    LEFT JOIN score_definitions sd ON sh.score_id = sd.id
                )
                SELECT entity_id, entity_name, kind, score_id, score_name, value, prev_value, recorded_at
                FROM ranked
                WHERE rn = 1 AND prev_value IS NOT NULL AND value != prev_value
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [limit],
            ).fetchall()
        return [
            {
                "entity_id": row[0],
                "entity_name": row[1],
                "kind": row[2],
                "score_id": row[3],
                "score_name": row[4] or row[3],
                "value": row[5],
                "prev_value": row[6],
                "recorded_at": row[7],
            }
            for row in result
        ]

    def get_recent_rank_changes(
        self, limit: int = 20, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent rank changes for dashboard.

        Args:
            limit: Maximum number of results
            scorecard_id: Filter by scorecard ID (via rank_definitions)
        """
        if scorecard_id:
            result = self.conn.execute(
                """
                WITH ranked AS (
                    SELECT rh.*, e.name as entity_name, e.kind, rd.name as rank_name,
                           LAG(rh.label) OVER (PARTITION BY rh.entity_id, rh.rank_id ORDER BY rh.recorded_at) as prev_label,
                           LAG(rh.value) OVER (PARTITION BY rh.entity_id, rh.rank_id ORDER BY rh.recorded_at) as prev_value,
                           ROW_NUMBER() OVER (PARTITION BY rh.entity_id, rh.rank_id ORDER BY rh.recorded_at DESC) as rn
                    FROM rank_history rh
                    LEFT JOIN entities e ON rh.entity_id = e.id
                    LEFT JOIN rank_definitions rd ON rh.rank_id = rd.id
                    WHERE rd.scorecard_id = ?
                )
                SELECT entity_id, entity_name, kind, rank_id, rank_name, value, label, prev_value, prev_label, recorded_at
                FROM ranked
                WHERE rn = 1 AND prev_label IS NOT NULL AND label != prev_label
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [scorecard_id, limit],
            ).fetchall()
        else:
            result = self.conn.execute(
                """
                WITH ranked AS (
                    SELECT rh.*, e.name as entity_name, e.kind, rd.name as rank_name,
                           LAG(rh.label) OVER (PARTITION BY rh.entity_id, rh.rank_id ORDER BY rh.recorded_at) as prev_label,
                           LAG(rh.value) OVER (PARTITION BY rh.entity_id, rh.rank_id ORDER BY rh.recorded_at) as prev_value,
                           ROW_NUMBER() OVER (PARTITION BY rh.entity_id, rh.rank_id ORDER BY rh.recorded_at DESC) as rn
                    FROM rank_history rh
                    LEFT JOIN entities e ON rh.entity_id = e.id
                    LEFT JOIN rank_definitions rd ON rh.rank_id = rd.id
                )
                SELECT entity_id, entity_name, kind, rank_id, rank_name, value, label, prev_value, prev_label, recorded_at
                FROM ranked
                WHERE rn = 1 AND prev_label IS NOT NULL AND label != prev_label
                ORDER BY recorded_at DESC
                LIMIT ?
            """,
                [limit],
            ).fetchall()
        return [
            {
                "entity_id": row[0],
                "entity_name": row[1],
                "kind": row[2],
                "rank_id": row[3],
                "rank_name": row[4] or row[3],
                "value": row[5],
                "label": row[6],
                "prev_value": row[7],
                "prev_label": row[8],
                "recorded_at": row[9],
            }
            for row in result
        ]

    # ========== Clear History ==========

    def clear_score_history(self, entity_id: str | None = None) -> None:
        """Clear score history, optionally for a specific entity."""
        if entity_id:
            self.conn.execute(
                "DELETE FROM score_history WHERE entity_id = ?", [entity_id]
            )
        else:
            self.conn.execute("DELETE FROM score_history")

    def clear_rank_history(self, entity_id: str | None = None) -> None:
        """Clear rank history, optionally for a specific entity."""
        if entity_id:
            self.conn.execute(
                "DELETE FROM rank_history WHERE entity_id = ?", [entity_id]
            )
        else:
            self.conn.execute("DELETE FROM rank_history")

    def clear_definition_history(self, definition_type: str | None = None) -> None:
        """Clear definition history, optionally for a specific type."""
        if definition_type:
            self.conn.execute(
                "DELETE FROM definition_history WHERE definition_type = ?",
                [definition_type],
            )
        else:
            self.conn.execute("DELETE FROM definition_history")

    # ========== Definition Change Snapshots ==========

    def insert_definition_history_with_id(
        self,
        definition_type: str,
        definition_id: str,
        change_type: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        changed_fields: list[str] | None = None,
        recorded_at: str | None = None,
        scorecard_id: str | None = None,
    ) -> int:
        """Insert a definition change history entry and return the generated ID."""
        if recorded_at is None:
            recorded_at = datetime.utcnow().isoformat() + "Z"
        old_json = json.dumps(old_value) if old_value else None
        new_json = json.dumps(new_value) if new_value else None
        fields_json = json.dumps(changed_fields) if changed_fields else None

        result = self.conn.execute(
            """
            INSERT INTO definition_history
            (id, definition_type, definition_id, change_type, old_value, new_value, changed_fields, recorded_at, scorecard_id)
            VALUES (nextval('definition_history_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """,
            [
                definition_type,
                definition_id,
                change_type,
                old_json,
                new_json,
                fields_json,
                recorded_at,
                scorecard_id,
            ],
        ).fetchone()
        return result[0] if result else -1

    def insert_definition_change_snapshot(
        self,
        definition_history_id: int,
        definition_type: str,
        definition_id: str,
        total_affected: int,
        recorded_at: str | None = None,
        scorecard_id: str | None = None,
    ) -> int:
        """Insert a definition change snapshot and return the generated ID."""
        if recorded_at is None:
            recorded_at = datetime.utcnow().isoformat() + "Z"

        result = self.conn.execute(
            """
            INSERT INTO definition_change_snapshots
            (id, definition_history_id, definition_type, definition_id, scorecard_id, recorded_at, total_affected)
            VALUES (nextval('definition_change_snapshots_id_seq'), ?, ?, ?, ?, ?, ?)
            RETURNING id
        """,
            [
                definition_history_id,
                definition_type,
                definition_id,
                scorecard_id,
                recorded_at,
                total_affected,
            ],
        ).fetchone()
        return result[0] if result else -1

    def insert_rank_impact_entries(
        self,
        snapshot_id: int,
        impacts: list[dict[str, Any]],
    ) -> None:
        """Insert multiple rank impact entries for a snapshot."""
        for impact in impacts:
            self.conn.execute(
                """
                INSERT INTO rank_impact_entries
                (id, snapshot_id, entity_id, before_value, before_label, after_value, after_label, change_type)
                VALUES (nextval('rank_impact_entries_id_seq'), ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    snapshot_id,
                    impact["entity_id"],
                    impact.get("before_value"),
                    impact.get("before_label"),
                    impact.get("after_value"),
                    impact.get("after_label"),
                    impact["change_type"],
                ],
            )

    def get_definition_change_snapshot(
        self, snapshot_id: int
    ) -> dict[str, Any] | None:
        """Get a definition change snapshot by ID."""
        result = self.conn.execute(
            """
            SELECT id, definition_history_id, definition_type, definition_id, scorecard_id, recorded_at, total_affected
            FROM definition_change_snapshots
            WHERE id = ?
        """,
            [snapshot_id],
        ).fetchone()
        if not result:
            return None
        return {
            "id": result[0],
            "definition_history_id": result[1],
            "definition_type": result[2],
            "definition_id": result[3],
            "scorecard_id": result[4],
            "recorded_at": result[5],
            "total_affected": result[6],
        }

    def get_snapshots_for_definition(
        self,
        definition_type: str,
        definition_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get all snapshots for a definition."""
        result = self.conn.execute(
            """
            SELECT id, definition_history_id, definition_type, definition_id, scorecard_id, recorded_at, total_affected
            FROM definition_change_snapshots
            WHERE definition_type = ? AND definition_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
        """,
            [definition_type, definition_id, limit],
        ).fetchall()
        return [
            {
                "id": row[0],
                "definition_history_id": row[1],
                "definition_type": row[2],
                "definition_id": row[3],
                "scorecard_id": row[4],
                "recorded_at": row[5],
                "total_affected": row[6],
            }
            for row in result
        ]

    def get_rank_impacts_for_snapshot(
        self, snapshot_id: int
    ) -> list[dict[str, Any]]:
        """Get all rank impact entries for a snapshot."""
        result = self.conn.execute(
            """
            SELECT rie.entity_id, rie.before_value, rie.before_label, rie.after_value, rie.after_label, rie.change_type,
                   e.name as entity_name, e.kind
            FROM rank_impact_entries rie
            LEFT JOIN entities e ON rie.entity_id = e.id
            WHERE rie.snapshot_id = ?
            ORDER BY rie.change_type, e.name
        """,
            [snapshot_id],
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "before_value": row[1],
                "before_label": row[2],
                "after_value": row[3],
                "after_label": row[4],
                "change_type": row[5],
                "entity_name": row[6],
                "kind": row[7],
            }
            for row in result
        ]

    def get_entity_rank_impacts(
        self, entity_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get all rank impacts for a specific entity across all definition changes."""
        result = self.conn.execute(
            """
            SELECT rie.before_value, rie.before_label, rie.after_value, rie.after_label, rie.change_type,
                   dcs.definition_id, dcs.recorded_at, dcs.scorecard_id
            FROM rank_impact_entries rie
            JOIN definition_change_snapshots dcs ON rie.snapshot_id = dcs.id
            WHERE rie.entity_id = ?
            ORDER BY dcs.recorded_at DESC
            LIMIT ?
        """,
            [entity_id, limit],
        ).fetchall()
        return [
            {
                "before_value": row[0],
                "before_label": row[1],
                "after_value": row[2],
                "after_label": row[3],
                "change_type": row[4],
                "definition_id": row[5],
                "recorded_at": row[6],
                "scorecard_id": row[7],
            }
            for row in result
        ]

    def get_recent_definition_change_snapshots(
        self, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent definition change snapshots with summary info."""
        result = self.conn.execute(
            """
            SELECT dcs.id, dcs.definition_type, dcs.definition_id, dcs.scorecard_id, dcs.recorded_at, dcs.total_affected,
                   dh.change_type, dh.changed_fields
            FROM definition_change_snapshots dcs
            JOIN definition_history dh ON dcs.definition_history_id = dh.id
            ORDER BY dcs.recorded_at DESC
            LIMIT ?
        """,
            [limit],
        ).fetchall()
        return [
            {
                "id": row[0],
                "definition_type": row[1],
                "definition_id": row[2],
                "scorecard_id": row[3],
                "recorded_at": row[4],
                "total_affected": row[5],
                "change_type": row[6],
                "changed_fields": json.loads(row[7]) if row[7] else [],
            }
            for row in result
        ]

    def clear_definition_change_snapshots(
        self, definition_id: str | None = None
    ) -> None:
        """Clear definition change snapshots, optionally for a specific definition."""
        if definition_id:
            # First get snapshot IDs
            snapshots = self.conn.execute(
                "SELECT id FROM definition_change_snapshots WHERE definition_id = ?",
                [definition_id],
            ).fetchall()
            for (snapshot_id,) in snapshots:
                self.conn.execute(
                    "DELETE FROM rank_impact_entries WHERE snapshot_id = ?",
                    [snapshot_id],
                )
            self.conn.execute(
                "DELETE FROM definition_change_snapshots WHERE definition_id = ?",
                [definition_id],
            )
        else:
            self.conn.execute("DELETE FROM rank_impact_entries")
            self.conn.execute("DELETE FROM definition_change_snapshots")
