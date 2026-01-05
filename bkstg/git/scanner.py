"""Scan catalog directory for YAML entity files."""

from pathlib import Path
from typing import Iterator

import yaml


class CatalogScanner:
    """Scan catalog directory for YAML entity files."""

    KIND_DIRS = {
        "Component": "components",
        "API": "apis",
        "Resource": "resources",
        "System": "systems",
        "Domain": "domains",
        "User": "users",
        "Group": "groups",
    }

    def __init__(self, root_path: str | Path):
        self.root = Path(root_path)
        # If the path itself is named "catalogs", use it directly
        # Otherwise, look for a "catalogs" subdirectory
        if self.root.name == "catalogs" and self.root.is_dir():
            self.catalogs_dir = self.root
        else:
            self.catalogs_dir = self.root / "catalogs"

    # Directories to skip when scanning for standard entities
    SKIP_DIRS = {"scorecards"}

    def scan(self) -> Iterator[tuple[Path, dict]]:
        """Yield (file_path, parsed_yaml) for all YAML files."""
        if not self.catalogs_dir.exists():
            return

        for yaml_file in self.catalogs_dir.rglob("*.yaml"):
            # Skip non-entity directories (e.g., scorecards)
            if any(skip_dir in yaml_file.parts for skip_dir in self.SKIP_DIRS):
                continue

            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        yield yaml_file, data
            except (yaml.YAMLError, OSError) as e:
                print(f"Warning: Failed to parse {yaml_file}: {e}")

    def scan_by_kind(self, kind: str) -> Iterator[tuple[Path, dict]]:
        """Scan specific kind directory (e.g., catalogs/components/)."""
        dir_name = self.KIND_DIRS.get(kind)
        if not dir_name:
            return

        kind_dir = self.catalogs_dir / dir_name
        if not kind_dir.exists():
            return

        for yaml_file in kind_dir.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        yield yaml_file, data
            except (yaml.YAMLError, OSError) as e:
                print(f"Warning: Failed to parse {yaml_file}: {e}")

    def get_file_path_for_entity(self, kind: str, name: str) -> Path:
        """Get the expected file path for an entity."""
        dir_name = self.KIND_DIRS.get(kind, kind.lower() + "s")
        return self.catalogs_dir / dir_name / f"{name}.yaml"

    def ensure_catalogs_dir(self) -> None:
        """Create catalogs directory structure if it doesn't exist."""
        for dir_name in self.KIND_DIRS.values():
            (self.catalogs_dir / dir_name).mkdir(parents=True, exist_ok=True)
