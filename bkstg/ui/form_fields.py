"""Reusable form field components for entity editing."""

from typing import Callable

from castella import (
    Button,
    CheckBox,
    Column,
    Component,
    Input,
    InputState,
    MultilineInput,
    MultilineInputState,
    RadioButtonsState,
    Row,
    Spacer,
    State,
    Text,
)
from castella.theme import ThemeManager

from ..i18n import t


class ButtonSelectState:
    """State for ButtonSelect component."""

    def __init__(self, options: list[str], selected_index: int = 0, on_change: Callable[[int], None] | None = None):
        self._options = options
        self._selected_index = selected_index
        self._on_change = on_change
        self._state = State(selected_index)

    def attach(self, component: Component):
        self._state.attach(component)

    def options(self) -> list[str]:
        return self._options

    def selected_index(self) -> int:
        return self._selected_index

    def selected_value(self) -> str:
        if 0 <= self._selected_index < len(self._options):
            return self._options[self._selected_index]
        return ""

    def select(self, index: int):
        if self._selected_index != index:
            self._selected_index = index
            # Call on_change BEFORE state.set() to update form_data before re-render
            if self._on_change:
                self._on_change(index)
            self._state.set(index)

    def set_on_change(self, callback: Callable[[int], None]):
        self._on_change = callback


class ButtonSelect(Component):
    """Horizontal button-based selector."""

    def __init__(self, state: ButtonSelectState):
        super().__init__()
        self._state = state
        self._state.attach(self)

    def view(self):
        theme = ThemeManager().current
        buttons = []
        selected = self._state.selected_index()
        for i, option in enumerate(self._state.options()):
            is_selected = i == selected
            btn = (
                Button(option)
                .on_click(lambda _, idx=i: self._on_select(idx))
                .fixed_height(32)
            )
            if is_selected:
                btn = btn.bg_color(theme.colors.bg_selected)
            else:
                btn = btn.bg_color(theme.colors.bg_secondary)
            buttons.append(btn)
            buttons.append(Spacer().fixed_width(4))

        return Row(*buttons).fixed_height(36)

    def _on_select(self, index: int):
        self._state.select(index)


