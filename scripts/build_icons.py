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
# Źródło: assets/icon/source.png (zdjęcie ikony na ciemnym tle)
# 
# Skrypt:
# 1. Znajduje gdzie jest ikona (fioletowy kształt) a gdzie tło
# 2. Przycina do kwadratu wokół ikony
# 3. Tworzy przezroczyste tło (alfa)
# 4. Zapisuje ikonę w wielu rozmiarach
# 5. Tworzy warstwy dla adaptacyjnych ikon (Android 8+)
# 6. Tworzy obraz powitalny (presplash.png)
# ---------------------------------------------------------------------------

import os
# "import os" – moduł do obsługi systemu plików (ścieżki, foldery).

import sys
# "import sys" – moduł do obsługi błędów (sys.exit).

from PIL import Image, ImageDraw, ImageFilter
# "PIL" – Python Imaging Library, biblioteka do obróbki obrazków.
# "Image" – podstawowa klasa do otwierania i zapisywania grafik.
# "ImageDraw" – rysowanie na obrazkach (np. prostokąty, kształty).
# "ImageFilter" – filtry graficzne (np. rozmycie GaussianBlur).


_HERE = os.path.dirname(os.path.abspath(__file__))
# "_HERE" – folder, w którym znajduje się ten plik (scripts/).

_ROOT = os.path.dirname(_HERE)
# "_ROOT" – główny folder projektu (jeden poziom wyżej niż scripts/).

_ICON_DIR = os.path.join(_ROOT, "assets", "icon")
# "_ICON_DIR" – folder, gdzie zapiszemy wygenerowane ikony (assets/icon/).

_SOURCE = os.path.join(_ICON_DIR, "source.png")
# "_SOURCE" – plik źródłowy z grafiką ikony (assets/icon/source.png).

# Rozmiary ikon do wygenerowania (w pikselach)
_SIZES = [1024, 512, 192, 144, 96, 72, 48]
# Różne urządzenia potrzebują różnych rozmiarów ikon. Te rozmiary pokrywają
# wszystkie potrzeby: sklepy, system, pasek powiadomień itp.

# Kolor tła dla adaptacyjnych ikon (fioletowy)
_BRAND_PURPLE = (94, 53, 177, 255)
# "_BRAND_PURPLE" – kolor fioletowy (R, G, B, A) używany jako tło
# adaptacyjnych ikon na Androidzie 8+.


def _is_icon_pixel(r, g, b, a):
    # "_is_icon_pixel(r, g, b, a)" – sprawdza czy piksel należy do ikony.
    # "r, g, b, a" – składowe koloru: Red (czerwony), Green (zielony), Blue (niebieski), Alpha (przezroczystość).
    # Tło jest ciemnoszare/czarne, ikona jest fioletowa lub biała.

    if a < 128:
        return False
    # Jeśli przezroczystość (alpha) jest mniejsza niż 50% – to nie ikona (puste tło).

    if r > 150 and g > 150 and b > 150:
        return True
    # Jeśli piksel jest jasny (R, G, B > 150) – to biały fragment wykresu (część ikony).

    if (r - g) > 12 and (b - g) > 12 and (r + b) > 50:
        return True
    # Jeśli piksel ma więcej czerwonego i niebieskiego niż zielonego – to fioletowy kształt.
    # Fiolet = dużo czerwonego i niebieskiego, mało zielonego.

    return False
    # W przeciwnym razie – to tło (ciemny piksel).


def _bbox_of_icon(img):
    # "_bbox_of_icon(img)" – znajduje prostokąt, który otacza ikonę.
    # "bbox" = bounding box (prostokąt ograniczający).
    # Przeszukuje wszystkie piksele obrazu i znajduje współrzędne
    # skrajnych pikseli ikony (min_x, min_y, max_x, max_y).

    w, h = img.size
    # "w, h" – szerokość i wysokość obrazka w pikselach.

    px = img.load()
    # "px" – tablica z pikselami. px[x, y] zwraca kolor piksela (R, G, B, A).

    # Ustawiamy wartości początkowe:
    # min_x, min_y – największe możliwe (szerokość/wysokość obrazka)
    # max_x, max_y – najmniejsze możliwe (0)
    min_x, min_y, max_x, max_y = w, h, 0, 0
    found = False
    # "found" – czy znaleźliśmy jakikolwiek piksel należący do ikony?

    # Przechodzimy przez wszystkie piksele obrazka (pionowo i poziomo).
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            # Sprawdź czy piksel należy do ikony (a nie do tła).
            if _is_icon_pixel(r, g, b, a):
                found = True
                # Aktualizujemy granice prostokąta jeśli piksel jest
                # bardziej na lewo (min_x), wyżej (min_y), itd.
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
    # Jeśli nie znaleziono żadnego piksela ikony – błąd (złe źródło).

    # Zwróć współrzędne prostokąta otaczającego ikonę.
    return min_x, min_y, max_x, max_y


