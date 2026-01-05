"""Entry point for bkstg application."""

import sys
from pathlib import Path

from castella import App
from castella.frame import Frame

from .ui import BkstgApp


def main():
    """Run bkstg application."""
    # Get catalog path from command line or use current directory
    if len(sys.argv) > 1:
        catalog_path = sys.argv[1]
    else:
        catalog_path = "."

    catalog_path = Path(catalog_path).resolve()

    # Create and run app
    app = App(
        Frame("bkstg - Mini IDP", width=1400, height=900),
        BkstgApp(str(catalog_path)),
    )
    app.run()


if __name__ == "__main__":
    main()
