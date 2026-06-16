#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# SKRYPT: Generowanie ikon aplikacji
# ---------------------------------------------------------------------------
# Ten skrypt tworzy wszystkie wersje ikony aplikacji (różne rozmiary)
# oraz obraz powitalny (presplash) z jednego pliku źródłowego.
# 
# CO ROBISZC Z IKONĄ?
# Aplikacja potrzebuje ikon w różnych rozmiarach dla różnych urządzeń
# i sklepów z aplikacjami. Ten skrypt automatycznie tworzy wszystkie
# potrzebne wersje z jednego pliku graficznego.
# ---------------------------------------------------------------------------
# 
# Źródło: assets/icon/source.png
#
# Obsługiwane formaty:
# - gotowa ikona na szarym tle (usuwa tylko szare tło, zostawia gradient)
# - zdjęcie ikony na ciemnym tle (starszy tryb z wycięciem i alfą)
#
# Skrypt zapisuje ikonę w wielu rozmiarach, warstwy adaptacyjne (Android 8+)
# oraz obraz powitalny (presplash.png).
# ---------------------------------------------------------------------------

import os
import sys

from collections import deque

from PIL import Image, ImageFilter


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_ICON_DIR = os.path.join(_ROOT, "assets", "icon")
_SOURCE = os.path.join(_ICON_DIR, "source.png")

# Rozmiary ikon do wygenerowania
_SIZES = [1024, 512, 192, 144, 96, 72, 48]

# Kolor tła dla adaptacyjnych ikon (fioletowy)
_BRAND_PURPLE = (94, 53, 177, 255)


def _is_icon_pixel(r, g, b, a):
    # Sprawdza czy piksel należy do ikony (a nie do tła).
    # Tło jest ciemnoszare/czarne, ikona jest fioletowa lub biała.
    if a < 128:
        return False
    if r > 150 and g > 150 and b > 150:
        return True  # Biały wykres
    if (r - g) > 12 and (b - g) > 12 and (r + b) > 50:
        return True  # Fioletowy kształt
    return False


def _bbox_of_icon(img):
    # Znajduje prostokąt który otacza ikonę (odrzuca tło).
    # Przeszukuje wszystkie piksele obrazu i znajduje współrzędne
    # skrajnych pikseli ikony (min_x, min_y, max_x, max_y).
    w, h = img.size
    px = img.load()
    min_x, min_y, max_x, max_y = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if _is_icon_pixel(r, g, b, a):
                found = True
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if not found:
        raise RuntimeError("no icon-like pixels detected in source")
    return min_x, min_y, max_x, max_y


def _square_crop(img, bbox, pad_px=4):
    # Przycina obrazek do kwadratu wokół ikony.
    # Wylicza środek prostokąta i tworzy kwadrat o boku równym najdłuższemu wymiarowi.
    min_x, min_y, max_x, max_y = bbox
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    side = max(max_x - min_x, max_y - min_y) + pad_px * 2
    left = int(round(cx - side / 2.0))
    top = int(round(cy - side / 2.0))
    right = left + side
    bottom = top + side
    return img.crop((left, top, right, bottom))


def _alpha_from_classifier(cropped):
    # Tworzy maskę przezroczystości – ikona widoczna, tło przezroczyste.
    # Działa na przeciętnie piksele, wykrywając które należą do ikony.
    w, h = cropped.size
    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    cp = cropped.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = cp[x, y]
            mp[x, y] = 255 if _is_icon_pixel(r, g, b, a) else 0
    return mask.filter(ImageFilter.GaussianBlur(radius=1.2))


def _extract_chart_layer(cropped):
    # Wyodrębnia tylko biały wykres z ikony (do warstwy przedniej adaptacyjnej ikony).
    # Adaptacyjne ikony to nowy format na Androidzie 8+, gdzie ikonę można animować.
    w, h = cropped.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    cp = cropped.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = cp[x, y]
            if a >= 128 and r > 150 and g > 150 and b > 150:
                op[x, y] = (255, 255, 255, 255)
    alpha = out.split()[3].filter(ImageFilter.GaussianBlur(radius=0.8))
    out.putalpha(alpha)
    return out


def _save_sizes(img, prefix, sizes):
    # Zapisuje obrazek w wielu rozmiarach.
    # Najpierw skaluje do największego rozmiaru, potem zmniejsza.
    largest = img.resize((max(sizes), max(sizes)), Image.LANCZOS)
    for s in sizes:
        out_path = os.path.join(_ICON_DIR, f"{prefix}_{s}.png")
        largest.resize((s, s), Image.LANCZOS).save(out_path, optimize=True)
        print(f"  wrote {os.path.relpath(out_path, _ROOT)} ({s}x{s})")


def _is_complete_icon(img):
    # Gotowa ikona sklepowa: kwadrat o boku >= 512 px.
    w, h = img.size
    if min(w, h) < 512:
        return False
    return abs(w - h) <= max(w, h) * 0.02


def _is_outer_frame_pixel(r, g, b):
    # Szare tło pod ikoną (ciemne rogi + jasna obwódka antyaliasingu).
    mx = max(r, g, b)
    mn = min(r, g, b)
    sat = 0.0 if mx == 0 else (mx - mn) / mx
    total = r + g + b
    if mx < 100 and sat < 0.42:
        return True
    if total > 330 and sat < 0.12:
        return True
    return False


