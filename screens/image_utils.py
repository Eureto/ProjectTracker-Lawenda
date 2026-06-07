# ---------------------------------------------------------------------------
# NARZĘDZIA DO OBRÓBKI ZDJĘĆ PROJEKTU
# ---------------------------------------------------------------------------
# Gdy użytkownik wybiera zdjęcie dla projektu, ten plik:
# 1. Otwiera wybrany plik graficzny
# 2. Obraca go zgodnie z orientacją zapisaną w EXIF (dane z aparatu)
# 3. Zapisuje kopię w folderze prywatnym aplikacji
# Dzięki temu zdjęcie zawsze wyświetla się prawidłowo, niezależnie
# od tego jak aparat je zapisał.
# ---------------------------------------------------------------------------

import os
# "import os" – moduł do obsługi systemu operacyjnego (foldery, pliki, ścieżki).

import uuid
# "import uuid" – moduł do generowania unikalnych identyfikatorów (UUID).
# UUID = Universally Unique Identifier – losowy ciąg znaków, który jest
# praktycznie niepowtarzalny. Używamy go do nazywania plików graficznych.

from PIL import Image, ImageOps
# "PIL" (Python Imaging Library) – biblioteka do obróbki obrazków.
# "Image" – podstawowa klasa do otwierania i zapisywania obrazków.
# "ImageOps" – dodatkowe operacje na obrazkach (np. obracanie według EXIF).


# Funkcja główna: przetwarza wybrane zdjęcie.
# "source_path" – ścieżka do oryginalnego pliku (np. z galerii telefonu).
# "cache_dir" – folder w pamięci aplikacji, gdzie zapiszemy przetworzoną kopię.
# Zwraca ścieżkę do przetworzonego pliku .jpg.
#
# CO TO JEST EXIF?
# EXIF (Exchangeable Image File Format) – to dodatkowe dane zapisane w pliku
# zdjęcia przez aparat lub telefon. Zawiera m.in. informację o tym, czy
# zdjęcie było zrobione pionowo (portret) czy poziomo (krajobraz).
# Bez użycia exif_transpose, zdjęcie zrobione pionowo może wyświetlać się
# przekręcone (bo aparat zapisuje zawsze poziomo, a obrót jest w danych EXIF).
def prepare_project_image(source_path, cache_dir):

    # "os.makedirs(exist_ok=True)" – utwórz folder jeśli nie istnieje.
    # Jeśli już istnieje – nic nie rób (nie wyrzucaj błędu).
    os.makedirs(cache_dir, exist_ok=True)

    # "with Image.open(source_path) as img:" – otwiera plik graficzny.
    # Składnia "with ... as" gwarantuje, że plik zostanie zamknięty
    # automatycznie po zakończeniu (nawet jeśli wystąpi błąd).
    with Image.open(source_path) as img:

        # "ImageOps.exif_transpose(img)" – odczytuje dane EXIF i obraca
        # obrazek tak, aby był w prawidłowej orientacji. Jeśli EXIF mówi
        # "obróć o 90 stopni" – funkcja to robi.
        # Dzięki temu zdjęcie portretowe nie leży na boku.
        img = ImageOps.exif_transpose(img)

        # Sprawdzamy "tryb" (mode) obrazka:
        # "RGBA" – ma przezroczystość (kanał Alfa). Niektóre formaty jak PNG
        #   mogą mieć przezroczyste tło.
        # "P" – paleta (indeksowane kolory). Starszy format.
        # W obu przypadkach zamieniamy na zwykły "RGB" (bez przezroczystości),
        # bo format JPEG nie obsługuje przezroczystości.
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # "uuid.uuid4().hex" – generuje losowy, unikalny identyfikator (UUID).
        # Dzięki temu każdy plik ma inną nazwę i nie nadpisuje się.
        # "hex" – wersja bez myślników, np. "a1b2c3d4e5f6...".
        dest = os.path.join(cache_dir, f"project_{uuid.uuid4().hex}.jpg")

        # Zapisujemy obrazek w formacie JPEG z jakością 92%.
        # quality=92 – wysoka jakość (100 = brak strat, ale plik duży).
        # 92 to dobry kompromis między jakością a rozmiarem pliku.
        img.save(dest, format="JPEG", quality=92)

    # Zwróć ścieżkę do przetworzonego pliku (do wyświetlenia w aplikacji).
    return dest