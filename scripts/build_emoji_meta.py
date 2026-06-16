#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# SKRYPT: Generowanie metadanych emoji (kategorie, kolejność, słowa kluczowe)
# ---------------------------------------------------------------------------
# Picker emoji potrzebuje dla każdego emoji trzech informacji:
#   1. kategorii (np. "Smileys & Emotion", "Flags") – do zakładek i grupowania,
#   2. oficjalnej kolejności wyświetlania (z Unicode) – żeby emoji nie były
#      rozrzucone losowo, tylko ułożone tak jak w systemowych klawiaturach,
#   3. słów kluczowych do wyszukiwania (nazwa + aliasy, w tym nazwy krajów
#      dla flag, np. "poland").
#
# Tych danych nie da się odczytać z samych nazw plików PNG, więc generujemy je
# raz na podstawie oficjalnego pliku Unicode "emoji-test.txt" oraz pakietu
# "emoji" (aliasy). Wynik zapisujemy do assets/emoji_meta.json, który jest
# pakowany razem z aplikacją i czytany przez screens/emoji_index.py.
#
# Uruchomienie (wymaga internetu przy pierwszym razie):
#     python scripts/build_emoji_meta.py
# ---------------------------------------------------------------------------

import json
import os
import re
import sys
import urllib.request

# Wersja danych emoji z Unicode. emoji-test.txt zawiera grupy i kolejność.
_EMOJI_TEST_URLS = [
    "https://unicode.org/Public/emoji/15.1/emoji-test.txt",
    "https://unicode.org/Public/emoji/15.0/emoji-test.txt",
    "https://unicode.org/Public/emoji/14.0/emoji-test.txt",
]

_OUT_PATH = os.path.join("assets", "emoji_meta.json")
_VARIATION_SELECTOR = 0xFE0F  # FE0F (variation selector-16) – pomijamy przy kluczu


# Zamienia listę punktów kodowych na klucz tekstowy, np. (0x1F1F5, 0x1F1F1)
# -> "1f1f5-1f1f1". Pomijamy FE0F, bo pliki PNG są nazwane bez niego.
def make_key(codepoints):
    return "-".join(f"{cp:x}" for cp in codepoints if cp != _VARIATION_SELECTOR)


# Zamienia listę punktów kodowych na klucz używany przez publiczne assety
# emoji (np. Twemoji). Tutaj zachowujemy FE0F, bo część sekwencji ZWJ
# istnieje na CDN-ie tylko z pełnym kwalifikatorem, np.
# "1f3f3-fe0f-200d-1f308" (rainbow flag).
def make_asset_key(codepoints):
    return "-".join(f"{cp:x}" for cp in codepoints)


# Pobiera emoji-test.txt z serwerów Unicode (próbuje kolejnych wersji).
def _download_emoji_test():
    last_err = None
    for url in _EMOJI_TEST_URLS:
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                print(f"[emoji-meta] Downloaded {url}")
                return resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - chcemy spróbować następnego URL
            last_err = exc
            print(f"[emoji-meta] Failed {url}: {exc}", file=sys.stderr)
    raise SystemExit(f"[emoji-meta] Could not download emoji-test.txt: {last_err}")


# Buduje słowa kluczowe (do wyszukiwania) z czytelnej nazwy emoji.
def _keywords_from_name(name):
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return [t for t in tokens if t]


# Dodaje słowa kluczowe z aliasów pakietu "emoji" (np. ":poland:", ":es:").
def _aliases_from_emoji_pkg():
    """Zwraca mapę: klucz punktów kodowych -> lista dodatkowych słów kluczowych."""
    try:
        import emoji
    except ImportError:
        print("[emoji-meta] 'emoji' package not installed – skipping aliases.")
        return {}

    extra = {}
    for char, info in emoji.EMOJI_DATA.items():
        key = make_key([ord(c) for c in char])
        words = []
        for field in ("en",) + tuple():
            val = info.get(field)
            if val:
                words += _keywords_from_name(val.strip(":"))
        for alias in info.get("alias", []) or []:
            words += _keywords_from_name(alias.strip(":"))
        if words:
            extra.setdefault(key, [])
            extra[key].extend(words)
    return extra


def build():
    text = _download_emoji_test()
    aliases = _aliases_from_emoji_pkg()

    groups = []
    group_index = {}
    entries = {}
    order = 0
    current_group = None

    line_re = re.compile(
        r"^(?P<cps>[0-9A-Fa-f ]+);\s*(?P<status>[\w-]+)\s*#\s*\S+\s+E[\d.]+\s+(?P<name>.+?)\s*$"
    )

    for line in text.splitlines():
        if line.startswith("# group:"):
            current_group = line.split(":", 1)[1].strip()
            if current_group not in group_index:
                group_index[current_group] = len(groups)
                groups.append(current_group)
            continue
        if not line or line.startswith("#"):
            continue

        m = line_re.match(line)
        if not m:
            continue
        # Bierzemy tylko w pełni kwalifikowane formy – jedna na emoji.
        if m.group("status") != "fully-qualified":
            continue

        codepoints = [int(p, 16) for p in m.group("cps").split()]
        key = make_key(codepoints)
        if key in entries:
            continue

        name = m.group("name").strip()
        keywords = sorted(set(_keywords_from_name(name) + aliases.get(key, [])))
        entries[key] = {
            "g": group_index.get(current_group, len(groups)),
            "o": order,
            "n": name,
            "u": make_asset_key(codepoints),
            "k": keywords,
        }
        order += 1

    payload = {"groups": groups, "emoji": entries}

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(_OUT_PATH) / 1024
    print(
        f"[emoji-meta] Wrote {_OUT_PATH}: {len(entries)} emoji, "
        f"{len(groups)} groups, {size_kb:.0f} KB."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
