"""Observable state managing the entity catalog."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ..config import BkstgConfig, ConfigLoader, GitHubSource
from ..db import CatalogLoader, CatalogQueries, DependencyAnalyzer, GroupHierarchyQueries, HistoryQueries, ScoreQueries, create_schema, get_connection
from ..git import CatalogScanner, EntityReader, EntityWriter, GitHubFetcher, HistoryReader, HistoryWriter, LocationProcessor
from ..git.repo_manager import GitRepoManager, LocationCloneInfo
from ..git.sync_manager import SyncManager, SyncResult, SyncState, SyncStatus
from ..models import Catalog, Entity, Location, ScorecardDefinition
from ..models.scorecard import ScorecardDefinitionMetadata, ScorecardDefinitionSpec
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
        self._location_clones: dict[str, LocationCloneInfo] = {}  # "owner/repo" -> clone info

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
        self._group_queries = GroupHierarchyQueries(self._conn)
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
        self._location_clones = {}

        locations: list[Location] = []

        # Phase 1: Scan all configured GitHub sources
        for source in self._config.sources:
            if not source.enabled:
                continue

            if isinstance(source, GitHubSource):
                self._scan_github_source(source, locations)

        # Phase 2: Process Location entities (clone and scan)
        if locations:
            self._process_locations(locations)

        # Load scorecard definitions first (before loading catalog)
        self._load_scorecard_definitions()

        # Load catalog (which also loads entity scores and computes ranks)
        self._loader.load_catalog(self._catalog, self._file_paths)

        # Load history from YAML files (from all sources)
        self._load_history_from_all_sources()

    def _scan_github_source(
        self, source: GitHubSource, locations: list[Location]
    ) -> None:
        """Scan a GitHub repository source.

        If sync_enabled, scan from local clone (creating if needed).
        Otherwise, fetch via GitHub API.

        Args:
            source: GitHub source configuration.
            locations: List to append discovered Location entities.
        """
        # If sync is enabled, use local clone (faster than API)
        if source.sync_enabled:
            clone_path = self._sync_manager.repo_manager.get_clone_path(source)
            if clone_path.exists():
                self._scan_github_clone(source, clone_path, locations)
                return
            # Clone doesn't exist - create it first (skip fetch for speed)
            result = self._sync_manager.repo_manager.clone_or_update(source)
            if result and result.exists():
                self._scan_github_clone(source, result, locations)
                return
            # Clone failed, fall through to API

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
        """Process Location entities and clone remote repositories.

        For GitHub URLs, clones the repository and reads entities from the clone.
        This makes Location entities editable (changes saved to clone, synced via PR).

        Clone operations are parallelized for faster startup.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        pending_locations = list(locations)
        processed_repos: set[str] = set()  # Track processed repos to avoid duplicates
        max_iterations = 100  # Prevent infinite loops

        for _ in range(max_iterations):
            if not pending_locations:
                break

            # Collect all GitHub URL targets for parallel cloning
            clone_tasks: list[tuple[LocationCloneInfo, str, str]] = []  # (info, target, parent_id)
            non_github_tasks: list[tuple[str, Location]] = []

            for location in pending_locations:
                targets = location.get_all_targets()

                for target in targets:
                    # Check if this is a GitHub URL
                    clone_info = GitRepoManager.parse_github_url(target)
                    if clone_info:
                        repo_key = f"{clone_info.owner}/{clone_info.repo}"
                        if repo_key in processed_repos:
                            logger.debug(f"Skipping already processed repo: {repo_key}")
                            continue

                        processed_repos.add(repo_key)
                        clone_tasks.append((clone_info, target, location.entity_id))
                    else:
                        non_github_tasks.append((target, location))

            # Clone GitHub repositories in parallel (with fetch to sync latest)
            clone_results: list[tuple[LocationCloneInfo, str]] = []  # (result, parent_id)
            if clone_tasks:
                with ThreadPoolExecutor(max_workers=self._config.settings.max_workers) as executor:
                    futures = {
                        executor.submit(
                            self._sync_manager.repo_manager.clone_location_target,
                            f"https://github.com/{info.owner}/{info.repo}/blob/{info.branch}/{info.path}",
                        ): (info, parent_id)
                        for info, _target, parent_id in clone_tasks
                    }
                    for future in as_completed(futures):
                        info, parent_id = futures[future]
                        try:
                            result = future.result()
                            if result:
                                clone_results.append((result, parent_id))
                        except Exception as e:
                            repo_key = f"{info.owner}/{info.repo}"
                            logger.error(f"Failed to clone {repo_key}: {e}")

            # Scan cloned repositories (sequential for thread safety)
            new_locations: list[Location] = []
            for result, parent_id in clone_results:
                new_locs = self._scan_cloned_location(result, parent_id)
                new_locations.extend(new_locs)

            # Process non-GitHub URLs
            for target, location in non_github_tasks:
                self._fetch_non_github_location(target, location)

            pending_locations = new_locations

        if pending_locations:
            logger.warning(
                f"Stopped processing locations after {max_iterations} iterations. "
                f"Remaining: {len(pending_locations)}"
            )

    def _scan_cloned_location(
        self, clone_info: LocationCloneInfo, parent_location_id: str
    ) -> list[Location]:
        """Scan a cloned Location repository for entities.

        This method is called after clone_location_target() completes.
        It scans the local clone and adds entities to the catalog.

        Args:
            clone_info: Clone info with local_path set
            parent_location_id: ID of the parent Location entity

        Returns:
            List of nested Location entities discovered (always empty for team repos).
        """
        repo_key = f"{clone_info.owner}/{clone_info.repo}"
        source_name = f"location:{repo_key}"

        # Store clone info for later use (save_entity, sync, etc.)
        self._location_clones[repo_key] = clone_info
        logger.info(f"Cloned Location target: {repo_key} -> {clone_info.local_path}")

        # Determine scan path
        if clone_info.path:
            scan_path = clone_info.local_path / clone_info.path
        else:
            scan_path = clone_info.local_path

        if not scan_path.exists():
            logger.warning(f"Location clone path does not exist: {scan_path}")
            return []

        # Scan for entities
        scanner = CatalogScanner(scan_path)

        for file_path, data in scanner.scan():
            entity = self._reader.parse_entity(data)
            if entity:
                if self._catalog.get_entity_by_id(entity.entity_id):
                    logger.debug(f"Skipping duplicate entity: {entity.entity_id}")
                    continue

                self._catalog.add_entity(entity)
                self._file_paths[entity.entity_id] = file_path
                self._entity_sources[entity.entity_id] = source_name

                # Note: Location entities in team repos are added to catalog
                # but NOT processed for recursive cloning (central repo only)
                if isinstance(entity, Location):
                    logger.debug(
                        f"Location '{entity.entity_id}' found in team repo - "
                        "not processing (Locations only processed from central repo)"
                    )

        logger.info(f"Scanned Location clone '{source_name}': {scan_path}")
        # Return empty list - Locations are only processed from central GitHub Source
        return []

    def _clone_and_scan_location(
        self, clone_info: LocationCloneInfo, parent_location_id: str
    ) -> list[Location]:
        """Clone a Location target repository and scan for entities.

        Note: This method is kept for backward compatibility.
        The new _process_locations uses parallel cloning with _scan_cloned_location.

        Args:
            clone_info: Parsed GitHub URL info (owner, repo, branch, path)
            parent_location_id: ID of the parent Location entity

        Returns:
            List of nested Location entities discovered.
        """
        repo_key = f"{clone_info.owner}/{clone_info.repo}"

        # Clone the repository
        result = self._sync_manager.repo_manager.clone_location_target(
            f"https://github.com/{clone_info.owner}/{clone_info.repo}/blob/{clone_info.branch}/{clone_info.path}"
        )
        if not result:
            logger.error(f"Failed to clone Location target: {repo_key}")
            return []

        return self._scan_cloned_location(result, parent_location_id)

    def _fetch_non_github_location(self, target: str, location: Location) -> None:
        """Fetch content from non-GitHub Location targets (local files, etc.).

        Args:
            target: Target URL or path
            location: Parent Location entity
        """
        # Use existing LocationProcessor for non-GitHub URLs
        fetched = self._location_processor.process_locations([location])

        for source_url, data in fetched:
            entity = self._reader.parse_entity(data)
            if entity:
                if self._catalog.get_entity_by_id(entity.entity_id):
                    logger.debug(f"Skipping duplicate entity: {entity.entity_id}")
                    continue

                self._catalog.add_entity(entity)
                self._file_paths[entity.entity_id] = Path(source_url)
                # Non-GitHub locations don't have a sync source

    def clear_location_cache(self) -> None:
        """Clear the location processor cache."""
        self._location_processor.clear_cache()

    def _load_scorecard_definitions(self) -> None:
        """Load scorecard definitions from YAML files.

        Loads from sync-enabled GitHub sources and local catalogs directory only.
        Location clones are intentionally excluded to enforce centralized scorecard
        management (all teams share the same scorecard definitions from central repo).
        """
        scorecard_dirs: list[Path] = []

        # Check sync-enabled GitHub sources (central repo)
        for source in self._config.sources:
            if isinstance(source, GitHubSource) and source.sync_enabled:
                clone_path = self._sync_manager.repo_manager.get_clone_path(source)
                if clone_path.exists():
                    if source.path:
                        base_dir = clone_path / source.path
                    else:
                        # Auto-detect catalogs directory (same logic as CatalogScanner)
                        catalogs_subdir = clone_path / "catalogs"
                        if catalogs_subdir.exists():
                            base_dir = catalogs_subdir
                        else:
                            base_dir = clone_path
                    scorecard_dir = base_dir / "scorecards"
                    if scorecard_dir.exists():
                        scorecard_dirs.append(scorecard_dir)

        # Check local catalogs directory
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
                        # Use metadata.name as scorecard_id
                        scorecard_id = scorecard.metadata.name
                        self._loader.load_scorecard_definitions(scorecard, scorecard_id)
                except Exception as e:
                    print(f"Warning: Failed to load scorecard from {yaml_file}: {e}")

    def _load_history_from_all_sources(self) -> None:
        """Load history from YAML files from all sources.

        Loads from sync-enabled GitHub clones, Location clones, and local catalogs directory.
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
                        # Auto-detect catalogs directory (same logic as CatalogScanner)
                        catalogs_subdir = clone_path / "catalogs"
                        if catalogs_subdir.exists():
                            base_dir = catalogs_subdir
                        else:
                            base_dir = clone_path
                    if base_dir.exists():
                        history_dirs.append(base_dir)

        # Also check Location clones
        for clone_info in self._location_clones.values():
            if clone_info.local_path.exists():
                # For Location clones, look for history at catalogs/history/
                # not under the specific target path (e.g., catalogs/components/history/)
                catalogs_dir = clone_info.local_path / "catalogs"
                if catalogs_dir.exists():
                    base_dir = catalogs_dir
                elif clone_info.path:
                    # Fallback: try to find 'catalogs' in the path
                    parts = clone_info.path.split("/")
                    if "catalogs" in parts:
                        idx = parts.index("catalogs")
                        base_dir = clone_info.local_path / "/".join(parts[: idx + 1])
                    else:
                        base_dir = clone_info.local_path / clone_info.path
                else:
                    base_dir = clone_info.local_path
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

    def get_dependency_graph(
        self,
        relation_types: list[str] | None = None,
        kind_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get dependency graph for visualization with optional filters."""
        return self._analyzer.get_dependency_graph(
            relation_types=relation_types,
            kind_filter=kind_filter,
        )

    def get_impact_analysis(self, entity_id: str) -> dict[str, Any]:
        """Analyze impact of changing an entity."""
        return self._analyzer.get_impact_analysis(entity_id)

    # Group hierarchy methods

    def get_root_groups(self) -> list[dict[str, Any]]:
        """Get all top-level groups (groups with no parent)."""
        return self._group_queries.get_root_groups()

    def get_child_groups(self, group_id: str) -> list[dict[str, Any]]:
        """Get direct child groups of a group."""
        return self._group_queries.get_child_groups(group_id)

    def get_all_descendant_groups(
        self, group_id: str, max_depth: int = 10
    ) -> list[dict[str, Any]]:
        """Get all descendant groups recursively."""
        return self._group_queries.get_all_descendants(group_id, max_depth)

    def get_group_owned_entities(
        self, group_id: str, include_descendants: bool = True
    ) -> list[dict[str, Any]]:
        """Get all entities owned by a group (and optionally its descendants)."""
        return self._group_queries.get_owned_entities(group_id, include_descendants)

    def get_group_entity_count(
        self, group_id: str, include_descendants: bool = True
    ) -> dict[str, int]:
        """Get entity count by kind for a group."""
        return self._group_queries.get_group_entity_count(
            group_id, include_descendants
        )

    def get_group_score_summary(
        self, group_id: str, include_descendants: bool = True
    ) -> list[dict[str, Any]]:
        """Get aggregated score summary for entities owned by a group."""
        return self._group_queries.get_group_score_aggregation(
            group_id, include_descendants
        )

    def get_group_rank_distribution(
        self, group_id: str, rank_id: str, include_descendants: bool = True
    ) -> list[dict[str, Any]]:
        """Get rank label distribution for entities owned by a group."""
        return self._group_queries.get_group_rank_distribution(
            group_id, rank_id, include_descendants
        )

    def get_group_average_rank(
        self, group_id: str, rank_id: str, include_descendants: bool = True
    ) -> dict[str, Any] | None:
        """Get average rank value for entities owned by a group."""
        return self._group_queries.get_group_average_rank(
            group_id, rank_id, include_descendants
        )

    def get_groups_comparison(
        self, group_ids: list[str], include_descendants: bool = True
    ) -> list[dict[str, Any]]:
        """Compare multiple groups by their score/rank aggregations."""
        return self._group_queries.get_groups_comparison(group_ids, include_descendants)

    def get_group_hierarchy_tree(
        self, root_group_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Build a hierarchical tree structure of groups."""
        return self._group_queries.get_group_hierarchy_tree(root_group_id)

    def save_entity(self, entity: Entity) -> None:
        """Save an entity to disk.

        Saves to the appropriate location based on entity source:
        - GitHub Source → clone directory (with auto-commit)
        - Location clone → clone directory (with auto-commit)
        - New entity → primary GitHub Source

        Raises:
            RuntimeError: If no GitHub Source is configured.
        """
        kind = entity.kind.value
        name = entity.metadata.name
        entity_id = entity.entity_id

        # Check if this entity belongs to a source
        source_name = self._entity_sources.get(entity_id)
        if source_name:
            # Check if it's a Location clone source (format: "location:owner/repo")
            if source_name.startswith("location:"):
                repo_key = source_name[len("location:"):]  # "owner/repo"
                clone_info = self._location_clones.get(repo_key)
                if clone_info:
                    # Save to the Location clone directory
                    kind_dir = CatalogScanner.KIND_DIRS.get(kind, f"{kind.lower()}s")
                    if clone_info.path:
                        file_path = clone_info.local_path / clone_info.path / kind_dir / f"{name}.yaml"
                    else:
                        file_path = clone_info.local_path / kind_dir / f"{name}.yaml"

                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    self._writer.write_entity(entity, file_path)

                    # Auto-commit for Location clones
                    self._sync_manager.repo_manager.commit_location(
                        clone_info.owner,
                        clone_info.repo,
                        clone_info.branch,
                        f"Update {entity_id}",
                    )

                    self.reload()
                    return

            # Check if it's a GitHub Source
            source = self._get_github_source(source_name)
            if source and source.sync_enabled:
                self._save_to_github_source(entity, source)
                return

        # New entity: save to primary GitHub Source
        primary_source = self._get_primary_sync_source()
        if primary_source is None:
            raise RuntimeError("No GitHub Source configured. Please add a GitHub Source in Settings.")

        self._save_to_github_source(entity, primary_source)

    def _save_to_github_source(self, entity: Entity, source: GitHubSource) -> None:
        """Save an entity to a GitHub Source clone directory.

        Args:
            entity: Entity to save.
            source: GitHub source to save to.
        """
        kind = entity.kind.value
        name = entity.metadata.name
        entity_id = entity.entity_id

        clone_path = self._sync_manager.repo_manager.get_clone_path(source)
        if not clone_path.exists():
            raise RuntimeError(f"Clone path does not exist for source: {source.name}")

        # Determine the relative path within the clone
        kind_dir = CatalogScanner.KIND_DIRS.get(kind, f"{kind.lower()}s")
        if source.path:
            base_dir = clone_path / source.path
        else:
            # Auto-detect catalogs directory (same logic as CatalogScanner)
            catalogs_subdir = clone_path / "catalogs"
            if catalogs_subdir.exists():
                base_dir = catalogs_subdir
            else:
                base_dir = clone_path
        file_path = base_dir / kind_dir / f"{name}.yaml"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer.write_entity(entity, file_path)

        # Auto-commit if enabled
        if source.auto_commit:
            self._sync_manager.repo_manager.commit(
                source,
                f"Update {entity_id}",
            )

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

    # ========== Multi-Scorecard Methods ==========

    def get_scorecards(self) -> list[dict[str, Any]]:
        """Get all registered scorecards."""
        return self._score_queries.get_scorecards()

    def get_active_scorecards(self) -> list[dict[str, Any]]:
        """Get all active scorecards."""
        return self._score_queries.get_active_scorecards()

    def get_scorecard(self, scorecard_id: str) -> dict[str, Any] | None:
        """Get a specific scorecard by ID."""
        return self._score_queries.get_scorecard(scorecard_id)

    def set_scorecard_status(self, scorecard_id: str, status: str) -> None:
        """Update a scorecard's status (draft/active/archived)."""
        self._score_queries.update_scorecard_status(scorecard_id, status)

    def delete_scorecard(self, scorecard_id: str) -> None:
        """Delete a scorecard and all its related data."""
        self._score_queries.delete_scorecard(scorecard_id)

    def create_scorecard(self, name: str, description: str | None = None) -> None:
        """Create a new scorecard with empty scores and ranks.

        Args:
            name: Scorecard name/ID (used as filename and metadata.name)
            description: Optional description
        """
        # Build ScorecardDefinition with empty spec
        scorecard = ScorecardDefinition(
            metadata=ScorecardDefinitionMetadata(
                name=name,
                title=name,
                description=description,
            ),
            spec=ScorecardDefinitionSpec(
                scores=[],
                ranks=[],
            ),
        )

        # Save to file and reload
        self.save_scorecard_definition(scorecard)

    def get_score_definitions_for_scorecard(
        self, scorecard_id: str
    ) -> list[dict[str, Any]]:
        """Get score definitions for a specific scorecard.

        Args:
            scorecard_id: Scorecard ID (required - all scores belong to a scorecard)
        """
        return self._score_queries.get_score_definitions_for_scorecard(scorecard_id)

    def get_rank_definitions_for_scorecard(
        self, scorecard_id: str
    ) -> list[dict[str, Any]]:
        """Get rank definitions for a specific scorecard.

        Args:
            scorecard_id: Scorecard ID (required - all ranks belong to a scorecard)
        """
        return self._score_queries.get_rank_definitions_for_scorecard(scorecard_id)

    def get_entity_scores(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all scores for an entity."""
        return self._score_queries.get_entity_scores(entity_id)

    def get_entity_ranks(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all computed ranks for an entity."""
        return self._score_queries.get_entity_ranks(entity_id)

    def get_all_scores_with_entities(
        self, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all scores with entity information."""
        return self._score_queries.get_all_scores_with_entities(scorecard_id)

    def get_leaderboard(
        self, rank_id: str, limit: int = 100, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get top entities by rank."""
        return self._score_queries.get_leaderboard(rank_id, limit, scorecard_id)

    def get_dashboard_summary(
        self, scorecard_id: str | None = None
    ) -> dict[str, Any]:
        """Get aggregated scorecard data for dashboard."""
        return self._score_queries.get_dashboard_summary(scorecard_id)

    def get_score_distribution(
        self, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get score distribution by score type (for charts)."""
        return self._score_queries.get_score_distribution(scorecard_id)

    def get_rank_label_distribution(
        self, rank_id: str | None = None, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get rank label distribution (S/A/B/C/D counts) for charts."""
        return self._score_queries.get_rank_label_distribution(rank_id, scorecard_id)

    def get_score_trends(self, days: int = 30) -> list[dict[str, Any]]:
        """Get score trends over time (daily aggregates) for charts."""
        return self._score_queries.get_score_trends(days)

    # ========== Heatmap Data Methods ==========

    def get_kind_score_average(
        self, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get average scores by Kind × Score Type for heatmap."""
        return self._score_queries.get_kind_score_average(scorecard_id)

    def get_entity_score_matrix(
        self, limit: int = 50, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get entity × score type matrix data for heatmap."""
        return self._score_queries.get_entity_score_matrix(limit, scorecard_id)

    def get_kind_rank_distribution(
        self, rank_id: str, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get Kind × Rank Label distribution for heatmap."""
        return self._score_queries.get_kind_rank_distribution(rank_id, scorecard_id)

    def get_entities_comparison(
        self, scorecard_a: str, scorecard_b: str
    ) -> list[dict[str, Any]]:
        """Get entities with ranks from both scorecards for comparison."""
        return self._score_queries.get_entities_comparison(scorecard_a, scorecard_b)

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
        data = scorecard.model_dump(exclude_none=True, by_alias=True, mode="json")

        # Use scorecard name for filename
        scorecard_name = scorecard.metadata.name
        filename = f"{scorecard_name}.yaml"

        # Check for sync-enabled GitHub source
        source = self._get_primary_sync_source()
        if source:
            clone_path = self._sync_manager.repo_manager.get_clone_path(source)
            if clone_path.exists():
                # Save to GitHub clone
                if source.path:
                    base_dir = clone_path / source.path
                else:
                    # Auto-detect catalogs directory (same logic as CatalogScanner)
                    catalogs_subdir = clone_path / "catalogs"
                    if catalogs_subdir.exists():
                        base_dir = catalogs_subdir
                    else:
                        base_dir = clone_path
                scorecard_dir = base_dir / "scorecards"

                scorecard_dir.mkdir(parents=True, exist_ok=True)
                path = scorecard_dir / filename

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
                        f"Update scorecard definition: {scorecard_name}",
                    )

                self.reload()
                return

        # Default: save to local catalogs directory
        if self._root_path.name == "catalogs" and self._root_path.is_dir():
            catalogs_dir = self._root_path
        else:
            catalogs_dir = self._root_path / "catalogs"

        scorecard_dir = catalogs_dir / "scorecards"
        scorecard_dir.mkdir(parents=True, exist_ok=True)
        path = scorecard_dir / filename

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

    def get_recent_score_changes(
        self, limit: int = 20, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent score changes for dashboard."""
        return self._history_queries.get_recent_score_changes(limit, scorecard_id)

    def get_recent_rank_changes(
        self, limit: int = 20, scorecard_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent rank changes for dashboard."""
        return self._history_queries.get_recent_rank_changes(limit, scorecard_id)

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

    def record_definition_history_with_snapshot(
        self,
        definition_type: str,
        definition_id: str,
        change_type: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        changed_fields: list[str] | None = None,
        before_ranks: dict[str, dict[str, Any]] | None = None,
        after_ranks: dict[str, dict[str, Any]] | None = None,
        scorecard_id: str | None = None,
    ) -> int | None:
        """Record a definition change with an impact snapshot.

        This method records the definition change and creates a snapshot
        capturing the before/after rank changes for affected entities.

        Args:
            definition_type: Type of definition ("score" or "rank")
            definition_id: ID of the definition
            change_type: Type of change ("created", "updated", "deleted")
            old_value: Previous definition value (for updates/deletes)
            new_value: New definition value (for creates/updates)
            changed_fields: List of changed field names
            before_ranks: Dict mapping entity_id -> {value, label} before change
            after_ranks: Dict mapping entity_id -> {value, label} after change
            scorecard_id: Optional scorecard ID for multi-scorecard support

        Returns:
            Snapshot ID if created, None if no snapshot (e.g., score definition change)
        """
        from datetime import datetime

        timestamp = datetime.utcnow().isoformat() + "Z"

        # Insert definition history and get the ID
        definition_history_id = self._history_queries.insert_definition_history_with_id(
            definition_type,
            definition_id,
            change_type,
            old_value,
            new_value,
            changed_fields,
            timestamp,
            scorecard_id,
        )

        # Save to YAML for persistence
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

        # Create snapshot for rank definition changes
        if definition_type == "rank" and before_ranks is not None and after_ranks is not None:
            return self._create_rank_impact_snapshot(
                definition_history_id,
                definition_id,
                before_ranks,
                after_ranks,
                timestamp,
                scorecard_id,
            )

        return None

    def _create_rank_impact_snapshot(
        self,
        definition_history_id: int,
        definition_id: str,
        before_ranks: dict[str, dict[str, Any]],
        after_ranks: dict[str, dict[str, Any]],
        timestamp: str,
        scorecard_id: str | None = None,
    ) -> int:
        """Create a snapshot capturing rank impacts from a definition change.

        Args:
            definition_history_id: ID of the definition history entry
            definition_id: ID of the rank definition
            before_ranks: Dict mapping entity_id -> {value, label} before change
            after_ranks: Dict mapping entity_id -> {value, label} after change
            timestamp: ISO timestamp for the snapshot
            scorecard_id: Optional scorecard ID

        Returns:
            Snapshot ID
        """
        # Compute impacts
        impacts = []
        all_entity_ids = set(before_ranks.keys()) | set(after_ranks.keys())

        for entity_id in all_entity_ids:
            before = before_ranks.get(entity_id)
            after = after_ranks.get(entity_id)

            if before is None and after is not None:
                # New entity or newly applicable rank
                change_type = "new"
            elif before is not None and after is None:
                # Entity removed or rank no longer applicable
                change_type = "removed"
            elif before is not None and after is not None:
                before_label = before.get("label")
                after_label = after.get("label")
                before_value = before.get("value")
                after_value = after.get("value")

                if before_label == after_label and before_value == after_value:
                    change_type = "unchanged"
                elif after_value is not None and before_value is not None:
                    if after_value > before_value:
                        change_type = "improved"
                    else:
                        change_type = "degraded"
                else:
                    change_type = "unchanged"
            else:
                continue  # Should not happen

            impacts.append({
                "entity_id": entity_id,
                "before_value": before.get("value") if before else None,
                "before_label": before.get("label") if before else None,
                "after_value": after.get("value") if after else None,
                "after_label": after.get("label") if after else None,
                "change_type": change_type,
            })

        # Count affected (exclude unchanged)
        total_affected = sum(1 for i in impacts if i["change_type"] != "unchanged")

        # Insert snapshot
        snapshot_id = self._history_queries.insert_definition_change_snapshot(
            definition_history_id,
            "rank",
            definition_id,
            total_affected,
            timestamp,
            scorecard_id,
        )

        # Insert impact entries
        self._history_queries.insert_rank_impact_entries(snapshot_id, impacts)

        # Save to YAML for persistence
        history_writer = self._get_history_writer_for_definitions()
        history_writer.add_definition_change_snapshot(
            definition_id, timestamp, total_affected, impacts, scorecard_id
        )

        return snapshot_id

    def get_all_entity_ranks_for_definition(
        self, rank_id: str, scorecard_id: str
    ) -> dict[str, dict[str, Any]]:
        """Get current ranks for all entities for a specific rank definition.

        Args:
            rank_id: The rank definition ID
            scorecard_id: Scorecard ID (required - all ranks belong to a scorecard)

        Returns:
            Dict mapping entity_id -> {value, label}
        """
        result = self._score_queries.get_all_ranks_for_definition(rank_id, scorecard_id)
        return {
            row["entity_id"]: {"value": row["value"], "label": row["label"]}
            for row in result
        }

    def get_definition_change_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        """Get a definition change snapshot by ID."""
        return self._history_queries.get_definition_change_snapshot(snapshot_id)

    def get_snapshots_for_definition(
        self, definition_type: str, definition_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get all snapshots for a definition."""
        return self._history_queries.get_snapshots_for_definition(
            definition_type, definition_id, limit
        )

    def get_rank_impacts_for_snapshot(self, snapshot_id: int) -> list[dict[str, Any]]:
        """Get all rank impact entries for a snapshot."""
        return self._history_queries.get_rank_impacts_for_snapshot(snapshot_id)

    def get_recent_definition_change_snapshots(
        self, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent definition change snapshots."""
        return self._history_queries.get_recent_definition_change_snapshots(limit)

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

        If the entity belongs to a GitHub source or Location clone, returns
        a HistoryWriter for the clone directory. Otherwise, returns the
        default local HistoryWriter.

        Args:
            entity_id: Entity ID.

        Returns:
            HistoryWriter for the appropriate directory.
        """
        source_name = self._entity_sources.get(entity_id)
        if source_name:
            # Check if it's a Location clone source
            if source_name.startswith("location:"):
                repo_key = source_name[len("location:"):]
                clone_info = self._location_clones.get(repo_key)
                if clone_info:
                    # Use catalogs/ directory for history (same as loading)
                    catalogs_dir = clone_info.local_path / "catalogs"
                    if catalogs_dir.exists():
                        base_path = catalogs_dir
                    elif clone_info.path:
                        # Fallback: try to find 'catalogs' in the path
                        parts = clone_info.path.split("/")
                        if "catalogs" in parts:
                            idx = parts.index("catalogs")
                            base_path = clone_info.local_path / "/".join(parts[: idx + 1])
                        else:
                            base_path = clone_info.local_path / clone_info.path
                    else:
                        base_path = clone_info.local_path
                    return HistoryWriter(base_path)

            # Check if it's a GitHub Source
            source = self._get_github_source(source_name)
            if source and source.sync_enabled:
                clone_path = self._sync_manager.repo_manager.get_clone_path(source)
                if clone_path.exists():
                    if source.path:
                        base_path = clone_path / source.path
                    else:
                        # Auto-detect catalogs directory (same logic as CatalogScanner)
                        catalogs_subdir = clone_path / "catalogs"
                        if catalogs_subdir.exists():
                            base_path = catalogs_subdir
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
                    # Auto-detect catalogs directory (same logic as CatalogScanner)
                    catalogs_subdir = clone_path / "catalogs"
                    if catalogs_subdir.exists():
                        base_path = catalogs_subdir
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
            # Check if it's a Location clone source
            if source_name.startswith("location:"):
                repo_key = source_name[len("location:"):]
                clone_info = self._location_clones.get(repo_key)
                if clone_info:
                    self._sync_manager.repo_manager.commit_location(
                        clone_info.owner,
                        clone_info.repo,
                        clone_info.branch,
                        message,
                    )
                return

            # Check if it's a GitHub Source
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

    def force_sync_source(
        self,
        source_name: str,
        on_progress: Any = None,
    ) -> SyncResult:
        """Force sync a source, discarding all local changes.

        This resets the local clone to match the remote exactly.

        Args:
            source_name: Name of the GitHub source.
            on_progress: Progress callback.

        Returns:
            SyncResult with success status and message.
        """
        source = self._get_github_source(source_name)
        if source is None:
            return SyncResult(success=False, message="Source not found")

        result = self._sync_manager.force_sync(source, on_progress)

        if result.success:
            # Reload entire catalog after force sync
            self.reload()

        return result

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

    # ========== Location Clone Methods ==========

    def get_location_clones(self) -> dict[str, LocationCloneInfo]:
        """Get all Location clones.

        Returns:
            Dictionary mapping repo_key ("owner/repo") to LocationCloneInfo.
        """
        return self._location_clones.copy()

    def get_location_clone_status(
        self, owner: str, repo: str, branch: str
    ) -> dict[str, Any] | None:
        """Get git status for a Location clone.

        Args:
            owner: GitHub owner/org
            repo: Repository name
            branch: Branch name

        Returns:
            Status dict with modified/added/deleted/untracked/ahead/behind info.
        """
        status = self._sync_manager.repo_manager.get_location_status(owner, repo, branch)
        if status is None:
            return None

        return {
            "modified": status.modified,
            "added": status.added,
            "deleted": status.deleted,
            "untracked": status.untracked,
            "ahead": status.ahead,
            "behind": status.behind,
            "has_conflicts": status.has_conflicts,
        }

    def push_location_clone(
        self, owner: str, repo: str, branch: str
    ) -> SyncResult:
        """Push changes for a Location clone.

        Args:
            owner: GitHub owner/org
            repo: Repository name
            branch: Branch name

        Returns:
            SyncResult with success status and message.
        """
        success, message = self._sync_manager.repo_manager.push_location(
            owner, repo, branch
        )
        return SyncResult(success=success, message=message)

    def pull_location_clone(
        self, owner: str, repo: str, branch: str
    ) -> SyncResult:
        """Pull changes for a Location clone.

        Args:
            owner: GitHub owner/org
            repo: Repository name
            branch: Branch name

        Returns:
            SyncResult with success status and message.
        """
        clone_path = self._sync_manager.repo_manager.get_location_clone_path(
            owner, repo, branch
        )
        if not clone_path.exists():
            return SyncResult(success=False, message="Clone not found")

        # Fetch and merge
        self._sync_manager.repo_manager._fetch(clone_path, branch)

        import subprocess
        try:
            result = subprocess.run(
                ["git", "-C", str(clone_path), "merge", f"origin/{branch}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                self.reload()
                return SyncResult(success=True, message="Pull successful")
            else:
                if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
                    return SyncResult(success=False, message="Merge conflict detected")
                return SyncResult(success=False, message=result.stderr)
        except Exception as e:
            return SyncResult(success=False, message=str(e))

    def create_location_pr(
        self,
        owner: str,
        repo: str,
        branch: str,
        title: str,
        body: str,
    ) -> SyncResult:
        """Create a PR for Location clone changes.

        Creates a new branch, pushes changes, and opens a PR.

        Args:
            owner: GitHub owner/org
            repo: Repository name
            branch: Base branch name
            title: PR title
            body: PR body/description

        Returns:
            SyncResult with PR URL if successful.
        """
        import subprocess
        import time

        clone_path = self._sync_manager.repo_manager.get_location_clone_path(
            owner, repo, branch
        )
        if not clone_path.exists():
            return SyncResult(success=False, message="Clone not found")

        # Create a unique branch name
        pr_branch = f"bkstg-sync-{int(time.time())}"

        try:
            # Create and checkout new branch
            result = subprocess.run(
                ["git", "-C", str(clone_path), "checkout", "-b", pr_branch],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return SyncResult(success=False, message=f"Failed to create branch: {result.stderr}")

            # Push new branch
            result = subprocess.run(
                ["git", "-C", str(clone_path), "push", "-u", "origin", pr_branch],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                # Checkout back to original branch
                subprocess.run(
                    ["git", "-C", str(clone_path), "checkout", branch],
                    capture_output=True,
                    timeout=30,
                )
                return SyncResult(success=False, message=f"Failed to push: {result.stderr}")

            # Create PR using gh CLI
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo", f"{owner}/{repo}",
                    "--base", branch,
                    "--head", pr_branch,
                    "--title", title,
                    "--body", body,
                ],
                capture_output=True,
                text=True,
                cwd=str(clone_path),
                timeout=60,
            )

            # Checkout back to original branch
            subprocess.run(
                ["git", "-C", str(clone_path), "checkout", branch],
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                pr_url = result.stdout.strip()
                return SyncResult(success=True, message=f"PR created: {pr_url}", pr_url=pr_url)
            else:
                return SyncResult(success=False, message=f"Failed to create PR: {result.stderr}")

        except subprocess.TimeoutExpired:
            return SyncResult(success=False, message="Operation timed out")
        except Exception as e:
            return SyncResult(success=False, message=str(e))
