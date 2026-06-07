#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# SKRYPT: Pakowanie emoji do pliku ZIP
# ---------------------------------------------------------------------------
# Ten skrypt tworzy plik ZIP z obrazkami emoji (PNG). Na Androidzie
# aplikacja nie może czytać folderu assets/ bezpośrednio, dlatego emoji
# są spakowane. Skrypt uruchamia się tylko wtedy, gdy pliki PNG uległy
# zmianie – sprawdza daty modyfikacji.
# ---------------------------------------------------------------------------

import os
# "import os" – moduł do obsługi systemu plików (foldery, ścieżki).

import sys
# "import sys" – moduł do obsługi błędów (sys.stderr).

import tempfile
# "import tempfile" – moduł do tworzenia plików tymczasowych.
# Używamy go, żeby najpierw zapisać ZIP do pliku tymczasowego, a potem podmienić.

import zipfile
# "import zipfile" – moduł do tworzenia i odczytywania plików ZIP.


SRC = os.path.join("assets", "Emoji_PNG")
# "SRC" – folder źródłowy z obrazkami PNG emoji.

DST = os.path.join("assets", "Emoji_PNG.zip")
# "DST" – plik wynikowy ZIP, do którego spakujemy emoji.


# Znajduje wszystkie pliki PNG w folderze źródłowym.
def _png_files():
    # "out" – lista, do której zbieramy znalezione pliki.
    out = []
    # "os.walk(SRC)" – przechodzi przez wszystkie foldery i pliki w SRC.
    for root, _dirs, files in os.walk(SRC):
        for name in files:
            if name.lower().endswith(".png"):
                # Jeśli plik kończy się na ".png" – dodaj do listy.
                out.append(os.path.join(root, name))
    out.sort()
    # Sortujemy alfabetycznie, żeby kolejność była zawsze taka sama.
    return out


# Sprawdza czy plik ZIP jest aktualny (czy pliki PNG nie są nowsze).
def _zip_is_current(files):
    if not os.path.exists(DST):
        return False
    # "os.path.getmtime(DST)" – data ostatniej modyfikacji pliku ZIP.
    zip_mtime = os.path.getmtime(DST)
    # Sprawdź czy WSZYSTKIE pliki PNG są starsze niż ZIP.
    # Jeśli jakikolwiek PNG jest nowszy – ZIP jest nieaktualny.
    return all(os.path.getmtime(path) <= zip_mtime for path in files)


# Główna funkcja skryptu: pakuje obrazki emoji (PNG) do pliku ZIP.
# Sprawdza czy plik ZIP jest już aktualny (czy obrazki nie są nowsze).
# Jeśli nie – tworzy nowy ZIP ze wszystkimi obrazkami i zapisuje go w folderze assets/.
def main():
    if not os.path.isdir(SRC):
        print(f"[emoji-zip] Missing source directory: {SRC}", file=sys.stderr)
        return 1

    # Znajdź wszystkie pliki PNG i sprawdź czy ZIP jest aktualny.
    files = _png_files()
    if _zip_is_current(files):
        print(f"[emoji-zip] {DST} is current ({len(files)} PNGs).")
        return 0

    # Zapisz do pliku tymczasowego, potem podmień – bezpieczniej
    # "os.makedirs(exist_ok=True)" – utwórz folder jeśli nie istnieje.
    os.makedirs(os.path.dirname(DST), exist_ok=True)

    # "tempfile.mkstemp" – tworzy plik tymczasowy z unikalną nazwą.
    fd, tmp = tempfile.mkstemp(prefix=".Emoji_PNG.", suffix=".zip", dir=os.path.dirname(DST))
    os.close(fd)
    # "os.close(fd)" – zamykamy deskryptor pliku (mkstemp zwraca otwarty plik).

    try:
        # "ZipFile(tmp, "w")" – otwiera plik ZIP do zapisu.
        # "compression=ZIP_DEFLATED" – kompresja (zmniejsza rozmiar).
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in files:
                # "zf.write(path, nazwa_w_zipie)" – dodaje plik do ZIP-a.
                zf.write(path, os.path.relpath(path, SRC))
        # "os.replace(tmp, DST)" – podmienia plik tymczasowy na docelowy (atomowo).
        os.replace(tmp, DST)
    finally:
        # "finally" – wykonaj nawet jeśli wystąpił błąd (sprzątanie).
        if os.path.exists(tmp):
            os.remove(tmp)
            # Usuń plik tymczasowy jeśli jeszcze istnieje.

    # Oblicz rozmiar pliku ZIP w megabajtach.
    size_mb = os.path.getsize(DST) / (1024 * 1024)
    print(f"[emoji-zip] Wrote {DST}: {len(files)} PNGs, {size_mb:.1f} MB.")
    return 0


if __name__ == "__main__":
    # Jeśli skrypt uruchomiony bezpośrednio – wykonaj main().
    raise SystemExit(main())