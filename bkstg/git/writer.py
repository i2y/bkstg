"""Write entity YAML files."""

from pathlib import Path

import yaml

from ..models import Entity


class EntityWriter:
    """Write entity back to YAML file."""

    def write_entity(self, entity: Entity, path: Path) -> None:
        """Write entity to YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        # mode="json" ensures Enums are serialized as strings
        data = entity.model_dump(exclude_none=True, by_alias=True, mode="json")

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    def write_entity_str(self, entity: Entity) -> str:
        """Convert entity to YAML string."""
        # mode="json" ensures Enums are serialized as strings
        data = entity.model_dump(exclude_none=True, by_alias=True, mode="json")
        return yaml.dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
