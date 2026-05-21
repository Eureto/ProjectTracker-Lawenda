#!/usr/bin/env python3
"""Build assets/Emoji_PNG.zip only when the source PNGs changed."""

import os
import sys
import tempfile
import zipfile


SRC = os.path.join("assets", "Emoji_PNG")
DST = os.path.join("assets", "Emoji_PNG.zip")


def _png_files():
    out = []
    for root, _dirs, files in os.walk(SRC):
        for name in files:
            if name.lower().endswith(".png"):
                out.append(os.path.join(root, name))
    out.sort()
    return out


def _zip_is_current(files):
    if not os.path.exists(DST):
        return False
    zip_mtime = os.path.getmtime(DST)
    return all(os.path.getmtime(path) <= zip_mtime for path in files)


def main():
    if not os.path.isdir(SRC):
        print(f"[emoji-zip] Missing source directory: {SRC}", file=sys.stderr)
        return 1

    files = _png_files()
    if _zip_is_current(files):
        print(f"[emoji-zip] {DST} is current ({len(files)} PNGs).")
        return 0

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".Emoji_PNG.", suffix=".zip", dir=os.path.dirname(DST))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in files:
                zf.write(path, os.path.relpath(path, SRC))
        os.replace(tmp, DST)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    size_mb = os.path.getsize(DST) / (1024 * 1024)
    print(f"[emoji-zip] Wrote {DST}: {len(files)} PNGs, {size_mb:.1f} MB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
