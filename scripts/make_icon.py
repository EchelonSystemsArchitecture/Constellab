"""Generate every derived app icon from the single official logo.

Source of truth: assets/icons/icon.png (square, >= 1024 px).
Outputs:
  assets/icons/icon.ico       multi-resolution Windows icon (electron-builder / .exe)
  frontend/public/favicon.png 256 px favicon served by Vite / packaged frontend

Requires Pillow:  python -m pip install pillow
Run via:          npm run icon
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: python -m pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "icons" / "icon.png"
ICO = ROOT / "assets" / "icons" / "icon.ico"
FAVICON = ROOT / "frontend" / "public" / "favicon.png"
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
FAVICON_SIZE = 256


def main() -> None:
    if not SOURCE.exists():
        sys.exit(f"missing source icon: {SOURCE}")
    src = Image.open(SOURCE).convert("RGBA")
    if src.width != src.height or src.width < 256:
        sys.exit(f"source icon must be square and >= 256 px, got {src.size}")

    def resized(size: int) -> Image.Image:
        return src.resize((size, size), Image.LANCZOS)

    resized(ICO_SIZES[-1]).save(
        ICO, format="ICO", sizes=[(s, s) for s in ICO_SIZES], bitmap_format="png"
    )
    resized(FAVICON_SIZE).save(FAVICON, format="PNG", optimize=True)
    print(f"wrote {ICO.relative_to(ROOT)} ({', '.join(map(str, ICO_SIZES))} px)")
    print(f"wrote {FAVICON.relative_to(ROOT)} ({FAVICON_SIZE} px)")


if __name__ == "__main__":
    main()
