"""Navigation sidebar component."""

from castella import Button, Column, Component, Row, Spacer, Text
from castella.theme import ThemeManager

from ..i18n import t


def _get_kind_styles():
    """Get entity kind icons and colors from theme."""
    theme = ThemeManager().current
    return {
        "Component": {"icon": "[C]", "color": theme.colors.text_info},      # cyan
        "API": {"icon": "[A]", "color": theme.colors.text_success},         # green
        "Resource": {"icon": "[R]", "color": "#ff9e64"},                    # orange
        "System": {"icon": "[S]", "color": "#bb9af7"},                      # magenta
        "Domain": {"icon": "[D]", "color": theme.colors.text_danger},       # red
        "User": {"icon": "[U]", "color": theme.colors.fg},                  # fg
        "Group": {"icon": "[G]", "color": theme.colors.text_warning},       # yellow
    }


class Sidebar(Component):
    """Navigation sidebar."""

    def __init__(
        self,
        active_view: str,
        on_view_change,
        counts: dict[str, int],
    ):
        super().__init__()
        self._active_view = active_view
        self._on_view_change = on_view_change
        self._counts = counts

    def view(self):
        theme = ThemeManager().current
        total = sum(self._counts.values())
        kind_styles = _get_kind_styles()

        return Column(
            # Logo/title
            Text(t("app.name"), font_size=28).fixed_height(60),
            Text(t("app.subtitle"), font_size=12).fixed_height(24),
            Spacer().fixed_height(20),
            # Navigation buttons
            self._nav_button(t("nav.about"), "about"),
            self._nav_button(t("nav.catalog"), "catalog"),
            self._nav_button(t("nav.dependencies"), "graph"),
            self._nav_button(t("nav.dashboard"), "dashboard"),
            self._nav_button(t("nav.editor"), "editor"),
            self._nav_button(t("nav.sync"), "sync"),
            Spacer().fixed_height(16),
            self._nav_button(t("nav.settings"), "settings"),
            Spacer().fixed_height(20),
            # Entity counts section
            Row(
                Text(t("nav.entities"), font_size=14),
                Spacer(),
                Text(str(total), font_size=14).text_color(theme.colors.text_info),
            ).fixed_height(30),
            Spacer().fixed_height(4),
            # Individual kind counts with badges
            *[
                self._count_row(kind, self._counts.get(kind, 0), kind_styles)
                for kind in kind_styles.keys()
            ],
            Spacer(),
        ).bg_color(theme.colors.bg_primary)

    def _nav_button(self, label: str, view: str):
        theme = ThemeManager().current
        is_active = self._active_view == view

        return (
            Button(label)
            .on_click(lambda _: self._on_view_change(view))
            .bg_color(theme.colors.bg_selected if is_active else theme.colors.bg_secondary)
        ).fixed_height(40)

    def _count_row(self, kind: str, count: int, kind_styles: dict):
        theme = ThemeManager().current
        style = kind_styles.get(kind, {"icon": "[-]", "color": theme.colors.fg})

        return Row(
            Text(style["icon"], font_size=12).text_color(style["color"]).fixed_width(30),
            Text(kind, font_size=12),
            Spacer(),
            Text(str(count), font_size=12).text_color(style["color"]).fixed_width(30),
        ).fixed_height(24)
