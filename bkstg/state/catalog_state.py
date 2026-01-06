"""Observable state managing the entity catalog."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ..config import BkstgConfig, ConfigLoader, GitHubSource, LocalSource
from ..db import CatalogLoader, CatalogQueries, DependencyAnalyzer, HistoryQueries, ScoreQueries, create_schema, get_connection
from ..git import CatalogScanner, EntityReader, EntityWriter, GitHubFetcher, HistoryReader, HistoryWriter, LocationProcessor
from ..git.sync_manager import SyncManager, SyncResult, SyncState, SyncStatus
from ..models import Catalog, Entity, Location, ScorecardDefinition
from ..models.base import EntityKind

if TYPE_CHECKING:
    from ..config import CatalogSource

logger = logging.getLogger(__name__)


class CatalogState:
    """Observable state managing the entity catalog."""

    def __init__(self, root_path: str | Path, config: BkstgConfig | None = None):
        self._root_path = Path(root_path)
        self._file_paths: dict[str, Path | str] = {}
        self._entity_sources: dict[str, str] = {}  # entity_id -> source name

        # Load or use provided config
        self._config_loader = ConfigLoader(self._root_path)
        self._config = config or self._config_loader.load()

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
        self._history_queries = HistoryQueries(self._conn)
        self._location_processor = LocationProcessor(
            root_path=self._root_path,
            cache_ttl=self._config.settings.cache_ttl,
            max_workers=self._config.settings.max_workers,
        )
        self._github_fetcher = GitHubFetcher()
        self._history_writer = HistoryWriter(self._get_catalogs_dir())
        self._sync_manager = SyncManager()

        # Initialize catalog
        self._catalog = Catalog()

        # Load initial catalog
        self.reload()

    def reload(self) -> None:
        """Reload catalog from all configured sources."""
        self._catalog = Catalog()
        self._file_paths = {}
        self._entity_sources = {}

        locations: list[Location] = []

        # Phase 1: Scan all configured sources
        for source in self._config.sources:
            if not source.enabled:
                continue

            if isinstance(source, LocalSource):
                self._scan_local_source(source, locations)
            elif isinstance(source, GitHubSource):
                self._scan_github_source(source, locations)

        # Phase 2: Process Location entities and fetch remote content
        if locations:
            self._process_locations(locations)

        # Load scorecard definitions first (before loading catalog)
        self._load_scorecard_definitions()

        # Load catalog (which also loads entity scores and computes ranks)
        self._loader.load_catalog(self._catalog, self._file_paths)

        # Load history from YAML files (from all sources)
        self._load_history_from_all_sources()

    def _scan_local_source(
        self, source: LocalSource, locations: list[Location]
    ) -> None:
        """Scan a local directory source.

        Args:
            source: Local source configuration.
            locations: List to append discovered Location entities.
        """
        path = Path(source.path)
        if not path.is_absolute():
            path = self._root_path / path

        if not path.exists():
            logger.warning(f"Local source path does not exist: {path}")
            return

        scanner = CatalogScanner(path)
        for file_path, data in scanner.scan():
            entity = self._reader.parse_entity(data)
            if entity:
                if self._catalog.get_entity_by_id(entity.entity_id):
                    logger.debug(f"Skipping duplicate entity: {entity.entity_id}")
                    continue

                self._catalog.add_entity(entity)
                self._file_paths[entity.entity_id] = file_path
                self._entity_sources[entity.entity_id] = source.name

                if isinstance(entity, Location):
                    locations.append(entity)

        logger.info(f"Scanned local source '{source.name}': {path}")

    def _scan_github_source(
        self, source: GitHubSource, locations: list[Location]
    ) -> None:
        """Scan a GitHub repository source.

        If sync_enabled and clone exists, scan from local clone.
        Otherwise, fetch via GitHub API.

        Args:
            source: GitHub source configuration.
            locations: List to append discovered Location entities.
        """
        # If sync is enabled and clone exists, scan from local clone
        if source.sync_enabled:
            clone_path = self._sync_manager.repo_manager.get_clone_path(source)
            if clone_path.exists():
                self._scan_github_clone(source, clone_path, locations)
                return

        # Fallback: fetch via GitHub API
        yaml_files = self._github_fetcher.scan_catalog_directory(
            owner=source.owner,
            repo=source.repo,
            path=source.path,
            ref=source.branch,
        )

        for file_path, file_url in yaml_files:
            content = self._github_fetcher.fetch_raw_content(
                owner=source.owner,
                repo=source.repo,
                path=file_path,
                ref=source.branch,
            )
            if content is None:
                continue

            try:
                data = yaml.safe_load(content)
                if not isinstance(data, dict):
                    continue

                entity = self._reader.parse_entity(data)
                if entity:
                    if self._catalog.get_entity_by_id(entity.entity_id):
                        logger.debug(f"Skipping duplicate entity: {entity.entity_id}")
                        continue

                    self._catalog.add_entity(entity)
                    self._file_paths[entity.entity_id] = file_url
                    self._entity_sources[entity.entity_id] = source.name

                    if isinstance(entity, Location):
                        locations.append(entity)
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse YAML from {file_url}: {e}")

        logger.info(
            f"Scanned GitHub source '{source.name}': "
            f"{source.owner}/{source.repo}:{source.branch}/{source.path}"
        )

    def _scan_github_clone(
        self, source: GitHubSource, clone_path: Path, locations: list[Location]
    ) -> None:
        """Scan a local clone of a GitHub source.

        Args:
            source: GitHub source configuration.
            clone_path: Path to the local clone.
            locations: List to append discovered Location entities.
        """
        # Determine the catalogs directory within the clone
        if source.path:
            scan_path = clone_path / source.path
        else:
            scan_path = clone_path

        if not scan_path.exists():
            logger.warning(f"Clone path does not exist: {scan_path}")
            return

        # Use CatalogScanner to scan the clone directory
        scanner = CatalogScanner(scan_path)
        for file_path, data in scanner.scan():
            entity = self._reader.parse_entity(data)
            if entity:
                if self._catalog.get_entity_by_id(entity.entity_id):
                    logger.debug(f"Skipping duplicate entity: {entity.entity_id}")
                    continue

                self._catalog.add_entity(entity)
                self._file_paths[entity.entity_id] = file_path
                self._entity_sources[entity.entity_id] = source.name

                if isinstance(entity, Location):
                    locations.append(entity)

        logger.info(
            f"Scanned GitHub clone '{source.name}': {scan_path}"
        )

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
        """Load scorecard definitions from YAML files.

        Loads from sync-enabled GitHub clones first (if available),
        then falls back to local catalogs directory.
        """
        scorecard_dirs: list[Path] = []

        # First, check sync-enabled GitHub sources
        for source in self._config.sources:
            if isinstance(source, GitHubSource) and source.sync_enabled:
                clone_path = self._sync_manager.repo_manager.get_clone_path(source)
                if clone_path.exists():
                    if source.path:
                        scorecard_dir = clone_path / source.path / "scorecards"
                    else:
                        scorecard_dir = clone_path / "scorecards"
                    if scorecard_dir.exists():
                        scorecard_dirs.append(scorecard_dir)

        # Then, check local catalogs directory
        if self._root_path.name == "catalogs" and self._root_path.is_dir():
            catalogs_dir = self._root_path
        else:
            catalogs_dir = self._root_path / "catalogs"

        local_scorecard_dir = catalogs_dir / "scorecards"
        if local_scorecard_dir.exists():
            scorecard_dirs.append(local_scorecard_dir)

        # Load from all discovered directories
        for scorecard_dir in scorecard_dirs:
            for yaml_file in scorecard_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)

                    if data and data.get("kind") == "ScorecardDefinition":
                        scorecard = ScorecardDefinition.model_validate(data)
                        self._loader.load_scorecard_definitions(scorecard)
                except Exception as e:
                    print(f"Warning: Failed to load scorecard from {yaml_file}: {e}")

    def _load_history_from_all_sources(self) -> None:
        """Load history from YAML files from all sources.

        Loads from sync-enabled GitHub clones and local catalogs directory.
        """
        history_dirs: list[Path] = []

        # First, check sync-enabled GitHub sources
        for source in self._config.sources:
            if isinstance(source, GitHubSource) and source.sync_enabled:
                clone_path = self._sync_manager.repo_manager.get_clone_path(source)
                if clone_path.exists():
                    if source.path:
                        base_dir = clone_path / source.path
                    else:
                        base_dir = clone_path
                    if base_dir.exists():
                        history_dirs.append(base_dir)

        # Then, add local catalogs directory
        history_dirs.append(self._get_catalogs_dir())

        # Clear history once, then load from all directories without clearing
        self._loader.clear_history()
        for base_dir in history_dirs:
            self._loader.load_history(base_dir, clear=False)

    @property
    def catalog(self) -> Catalog:
        """Get the catalog."""
        return self._catalog

    # ========== Configuration Methods ==========

    def get_config(self) -> BkstgConfig:
        """Get current configuration."""
        return self._config

    def update_config(self, config: BkstgConfig, save: bool = True) -> None:
        """Update configuration and optionally save to file.

        Args:
            config: New configuration.
            save: Whether to save to config file.
        """
        self._config = config

        # Update location processor settings
        self._location_processor = LocationProcessor(
            root_path=self._root_path,
            cache_ttl=config.settings.cache_ttl,
            max_workers=config.settings.max_workers,
        )

        if save:
            self._config_loader.save(config)

        self.reload()

    def get_entity_source(self, entity_id: str) -> str | None:
        """Get the source name for an entity.

        Args:
            entity_id: Entity ID.

        Returns:
            Source name, or None if not found.
        """
        return self._entity_sources.get(entity_id)

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
        """Save an entity to disk.

        If the entity belongs to a sync-enabled GitHub source, save to the clone directory.
        Otherwise, save to the local catalogs directory.
        """
        kind = entity.kind.value
        name = entity.metadata.name
        entity_id = entity.entity_id

        # Check if this entity belongs to a sync-enabled GitHub source
        source_name = self._entity_sources.get(entity_id)
        if source_name:
            source = self._get_github_source(source_name)
            if source and source.sync_enabled:
                # Save to the clone directory
                clone_path = self._sync_manager.repo_manager.get_clone_path(source)
                if clone_path.exists():
                    # Determine the relative path within the clone
                    kind_dir = CatalogScanner.KIND_DIRS.get(kind, f"{kind.lower()}s")
                    if source.path:
                        file_path = clone_path / source.path / kind_dir / f"{name}.yaml"
                    else:
                        file_path = clone_path / kind_dir / f"{name}.yaml"

                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    self._writer.write_entity(entity, file_path)

                    # Auto-commit if enabled
                    if source.auto_commit:
                        self._sync_manager.repo_manager.commit(
                            source,
                            f"Update {entity_id}",
                        )

                    self.reload()
                    return

        # Default: save to local catalogs directory
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
        """Save scorecard definition to YAML file and reload.

        If a sync-enabled GitHub source exists, saves to the clone directory.
        Otherwise, saves to the local catalogs directory.
        """
        data = scorecard.model_dump(exclude_none=True, by_alias=True)

        # Check for sync-enabled GitHub source
        source = self._get_primary_sync_source()
        if source:
            clone_path = self._sync_manager.repo_manager.get_clone_path(source)
            if clone_path.exists():
                # Save to GitHub clone
                if source.path:
                    scorecard_dir = clone_path / source.path / "scorecards"
                else:
                    scorecard_dir = clone_path / "scorecards"

                scorecard_dir.mkdir(parents=True, exist_ok=True)
                path = scorecard_dir / "tech-health.yaml"

                with open(path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        data,
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        allow_unicode=True,
                    )

                # Auto-commit if enabled
                if source.auto_commit:
                    self._sync_manager.repo_manager.commit(
                        source,
                        "Update scorecard definition",
                    )

                self.reload()
                return

        # Default: save to local catalogs directory
        path = self.get_scorecard_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        self.reload()

    def _get_catalogs_dir(self) -> Path:
        """Get the catalogs directory path."""
        if self._root_path.name == "catalogs" and self._root_path.is_dir():
            return self._root_path
        return self._root_path / "catalogs"

    # ========== History Methods (bkstg extension) ==========

    def get_entity_score_history(
        self, entity_id: str, score_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get score history for an entity."""
        return self._history_queries.get_entity_score_history(entity_id, score_id, limit)

    def get_entity_rank_history(
        self, entity_id: str, rank_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get rank history for an entity."""
        return self._history_queries.get_entity_rank_history(entity_id, rank_id, limit)

    def get_all_score_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get all score history entries."""
        return self._history_queries.get_all_score_history(limit)

    def get_all_rank_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get all rank history entries."""
        return self._history_queries.get_all_rank_history(limit)

    def get_score_history_by_score(
        self, score_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get history for a specific score across all entities."""
        return self._history_queries.get_score_history_by_score(score_id, limit)

    def get_rank_history_by_rank(
        self, rank_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get history for a specific rank across all entities."""
        return self._history_queries.get_rank_history_by_rank(rank_id, limit)

    def get_score_history_for_definition(
        self, score_id: str, entity_ids: list[str] | None = None, days: int = 90
    ) -> list[dict[str, Any]]:
        """Get score history for a definition, grouped by entity for charting."""
        return self._history_queries.get_score_history_for_definition(
            score_id, entity_ids, days
        )

    def get_rank_history_for_definition(
        self, rank_id: str, entity_ids: list[str] | None = None, days: int = 90
    ) -> list[dict[str, Any]]:
        """Get rank history for a definition, grouped by entity for charting."""
        return self._history_queries.get_rank_history_for_definition(
            rank_id, entity_ids, days
        )

    def get_definition_change_timestamps(
        self,
        definition_type: str,
        definition_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get timestamps when a definition was changed (for chart markers)."""
        return self._history_queries.get_definition_change_timestamps(
            definition_type, definition_id, start_date, end_date
        )

    def get_definition_history(
        self,
        definition_type: str | None = None,
        definition_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get definition change history."""
        return self._history_queries.get_definition_history(
            definition_type, definition_id, limit
        )

    def get_entity_score_trend(
        self, entity_id: str, score_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get score trend for an entity over time."""
        return self._history_queries.get_entity_score_trend(entity_id, score_id, days)

    def get_entity_rank_trend(
        self, entity_id: str, rank_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Get rank trend for an entity over time."""
        return self._history_queries.get_entity_rank_trend(entity_id, rank_id, days)

    def get_recent_score_changes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent score changes for dashboard."""
        return self._history_queries.get_recent_score_changes(limit)

    def get_recent_rank_changes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent rank changes for dashboard."""
        return self._history_queries.get_recent_rank_changes(limit)

    def record_score_history(
        self,
        entity_id: str,
        score_id: str,
        value: float,
        reason: str | None = None,
        source: str | None = None,
    ) -> None:
        """Record a score change to both DB and YAML.

        History is saved to the appropriate location based on entity source:
        - GitHub-derived entities → clone directory
        - Local entities → local catalogs directory
        """
        from datetime import datetime

        timestamp = datetime.utcnow().isoformat() + "Z"

        # Save to DB
        self._history_queries.insert_score_history(
            entity_id, score_id, value, reason, source, timestamp
        )

        # Save to YAML for persistence (use entity-specific writer)
        history_writer = self._get_history_writer_for_entity(entity_id)
        history_writer.add_score_history_entry(
            entity_id, score_id, value, reason, source, timestamp
        )

        # Auto-commit if entity belongs to sync-enabled source
        self._auto_commit_history_for_entity(entity_id, f"Update score {score_id}")

    def record_rank_history(
        self,
        entity_id: str,
        rank_id: str,
        value: float,
        label: str | None = None,
        score_snapshot: dict[str, float] | None = None,
    ) -> None:
        """Record a rank change to both DB and YAML.

        History is saved to the appropriate location based on entity source:
        - GitHub-derived entities → clone directory
        - Local entities → local catalogs directory
        """
        from datetime import datetime

        timestamp = datetime.utcnow().isoformat() + "Z"

        # Save to DB
        self._history_queries.insert_rank_history(
            entity_id, rank_id, value, label, score_snapshot, timestamp
        )

        # Save to YAML for persistence (use entity-specific writer)
        history_writer = self._get_history_writer_for_entity(entity_id)
        history_writer.add_rank_history_entry(
            entity_id, rank_id, value, label, score_snapshot, timestamp
        )

        # Auto-commit if entity belongs to sync-enabled source
        self._auto_commit_history_for_entity(entity_id, f"Update rank {rank_id}")

    def record_definition_history(
        self,
        definition_type: str,
        definition_id: str,
        change_type: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        changed_fields: list[str] | None = None,
    ) -> None:
        """Record a definition change to both DB and YAML.

        Definition history is saved to sync-enabled GitHub source if available,
        otherwise to local catalogs directory.
        """
        from datetime import datetime

        timestamp = datetime.utcnow().isoformat() + "Z"

        # Save to DB
        self._history_queries.insert_definition_history(
            definition_type,
            definition_id,
            change_type,
            old_value,
            new_value,
            changed_fields,
            timestamp,
        )

        # Save to YAML for persistence (use definitions writer)
        history_writer = self._get_history_writer_for_definitions()
        if definition_type == "score":
            history_writer.add_score_definition_history_entry(
                definition_id, change_type, old_value, new_value, changed_fields, timestamp
            )
        elif definition_type == "rank":
            history_writer.add_rank_definition_history_entry(
                definition_id, change_type, old_value, new_value, changed_fields, timestamp
            )

        # Auto-commit if sync-enabled source exists
        self._auto_commit_definitions(f"Update {definition_type} definition {definition_id}")

    # ========== Sync Methods (GitHub bidirectional sync) ==========

    def _get_github_source(self, source_name: str) -> GitHubSource | None:
        """Get a GitHubSource by name.

        Args:
            source_name: Source name to find.

        Returns:
            GitHubSource if found and is a GitHub source, None otherwise.
        """
        for source in self._config.sources:
            if source.name == source_name and isinstance(source, GitHubSource):
                return source
        return None

    def _get_primary_sync_source(self) -> GitHubSource | None:
        """Get the primary sync-enabled GitHub source.

        Used for saving scorecard definitions and definition history.

        Returns:
            First sync-enabled GitHubSource, or None if none.
        """
        for source in self._config.sources:
            if isinstance(source, GitHubSource) and source.sync_enabled:
                return source
        return None

    def _get_history_writer_for_entity(self, entity_id: str) -> HistoryWriter:
        """Get the appropriate HistoryWriter for an entity.

        If the entity belongs to a sync-enabled GitHub source, returns
        a HistoryWriter for the clone directory. Otherwise, returns the
        default local HistoryWriter.

        Args:
            entity_id: Entity ID.

        Returns:
            HistoryWriter for the appropriate directory.
        """
        source_name = self._entity_sources.get(entity_id)
        if source_name:
            source = self._get_github_source(source_name)
            if source and source.sync_enabled:
                clone_path = self._sync_manager.repo_manager.get_clone_path(source)
                if clone_path.exists():
                    if source.path:
                        base_path = clone_path / source.path
                    else:
                        base_path = clone_path
                    return HistoryWriter(base_path)
        return self._history_writer

    def _get_history_writer_for_definitions(self) -> HistoryWriter:
        """Get the HistoryWriter for definition history.

        If a sync-enabled GitHub source exists, returns a HistoryWriter
        for that clone directory. Otherwise, returns the default local writer.

        Returns:
            HistoryWriter for the appropriate directory.
        """
        source = self._get_primary_sync_source()
        if source:
            clone_path = self._sync_manager.repo_manager.get_clone_path(source)
            if clone_path.exists():
                if source.path:
                    base_path = clone_path / source.path
                else:
                    base_path = clone_path
                return HistoryWriter(base_path)
        return self._history_writer

    def _auto_commit_history_for_entity(self, entity_id: str, message: str) -> None:
        """Auto-commit history changes if entity belongs to sync-enabled source.

        Args:
            entity_id: Entity ID.
            message: Commit message.
        """
        source_name = self._entity_sources.get(entity_id)
        if source_name:
            source = self._get_github_source(source_name)
            if source and source.sync_enabled and source.auto_commit:
                clone_path = self._sync_manager.repo_manager.get_clone_path(source)
                if clone_path.exists():
                    self._sync_manager.repo_manager.commit(source, message)

    def _auto_commit_definitions(self, message: str) -> None:
        """Auto-commit definition changes if sync-enabled source exists.

        Args:
            message: Commit message.
        """
        source = self._get_primary_sync_source()
        if source and source.auto_commit:
            clone_path = self._sync_manager.repo_manager.get_clone_path(source)
            if clone_path.exists():
                self._sync_manager.repo_manager.commit(source, message)

    def get_sync_status(self, source_name: str) -> SyncStatus | None:
        """Get sync status for a source by name.

        Args:
            source_name: Name of the GitHub source.

        Returns:
            SyncStatus if found, None otherwise.
        """
        source = self._get_github_source(source_name)
        if source is None:
            return None
        return self._sync_manager.get_sync_status(source)

    def get_all_sync_status(self) -> list[SyncStatus]:
        """Get sync status for all sync-enabled GitHub sources.

        Returns:
            List of SyncStatus for all enabled GitHub sources.
        """
        statuses = []
        for source in self._config.sources:
            if isinstance(source, GitHubSource) and source.sync_enabled:
                statuses.append(self._sync_manager.get_sync_status(source))
        return statuses

    def get_github_sources(self) -> list[GitHubSource]:
        """Get all GitHub sources.

        Returns:
            List of all GitHubSource configurations.
        """
        return [
            source
            for source in self._config.sources
            if isinstance(source, GitHubSource)
        ]

    def sync_source(
        self,
        source_name: str,
        commit_message: str | None = None,
        on_progress: Any = None,
    ) -> SyncResult:
        """Sync a source with GitHub (full bidirectional sync).

        Args:
            source_name: Name of the GitHub source.
            commit_message: Optional commit message for local changes.
            on_progress: Progress callback.

        Returns:
            SyncResult with success status and message.
        """
        source = self._get_github_source(source_name)
        if source is None:
            return SyncResult(success=False, message="Source not found")

        result = self._sync_manager.sync(source, commit_message, on_progress)
        if result.success:
            self.reload()  # Reload catalog after sync
        return result

    def pull_source(
        self,
        source_name: str,
        on_progress: Any = None,
    ) -> SyncResult:
        """Pull changes from GitHub.

        Args:
            source_name: Name of the GitHub source.
            on_progress: Progress callback.

        Returns:
            SyncResult with success status and message.
        """
        source = self._get_github_source(source_name)
        if source is None:
            return SyncResult(success=False, message="Source not found")

        result = self._sync_manager.pull(source, on_progress)
        if result.success:
            self.reload()  # Reload catalog after pull
        return result

    def push_source(
        self,
        source_name: str,
        commit_message: str | None = None,
        on_progress: Any = None,
    ) -> SyncResult:
        """Push changes to GitHub.

        Args:
            source_name: Name of the GitHub source.
            commit_message: Optional commit message.
            on_progress: Progress callback.

        Returns:
            SyncResult with success status and message.
        """
        source = self._get_github_source(source_name)
        if source is None:
            return SyncResult(success=False, message="Source not found")

        return self._sync_manager.push(source, commit_message, on_progress)

    def create_sync_pr(
        self,
        source_name: str,
        title: str,
        body: str,
        on_progress: Any = None,
    ) -> SyncResult:
        """Create PR for sync conflicts.

        Args:
            source_name: Name of the GitHub source.
            title: PR title.
            body: PR body/description.
            on_progress: Progress callback.

        Returns:
            SyncResult with PR URL if successful.
        """
        source = self._get_github_source(source_name)
        if source is None:
            return SyncResult(success=False, message="Source not found")

        return self._sync_manager.create_pr_for_conflicts(
            source, title, body, on_progress=on_progress
        )

    def get_open_sync_prs(self, source_name: str) -> list[dict]:
        """Get open PRs created by bkstg for a source.

        Args:
            source_name: Name of the GitHub source.

        Returns:
            List of PR info dicts.
        """
        source = self._get_github_source(source_name)
        if source is None:
            return []

        return self._sync_manager.get_open_prs(source)
