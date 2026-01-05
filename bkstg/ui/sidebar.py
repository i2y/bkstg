"""Navigation sidebar component."""

from castella import Button, Column, Component, Row, Spacer, Text


# Entity kind icons and colors
KIND_STYLES = {
    "Component": {"icon": "[C]", "color": "#4fc3f7"},
    "API": {"icon": "[A]", "color": "#81c784"},
    "Resource": {"icon": "[R]", "color": "#ffb74d"},
    "System": {"icon": "[S]", "color": "#ba68c8"},
    "Domain": {"icon": "[D]", "color": "#f06292"},
    "User": {"icon": "[U]", "color": "#90a4ae"},
    "Group": {"icon": "[G]", "color": "#a1887f"},
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
        total = sum(self._counts.values())

        return Column(
            # Logo/title
            Text("bkstg", font_size=28).fixed_height(60),
            Text("Mini IDP", font_size=12).fixed_height(24),
            Spacer().fixed_height(20),
            # Navigation buttons
            self._nav_button("Catalog", "catalog"),
            self._nav_button("Dependencies", "graph"),
            self._nav_button("Dashboard", "dashboard"),
            self._nav_button("Editor", "editor"),
            Spacer().fixed_height(30),
            # Entity counts section
            Row(
                Text("Entities", font_size=14),
                Spacer(),
                Text(str(total), font_size=14).text_color("#4fc3f7"),
            ).fixed_height(30),
            Spacer().fixed_height(4),
            # Individual kind counts with badges
            *[
                self._count_row(kind, self._counts.get(kind, 0))
                for kind in KIND_STYLES.keys()
            ],
            Spacer(),
        ).bg_color("#1a1b26")

    def _nav_button(self, label: str, view: str):
        is_active = self._active_view == view

        return (
            Button(label)
            .on_click(lambda _: self._on_view_change(view))
            .bg_color("#3d5a80" if is_active else "#2a2b3d")
        ).fixed_height(40)

    def _count_row(self, kind: str, count: int):
        style = KIND_STYLES.get(kind, {"icon": "[-]", "color": "#aaa"})

        return Row(
            Text(style["icon"], font_size=12).text_color(style["color"]).fixed_width(30),
            Text(kind, font_size=12),
            Spacer(),
            Text(str(count), font_size=12).text_color(style["color"]).fixed_width(30),
        ).fixed_height(24)
