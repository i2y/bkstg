"""Location processor for fetching entities from remote sources."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .github_fetcher import GitHubFetcher

if TYPE_CHECKING:
    from bkstg.models import Location

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for fetched content."""

    content: str
    fetched_at: float


@dataclass
class LocationProcessor:
    """Processes Location entities and fetches remote content.

    Handles:
    - GitHub URL targets (via gh CLI)
    - Local file targets
    - Caching with TTL
    - Circular reference detection
    """

    root_path: Path
    cache_ttl: int = 300  # 5 minutes default
    _cache: dict[str, CacheEntry] = field(default_factory=dict)
    _visited: set[str] = field(default_factory=set)
    _fetcher: GitHubFetcher = field(default_factory=GitHubFetcher)

    def clear_cache(self) -> None:
        """Clear all cached content."""
        self._cache.clear()

    def reset_visited(self) -> None:
        """Reset visited URLs (call before each reload cycle)."""
        self._visited.clear()

    def process_locations(
        self, locations: list[Location]
    ) -> list[tuple[str, dict]]:
        """Process all Location entities and fetch their targets.

        Args:
            locations: List of Location entities to process.

        Returns:
            List of (source_url, parsed_yaml_dict) tuples for fetched entities.
        """
        self.reset_visited()
        results: list[tuple[str, dict]] = []

        for location in locations:
            fetched = self._process_single(location)
            results.extend(fetched)

        return results

    def _process_single(self, location: Location) -> list[tuple[str, dict]]:
        """Process a single Location entity.

        Args:
            location: Location entity to process.

        Returns:
            List of (source_url, parsed_yaml_dict) tuples.
        """
        results: list[tuple[str, dict]] = []
        targets = location.get_all_targets()
        presence = location.spec.presence
        location_type = location.spec.type

        for target in targets:
            # Check for circular reference
            if target in self._visited:
                logger.warning(f"Circular reference detected, skipping: {target}")
                continue

            self._visited.add(target)

            # Determine how to fetch the target
            if self._is_url(target):
                content = self._fetch_url(target, presence)
            else:
                content = self._fetch_local(target, location_type, presence)

            if content is None:
                continue

            # Parse YAML content
            parsed = self._parse_yaml(content, target, presence)
            if parsed:
                results.append((target, parsed))

        return results

    def _is_url(self, target: str) -> bool:
        """Check if target is a URL."""
        return target.startswith("http://") or target.startswith("https://")

    def _fetch_url(self, url: str, presence: str) -> str | None:
        """Fetch content from URL with caching.

        Args:
            url: URL to fetch.
            presence: "required" or "optional".

        Returns:
            Content string, or None if fetch failed.
        """
        # Check cache
        now = time.time()
        if url in self._cache:
            entry = self._cache[url]
            if now - entry.fetched_at < self.cache_ttl:
                logger.debug(f"Cache hit for: {url}")
                return entry.content

        # Fetch from GitHub
        if self._fetcher.is_github_url(url):
            content = self._fetcher.fetch_from_url(url)
            if content is not None:
                self._cache[url] = CacheEntry(content=content, fetched_at=now)
                logger.info(f"Fetched from GitHub: {url}")
                return content
            else:
                if presence == "required":
                    logger.error(f"Failed to fetch required URL: {url}")
                else:
                    logger.warning(f"Failed to fetch optional URL: {url}")
                return None
        else:
            logger.warning(f"Unsupported URL type (only GitHub URLs supported): {url}")
            return None

    def _fetch_local(
        self, target: str, location_type: str | None, presence: str
    ) -> str | None:
        """Fetch content from local file.

        Args:
            target: File path (relative or absolute).
            location_type: Location type hint.
            presence: "required" or "optional".

        Returns:
            Content string, or None if read failed.
        """
        # Resolve path relative to root
        if target.startswith("./") or target.startswith("../"):
            path = self.root_path / target
        else:
            path = Path(target)

        path = path.resolve()

        try:
            content = path.read_text(encoding="utf-8")
            logger.info(f"Read local file: {path}")
            return content
        except FileNotFoundError:
            if presence == "required":
                logger.error(f"Required local file not found: {path}")
            else:
                logger.warning(f"Optional local file not found: {path}")
            return None
        except Exception as e:
            logger.warning(f"Error reading local file {path}: {e}")
            return None

    def _parse_yaml(
        self, content: str, source: str, presence: str
    ) -> dict | None:
        """Parse YAML content.

        Args:
            content: YAML string to parse.
            source: Source URL/path for logging.
            presence: "required" or "optional".

        Returns:
            Parsed dict, or None if parsing failed.
        """
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                logger.warning(f"YAML content is not a dict: {source}")
                return None
            return data
        except yaml.YAMLError as e:
            if presence == "required":
                logger.error(f"Failed to parse required YAML from {source}: {e}")
            else:
                logger.warning(f"Failed to parse optional YAML from {source}: {e}")
            return None
