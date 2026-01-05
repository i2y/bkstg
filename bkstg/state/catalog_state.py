"""Observable state managing the entity catalog."""

import logging
from pathlib import Path
from typing import Any

import yaml

from ..db import CatalogLoader, CatalogQueries, DependencyAnalyzer, ScoreQueries, create_schema, get_connection
from ..git import CatalogScanner, EntityReader, EntityWriter, LocationProcessor
from ..models import Catalog, Entity, Location, ScorecardDefinition
from ..models.base import EntityKind

logger = logging.getLogger(__name__)


class CatalogState:
    """Observable state managing the entity catalog."""

    def __init__(self, root_path: str | Path):
        self._root_path = Path(root_path)
        self._file_paths: dict[str, Path] = {}

        # Initialize DuckDB (in-memory)
        self._conn = get_connection(":memory:")
        create_schema(self._conn)

        # Initialize services
        self._scanner = CatalogScanner(self._root_path)
        self._reader = EntityReader()
        self._writer = EntityWriter()
        self._loader = CatalogLoader(self._conn)
        self._queries = CatalogQueries(self._conn)
        self._analyzer = DependencyAnalyzer(self._conn)
        self._score_queries = ScoreQueries(self._conn)
        self._location_processor = LocationProcessor(root_path=self._root_path)

        # Initialize catalog
        self._catalog = Catalog()

        # Load initial catalog
        self.reload()

    def reload(self) -> None:
        """Reload catalog from disk and remote locations."""
        self._catalog = Catalog()
        self._file_paths = {}

        # Phase 1: Scan local files
        locations: list[Location] = []
        for path, data in self._scanner.scan():
            entity = self._reader.parse_entity(data)
            if entity:
                self._catalog.add_entity(entity)
                self._file_paths[entity.entity_id] = path
                if isinstance(entity, Location):
                    locations.append(entity)

        # Phase 2: Process Location entities and fetch remote content
        if locations:
            self._process_locations(locations)

        # Load scorecard definitions first (before loading catalog)
        self._load_scorecard_definitions()

        # Load catalog (which also loads entity scores and computes ranks)
        self._loader.load_catalog(self._catalog, self._file_paths)

    def _process_locations(self, locations: list[Location]) -> None:
        """Process Location entities and fetch remote content recursively."""
        pending_locations = list(locations)
        max_iterations = 100  # Prevent infinite loops

        for _ in range(max_iterations):
            if not pending_locations:
                break

            # Process current batch of locations
            fetched = self._location_processor.process_locations(pending_locations)
            pending_locations = []

            for source_url, data in fetched:
                entity = self._reader.parse_entity(data)
                if entity:
                    # Check for duplicates
                    if self._catalog.get_entity_by_id(entity.entity_id):
                        logger.debug(f"Skipping duplicate entity: {entity.entity_id}")
                        continue

                    self._catalog.add_entity(entity)
                    # Store source URL as path (for tracking purposes)
                    self._file_paths[entity.entity_id] = Path(source_url)

                    # If this is a Location, queue it for processing
                    if isinstance(entity, Location):
                        pending_locations.append(entity)
                        logger.info(f"Discovered nested Location: {entity.entity_id}")

        if pending_locations:
            logger.warning(
                f"Stopped processing locations after {max_iterations} iterations. "
                f"Remaining: {len(pending_locations)}"
            )

    def clear_location_cache(self) -> None:
        """Clear the location processor cache."""
        self._location_processor.clear_cache()

    def _load_scorecard_definitions(self) -> None:
        """Load scorecard definitions from YAML files."""
        # Use same logic as CatalogScanner to find catalogs directory
        if self._root_path.name == "catalogs" and self._root_path.is_dir():
            catalogs_dir = self._root_path
        else:
            catalogs_dir = self._root_path / "catalogs"

        scorecard_dir = catalogs_dir / "scorecards"
        if not scorecard_dir.exists():
            return

        for yaml_file in scorecard_dir.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and data.get("kind") == "ScorecardDefinition":
                    scorecard = ScorecardDefinition.model_validate(data)
                    self._loader.load_scorecard_definitions(scorecard)
            except Exception as e:
                print(f"Warning: Failed to load scorecard from {yaml_file}: {e}")

    @property
    def catalog(self) -> Catalog:
        """Get the catalog."""
        return self._catalog

    def search(self, query: str, kind: str | None = None) -> list[dict[str, Any]]:
        """Search entities."""
        if not query:
            if kind:
                return self._queries.get_by_kind(kind)
            return self._queries.get_all()
        return self._queries.search(query, kind)

    def get_all(self) -> list[dict[str, Any]]:
        """Get all entities."""
        return self._queries.get_all()

    def get_by_kind(self, kind: str) -> list[dict[str, Any]]:
        """Get entities by kind."""
        return self._queries.get_by_kind(kind)

    def get_by_id(self, entity_id: str) -> dict[str, Any] | None:
        """Get entity by ID."""
        return self._queries.get_by_id(entity_id)

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get entity object by ID."""
        return self._catalog.get_entity_by_id(entity_id)

    def get_file_path(self, entity_id: str) -> Path | None:
        """Get file path for an entity."""
        return self._file_paths.get(entity_id)

    def get_relations(self, entity_id: str) -> list[dict[str, Any]]:
        """Get relations for an entity."""
        return self._queries.get_relations(entity_id)

    def count_by_kind(self) -> dict[str, int]:
        """Get entity count by kind."""
        return self._queries.count_by_kind()

    def get_dependencies(self, entity_id: str) -> list[str]:
        """Get direct dependencies."""
        return self._analyzer.get_dependencies(entity_id)

    def get_dependents(self, entity_id: str) -> list[str]:
        """Get direct dependents."""
        return self._analyzer.get_dependents(entity_id)

    def find_all_dependencies(self, entity_id: str) -> list[dict[str, Any]]:
        """Find all transitive dependencies."""
        return self._analyzer.find_all_dependencies(entity_id)

    def detect_cycles(self) -> list[list[str]]:
        """Detect dependency cycles."""
        return self._analyzer.detect_cycles()

    def get_dependency_graph(self) -> dict[str, Any]:
        """Get full dependency graph for visualization."""
        return self._analyzer.get_dependency_graph()

    def get_impact_analysis(self, entity_id: str) -> dict[str, Any]:
        """Analyze impact of changing an entity."""
        return self._analyzer.get_impact_analysis(entity_id)

    def save_entity(self, entity: Entity) -> None:
        """Save an entity to disk."""
        kind = entity.kind.value
        name = entity.metadata.name
        path = self._scanner.get_file_path_for_entity(kind, name)

        self._writer.write_entity(entity, path)
        self.reload()

    def ensure_catalogs_dir(self) -> None:
        """Create catalogs directory structure."""
        self._scanner.ensure_catalogs_dir()

    def resolve_ref(self, ref: str) -> str | None:
        """Resolve a reference to an entity ID.

        Refs can be:
        - "name" - match by name across all kinds
        - "kind:name" - match by kind and name (default namespace)
        - "kind:namespace/name" - fully qualified

        Returns the entity_id if found, None otherwise.
        """
        # First check if it's already a valid entity ID
        if self._catalog.get_entity_by_id(ref):
            return ref

        # Try to parse the ref format
        if ":" in ref:
            parts = ref.split(":", 1)
            kind = parts[0]
            name_part = parts[1]

            if "/" in name_part:
                namespace, name = name_part.split("/", 1)
            else:
                namespace = "default"
                name = name_part

            # Construct entity ID and check
            entity_id = f"{kind}:{namespace}/{name}"
            if self._catalog.get_entity_by_id(entity_id):
                return entity_id
        else:
            # Just a name - search across all entities
            # Try common kinds: User, Group, System, Domain, Component
            for kind in ["User", "Group", "System", "Domain", "Component", "API", "Resource"]:
                entity_id = f"{kind}:default/{ref}"
                if self._catalog.get_entity_by_id(entity_id):
                    return entity_id

        return None

    # ========== Scorecard Methods (bkstg extension) ==========

    def get_score_definitions(self) -> list[dict[str, Any]]:
        """Get all score definitions."""
        return self._score_queries.get_score_definitions()

    def get_rank_definitions(self) -> list[dict[str, Any]]:
        """Get all rank definitions."""
        return self._score_queries.get_rank_definitions()

    def get_entity_scores(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all scores for an entity."""
        return self._score_queries.get_entity_scores(entity_id)

    def get_entity_ranks(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all computed ranks for an entity."""
        return self._score_queries.get_entity_ranks(entity_id)

    def get_all_scores_with_entities(self) -> list[dict[str, Any]]:
        """Get all scores with entity information."""
        return self._score_queries.get_all_scores_with_entities()

    def get_leaderboard(self, rank_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get top entities by rank."""
        return self._score_queries.get_leaderboard(rank_id, limit)

    def get_dashboard_summary(self) -> dict[str, Any]:
        """Get aggregated scorecard data for dashboard."""
        return self._score_queries.get_dashboard_summary()

    def get_score_distribution(self) -> list[dict[str, Any]]:
        """Get score distribution by score type (for charts)."""
        return self._score_queries.get_score_distribution()

    def get_rank_label_distribution(self, rank_id: str | None = None) -> list[dict[str, Any]]:
        """Get rank label distribution (S/A/B/C/D counts) for charts."""
        return self._score_queries.get_rank_label_distribution(rank_id)

    def get_score_trends(self, days: int = 30) -> list[dict[str, Any]]:
        """Get score trends over time (daily aggregates) for charts."""
        return self._score_queries.get_score_trends(days)

    # ========== Heatmap Data Methods ==========

    def get_kind_score_average(self) -> list[dict[str, Any]]:
        """Get average scores by Kind × Score Type for heatmap."""
        return self._score_queries.get_kind_score_average()

    def get_entity_score_matrix(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get entity × score type matrix data for heatmap."""
        return self._score_queries.get_entity_score_matrix(limit)

    def get_kind_rank_distribution(self, rank_id: str) -> list[dict[str, Any]]:
        """Get Kind × Rank Label distribution for heatmap."""
        return self._score_queries.get_kind_rank_distribution(rank_id)

    def get_score_trends_by_type(self, days: int = 30) -> list[dict[str, Any]]:
        """Get score trends by score type over time for heatmap."""
        return self._score_queries.get_score_trends_by_type(days)

    def get_scorecard_file_path(self) -> Path:
        """Get path to the scorecard definition file."""
        if self._root_path.name == "catalogs" and self._root_path.is_dir():
            catalogs_dir = self._root_path
        else:
            catalogs_dir = self._root_path / "catalogs"

        scorecard_dir = catalogs_dir / "scorecards"
        scorecard_dir.mkdir(parents=True, exist_ok=True)

        # Return the first yaml file or default to tech-health.yaml
        yaml_files = list(scorecard_dir.glob("*.yaml"))
        if yaml_files:
            return yaml_files[0]
        return scorecard_dir / "tech-health.yaml"

    def save_scorecard_definition(self, scorecard: ScorecardDefinition) -> None:
        """Save scorecard definition to YAML file and reload."""
        path = self.get_scorecard_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        data = scorecard.model_dump(exclude_none=True, by_alias=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        self.reload()
