"""Settings view component."""

from castella import (
    Button,
    Column,
    Component,
    Input,
    InputState,
    Row,
    Spacer,
    State,
    Tabs,
    TabItem,
    TabsState,
    Text,
)
from castella.theme import ThemeManager

from ..i18n import t, set_locale, detect_os_locale, SUPPORTED_LOCALES
from ..state.catalog_state import CatalogState
from .source_settings import CatalogSourcesSettingsTab


class SettingsView(Component):
    """Settings view with tabs for general settings and sources configuration."""

    def __init__(
        self,
        catalog_state: CatalogState,
        status: str = "",
        on_status_change: callable = None,
    ):
        super().__init__()
        self._catalog_state = catalog_state
        self._status = status  # Status passed from parent (persists across re-renders)
        self._on_status_change = on_status_change
        # Initialize GitHub org input state
        config = catalog_state.get_config()
        self._github_org_state = InputState(config.settings.github_org or "")
        self._github_org_state.attach(self)
        # Tab state
        self._active_tab = State("language")
        self._active_tab.attach(self)

    def view(self):
        theme = ThemeManager().current
        active_tab = self._active_tab()

        tab_items = [
            TabItem(id="language", label=t("settings.tab.language"), content=Spacer()),
            TabItem(id="github", label=t("settings.tab.github"), content=Spacer()),
            TabItem(id="sources", label=t("settings.tab.sources"), content=Spacer()),
        ]
        tabs_state = TabsState(tabs=tab_items, selected_id=active_tab)

        return Column(
            Spacer().fixed_height(16),
            # Header
            Text(t("nav.settings"), font_size=24).text_color(theme.colors.text_primary).fixed_height(40),
            Spacer().fixed_height(16),
            # Tabs
            Tabs(tabs_state).on_change(self._handle_tab_change).fixed_height(44),
            Spacer().fixed_height(16),
            # Content
            self._build_content(active_tab),
        ).flex(1)

    def _handle_tab_change(self, tab_id: str):
        self._active_tab.set(tab_id)

    def _build_content(self, tab: str):
        if tab == "language":
            return self._build_language_settings()
        elif tab == "github":
            return self._build_github_settings()
        elif tab == "sources":
            return CatalogSourcesSettingsTab(self._catalog_state)
        return Spacer()

    def _build_language_settings(self):
        """Build language settings content."""
        theme = ThemeManager().current
        config = self._catalog_state.get_config()
        configured_locale = config.settings.locale
        status = self._status  # Use prop from parent

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

    def _build_github_settings(self):
        """Build GitHub settings content."""
        theme = ThemeManager().current
        status = self._status  # Use prop from parent

        return Column(
            # GitHub org section
            Text(t("settings.github_org"), font_size=16).text_color(theme.colors.text_primary).fixed_height(28),
            Spacer().fixed_height(8),
            Row(
                Input(self._github_org_state).fixed_height(36).fixed_width(300),
                Spacer().fixed_width(8),
                Button(t("common.save"))
                .on_click(lambda _: self._save_github_org())
                .fixed_height(36),
                Spacer(),
            ).fixed_height(36),
            Spacer().fixed_height(4),
            Text(t("settings.github_org_hint"), font_size=12).text_color(theme.colors.fg).fixed_height(20),
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
        # Update config file first (save the user's choice, not the detected locale)
        config = self._catalog_state.get_config()
        config.settings.locale = locale_code
        self._catalog_state.update_config(config)

        # Apply the actual locale (detect OS locale if "auto")
        actual_locale = detect_os_locale() if locale_code == "auto" else locale_code

        # Set locale (this triggers app-wide re-render via I18nManager listeners)
        from ..i18n import I18nManager
        manager = I18nManager()
        manager.set_locale(actual_locale)

        # Set status via parent callback (will be shown after re-render)
        if self._on_status_change:
            self._on_status_change(t("status.saved"))

    def _save_github_org(self):
        """Save GitHub org setting."""
        org = self._github_org_state.value().strip()
        config = self._catalog_state.get_config()
        config.settings.github_org = org if org else None
        self._catalog_state.update_config(config)
        if self._on_status_change:
            self._on_status_change(t("status.saved"))
