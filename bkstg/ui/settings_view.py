"""Settings view component."""

from castella import Button, Column, Component, Row, Spacer, State, Text
from castella.theme import ThemeManager

from ..i18n import t, get_locale, set_locale, detect_os_locale, SUPPORTED_LOCALES
from ..state.catalog_state import CatalogState


class SettingsView(Component):
    """Settings view with language and other configuration options."""

    def __init__(self, catalog_state: CatalogState):
        super().__init__()
        self._catalog_state = catalog_state
        self._render_trigger = State(0)
        self._render_trigger.attach(self)
        self._status = State("")
        self._status.attach(self)

    def view(self):
        theme = ThemeManager().current
        # Read configured locale from config (not the detected/applied locale)
        config = self._catalog_state.get_config()
        configured_locale = config.settings.locale
        status = self._status()

        # Language options: auto, en, ja
        locale_options = [("auto", t("settings.language_auto"))]
        for loc in SUPPORTED_LOCALES:
            label_key = f"settings.language_{loc}"
            locale_options.append((loc, t(label_key)))

        # Build language selector buttons
        lang_buttons = []
        for loc_code, loc_label in locale_options:
            is_selected = configured_locale == loc_code
            lang_buttons.append(
                Button(loc_label)
                .on_click(lambda _, lc=loc_code: self._change_language(lc))
                .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
                .fixed_height(36)
            )
            lang_buttons.append(Spacer().fixed_width(8))

        return Column(
            Spacer().fixed_height(16),
            # Header
            Text(t("nav.settings"), font_size=24).text_color(theme.colors.text_primary).fixed_height(40),
            Spacer().fixed_height(24),
            # Language section
            Text(t("settings.language"), font_size=16).text_color(theme.colors.text_primary).fixed_height(28),
            Spacer().fixed_height(8),
            Row(*lang_buttons, Spacer()).fixed_height(44),
            # Status message
            (
                Row(
                    Spacer().fixed_height(16),
                    Text(status, font_size=12).text_color(theme.colors.text_success),
                ).fixed_height(24)
                if status
                else Spacer().fixed_height(16)
            ),
            Spacer(),
        ).flex(1)

    def _change_language(self, locale_code: str):
        """Change language and update config."""
        # Apply the actual locale (detect OS locale if "auto")
        actual_locale = detect_os_locale() if locale_code == "auto" else locale_code
        set_locale(actual_locale)
        # Update config file (save the user's choice, not the detected locale)
        config = self._catalog_state.get_config()
        config.settings.locale = locale_code
        self._catalog_state.update_config(config)
        self._status.set(t("status.saved"))
        # Trigger re-render of this view
        self._render_trigger.set(self._render_trigger() + 1)
