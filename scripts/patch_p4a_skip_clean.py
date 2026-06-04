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
import sys


TOOLCHAIN_REL = os.path.join(
    ".buildozer", "android", "platform", "python-for-android",
    "pythonforandroid", "toolchain.py",
)

# Tekst który znajdujemy (z "clean") i na co zmieniamy (bez "clean")
ORIGINAL = 'output = shprint(gradlew, "clean", gradle_task, _tail=20,'
PATCHED = 'output = shprint(gradlew, gradle_task, _tail=20,  # patched: skip clean'


# Główna funkcja skryptu: modyfikuje plik Python-for-Android tak,
# żeby pomijał czyszczenie (gradlew clean) przed budowaniem aplikacji.
# Dzięki temu kolejne budowanie jest szybsze. Jeśli plik nie istnieje
# lub jest już zmodyfikowany – nic nie robi.
def main():
    path = os.path.join(os.getcwd(), TOOLCHAIN_REL)
    if not os.path.isfile(path):
        print(f"[patch-p4a] {TOOLCHAIN_REL} not present yet; skipping.")
        return 0

    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()

    if PATCHED in src:
        print("[patch-p4a] already patched (gradle clean skipped).")
        return 0

    if ORIGINAL not in src:
        print(
            "[patch-p4a] WARNING: expected line not found in p4a toolchain.py; "
            "skipping (p4a may have changed upstream).",
            file=sys.stderr,
        )
        return 0

    new_src = src.replace(ORIGINAL, PATCHED, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_src)
    print("[patch-p4a] patched p4a to skip 'gradlew clean' before assembleDebug.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())