#!/usr/bin/env python3
"""Strip the forced ``gradlew clean`` from python-for-android.

p4a's ``toolchain.py`` hard-codes ``shprint(gradlew, "clean", gradle_task, ...)``
which throws away the Gradle incremental build cache on every APK build. For
day-to-day iteration (Python / .kv edits only) the clean is unnecessary and
costs ~5-10 s plus warm-cache loss. This script removes the "clean" arg in
place; it is idempotent and safe to re-run.

Triggered from the Makefile after ``prepare``. If the toolchain file is missing
(fresh checkout, no buildozer run yet) the script exits silently with code 0.
"""

import os
import sys


TOOLCHAIN_REL = os.path.join(
    ".buildozer", "android", "platform", "python-for-android",
    "pythonforandroid", "toolchain.py",
)

ORIGINAL = 'output = shprint(gradlew, "clean", gradle_task, _tail=20,'
PATCHED = 'output = shprint(gradlew, gradle_task, _tail=20,  # patched: skip clean'


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
