"""DuckDB schema definitions."""

import duckdb


def get_connection(path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection."""
    return duckdb.connect(path)


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create DuckDB tables for catalog entities."""

    # Main entities table (common fields)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id VARCHAR PRIMARY KEY,
            kind VARCHAR NOT NULL,
            namespace VARCHAR DEFAULT 'default',
            name VARCHAR NOT NULL,
            title VARCHAR,
            description VARCHAR,
            owner VARCHAR,
            lifecycle VARCHAR,
            type VARCHAR,
            system VARCHAR,
            domain VARCHAR,
            tags VARCHAR[],
            labels JSON,
            file_path VARCHAR,
            raw_yaml JSON,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Relations table (for dependency graph)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relations (
            id INTEGER PRIMARY KEY,
            source_id VARCHAR NOT NULL,
            target_id VARCHAR NOT NULL,
            relation_type VARCHAR NOT NULL
        )
    """)

    # Create sequence for relations id
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS relations_id_seq START 1
    """)

    # Create indexes for common queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_owner ON entities(owner)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_system ON entities(system)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type)"
    )

    # Score definitions table (bkstg extension)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS score_definitions (
            id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            description VARCHAR,
            target_kinds VARCHAR[],
            min_value DOUBLE DEFAULT 0,
            max_value DOUBLE DEFAULT 100,
            scorecard_id VARCHAR NOT NULL,
            levels JSON,
            created_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY(id, scorecard_id)
        )
    """)

    # Rank definitions table (bkstg extension)
    # Supports three modes:
    # 1. Simple: formula only (returns numeric, uses thresholds)
    # 2. Conditional: rules array (condition + formula pairs, uses thresholds)
    # 3. Label function: label_function code (returns label directly)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rank_definitions (
            id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            description VARCHAR,
            target_kinds VARCHAR[],
            score_refs VARCHAR[],
            formula VARCHAR,
            rules JSON,
            label_function VARCHAR,
            entity_refs VARCHAR[],
            thresholds JSON,
            scorecard_id VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY(id, scorecard_id)
        )
    """)

    # Entity scores table (actual score values per entity)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_scores (
            id INTEGER PRIMARY KEY,
            entity_id VARCHAR NOT NULL,
            score_id VARCHAR NOT NULL,
            value DOUBLE NOT NULL,
            reason VARCHAR,
            scorecard_id VARCHAR,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            UNIQUE(entity_id, score_id, scorecard_id)
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS entity_scores_id_seq START 1
    """)

    # Computed ranks table (cached rank values)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_ranks (
            id INTEGER PRIMARY KEY,
            entity_id VARCHAR NOT NULL,
            rank_id VARCHAR NOT NULL,
            value DOUBLE NOT NULL,
            label VARCHAR,
            scorecard_id VARCHAR,
            computed_at TIMESTAMP DEFAULT current_timestamp,
            UNIQUE(entity_id, rank_id, scorecard_id)
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS entity_ranks_id_seq START 1
    """)

    # Indexes for scorecard tables
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_scores_entity ON entity_scores(entity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_scores_score ON entity_scores(score_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_ranks_entity ON entity_ranks(entity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_ranks_rank ON entity_ranks(rank_id)"
    )

    # Score history table (bkstg extension)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY,
            entity_id VARCHAR NOT NULL,
            score_id VARCHAR NOT NULL,
            value DOUBLE NOT NULL,
            reason VARCHAR,
            source VARCHAR,
            recorded_at TIMESTAMP NOT NULL
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS score_history_id_seq START 1
    """)

    # Rank history table (bkstg extension)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rank_history (
            id INTEGER PRIMARY KEY,
            entity_id VARCHAR NOT NULL,
            rank_id VARCHAR NOT NULL,
            value DOUBLE NOT NULL,
            label VARCHAR,
            score_snapshot JSON,
            recorded_at TIMESTAMP NOT NULL
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS rank_history_id_seq START 1
    """)

    # Definition change history table (bkstg extension)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS definition_history (
            id INTEGER PRIMARY KEY,
            definition_type VARCHAR NOT NULL,
            definition_id VARCHAR NOT NULL,
            change_type VARCHAR NOT NULL,
            old_value JSON,
            new_value JSON,
            changed_fields JSON,
            recorded_at TIMESTAMP NOT NULL
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS definition_history_id_seq START 1
    """)

    # Indexes for history tables
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_score_history_entity ON score_history(entity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_score_history_score ON score_history(score_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_score_history_time ON score_history(recorded_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rank_history_entity ON rank_history(entity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rank_history_rank ON rank_history(rank_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rank_history_time ON rank_history(recorded_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_definition_history_type ON definition_history(definition_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_definition_history_id ON definition_history(definition_id)"
    )

    # Definition change snapshots table (captures entity rank impacts from definition changes)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS definition_change_snapshots (
            id INTEGER PRIMARY KEY,
            definition_history_id INTEGER NOT NULL,
            definition_type VARCHAR NOT NULL,
            definition_id VARCHAR NOT NULL,
            scorecard_id VARCHAR,
            recorded_at TIMESTAMP NOT NULL,
            total_affected INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS definition_change_snapshots_id_seq START 1
    """)

    # Rank impact entries table (individual entity impacts from a definition change)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rank_impact_entries (
            id INTEGER PRIMARY KEY,
            snapshot_id INTEGER NOT NULL,
            entity_id VARCHAR NOT NULL,
            before_value DOUBLE,
            before_label VARCHAR,
            after_value DOUBLE,
            after_label VARCHAR,
            change_type VARCHAR NOT NULL
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS rank_impact_entries_id_seq START 1
    """)

    # Indexes for snapshot tables
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_def_history ON definition_change_snapshots(definition_history_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_def_id ON definition_change_snapshots(definition_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rank_impacts_snapshot ON rank_impact_entries(snapshot_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rank_impacts_entity ON rank_impact_entries(entity_id)"
    )

    # Scorecards table (for multi-scorecard support)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scorecards (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Add scorecard_id to history tables (for multi-scorecard support)
    # Note: Using TRY_CAST pattern to handle column existence gracefully
    _add_column_if_not_exists(conn, "score_history", "scorecard_id", "VARCHAR")
    _add_column_if_not_exists(conn, "rank_history", "scorecard_id", "VARCHAR")
    _add_column_if_not_exists(conn, "definition_history", "scorecard_id", "VARCHAR")


def _add_column_if_not_exists(
    conn: duckdb.DuckDBPyConnection, table: str, column: str, dtype: str
) -> None:
    """Add a column to a table if it doesn't already exist."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {dtype}")
    except duckdb.CatalogException:
        # Column already exists
        pass


def drop_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop all tables."""
    conn.execute("DROP TABLE IF EXISTS rank_impact_entries")
    conn.execute("DROP TABLE IF EXISTS definition_change_snapshots")
    conn.execute("DROP TABLE IF EXISTS scorecards")
    conn.execute("DROP TABLE IF EXISTS definition_history")
    conn.execute("DROP TABLE IF EXISTS rank_history")
    conn.execute("DROP TABLE IF EXISTS score_history")
    conn.execute("DROP TABLE IF EXISTS entity_ranks")
    conn.execute("DROP TABLE IF EXISTS entity_scores")
    conn.execute("DROP TABLE IF EXISTS rank_definitions")
    conn.execute("DROP TABLE IF EXISTS score_definitions")
    conn.execute("DROP TABLE IF EXISTS relations")
    conn.execute("DROP TABLE IF EXISTS entities")
    conn.execute("DROP SEQUENCE IF EXISTS rank_impact_entries_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS definition_change_snapshots_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS definition_history_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS rank_history_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS score_history_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS entity_ranks_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS entity_scores_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS relations_id_seq")
