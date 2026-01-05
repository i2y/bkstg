"""Predefined SQL queries for catalog data."""

from typing import Any

import duckdb


class CatalogQueries:
    """Predefined SQL queries for catalog data."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    def search(
        self,
        query: str,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Full-text search across entities."""
        sql = """
            SELECT * FROM entities
            WHERE (
                name ILIKE ? OR
                title ILIKE ? OR
                description ILIKE ?
            )
        """
        params = [f"%{query}%"] * 3

        if kind:
            sql += " AND kind = ?"
            params.append(kind)

        sql += " ORDER BY name LIMIT ?"
        params.append(limit)

        result = self.conn.execute(sql, params).fetchall()
        return self._to_dicts(result)

    def get_all(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Get all entities."""
        result = self.conn.execute(
            "SELECT * FROM entities ORDER BY kind, name LIMIT ?", [limit]
        ).fetchall()
        return self._to_dicts(result)

    def get_by_kind(self, kind: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get all entities of a specific kind."""
        result = self.conn.execute(
            "SELECT * FROM entities WHERE kind = ? ORDER BY name LIMIT ?",
            [kind, limit],
        ).fetchall()
        return self._to_dicts(result)

    def get_by_id(self, entity_id: str) -> dict[str, Any] | None:
        """Get entity by ID."""
        result = self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", [entity_id]
        ).fetchone()
        if result:
            return self._to_dict(result)
        return None

    def get_by_owner(self, owner: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get all entities owned by a group/user."""
        result = self.conn.execute(
            "SELECT * FROM entities WHERE owner = ? ORDER BY kind, name LIMIT ?",
            [owner, limit],
        ).fetchall()
        return self._to_dicts(result)

    def get_by_system(self, system: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get all entities in a system."""
        result = self.conn.execute(
            "SELECT * FROM entities WHERE system = ? ORDER BY kind, name LIMIT ?",
            [system, limit],
        ).fetchall()
        return self._to_dicts(result)

    def get_by_type(
        self, kind: str, entity_type: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get entities by kind and type."""
        result = self.conn.execute(
            "SELECT * FROM entities WHERE kind = ? AND type = ? ORDER BY name LIMIT ?",
            [kind, entity_type, limit],
        ).fetchall()
        return self._to_dicts(result)

    def get_by_tag(self, tag: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get entities with a specific tag."""
        result = self.conn.execute(
            "SELECT * FROM entities WHERE list_contains(tags, ?) ORDER BY kind, name LIMIT ?",
            [tag, limit],
        ).fetchall()
        return self._to_dicts(result)

    def count_by_kind(self) -> dict[str, int]:
        """Get entity count by kind."""
        result = self.conn.execute(
            "SELECT kind, COUNT(*) as count FROM entities GROUP BY kind"
        ).fetchall()
        return {row[0]: row[1] for row in result}

    def count_by_owner(self) -> list[dict[str, Any]]:
        """Get entity count by owner."""
        result = self.conn.execute(
            """
            SELECT owner, COUNT(*) as count
            FROM entities
            WHERE owner IS NOT NULL
            GROUP BY owner
            ORDER BY count DESC
            """
        ).fetchall()
        return [{"owner": row[0], "count": row[1]} for row in result]

    def get_relations(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all relations for an entity."""
        result = self.conn.execute(
            """
            SELECT relation_type, target_id, 'outgoing' as direction
            FROM relations WHERE source_id = ?
            UNION ALL
            SELECT relation_type, source_id, 'incoming' as direction
            FROM relations WHERE target_id = ?
            """,
            [entity_id, entity_id],
        ).fetchall()
        return [
            {"type": row[0], "entity_id": row[1], "direction": row[2]} for row in result
        ]

    def _to_dict(self, row: tuple) -> dict[str, Any]:
        """Convert a row to a dictionary."""
        columns = [
            "id",
            "kind",
            "namespace",
            "name",
            "title",
            "description",
            "owner",
            "lifecycle",
            "type",
            "system",
            "domain",
            "tags",
            "labels",
            "file_path",
            "raw_yaml",
            "created_at",
        ]
        return dict(zip(columns, row))

    def _to_dicts(self, rows: list[tuple]) -> list[dict[str, Any]]:
        """Convert rows to dictionaries."""
        return [self._to_dict(row) for row in rows]
