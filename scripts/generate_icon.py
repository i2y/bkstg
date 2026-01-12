#!/usr/bin/env python3
"""Generate macOS app icon for bkstg."""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Icon sizes for macOS (Apple Human Interface Guidelines)
ICON_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

# Colors
GRADIENT_START = (107, 70, 193)  # #6B46C1 (purple)
GRADIENT_END = (59, 130, 246)  # #3B82F6 (blue)
TEXT_COLOR = (255, 255, 255)  # white


def create_gradient(size: int) -> Image.Image:
    """Create a diagonal gradient from purple to blue."""
    img = Image.new("RGB", (size, size))
    pixels = img.load()

    for y in range(size):
        for x in range(size):
            # Diagonal gradient (top-left to bottom-right)
            t = (x + y) / (2 * size - 2) if size > 1 else 0
            r = int(GRADIENT_START[0] + (GRADIENT_END[0] - GRADIENT_START[0]) * t)
            g = int(GRADIENT_START[1] + (GRADIENT_END[1] - GRADIENT_START[1]) * t)
            b = int(GRADIENT_START[2] + (GRADIENT_END[2] - GRADIENT_START[2]) * t)
            pixels[x, y] = (r, g, b)

    return img


def get_font(size: int) -> ImageFont.FreeTypeFont:
    """Get a bold system font at the specified size."""
    # Try common macOS system fonts
    font_paths = [
        "/System/Library/Fonts/SFNSTextCondensed-Bold.otf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]

    for font_path in font_paths:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue

    # Fallback to default
    return ImageFont.load_default()


def create_icon(size: int) -> Image.Image:
    """Create a single icon at the specified size."""
    img = create_gradient(size)
    draw = ImageDraw.Draw(img)

    # Calculate font size (approximately 35% of icon size for "bkstg")
    font_size = max(int(size * 0.35), 8)
    font = get_font(font_size)

    text = "bkstg"

    # Get text bounding box for centering
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Center the text
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]  # Adjust for baseline

    draw.text((x, y), text, font=font, fill=TEXT_COLOR)

    return img


def main():
    """Generate all icon sizes and create .icns file."""
    project_root = Path(__file__).parent.parent
    iconset_dir = project_root / "assets" / "icon.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)

    print("Generating icon images...")
    for filename, size in ICON_SIZES:
        icon = create_icon(size)
        icon_path = iconset_dir / filename
        icon.save(icon_path, "PNG")
        print(f"  Created {filename} ({size}x{size})")

    # Generate .icns file using iconutil
    icns_path = project_root / "assets" / "icon.icns"
    print(f"\nGenerating {icns_path}...")

    try:
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
            check=True,
            capture_output=True,
        )
        print(f"Successfully created {icns_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error running iconutil: {e.stderr.decode()}")
        raise
    except FileNotFoundError:
        print("iconutil not found. Make sure you're running on macOS.")
        raise

    print("\nDone!")


if __name__ == "__main__":
    main()
