# ---------------------------------------------------------------------------
# NARZĘDZIA DO ŁADOWANIA IKON EMOJI
# ---------------------------------------------------------------------------
# Ta aplikacja używa emoji jako ikon projektów. Emoji są zapisane jako
# pliki PNG (obrazki) w folderze assets/Emoji_PNG. Na komputerze aplikacja
# czyta je bezpośrednio z tego folderu. Na Androidzie folder jest spakowany
# jako ZIP, a ten plik rozpakowuje go przy pierwszym uruchomieniu.
# ---------------------------------------------------------------------------

import os
import zipfile


_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SOURCE_DIR = os.path.join(_PKG_ROOT, "assets", "Emoji_PNG")
_ZIP_PATH = os.path.join(_PKG_ROOT, "assets", "Emoji_PNG.zip")
_EXTRACTED_DIR_NAME = "Emoji_PNG"
_STAMP_FILE = ".emoji_assets_zip_mtime"  # Specjalny plik pomocniczy, w którym zapisujemy datę ostatniej zmiany pliku ZIP – dzięki temu wiemy, czy trzeba ponownie rozpakować emoji


# Zwraca ścieżkę do prywatnego folderu aplikacji (user_data_dir).
# To miejsce gdzie aplikacja może zapisywać własne pliki (np. rozpakowane emoji).
# Jeśli nie można uzyskać user_data_dir (np. podczas testów), używa bieżącego folderu.
def _user_data_dir():
    try:
        from kivymd.app import MDApp
        app = MDApp.get_running_app()
        if app is not None and getattr(app, "user_data_dir", ""):
            return app.user_data_dir
    except Exception:
        pass
    return os.environ.get("PROJECTTRACKER_USER_DATA_DIR") or os.getcwd()


# Sprawdza kiedy plik ZIP z emoji był ostatnio modyfikowany (data modyfikacji pliku).
# "mtime" = modification time. Służy do sprawdzenia, czy trzeba ponownie rozpakować ZIP.
def _zip_mtime():
    try:
        return str(os.path.getmtime(_ZIP_PATH))
    except OSError:
        return ""


# Zwraca ścieżkę do folderu gdzie emoji zostaną rozpakowane.
def _extracted_dir():
    return os.path.join(_user_data_dir(), _EXTRACTED_DIR_NAME)


# Sprawdza czy trzeba rozpakować ZIP.
# Jeśli folder docelowy nie istnieje – trzeba rozpakować.
# Jeśli istnieje plik znacznikowy z datą modyfikacji ZIP-a i jest aktualna – nie trzeba.
# Jeśli ZIP został zmodyfikowany (np. dodaliśmy nowe emoji) – trzeba rozpakować ponownie.
def _needs_extract(target_dir):
    if not os.path.exists(_ZIP_PATH):
        return False
    stamp_path = os.path.join(target_dir, _STAMP_FILE)
    if not os.path.isdir(target_dir):
        return True
    try:
        with open(stamp_path, "r", encoding="utf-8") as f:
            # Porównaj zapisaną datę z aktualną datą ZIP-a
            return f.read().strip() != _zip_mtime()
    except OSError:
        return True


# Rozpakowuje plik ZIP z emoji do podanego folderu.
# "ZipFile(_ZIP_PATH, "r")" – otwiera ZIP w trybie do odczytu ("r" = read).
# "extractall(target_dir)" – rozpakowuje wszystkie pliki do folderu.
# "stamp_path" – zapisuje datę modyfikacji ZIP-a, żeby wiedzieć czy rozpakować ponownie.
def _extract_zip(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(_ZIP_PATH, "r") as zf:
        zf.extractall(target_dir)
    try:
        with open(os.path.join(target_dir, _STAMP_FILE), "w", encoding="utf-8") as f:
            f.write(_zip_mtime())
    except OSError:
        pass


# Główna funkcja: zwraca ścieżkę do folderu z emoji PNG.
# Na komputerze (gdzie folder assets jest dostępny bezpośrednio) – zwraca oryginalny folder.
# Na Androidzie – rozpakowuje ZIP jeśli potrzeba i zwraca rozpakowany folder.
def ensure_emoji_assets():
    if os.path.isdir(_SOURCE_DIR):
        return _SOURCE_DIR
    target_dir = _extracted_dir()
    if _needs_extract(target_dir):
        _extract_zip(target_dir)
    return target_dir


# Zwraca pełną ścieżkę do pliku PNG z emoji.
# "os.path.basename" – wyciąga samą nazwę pliku ze ścieżki (np. z "folder/emoji.png" -> "emoji.png").
# Jeśli plik nie istnieje – zwraca pusty string.
def emoji_path(filename):
    name = os.path.basename(str(filename or ""))
    if not name:
        return ""
    path = os.path.join(ensure_emoji_assets(), name)
    return path if os.path.exists(path) else ""


# Rozpoznaje źródło emoji – może to być:
# 1. Nazwa ikony z biblioteki Material Design Icons (np. "emoticon-happy-outline")
#    – wtedy zwracamy ją bez zmian.
# 2. Ścieżka do własnego pliku PNG z emoji (np. "u1F600.png")
#    – wtedy szukamy pliku w folderze z emoji i zwracamy pełną ścieżkę.
# 3. Jeśli źródło jest puste – zwraca domyślną ikonę "folder-outline".
def resolve_emoji_source(source):
    value = str(source or "").strip()
    if not value:
        return "folder-outline"

    # Sprawdź czy to plik PNG
    if value.lower().endswith(".png"):
        # Jeśli to już jest pełna ścieżka i plik istnieje – zwróć jak jest
        if os.path.isabs(value) and os.path.exists(value):
            return value
        # W przeciwnym razie – poszukaj w folderze z emoji
        resolved = emoji_path(value)
        return resolved or value

    # To nie jest PNG – musi być nazwą ikony Material Design
    return value