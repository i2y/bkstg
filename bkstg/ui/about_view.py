"""About view component displaying catalog repository README."""

from pathlib import Path

from castella import Column, Component, Markdown, Spacer, Text
from castella.theme import ThemeManager

from ..config import GitHubSource
from ..i18n import t
from ..state.catalog_state import CatalogState


class AboutView(Component):
    """Displays about.md or README.md from the catalog repository."""

    # File names to search for, in priority order
    MARKDOWN_FILES = ["about.md", "README.md", "readme.md"]

    def __init__(self, catalog_state: CatalogState):
        super().__init__()
        self._catalog_state = catalog_state

    def view(self):
        theme = ThemeManager().current
        content = self._load_markdown()

        if content:
            # Replace ```yaml with ``` to avoid Pygments YAML token error
            content = content.replace("```yaml", "```")
            return Markdown(content, base_font_size=14)
        else:
            return Column(
                Spacer().fixed_height(20),
                Text(t("about.no_file"), font_size=14).text_color(theme.colors.fg),
            )

    def _load_markdown(self) -> str | None:
        """Load markdown content from the catalog repository.

        Searches for about.md, README.md, or readme.md in the repository root
        (not the catalogs directory).

        Returns:
            Markdown content as string, or None if not found.
        """
        config = self._catalog_state.get_config()
        repo_manager = self._catalog_state._sync_manager.repo_manager

        for source in config.sources:
            if isinstance(source, GitHubSource) and source.enabled:
                clone_path = repo_manager.get_clone_path(source)
                if clone_path.exists():
                    for filename in self.MARKDOWN_FILES:
                        file_path = clone_path / filename
                        if file_path.exists():
                            try:
                                return file_path.read_text(encoding="utf-8")
                            except Exception:
                                continue
        return None
