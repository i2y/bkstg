"""Configuration file loader and writer."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .models import BkstgConfig, LocalSource

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load and save bkstg configuration."""

    CONFIG_FILENAME = "bkstg.yaml"
    USER_CONFIG_DIR = Path.home() / ".bkstg"

    def __init__(self, project_path: Path | None = None):
        """Initialize config loader.

        Args:
            project_path: Project directory path. If None, uses current directory.
        """
        self._project_path = project_path or Path.cwd()

    def get_config_path(self) -> Path | None:
        """Find config file (project-level first, then user-level).

        Returns:
            Path to config file if found, None otherwise.
        """
        # Check project-level first
        project_config = self._project_path / self.CONFIG_FILENAME
        if project_config.exists():
            return project_config

        # Check user-level
        user_config = self.USER_CONFIG_DIR / self.CONFIG_FILENAME
        if user_config.exists():
            return user_config

        return None

    def load(self) -> BkstgConfig:
        """Load configuration, returning defaults if no config exists.

        Returns:
            BkstgConfig with loaded or default values.
        """
        config_path = self.get_config_path()
        if config_path is None:
            logger.debug("No config file found, using defaults")
            return self._default_config()

        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            logger.info(f"Loaded config from: {config_path}")
            return BkstgConfig.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            return self._default_config()

    def save(self, config: BkstgConfig, user_level: bool = False) -> Path:
        """Save configuration to file.

        Args:
            config: Configuration to save.
            user_level: If True, save to user-level config directory.

        Returns:
            Path where config was saved.
        """
        if user_level:
            self.USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            config_path = self.USER_CONFIG_DIR / self.CONFIG_FILENAME
        else:
            config_path = self._project_path / self.CONFIG_FILENAME

        data = config.model_dump(exclude_none=True)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        logger.info(f"Saved config to: {config_path}")
        return config_path

    def _default_config(self) -> BkstgConfig:
        """Create default configuration with local source.

        Returns:
            BkstgConfig with default local source.
        """
        return BkstgConfig(
            sources=[
                LocalSource(
                    path="./catalogs",
                    name="Local Catalogs",
                    enabled=True,
                )
            ]
        )


def load_config(project_path: Path | str | None = None) -> BkstgConfig:
    """Load configuration from project or user directory.

    Convenience function that creates a ConfigLoader and loads config.

    Args:
        project_path: Project directory path. If None, uses current directory.

    Returns:
        BkstgConfig with loaded or default values.
    """
    path = Path(project_path) if project_path else None
    return ConfigLoader(path).load()
