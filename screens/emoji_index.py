# ---------------------------------------------------------------------------
# INDEKS EMOJI – kategorie, kolejność i wyszukiwanie
# ---------------------------------------------------------------------------
# Ten moduł buduje listę emoji dostępnych w pickerze. Dla każdego pliku PNG
# z folderu emoji odczytuje punkty kodowe Unicode z nazwy pliku, a następnie
# dopasowuje je do metadanych z assets/emoji_meta.json (wygenerowanych przez
# scripts/build_emoji_meta.py). Dzięki temu każde emoji ma:
#   - kategorię (np. "Smileys & Emotion", "Flags"),
#   - oficjalną kolejność Unicode (żeby emoji były ułożone sensownie),
#   - nazwę i słowa kluczowe do wyszukiwania (np. flagi po nazwie kraju).
#
# Budowanie indeksu jest tanie (parsowanie nazw + odczyt jednego JSON-a),
# więc nie tworzymy tutaj żadnych widżetów – to robi dopiero picker, leniwie,
# przez RecycleView.
# ---------------------------------------------------------------------------

import json
import os

from screens.emoji_assets import ensure_emoji_assets

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_META_PATH = os.path.join(_PKG_ROOT, "assets", "emoji_meta.json")
_VARIATION_SELECTOR = 0xFE0F

# Grupa "Component" to modyfikatory (kolor skóry, włosy) – nie są to ikony,
# które użytkownik chciałby ustawić dla projektu, więc je pomijamy.
_SKIP_GROUPS = {"Component"}

_meta_cache = None
_index_cache = None


# Wczytuje metadane emoji z pliku JSON (raz, potem z pamięci podręcznej).
def _load_meta():
    global _meta_cache
    if _meta_cache is None:
        try:
            with open(_META_PATH, "r", encoding="utf-8") as f:
                _meta_cache = json.load(f)
        except (OSError, ValueError):
            _meta_cache = {"groups": [], "emoji": {}}
    return _meta_cache


# Odczytuje z nazwy pliku PNG klucz punktów kodowych w formacie zgodnym
# z metadanymi, np. "u1F600.png" -> "1f600", a (w przyszłości, dla flag)
# "u1F1F5_1F1F1.png" -> "1f1f5-1f1f1". Obsługuje prefiksy "u"/"uni" oraz
# separatory "_" i "-" między kolejnymi punktami kodowymi.
def decode_key(filename):
    base = os.path.splitext(os.path.basename(filename))[0]

    if base.startswith("uni"):
        body = base[3:]
    elif base.startswith("u"):
        body = base[1:]
    else:
        return None

    parts = [p for p in body.replace("-", "_").split("_") if p]
    if not parts:
        return None

    codepoints = []
    for part in parts:
        try:
            codepoints.append(int(part, 16))
        except ValueError:
            return None

    key = "-".join(f"{cp:x}" for cp in codepoints if cp != _VARIATION_SELECTOR)
    return key or None


# Buduje (i zapamiętuje) pełny indeks emoji posortowany w oficjalnej
# kolejności Unicode. Każdy wpis to słownik z polami: source, category,
# order, name, key, keywords.
def build_index(force=False):
    global _index_cache
    if _index_cache is not None and not force:
        return _index_cache

    meta = _load_meta()
    groups = meta.get("groups", [])
    emoji_meta = meta.get("emoji", {})

    emoji_dir = ensure_emoji_assets()
    if not emoji_dir or not os.path.isdir(emoji_dir):
        _index_cache = []
        return _index_cache

    items = []
    for filename in os.listdir(emoji_dir):
        if not filename.lower().endswith(".png"):
            continue
        key = decode_key(filename)
        if not key:
            continue
        info = emoji_meta.get(key)
        if not info:
            continue
        group_idx = info.get("g", len(groups))
        category = groups[group_idx] if 0 <= group_idx < len(groups) else "Symbols"
        if category in _SKIP_GROUPS:
            continue
        items.append({
            "source": os.path.join(emoji_dir, filename),
            "category": category,
            "order": info.get("o", 10 ** 9),
            "name": info.get("n", ""),
            "key": key,
            "keywords": info.get("k", []),
        })

    items.sort(key=lambda e: e["order"])
    _index_cache = items
    return _index_cache


# Zwraca listę kategorii (w oficjalnej kolejności), które faktycznie
# zawierają jakieś emoji – tylko dla nich pokazujemy zakładki.
def category_order(index=None):
    if index is None:
        index = build_index()
    seen = []
    for item in index:
        if item["category"] not in seen:
            seen.append(item["category"])
    return seen


# Filtruje emoji po frazie. Dopasowuje do słów kluczowych, nazwy oraz
# kodu szesnastkowego. Pusta fraza zwraca całą (posortowaną) listę.
def filter_index(index, search_term):
    if not search_term or not search_term.strip():
        return index
    term = search_term.lower().strip()
    result = []
    for item in index:
        if term in item["key"]:
            result.append(item)
        elif term in item["name"].lower():
            result.append(item)
        elif any(term in kw for kw in item["keywords"]):
            result.append(item)
    return result
