#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# SKRYPT: Przyspieszenie budowania aplikacji na Androida
# ---------------------------------------------------------------------------
# Python-for-Android (p4a) domyślnie czyści cały projekt przed każdym
# budowaniem (gradlew clean). To trwa 5-10 sekund i usuwa pamięć podręczną,
# przez co kolejne budowanie trwa dłużej.
#
# Ten skrypt modyfikuje plik p4a, aby pomijał "clean" – przydatne gdy
# zmieniamy tylko kod Pythona lub pliki .kv, a nie strukturę Gradle.
# Skrypt jest bezpieczny – można go uruchamiać wielokrotnie.
# ---------------------------------------------------------------------------

import os
# "import os" – moduł do obsługi systemu operacyjnego (ścieżki, pliki).

import sys
# "import sys" – moduł do obsługi argumentów i wyjścia programu (błędy na stderr).


TOOLCHAIN_REL = os.path.join(
    ".buildozer", "android", "platform", "python-for-android",
    "pythonforandroid", "toolchain.py",
)
# "TOOLCHAIN_REL" – względna ścieżka do pliku Python-for-Android, który odpowiada
# za budowanie aplikacji na Androida. Buildozer pobiera go do folderu .buildozer/.

# Tekst który znajdujemy (z "clean") i na co zmieniamy (bez "clean")
ORIGINAL = 'output = shprint(gradlew, "clean", gradle_task, _tail=20,'
# "ORIGINAL" – oryginalna linia w pliku p4a, która zawiera polecenie "gradlew clean"
# (czyści projekt przed budowaniem). To chcemy zmienić.

PATCHED = 'output = shprint(gradlew, gradle_task, _tail=20,  # patched: skip clean'
# "PATCHED" – nowa wersja linii BEZ "clean" (pomija czyszczenie).
# Dzięki temu budowanie jest szybsze.


# Główna funkcja skryptu: modyfikuje plik Python-for-Android tak,
# żeby pomijał czyszczenie (gradlew clean) przed budowaniem aplikacji.
# Dzięki temu kolejne budowanie jest szybsze. Jeśli plik nie istnieje
# lub jest już zmodyfikowany – nic nie robi.
def main():
    # "main()" – główna funkcja skryptu. Szuka pliku toolchain.py i modyfikuje go.

    # "os.getcwd()" – bieżący folder roboczy (tam gdzie jest buildozer.spec).
    # Dołączamy ścieżkę względną do pliku p4a.
    path = os.path.join(os.getcwd(), TOOLCHAIN_REL)

    # "os.path.isfile(path)" – sprawdza czy plik istnieje.
    # Jeśli nie (np. pierwsze budowanie jeszcze nie ściągnęło p4a) – pomiń.
    if not os.path.isfile(path):
        print(f"[patch-p4a] {TOOLCHAIN_REL} not present yet; skipping.")
        return 0

    # Otwieramy plik do odczytu ("r" = read) i czytamy całą zawartość.
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()

    # Jeśli już jest zmodyfikowany (zawiera "patched") – nic nie rób.
    if PATCHED in src:
        print("[patch-p4a] already patched (gradle clean skipped).")
        return 0

    # Jeśli nie ma oryginalnej linii – to znaczy że p4a się zmienił.
    # Wyświetlamy ostrzeżenie i pomijamy.
    if ORIGINAL not in src:
        print(
            "[patch-p4a] WARNING: expected line not found in p4a toolchain.py; "
            "skipping (p4a may have changed upstream).",
            file=sys.stderr,
        )
        return 0

    # "src.replace(ORIGINAL, PATCHED, 1)" – zamień pierwszą ("1") linijkę
    # ORIGINAL na PATCHED. Tylko pierwsze wystąpienie (na wszelki wypadek).
    new_src = src.replace(ORIGINAL, PATCHED, 1)

    # Otwieramy plik do zapisu ("w" = write) i zapisujemy zmodyfikowaną treść.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_src)

    print("[patch-p4a] patched p4a to skip 'gradlew clean' before assembleDebug.")
    return 0


if __name__ == "__main__":
    # "__name__ == '__main__'" – sprawdza czy ten plik jest uruchomiony bezpośrednio
    # (a nie zaimportowany jako moduł). Jeśli tak – wykonaj main().
    # "raise SystemExit(main())" – uruchom main() i zakończ program z kodem błędu (0 = sukces).
    raise SystemExit(main())