def _strip_outer_frame(img):
    # Zostawia samą ikonę (gradient + lawenda), usuwa szare tło wokół niej.
    w, h = img.size
    px = img.load()
    icon = bytearray(w * h)
    q = deque([(w // 2, h // 2)])
    icon[w // 2 + (h // 2) * w] = 1
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                i = ny * w + nx
                if not icon[i] and not _is_outer_frame_pixel(*px[nx, ny][:3]):
                    icon[i] = 1
                    q.append((nx, ny))

    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            mp[x, y] = 255 if icon[y * w + x] else 0
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1.2))

    out = img.copy()
    out.putalpha(mask)
    return out


def _crop_to_alpha_content(img, pad_px=4):
    # Przycina do kwadratu wokół widocznej ikony (bez przezroczystych marginesów).
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return img
    return _square_crop(img, bbox, pad_px=pad_px)


def _adaptive_bg_color(img):
    # Kolor tła adaptacyjnej ikony z dolnej krawędzi gradientu.
    w, h = img.size
    px = img.load()
    samples = [px[x, h - 1][:3] for x in range(0, w, max(1, w // 32))]
    samples.extend(px[x, h // 2][:3] for x in range(0, w, max(1, w // 32)))
    return tuple(int(sum(c[i] for c in samples) / len(samples)) for i in range(3)) + (255,)


def _build_complete(src):
    print("  stripping gray outer frame...")
    stripped = _strip_outer_frame(src)
    cropped = _crop_to_alpha_content(stripped)
    print(f"  cropped to content: {cropped.size}")
    master = cropped.resize((1024, 1024), Image.LANCZOS)

    print("writing classic icon set:")
    icon_png = os.path.join(_ICON_DIR, "icon.png")
    master.resize((512, 512), Image.LANCZOS).save(icon_png, optimize=True)
    print(f"  wrote {os.path.relpath(icon_png, _ROOT)} (512x512)")
    _save_sizes(master, "icon", _SIZES)

    print("writing adaptive icon layers:")
    fg_path = os.path.join(_ICON_DIR, "icon_adaptive_fg.png")
    master.save(fg_path, optimize=True)
    print(f"  wrote {os.path.relpath(fg_path, _ROOT)} (1024x1024)")

    bg_color = _adaptive_bg_color(master)
    bg = Image.new("RGBA", (1024, 1024), bg_color)
    bg_path = os.path.join(_ICON_DIR, "icon_adaptive_bg.png")
    bg.save(bg_path, optimize=True)
    print(f"  wrote {os.path.relpath(bg_path, _ROOT)} (1024x1024, bg={bg_color[:3]})")

    print("writing splash (presplash) image:")
    presplash = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    icon_size = 480
    centered_icon = master.resize((icon_size, icon_size), Image.LANCZOS)
    off = (1024 - icon_size) // 2
    presplash.alpha_composite(centered_icon, dest=(off, off))
    presplash_path = os.path.join(_ICON_DIR, "presplash.png")
    presplash.save(presplash_path, optimize=True)
    print(f"  wrote {os.path.relpath(presplash_path, _ROOT)} (1024x1024)")


def _build_extracted(src):
    bbox = _bbox_of_icon(src)
    print(f"  icon bbox: {bbox}")

    cropped = _square_crop(src, bbox)
    print(f"  square crop: {cropped.size}")

    mask = _alpha_from_classifier(cropped)
    masked = cropped.copy()
    masked.putalpha(mask)

    master = masked.resize((1024, 1024), Image.LANCZOS)

    print("writing classic icon set:")
    icon_png = os.path.join(_ICON_DIR, "icon.png")
    master.resize((512, 512), Image.LANCZOS).save(icon_png, optimize=True)
    print(f"  wrote {os.path.relpath(icon_png, _ROOT)} (512x512)")
    _save_sizes(masked, "icon", _SIZES)

    print("writing adaptive icon layers:")
    chart = _extract_chart_layer(cropped)
    fg = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    chart_resized = chart.resize((1024, 1024), Image.LANCZOS)
    fg.alpha_composite(chart_resized)
    fg_path = os.path.join(_ICON_DIR, "icon_adaptive_fg.png")
    fg.save(fg_path, optimize=True)
    print(f"  wrote {os.path.relpath(fg_path, _ROOT)} (1024x1024)")

    bg = Image.new("RGBA", (1024, 1024), _BRAND_PURPLE)
    bg_path = os.path.join(_ICON_DIR, "icon_adaptive_bg.png")
    bg.save(bg_path, optimize=True)
    print(f"  wrote {os.path.relpath(bg_path, _ROOT)} (1024x1024)")

    print("writing splash (presplash) image:")
    presplash = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    icon_size = 480
    centered_icon = masked.resize((icon_size, icon_size), Image.LANCZOS)
    off = (1024 - icon_size) // 2
    presplash.alpha_composite(centered_icon, dest=(off, off))
    presplash_path = os.path.join(_ICON_DIR, "presplash.png")
    presplash.save(presplash_path, optimize=True)
    print(f"  wrote {os.path.relpath(presplash_path, _ROOT)} (1024x1024)")


# Główna funkcja budująca ikony.
def build():
    if not os.path.exists(_SOURCE):
        raise SystemExit(
            f"source image not found: {_SOURCE}\n"
            "Place the high-res icon shot at assets/icon/source.png first."
        )

    os.makedirs(_ICON_DIR, exist_ok=True)

    print(f"reading source: {os.path.relpath(_SOURCE, _ROOT)}")
    src = Image.open(_SOURCE).convert("RGBA")
    print(f"  source size: {src.size}")

    if _is_complete_icon(src):
        print("  mode: complete square app icon")
        _build_complete(src)
    else:
        print("  mode: icon on dark background (extract + alpha)")
        _build_extracted(src)


if __name__ == "__main__":
    try:
        build()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"icon build failed: {exc!r}", file=sys.stderr)
        sys.exit(1)