"""Welcome view for first-time setup."""

import re
from typing import Callable

from castella import (
    Button,
    Column,
    Component,
    Input,
    InputState,
    Row,
    Spacer,
    State,
    Text,
)

from ..i18n import t


class WelcomeView(Component):
    """Welcome screen for first-time setup."""

    def __init__(self, on_complete: Callable[[dict], None]):
        super().__init__()
        self._on_complete = on_complete
        self._url_state = InputState("")
        self._url_state.attach(self)
        self._error_message = State("")
        self._error_message.attach(self)

    def view(self):
        error = self._error_message()

        return Column(
            Spacer(),
            Row(
                Spacer(),
                Column(
                    # Title
                    Text(t("welcome.title"), font_size=32).erase_border(),
                    Spacer().fixed_height(16),
                    # Description
                    Text(t("welcome.description"), font_size=14).erase_border(),
                    Spacer().fixed_height(24),
                    # URL input
                    Text(t("welcome.url_label"), font_size=12).erase_border(),
                    Spacer().fixed_height(8),
                    Input(self._url_state).fixed_height(40),
                    Spacer().fixed_height(8),
                    # Example hint
                    Text(t("welcome.example"), font_size=11).erase_border(),
                    Spacer().fixed_height(16),
                    # Error message
                    (
                        Text(error, font_size=12).text_color("#ff6b6b").erase_border()
                        if error
                        else Spacer().fixed_height(16)
                    ),
                    Spacer().fixed_height(16),
                    # Start button
                    Row(
                        Spacer(),
                        Button(t("welcome.start"))
                        .on_click(self._on_start)
                        .fixed_width(120)
                        .fixed_height(40),
                        Spacer(),
                    ).fixed_height(40),
                ).fixed_width(500),
                Spacer(),
            ),
            Spacer(),
        )

    def _on_start(self, _):
        """Handle start button click."""
        url = self._url_state.value().strip()
        if not url:
            self._error_message.set(t("welcome.invalid_url"))
            return

        parsed = self._parse_github_url(url)
        if parsed is None:
            self._error_message.set(t("welcome.invalid_url"))
            return

        self._error_message.set("")
        self._on_complete(parsed)

    def _parse_github_url(self, url: str) -> dict | None:
        """Parse GitHub URL to extract owner, repo, branch, and path.

        Supported formats:
        - https://github.com/owner/repo
        - https://github.com/owner/repo/tree/branch
        - https://github.com/owner/repo/tree/branch/path/to/catalogs
        - github.com/owner/repo (without https://)
        """
        # Normalize URL
        url = url.strip()
        if url.startswith("github.com"):
            url = "https://" + url

        # Pattern for GitHub URLs
        pattern = r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)(?:/(.+))?)?"
        match = re.match(pattern, url)

        if not match:
            return None

        owner = match.group(1)
        repo = match.group(2)
        branch = match.group(3) or "main"
        path = match.group(4) or ""

        # Remove .git suffix if present
        if repo.endswith(".git"):
            repo = repo[:-4]

        return {
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "path": path,
        }
