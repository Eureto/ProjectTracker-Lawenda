"""Build the app icon set + splash (presplash) image from a source image.

Source: ``assets/icon/source.png`` (a photographic shot of the icon on a dark
background — typically a screenshot or render). The script:

1. Classifies each pixel as "icon" (saturated purple or near-white chart) vs
   "background" (dark grey film grain) and finds the bounding box of icon
   pixels.
2. Crops a centered square around that bbox.
3. Builds an alpha mask from the same classifier, smoothed for anti-aliasing.
   The natural rounded corners of the source icon survive into the mask.
4. Saves ``icon.png`` (512×512) plus power-of-two and Android launcher sizes.
5. Writes ``icon_adaptive_fg.png`` and ``icon_adaptive_bg.png`` for use with
   ``icon.adaptive_foreground.filename`` / ``icon.adaptive_background.filename``
   in ``buildozer.spec`` (API 26+ adaptive icons).
6. Writes ``presplash.png`` — a transparent 1024×1024 canvas with the masked
   icon centered at ~47% of canvas width, intended to be shown on top of the
   ``android.presplash_color`` background.

Re-run after replacing ``assets/icon/source.png``.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFilter


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_ICON_DIR = os.path.join(_ROOT, "assets", "icon")
_SOURCE = os.path.join(_ICON_DIR, "source.png")

# Sizes commonly requested by Android launchers + a 1024 for stores. We keep
# the full set so different toolchains can pick what they need.
_SIZES = [1024, 512, 192, 144, 96, 72, 48]

# Brand purple, used as solid background for the adaptive-icon background
# layer. Sampled from the source after lifting the film-grain texture.
_BRAND_PURPLE = (94, 53, 177, 255)  # ~#5e35b1, the app's theme_session_bg


def _is_icon_pixel(r, g, b, a):
    """Classify a pixel as belonging to the icon vs the photographic
    background.

    The source has a dark grey/black film-grain background and a deeply
    saturated purple icon body with a white chart graphic. Purple has G much
    lower than R and B; the chart is near-white.
    """
    if a < 128:
        return False
    if r > 150 and g > 150 and b > 150:
        return True
    if (r - g) > 12 and (b - g) > 12 and (r + b) > 50:
        return True
    return False


def _bbox_of_icon(img):
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
    """Return an RGBA image whose alpha tracks only the white chart graphic.

    Used for the adaptive-icon foreground layer.
    """
    w, h = cropped.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    cp = cropped.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = cp[x, y]
            if a >= 128 and r > 150 and g > 150 and b > 150:
                # Re-render as a flat white so the foreground looks crisp
                # against the purple background layer.
                op[x, y] = (255, 255, 255, 255)
    # Soft edges.
    alpha = out.split()[3].filter(ImageFilter.GaussianBlur(radius=0.8))
    out.putalpha(alpha)
    return out


def _save_sizes(img, prefix, sizes):
    largest = img.resize((max(sizes), max(sizes)), Image.LANCZOS)
    for s in sizes:
        out_path = os.path.join(_ICON_DIR, f"{prefix}_{s}.png")
        largest.resize((s, s), Image.LANCZOS).save(out_path, optimize=True)
        print(f"  wrote {os.path.relpath(out_path, _ROOT)} ({s}x{s})")


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

    bbox = _bbox_of_icon(src)
    print(f"  icon bbox: {bbox}")

    cropped = _square_crop(src, bbox)
    print(f"  square crop: {cropped.size}")

    mask = _alpha_from_classifier(cropped)
    masked = cropped.copy()
    masked.putalpha(mask)

    # Upsample once to 1024 for the highest fidelity, then downsample each
    # target size from that master to avoid stacked resampling artifacts.
    master = masked.resize((1024, 1024), Image.LANCZOS)

    print("writing classic icon set:")
    icon_png = os.path.join(_ICON_DIR, "icon.png")
    master.resize((512, 512), Image.LANCZOS).save(icon_png, optimize=True)
    print(f"  wrote {os.path.relpath(icon_png, _ROOT)} (512x512)")
    _save_sizes(masked, "icon", _SIZES)

    # Adaptive icon foreground = chart layer centered with a safe-zone margin
    # (~25% so the chart sits inside the 66% Android safe area on all mask
    # shapes — circle, squircle, teardrop). The background is a solid purple
    # square that Android will mask into whatever launcher shape is active.
    print("writing adaptive icon layers:")
    chart = _extract_chart_layer(cropped)
    # Chart already sits inside the cropped icon body, occupying roughly the
    # central 60–70% area. We embed it onto a 1024 transparent canvas to
    # match the adaptive-foreground spec.
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
    # 1024×1024 transparent canvas with the icon centered at ~47% of the
    # canvas width. On a typical portrait phone screen, buildozer's
    # presplash widget scales the image to fit the screen width, so the icon
    # ends up at roughly half the screen width — a clean "branded splash"
    # composition with the presplash_color showing around it.
    presplash = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    icon_size = 480
    centered_icon = masked.resize((icon_size, icon_size), Image.LANCZOS)
    off = (1024 - icon_size) // 2
    presplash.alpha_composite(centered_icon, dest=(off, off))
    presplash_path = os.path.join(_ICON_DIR, "presplash.png")
    presplash.save(presplash_path, optimize=True)
    print(f"  wrote {os.path.relpath(presplash_path, _ROOT)} (1024x1024)")


if __name__ == "__main__":
    try:
        build()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - friendly CLI
        print(f"icon build failed: {exc!r}", file=sys.stderr)
        sys.exit(1)
