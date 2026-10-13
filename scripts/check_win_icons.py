"""Verify official icon images in both Windows binaries, not just the launcher."""
import json
from pathlib import Path
import struct


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    version = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
    ico = (root / "assets/icons/icon.ico").read_bytes()
    count = struct.unpack_from("<H", ico, 4)[0]
    images = []
    for i in range(count):
        width, _, _, _, _, _, size, offset = struct.unpack_from("<BBBBHHII", ico, 6 + 16 * i)
        images.append((width or 256, ico[offset:offset + size]))
    for relative in (f"ConstellaLab-{version}-portable.exe", "win-unpacked/ConstellaLab.exe"):
        executable = root / "dist-electron" / relative
        binary = executable.read_bytes()
        missing = [width for width, image in images if image not in binary]
        if missing:
            raise SystemExit(
                f"{relative}: official icon sizes missing: {missing}. "
                "Do not disable signAndEditExecutable; Linux resource editing needs Wine."
            )
        print(f"[icons] {relative}: all {count} official icon images embedded")


if __name__ == "__main__":
    main()
