"""Internationalization support for bkstg.

This module provides i18n functionality for the bkstg application.
It wraps Castella's i18n system and loads bkstg-specific translations.

Usage:
    from bkstg.i18n import init_i18n, t

    # Initialize i18n at app startup
    init_i18n()  # Auto-detect from OS
    init_i18n("ja")  # or explicit locale

    # Use translations in UI
    Button(t("common.save"))
    Text(t("validation.required", field=t("entity.field.name")))
"""

import locale
import os
from pathlib import Path
from typing import Any

from castella.i18n import I18nManager, LocalePluralString, LocaleString, load_yaml_catalog

# Path to bkstg translations
_LOCALES_DIR = Path(__file__).parent / "locales"

# Supported locales
SUPPORTED_LOCALES = ["en", "ja", "zh-Hant", "zh-Hans", "ko"]


def detect_os_locale() -> str:
    """Detect the OS language setting.

    Returns:
        Detected locale code ('en', 'ja', etc.), defaults to 'en' if not detected
    """
    import sys

    # On macOS, prioritize AppleLanguages (system GUI language)
    # over environment variables (which may be set differently for terminal)
    if sys.platform == "darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                # Parse output like: (\n    "ja-JP",\n    "en-US"\n)
                for line in result.stdout.split("\n"):
                    line = line.strip().strip('",')
                    if line and not line.startswith("(") and not line.startswith(")"):
                        # Extract language code (e.g., "ja-JP" -> "ja")
                        lang_code = line.split("-")[0].lower()
                        if lang_code in SUPPORTED_LOCALES:
                            return lang_code
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    # Try environment variables (for Linux and fallback)
    for env_var in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        lang = os.environ.get(env_var, "")
        if lang:
            # Extract language code (e.g., "ja_JP.UTF-8" -> "ja")
            lang_code = lang.split("_")[0].split(".")[0].lower()
            if lang_code in SUPPORTED_LOCALES:
                return lang_code

    # Try Python's locale module
    try:
        system_locale = locale.getdefaultlocale()[0]
        if system_locale:
            lang_code = system_locale.split("_")[0].lower()
            if lang_code in SUPPORTED_LOCALES:
                return lang_code
    except (ValueError, TypeError):
        pass

    # Default to English
    return "en"


def init_i18n(locale_code: str | None = None) -> None:
    """Initialize bkstg internationalization.

    Loads all available translation catalogs and sets the initial locale.

    Args:
        locale_code: Initial locale code (e.g., 'en', 'ja').
                     If None or 'auto', auto-detect from OS settings.
    """
    manager = I18nManager()

    # Load all available locale files
    if _LOCALES_DIR.exists():
        for yaml_file in _LOCALES_DIR.glob("*.yaml"):
            try:
                catalog = load_yaml_catalog(yaml_file)
                manager.load_catalog(catalog.locale, catalog)
            except Exception as e:
                print(f"Warning: Failed to load locale {yaml_file}: {e}")

    # Determine locale to use
    if locale_code is None or locale_code == "auto":
        locale_code = detect_os_locale()

    # Set initial locale
    manager.set_locale(locale_code)


def t(key: str, **kwargs: Any) -> str:
    """Translate a key using the current locale.

    Args:
        key: Translation key (dot-notation, e.g., 'common.save')
        **kwargs: Values for string interpolation

    Returns:
        Translated string, or the key itself if not found

    Example:
        t("common.save")  # Returns "Save" or "保存"
        t("status.showing", count=5, total=100)  # Returns "Showing 5 of 100 entities"
    """
    return I18nManager().t(key, **kwargs)


def tn(key: str, count: int, **kwargs: Any) -> str:
    """Translate a key with pluralization.

    Args:
        key: Translation key for plural forms
        count: Count for plural selection
        **kwargs: Additional interpolation values

    Returns:
        Translated string with appropriate plural form

    Example:
        tn("entities", 1)  # Returns "1 entity"
        tn("entities", 5)  # Returns "5 entities"
    """
    return I18nManager().tn(key, count, **kwargs)


def get_locale() -> str:
    """Get the current locale.

    Returns:
        Current locale code (e.g., 'en', 'ja')
    """
    return I18nManager().locale


def set_locale(locale: str) -> None:
    """Set the current locale.

    Args:
        locale: Locale code (e.g., 'en', 'ja')
    """
    I18nManager().set_locale(locale)


def available_locales() -> list[str]:
    """Get list of available locales.

    Returns:
        List of locale codes that have been loaded
    """
    return I18nManager().available_locales


__all__ = [
    "init_i18n",
    "t",
    "tn",
    "get_locale",
    "set_locale",
    "available_locales",
    "detect_os_locale",
    "SUPPORTED_LOCALES",
    "LocaleString",
    "LocalePluralString",
]
