"""Read and parse entity YAML files."""

from pathlib import Path
from typing import Any

import yaml

from ..models import (
    API,
    Component,
    Domain,
    Entity,
    Group,
    Resource,
    System,
    User,
)
from ..models.base import EntityKind


class EntityReader:
    """Read and parse entity YAML files."""

    ENTITY_CLASSES = {
        EntityKind.COMPONENT: Component,
        EntityKind.API: API,
        EntityKind.RESOURCE: Resource,
        EntityKind.SYSTEM: System,
        EntityKind.DOMAIN: Domain,
        EntityKind.USER: User,
        EntityKind.GROUP: Group,
    }

    def read_entity(self, path: Path) -> Entity | None:
        """Read and parse a single entity file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data:
                return self.parse_entity(data)
        except (yaml.YAMLError, OSError, ValueError) as e:
            print(f"Warning: Failed to read entity from {path}: {e}")
        return None

    def parse_entity(self, data: dict[str, Any]) -> Entity | None:
        """Parse dict to appropriate Entity type."""
        kind_str = data.get("kind")
        if not kind_str:
            return None

        try:
            kind = EntityKind(kind_str)
        except ValueError:
            print(f"Warning: Unknown entity kind: {kind_str}")
            return None

        entity_class = self.ENTITY_CLASSES.get(kind)
        if not entity_class:
            return None

        try:
            return entity_class.model_validate(data)
        except ValueError as e:
            print(f"Warning: Failed to validate entity: {e}")
            return None

    def parse_entities(
        self, items: list[tuple[Path, dict[str, Any]]]
    ) -> list[tuple[Path, Entity]]:
        """Parse multiple entities from (path, data) tuples."""
        results = []
        for path, data in items:
            entity = self.parse_entity(data)
            if entity:
                results.append((path, entity))
        return results