def _square_crop(img, bbox, pad_px=4):
    # "_square_crop" – przycina obrazek do kwadratu wokół ikony.
    # Wylicza środek prostokąta i tworzy kwadrat o boku równym najdłuższemu wymiarowi.

    min_x, min_y, max_x, max_y = bbox
    # Współrzędne prostokąta otaczającego ikonę.

    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    # "cx, cy" – środek prostokąta (wyliczamy, żeby wyśrodkować kwadrat).

    side = max(max_x - min_x, max_y - min_y) + pad_px * 2
    # "side" – bok kwadratu = dłuższy wymiar ikony + 4 piksele zapasu z każdej strony.

    left = int(round(cx - side / 2.0))
    top = int(round(cy - side / 2.0))
    right = left + side
    bottom = top + side
    # Współrzędne kwadratu: lewy, górny, prawy, dolny róg.
    # "int(round(...))" – zaokrąglamy do liczby całkowitej (piksele muszą być całkowite).

    # "img.crop((left, top, right, bottom))" – wycina kwadrat z obrazka.
    return img.crop((left, top, right, bottom))


def _alpha_from_classifier(cropped):
    # "_alpha_from_classifier" – tworzy maskę przezroczystości.
    # Maska mówi: które piksele są ikoną (widoczne), a które tłem (przezroczyste).

    w, h = cropped.size
    mask = Image.new("L", (w, h), 0)
    # "Image.new("L", ...)" – tworzy nowy obrazek w odcieniach szarości ("L" = luminance).
    # Wartość 0 = czarny (przezroczysty), 255 = biały (widoczny).

    mp = mask.load()
    cp = cropped.load()
    # Odczytujemy piksele maski i przyciętego obrazka.

    for y in range(h):
        for x in range(w):
            r, g, b, a = cp[x, y]
            # Jeśli piksel należy do ikony – ustaw na biały (255), inaczej czarny (0).
            mp[x, y] = 255 if _is_icon_pixel(r, g, b, a) else 0

    # "GaussianBlur(radius=1.2)" – rozmycie maski, żeby krawędzie były gładkie.
    # Dzięki temu ikona nie będzie miała ostrych, poszarpanych brzegów.
    return mask.filter(ImageFilter.GaussianBlur(radius=1.2))


def _extract_chart_layer(cropped):
    # "_extract_chart_layer" – wyodrębnia tylko biały wykres z ikony.
    # To jest warstwa przednia adaptacyjnej ikony (Android 8+).
    # Adaptacyjne ikony mają dwie warstwy: przednią (obrazek) i tło (kolor).

    w, h = cropped.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # "Image.new("RGBA", ..., (0,0,0,0))" – pusty obrazek (całkowicie przezroczysty).

    op = out.load()
    cp = cropped.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = cp[x, y]
            # Jeśli piksel jest biały (jasny) i nieprzezroczysty – to fragment wykresu.
            if a >= 128 and r > 150 and g > 150 and b > 150:
                op[x, y] = (255, 255, 255, 255)
                # Ustaw biały, nieprzezroczysty piksel.

    alpha = out.split()[3].filter(ImageFilter.GaussianBlur(radius=0.8))
    # "out.split()[3]" – wyciąga kanał alfa (przezroczystość) z obrazka.
    # Rozmywamy go, żeby krawędzie wykresu były gładkie.

    out.putalpha(alpha)
    # "putalpha(alpha)" – ustawia rozmyty kanał alfa jako przezroczystość obrazka.

    return out


def _save_sizes(img, prefix, sizes):
    # "_save_sizes" – zapisuje obrazek w wielu rozmiarach (dla różnych urządzeń).
    # Najpierw skaluje do największego rozmiaru, potem zmniejsza – lepsza jakość.

    largest = img.resize((max(sizes), max(sizes)), Image.LANCZOS)
    # "Image.LANCZOS" – algorytm skalowania (najwyższa jakość).

    for s in sizes:
        out_path = os.path.join(_ICON_DIR, f"{prefix}_{s}.png")
        # Zapisuje obrazek w rozmiarze "s" do pliku.
        largest.resize((s, s), Image.LANCZOS).save(out_path, optimize=True)
        # "optimize=True" – optymalizuj rozmiar pliku PNG.
        print(f"  wrote {os.path.relpath(out_path, _ROOT)} ({s}x{s})")


