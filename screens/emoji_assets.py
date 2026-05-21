"""Runtime access helpers for emoji PNG assets.

During desktop development the app can read ``assets/Emoji_PNG`` directly.
Android builds exclude that directory and include ``assets/Emoji_PNG.zip``
instead, so the zip is extracted into app-private storage on first use.
"""

import os
import zipfile


_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SOURCE_DIR = os.path.join(_PKG_ROOT, "assets", "Emoji_PNG")
_ZIP_PATH = os.path.join(_PKG_ROOT, "assets", "Emoji_PNG.zip")
_EXTRACTED_DIR_NAME = "Emoji_PNG"
_STAMP_FILE = ".emoji_assets_zip_mtime"


def _user_data_dir():
    try:
        from kivymd.app import MDApp

        app = MDApp.get_running_app()
        if app is not None and getattr(app, "user_data_dir", ""):
            return app.user_data_dir
    except Exception:
        pass
    return os.environ.get("PROJECTTRACKER_USER_DATA_DIR") or os.getcwd()


def _zip_mtime():
    try:
        return str(os.path.getmtime(_ZIP_PATH))
    except OSError:
        return ""


def _extracted_dir():
    return os.path.join(_user_data_dir(), _EXTRACTED_DIR_NAME)


def _needs_extract(target_dir):
    if not os.path.exists(_ZIP_PATH):
        return False
    stamp_path = os.path.join(target_dir, _STAMP_FILE)
    if not os.path.isdir(target_dir):
        return True
    try:
        with open(stamp_path, "r", encoding="utf-8") as f:
            return f.read().strip() != _zip_mtime()
    except OSError:
        return True


def _extract_zip(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(_ZIP_PATH, "r") as zf:
        zf.extractall(target_dir)
    try:
        with open(os.path.join(target_dir, _STAMP_FILE), "w", encoding="utf-8") as f:
            f.write(_zip_mtime())
    except OSError:
        pass


def ensure_emoji_assets():
    """Return a directory containing emoji PNG files."""
    if os.path.isdir(_SOURCE_DIR):
        return _SOURCE_DIR

    target_dir = _extracted_dir()
    if _needs_extract(target_dir):
        _extract_zip(target_dir)
    return target_dir


def emoji_path(filename):
    """Return an absolute path for an emoji PNG filename."""
    name = os.path.basename(str(filename or ""))
    if not name:
        return ""
    path = os.path.join(ensure_emoji_assets(), name)
    return path if os.path.exists(path) else ""


def resolve_emoji_source(source):
    """Resolve stored icon values while leaving KivyMD icon names unchanged."""
    value = str(source or "").strip()
    if not value:
        return "folder-outline"

    if value.lower().endswith(".png"):
        if os.path.isabs(value) and os.path.exists(value):
            return value
        resolved = emoji_path(value)
        return resolved or value

    return value
