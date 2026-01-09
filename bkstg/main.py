"""Entry point for bkstg application."""

import sys
from pathlib import Path

from castella import App
from castella.frame import Frame

from .config.loader import load_config
from .i18n import init_i18n
from .ui import BkstgApp


def main():
    """Run bkstg application."""
    # Get catalog path from command line or use ~/.bkstg
    if len(sys.argv) > 1:
        catalog_path = Path(sys.argv[1]).resolve()
    else:
        catalog_path = Path.home() / ".bkstg"
        catalog_path.mkdir(parents=True, exist_ok=True)

    catalog_path = Path(catalog_path).resolve()

    # Load config and initialize i18n
    config = load_config(catalog_path)
    init_i18n(config.settings.locale)

    # Create and run app
    app = App(
        Frame("bkstg - Mini IDP", width=1400, height=900),
        BkstgApp(str(catalog_path)),
    )
    app.run()


if __name__ == "__main__":
    main()