class TextField(Component):
    """Single-line text input field with label."""

    def __init__(
        self,
        label: str,
        state: InputState,
        required: bool = False,
        placeholder: str = "",
        error: str = "",
    ):
        super().__init__()
        self._label = label
        self._state = state
        self._required = required
        self._placeholder = placeholder
        self._error = error

    def view(self):
        theme = ThemeManager().current
        label_text = f"{self._label} *" if self._required else self._label

        return Column(
            Text(label_text, font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Input(self._state).fixed_height(36),
            (
                Text(self._error, font_size=11).text_color(theme.colors.text_danger).fixed_height(16)
                if self._error
                else Spacer().fixed_height(4)
            ),
        ).fixed_height(76)


class TextAreaField(Component):
    """Multi-line text input field with label."""

    def __init__(
        self,
        label: str,
        state: MultilineInputState,
        required: bool = False,
        height: int = 100,
        error: str = "",
        font_size: int = 13,
    ):
        super().__init__()
        self._label = label
        self._state = state
        self._required = required
        self._height = height
        self._error = error
        self._font_size = font_size

    def view(self):
        theme = ThemeManager().current
        label_text = f"{self._label} *" if self._required else self._label
        # Total height = label (20) + input (height) + error/spacer (4) + margins (8)
        total_height = 20 + self._height + 4 + 8

        return Column(
            Text(label_text, font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            # Use fit_parent() so MultilineInput expands to fill the remaining space
            MultilineInput(self._state, font_size=self._font_size).fit_parent(),
            (
                Text(self._error, font_size=11).text_color(theme.colors.text_danger).fixed_height(16)
                if self._error
                else Spacer().fixed_height(4)
            ),
        ).fixed_height(total_height)


class SelectField(Component):
    """Selection field using custom radio buttons with consistent sizing."""

    def __init__(
        self,
        label: str,
        options: list[str],
        state: RadioButtonsState,
        required: bool = False,
        error: str = "",
    ):
        super().__init__()
        self._label = label
        self._options = options
        self._state = state
        self._required = required
        self._error = error
        self._state.attach(self)

    def view(self):
        theme = ThemeManager().current
        label_text = f"{self._label} *" if self._required else self._label
        selected_index = self._state.selected_index()

        # Build radio button rows with consistent sizing
        radio_rows = []
        for i, option in enumerate(self._options):
            is_selected = i == selected_index
            radio_rows.append(
                Row(
                    CheckBox(is_selected, is_circle=True)
                    .on_click(lambda _, idx=i: self._state.select(idx))
                    .fixed_width(20)
                    .fixed_height(20),
                    Spacer().fixed_width(8),
                    Text(option, font_size=12).text_color(theme.colors.text_primary).fixed_height(20),
                    Spacer(),
                ).fixed_height(28)
            )

        # Scrollable list with max height (about 3 items visible)
        radio_list = Column(*radio_rows, scrollable=True).fixed_height(90)

        # Fixed width to prevent stretching
        return Column(
            Text(label_text, font_size=13).text_color(theme.colors.text_primary).fixed_height(24),
            radio_list,
            Spacer().fixed_height(4),
        ).fixed_width(160)


class TagEditor(Component):
    """Tag input with add/remove functionality."""

    def __init__(
        self,
        label: str,
        tags: list[str],
        on_change: Callable[[list[str]], None],
    ):
        super().__init__()
        self._label = label
        self._tags = tags
        self._on_change = on_change
        self._input_state = InputState("")
        self._input_state.attach(self)
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        tag_widgets = []
        for i, tag in enumerate(self._tags):
            tag_widgets.append(
                Row(
                    Text(tag, font_size=12)
                    .text_color(theme.colors.text_primary)
                    .bg_color(theme.colors.bg_secondary)
                    .fixed_height(24),
                    Button(t("common.x"))
                    .on_click(lambda _, idx=i: self._remove_tag(idx))
                    .fixed_width(24)
                    .fixed_height(24),
                ).fixed_height(24)
            )
            tag_widgets.append(Spacer().fixed_width(4))

        return Column(
            Text(self._label, font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Row(
                *tag_widgets,
                Spacer(),
            ).fixed_height(28),
            Row(
                Input(self._input_state).flex(1).fixed_height(32),
                Spacer().fixed_width(8),
                Button(t("common.add")).on_click(self._add_tag).fixed_width(60).fixed_height(32),
            ).fixed_height(36),
            Spacer().fixed_height(4),
        )

    def _add_tag(self, _):
        """Add a new tag."""
        new_tag = self._input_state.value().strip()
        if new_tag and new_tag not in self._tags:
            self._tags.append(new_tag)
            self._input_state.set("")
            self._on_change(self._tags)
            self._render_trigger.set(self._render_trigger() + 1)

    def _remove_tag(self, index: int):
        """Remove a tag by index."""
        if 0 <= index < len(self._tags):
            self._tags.pop(index)
            self._on_change(self._tags)
            self._render_trigger.set(self._render_trigger() + 1)


class ArrayField(Component):
    """Array input for list of strings (like dependsOn, providesApis)."""

    def __init__(
        self,
        label: str,
        items: list[str],
        on_change: Callable[[list[str]], None],
        placeholder: str = "Add item...",
    ):
        super().__init__()
        self._label = label
        self._items = items
        self._on_change = on_change
        self._placeholder = placeholder
        self._input_state = InputState("")
        self._input_state.attach(self)
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        item_widgets = []
        for i, item in enumerate(self._items):
            item_widgets.append(
                Row(
                    Text(item, font_size=12).flex(1),
                    Button(t("common.x"))
                    .on_click(lambda _, idx=i: self._remove_item(idx))
                    .fixed_width(28)
                    .fixed_height(28),
                ).fixed_height(32).bg_color(theme.colors.bg_secondary)
            )
            item_widgets.append(Spacer().fixed_height(4))

        return Column(
            Text(self._label, font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            *item_widgets,
            Row(
                Input(self._input_state).flex(1).fixed_height(32),
                Spacer().fixed_width(8),
                Button(t("common.add")).on_click(self._add_item).fixed_width(60).fixed_height(32),
            ).fixed_height(36),
            Spacer().fixed_height(8),
        )

    def _add_item(self, _):
        """Add a new item."""
        new_item = self._input_state.value().strip()
        if new_item and new_item not in self._items:
            self._items.append(new_item)
            self._input_state.set("")
            self._on_change(self._items)
            self._render_trigger.set(self._render_trigger() + 1)

    def _remove_item(self, index: int):
        """Remove an item by index."""
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._on_change(self._items)
            self._render_trigger.set(self._render_trigger() + 1)
