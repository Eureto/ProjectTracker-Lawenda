#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# SKRYPT: Regenerowanie całego zestawu emoji PNG
# ---------------------------------------------------------------------------
# Pobiera spójny zestaw obrazków emoji z Twemoji i zapisuje je pod nazwami
# Unicode, np.:
#   u1F600.png
#   u1F1F5_1F1F1.png
#   u1F3F3_200D_1F308.png
#
# Dzięki temu picker nie musi zgadywać, czym jest plik glyphNNNNN.png.
# Każdy plik ma nazwę, którą screens/emoji_index.py potrafi jednoznacznie
# połączyć z assets/emoji_meta.json (kategorie, kolejność, wyszukiwanie).
#
# Uruchomienie:
#     python scripts/regenerate_emoji_assets.py
#     python scripts/build_emoji_zip.py
# ---------------------------------------------------------------------------

import concurrent.futures
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_META_PATH = os.path.join(_PKG_ROOT, "assets", "emoji_meta.json")
_EMOJI_DIR = os.path.join(_PKG_ROOT, "assets", "Emoji_PNG")
_TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72"
_MAX_WORKERS = 16
_VARIATION_SELECTOR = "fe0f"


def _filename_from_key(key):
    parts = [p.upper() for p in key.split("-") if p != _VARIATION_SELECTOR]
    if not parts:
        return None
    return "u" + "_".join(parts) + ".png"


def _normalize_asset_key(asset_key):
    parts = []
    for part in asset_key.split("-"):
        try:
            parts.append(f"{int(part, 16):x}")
        except ValueError:
            parts.append(part.lower())
    return "-".join(parts)


def _candidate_asset_keys(entry_key, entry):
    # Pierwsza próba: pełny klucz z emoji-test.txt (z FE0F tam, gdzie Unicode
    # go wymaga). Druga: wersja bez FE0F, bo Twemoji dla prostych symboli
    # często tak właśnie nazywa pliki (np. "2764.png", nie "2764-fe0f.png").
    raw = _normalize_asset_key(entry.get("u") or entry_key)
    stripped = "-".join(p for p in raw.split("-") if p != _VARIATION_SELECTOR)
    candidates = [raw, stripped, _normalize_asset_key(entry_key)]

    out = []
    for candidate in candidates:
        if candidate and candidate not in out:
            out.append(candidate)
    return out


def _download_one(item):
    entry_key, entry, dest_dir = item
    filename = _filename_from_key(entry_key)
    if not filename:
        return ("skip", entry_key, "empty filename")

    dest_path = os.path.join(dest_dir, filename)
    for asset_key in _candidate_asset_keys(entry_key, entry):
        url = f"{_TWEMOJI_BASE}/{asset_key}.png"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
            if len(data) < 50:
                continue
            with open(dest_path, "wb") as f:
                f.write(data)
            return ("ok", entry_key, asset_key)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            return ("fail", entry_key, f"HTTP {exc.code}")
        except OSError as exc:
            return ("fail", entry_key, str(exc))

    return ("fail", entry_key, "not found")


def regenerate():
    if not os.path.isfile(_META_PATH):
        print("[emoji-assets] Missing assets/emoji_meta.json. Run build_emoji_meta.py first.")
        return 1

    with open(_META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    entries = sorted(
        meta.get("emoji", {}).items(),
        key=lambda kv: kv[1].get("o", 10**9),
    )
    if not entries:
        print("[emoji-assets] No emoji metadata entries found.")
        return 1

    parent = os.path.dirname(_EMOJI_DIR)
    temp_dir = tempfile.mkdtemp(prefix=".Emoji_PNG.", dir=parent)
    failures = []
    downloaded = 0

    print(f"[emoji-assets] Downloading {len(entries)} emoji from Twemoji...")
    try:
        work = [(key, entry, temp_dir) for key, entry in entries]
        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            for status, key, detail in executor.map(_download_one, work):
                if status == "ok":
                    downloaded += 1
                    if downloaded % 250 == 0:
                        print(f"[emoji-assets] Downloaded {downloaded}...")
                elif status == "fail":
                    failures.append((key, detail))

        if downloaded < 1000:
            print(
                f"[emoji-assets] Only downloaded {downloaded} files; "
                "keeping existing assets."
            )
            return 1

        if os.path.isdir(_EMOJI_DIR):
            shutil.rmtree(_EMOJI_DIR)
        os.replace(temp_dir, _EMOJI_DIR)
        temp_dir = None

        print(
            f"[emoji-assets] Replaced assets/Emoji_PNG: "
            f"{downloaded} PNGs downloaded, {len(failures)} missing."
        )
        if failures:
            print("[emoji-assets] Missing examples:")
            for key, detail in failures[:20]:
                print(f"  {key}: {detail}")
        return 0 if len(failures) < 50 else 1
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    raise SystemExit(regenerate())
