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
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description VARCHAR,
            target_kinds VARCHAR[],
            min_value DOUBLE DEFAULT 0,
            max_value DOUBLE DEFAULT 100,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Rank definitions table (bkstg extension)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rank_definitions (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description VARCHAR,
            target_kinds VARCHAR[],
            score_refs VARCHAR[],
            formula VARCHAR NOT NULL,
            thresholds JSON,
            created_at TIMESTAMP DEFAULT current_timestamp
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
            updated_at TIMESTAMP DEFAULT current_timestamp,
            UNIQUE(entity_id, score_id)
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
            computed_at TIMESTAMP DEFAULT current_timestamp,
            UNIQUE(entity_id, rank_id)
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


def drop_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop all tables."""
    conn.execute("DROP TABLE IF EXISTS entity_ranks")
    conn.execute("DROP TABLE IF EXISTS entity_scores")
    conn.execute("DROP TABLE IF EXISTS rank_definitions")
    conn.execute("DROP TABLE IF EXISTS score_definitions")
    conn.execute("DROP TABLE IF EXISTS relations")
    conn.execute("DROP TABLE IF EXISTS entities")
    conn.execute("DROP SEQUENCE IF EXISTS entity_ranks_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS entity_scores_id_seq")
    conn.execute("DROP SEQUENCE IF EXISTS relations_id_seq")
