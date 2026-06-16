#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# SKRYPT: Pobieranie brakujących flag emoji (Twemoji)
# ---------------------------------------------------------------------------
# W folderze assets/Emoji_PNG brakuje plików PNG dla flag krajów (np. Polska).
# Są tylko pojedyncze litery regionalne (u1F1F5.png) oraz tysiące plików
# glyphNNNNN.png bez informacji Unicode – stąd flagi są niewidoczne i nie da
# się ich wyszukać.
#
# Ten skrypt pobiera brakujące obrazki flag z Twemoji (open source) i zapisuje
# je pod nazwami zgodnymi z naszym indeksem, np. u1F1F5_1F1F1.png.
#
# Uruchomienie (wymaga internetu):
#     python scripts/fetch_flag_emojis.py
# ---------------------------------------------------------------------------

import json
import os
import sys
import urllib.error
import urllib.request

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_META_PATH = os.path.join(_PKG_ROOT, "assets", "emoji_meta.json")
_EMOJI_DIR = os.path.join(_PKG_ROOT, "assets", "Emoji_PNG")
_TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"


# Zamienia klucz metadanych (np. "1f1f5-1f1f1") na nazwę pliku PNG
# w naszym formacie (np. "u1F1F5_1F1F1.png").
def key_to_filename(key):
    parts = key.split("-")
    if len(parts) == 1:
        return f"u{parts[0].upper()}.png"
    return "u" + "_".join(p.upper() for p in parts) + ".png"


def fetch_flags():
    if not os.path.isfile(_META_PATH):
        print(f"[flags] Missing {_META_PATH} – run scripts/build_emoji_meta.py first.")
        return 1

    with open(_META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    groups = meta.get("groups", [])
    flags_group = groups.index("Flags") if "Flags" in groups else -1
    if flags_group < 0:
        print("[flags] No Flags group in metadata.")
        return 1

    os.makedirs(_EMOJI_DIR, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    for key, info in meta.get("emoji", {}).items():
        if info.get("g") != flags_group:
            continue

        filename = key_to_filename(key)
        dest = os.path.join(_EMOJI_DIR, filename)
        if os.path.isfile(dest):
            skipped += 1
            continue

        url = f"{_TWEMOJI_BASE}/{key}.png"
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = resp.read()
            if len(data) < 50:
                print(f"[flags] Skip tiny response: {filename}")
                failed += 1
                continue
            with open(dest, "wb") as out:
                out.write(data)
            downloaded += 1
            if downloaded % 50 == 0:
                print(f"[flags] Downloaded {downloaded}...")
        except urllib.error.HTTPError as exc:
            print(f"[flags] HTTP {exc.code} for {key} ({filename})")
            failed += 1
        except OSError as exc:
            print(f"[flags] Error {key}: {exc}")
            failed += 1

    print(
        f"[flags] Done: {downloaded} downloaded, {skipped} already present, "
        f"{failed} failed."
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(fetch_flags())