# Główna funkcja budująca ikony.
def build():
    # "build()" – główna funkcja skryptu: tworzy wszystkie wersje ikon.

    # Sprawdź czy plik źródłowy istnieje; jeśli nie – zakończ z błędem.
    if not os.path.exists(_SOURCE):
        raise SystemExit(
            f"source image not found: {_SOURCE}\n"
            "Place the high-res icon shot at assets/icon/source.png first."
        )

    # Utwórz folder na ikony jeśli nie istnieje.
    os.makedirs(_ICON_DIR, exist_ok=True)

    print(f"reading source: {os.path.relpath(_SOURCE, _ROOT)}")
    src = Image.open(_SOURCE).convert("RGBA")
    # Otwórz plik źródłowy i zamień na format RGBA (z kanałem przezroczystości).
    print(f"  source size: {src.size}")

    # Znajdź prostokąt otaczający ikonę.
    bbox = _bbox_of_icon(src)
    print(f"  icon bbox: {bbox}")

    # Przytnij do kwadratu.
    cropped = _square_crop(src, bbox)
    print(f"  square crop: {cropped.size}")

    # Stwórz maskę przezroczystości (tło przezroczyste, ikona widoczna).
    mask = _alpha_from_classifier(cropped)
    masked = cropped.copy()
    masked.putalpha(mask)
    # "putalpha(mask)" – ustaw maskę jako kanał przezroczystości obrazka.

    # Najpierw przeskaluj do 1024, potem zmniejszaj – lepsza jakość
    master = masked.resize((1024, 1024), Image.LANCZOS)

    print("writing classic icon set:")
    # "icon.png" – główna ikona 512x512 (wymagana przez sklepy z aplikacjami).
    icon_png = os.path.join(_ICON_DIR, "icon.png")
    master.resize((512, 512), Image.LANCZOS).save(icon_png, optimize=True)
    print(f"  wrote {os.path.relpath(icon_png, _ROOT)} (512x512)")
    # Zapisz wszystkie pozostałe rozmiary.
    _save_sizes(masked, "icon", _SIZES)

    print("writing adaptive icon layers:")
    # Adaptacyjne ikony (Android 8+) mają warstwę przednią i tło.
    chart = _extract_chart_layer(cropped)
    # Warstwa przednia: tylko biały wykres (przezroczyste tło).
    fg = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    chart_resized = chart.resize((1024, 1024), Image.LANCZOS)
    fg.alpha_composite(chart_resized)
    # "alpha_composite" – nakłada wykres na przezroczyste tło.
    fg_path = os.path.join(_ICON_DIR, "icon_adaptive_fg.png")
    fg.save(fg_path, optimize=True)
    print(f"  wrote {os.path.relpath(fg_path, _ROOT)} (1024x1024)")

    # Warstwa tła: jednolity fioletowy kolor.
    bg = Image.new("RGBA", (1024, 1024), _BRAND_PURPLE)
    bg_path = os.path.join(_ICON_DIR, "icon_adaptive_bg.png")
    bg.save(bg_path, optimize=True)
    print(f"  wrote {os.path.relpath(bg_path, _ROOT)} (1024x1024)")

    print("writing splash (presplash) image:")
    # Obraz powitalny (presplash) – wyświetlany podczas ładowania aplikacji.
    presplash = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    icon_size = 480
    centered_icon = masked.resize((icon_size, icon_size), Image.LANCZOS)
    off = (1024 - icon_size) // 2
    # "off" – przesunięcie, żeby ikona była na środku (połowa różnicy wymiarów).
    presplash.alpha_composite(centered_icon, dest=(off, off))
    # Nakłada ikonę na środek czarnego tła.
    presplash_path = os.path.join(_ICON_DIR, "presplash.png")
    presplash.save(presplash_path, optimize=True)
    print(f"  wrote {os.path.relpath(presplash_path, _ROOT)} (1024x1024)")


if __name__ == "__main__":
    # Jeśli skrypt uruchomiony bezpośrednio – wykonaj build().
    try:
        build()
    except SystemExit:
        # "SystemExit" – celowe zakończenie (np. brak pliku źródłowego) – przepuść.
        raise
    except Exception as exc:
        # Inne błędy (np. uszkodzony plik) – wyświetl i zakończ z kodem 1.
        print(f"icon build failed: {exc!r}", file=sys.stderr)
        sys.exit(1)