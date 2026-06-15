# ---------------------------------------------------------------------------
# EKRAN USTAWIEŃ PROJEKTU – edycja i usuwanie
# ---------------------------------------------------------------------------
# Ten ekran pozwala edytować istniejący projekt: zmienić nazwę, zdjęcie,
# kolor, emoji, lub usunąć projekt całkowicie (wymaga potwierdzenia).
# Wszystkie zmiany są zapisywane dopiero po kliknięciu przycisku zapisu.
# ---------------------------------------------------------------------------

import json
import os

from kivy.clock import Clock
from kivy.properties import ColorProperty, StringProperty
from kivymd.uix.screen import MDScreen
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from plyer import filechooser

from screens.color_palette import open_palette_picker
from screens.emoji_assets import resolve_emoji_source
from screens.image_utils import prepare_project_image


# Zwraca ścieżkę do pliku lub folderu w prywatnym katalogu aplikacji.
# *parts to lista fragmentów ścieżki, które są łączone ze sobą.
def _user_path(*parts):
    app = MDApp.get_running_app()
    return os.path.join(app.user_data_dir, *parts)


# Odczytuje plik JSON i zwraca jego zawartość. Jeśli plik nie istnieje
# lub jest uszkodzony – zwraca wartość domyślną podaną w "default".
def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


# Zapisuje dane do pliku w formacie JSON. Tworzy foldery jeśli trzeba.
# "data" to dowolna wartość którą można zapisać w JSON (lista, słownik itp.).
def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# Ekran do edycji/usuwania projektu. project_uid to unikalny numer identyfikacyjny (UID),
# który odróżnia ten projekt od innych – nawet jeśli mają taką samą nazwę.
class ProjectSettingsScreen(MDScreen):

    project_uid = StringProperty("")
    project_title = StringProperty("")
    selected_color = ColorProperty([0.7, 0.5, 1, 1])
    selected_icon = StringProperty("emoticon-happy-outline")
    selected_image_path = StringProperty("")
    name_text = StringProperty("")

    _original_title = ""
    _original_uid = ""

    # Przed wejściem na ekran – wczytaj dane projektu z pliku.
    def on_pre_enter(self, *_args):
        self._load_project_meta()

    # Po wejściu na ekran – poproś o pozwolenia na pliki (Android).
    # Potrzebujemy dostępu do zdjęć w galerii użytkownika.
    def on_enter(self, *_args):
        if platform == "android":
            from android.permissions import Permission, request_permissions
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])

    # Znajduje projekt w liście projektów.
    # Najpierw szuka po UID (unikalny numer identyfikacyjny).
    # Jeśli nie znajdzie – szuka po nazwie projektu (rozwiązanie awaryjne).
    def _find_project(self, projects):
        if self._original_uid:
            for p in projects:
                if p.get("uid") == self._original_uid:
                    return p
        for p in projects:
            if p.get("title") == self._original_title:
                return p
        return None

    # Wczytuje aktualne dane projektu (nazwa, kolor, emoji, zdjęcie) z pliku.
    def _load_project_meta(self):
        self._original_uid = self.project_uid or ""
        self._original_title = self.project_title or ""
        self.name_text = self._original_title
        name_input = self.ids.get("name_input")
        if name_input is not None:
            name_input.text = self._original_title

        projects = _load_json(_user_path("projects.json"), [])
        proj = self._find_project(projects)
        if proj is None:
            self.selected_color = [0.7, 0.5, 1, 1]
            self.selected_icon = resolve_emoji_source("emoticon-happy-outline")
            self.selected_image_path = ""
            return
        self.selected_color = list(proj.get("color") or [0.7, 0.5, 1, 1])
        self.selected_icon = resolve_emoji_source(
            proj.get("icon") or "emoticon-happy-outline"
        )
        self.selected_image_path = proj.get("image") or ""

    # Otwiera wybór zdjęcia z galerii systemowej.
    def select_photo(self):
        filechooser.open_file(
            title="Wybierz zdjęcie projektu",
            filters=[("Images", "*.png", "*.jpg", "*.jpeg")],
            on_selection=self._on_image_selected,
        )

    # Po wybraniu zdjęcia z galerii – przekazuje je do funkcji, która
    # przetworzy i wyświetli obrazek. Jeśli nic nie wybrano – nic nie robi.
    def _on_image_selected(self, selection):
        if not selection:
            return
        Clock.schedule_once(
            lambda _dt: self._apply_selected_photo(selection[0]), 0
        )

    # Przygotowuje wybrane zdjęcie do użycia: zmniejsza je i zapisuje
    # w prywatnym folderze aplikacji. Jeśli się nie uda – używa oryginału.
    def _apply_selected_photo(self, path):
        cache_dir = _user_path("project_images")
        try:
            path = prepare_project_image(path, cache_dir)
        except Exception as exc:
            print(f"[ProjectSettings] image normalize failed, using original: {exc}")
        self.selected_image_path = ""
        Clock.schedule_once(lambda _dt: self._set_image_path(path), 0.05)

    # Ustawia ścieżkę do wybranego zdjęcia w podglądzie, co powoduje
    # wyświetlenie nowego obrazka na karcie projektu.
    def _set_image_path(self, path):
        self.selected_image_path = path

    # Usuwa zdjęcie projektu (przywraca do domyślnego tła kolorowego).
    def clear_photo(self):
        self.selected_image_path = ""

    # Otwiera okno wyboru koloru tła projektu (paleta barw).
    def select_color(self):
        open_palette_picker(
            default_color=tuple(self.selected_color),
            on_pick=self._apply_picked_color,
        )

    # Zapisuje wybrany przez użytkownika kolor jako aktualny kolor projektu.
    def _apply_picked_color(self, color):
        self.selected_color = list(color)

    # Anuluj – wróć do ekranu projektu bez zapisywania zmian.
    def cancel(self):
        self._return_to_project(self._original_title)

    # Zapisz zmiany – nadpisz dane projektu w plikach.
    # Zapisuje zmienione dane projektu do plików: aktualizuje nazwę,
    # kolor, emoji i zdjęcie. Odświeża ekran główny i wraca do projektu.
    def save(self):
        new_name = (self.name_text or "").strip()
        if not new_name:
            new_name = self._original_title

        original = self._original_title
        original_uid = self._original_uid
        # Po zmianie nazwy nie trzeba już przestawiać kluczy w danych —
        # każdy plik stanu jest powiązany z unikalnym identyfikatorem (uid),
        # więc projekty o takich samych nazwach nie stanowią problemu.
        self._write_projects_json(new_name)
        self._rename_sessions_by_uid(new_name)
        self._refresh_home_cards()
        self._return_to_project(new_name, original_uid)

    # Pokaż okno z prośbą o potwierdzenie usunięcia projektu.
    # Operacja jest nieodwracalna – dlatego wymaga potwierdzenia.
    def delete_project(self):
        cancel_btn = MDFlatButton(text="ANULUJ")
        confirm_btn = MDFlatButton(
            text="USUŃ NA ZAWSZE",
            theme_text_color="Custom",
            text_color=(0.85, 0.18, 0.18, 1),
        )
        dlg = MDDialog(
            title="Usunąć projekt?",
            text=(
                f"Tej operacji nie da się cofnąć. Cała historia czasu, "
                f"notatki i etapy projektu „{self._original_title}” "
                f"zostaną trwale usunięte."
            ),
            buttons=[cancel_btn, confirm_btn],
        )
        cancel_btn.bind(on_release=lambda *_a: dlg.dismiss())
        confirm_btn.bind(on_release=lambda *_a: self._confirm_delete(dlg))
        dlg.open()

    def _confirm_delete(self, dlg):
        # Usuwa projekt ze wszystkich plików po potwierdzeniu przez użytkownika.
        # Czyści: listę projektów, szczegóły (notatki, cele), historię sesji
        # oraz zapisane pozycje kart na ekranie głównym.
        # Na koniec odświeża ekran główny i wraca do niego.
        dlg.dismiss()
        uid = self._original_uid
        title = self._original_title
        if not uid and not title:
            return

        projects = _load_json(_user_path("projects.json"), [])
        if uid:
            projects = [p for p in projects if p.get("uid") != uid]
        else:
            projects = [p for p in projects if p.get("title") != title]
        _save_json(_user_path("projects.json"), projects)

        details = _load_json(_user_path("project_details.json"), {})
        for key in (uid, title):
            if key and key in details:
                details.pop(key)
        _save_json(_user_path("project_details.json"), details)

        sessions = _load_json(_user_path("sessions.json"), [])
        if uid:
            sessions = [s for s in sessions if s.get("project_uid") != uid]
        else:
            sessions = [s for s in sessions if s.get("project_title") != title]
        _save_json(_user_path("sessions.json"), sessions)

        positions = _load_json(_user_path("card_positions.json"), {})
        for key in (uid, title):
            if key and key in positions:
                positions.pop(key)
        _save_json(_user_path("card_positions.json"), positions)

        self._refresh_home_cards()
        self._go_home_after_delete()

    # Zapisuje zmienione dane projektu do pliku projects.json.
    # Tworzy nowy UID jeśli projekt go nie miał (migracja ze starej wersji).
    def _write_projects_json(self, new_name):
        import uuid as _uuid
        path = _user_path("projects.json")
        projects = _load_json(path, [])
        updated = False
        for p in projects:
            match = (
                (self._original_uid and p.get("uid") == self._original_uid)
                or (not self._original_uid and p.get("title") == self._original_title)
            )
            if match:
                p["title"] = new_name
                p["color"] = list(self.selected_color)
                p["icon"] = self.selected_icon
                p["image"] = self.selected_image_path
                if not p.get("uid"):
                    p["uid"] = self._original_uid or f"proj-{_uuid.uuid4().hex}"
                self._original_uid = p["uid"]
                self.project_uid = p["uid"]
                updated = True
                break
        if not updated:
            new_uid = self._original_uid or f"proj-{_uuid.uuid4().hex}"
            projects.append(
                {
                    "uid": new_uid,
                    "title": new_name,
                    "color": list(self.selected_color),
                    "icon": self.selected_icon,
                    "image": self.selected_image_path,
                }
            )
            self._original_uid = new_uid
            self.project_uid = new_uid
        _save_json(path, projects)

    # Po zmianie nazwy – aktualizuje nazwę we wszystkich zapisanych sesjach.
    # Dzięki temu historia sesji nadal pasuje do projektu mimo zmiany nazwy.
    def _rename_sessions_by_uid(self, new_name):
        if not self._original_uid:
            return
        path = _user_path("sessions.json")
        sessions = _load_json(path, [])
        changed = False
        for s in sessions:
            if s.get("project_uid") == self._original_uid and s.get("project_title") != new_name:
                s["project_title"] = new_name
                changed = True
        if changed:
            _save_json(path, sessions)

    # Odświeża karty na ekranie głównym po zmianie lub usunięciu projektu.
    # Usuwa stare karty i ładuje je ponownie z pliku.
    def _refresh_home_cards(self):
        app = MDApp.get_running_app()
        if not app or not getattr(app, "root", None):
            return
        try:
            home = app.root.get_screen("home")
        except Exception:
            return
        if home is None:
            return
        container = home.ids.get("projects_container")
        if container is None:
            return
        from screens.home import ProjectCard
        for child in list(container.children):
            if isinstance(child, ProjectCard):
                container.remove_widget(child)
        home.load_projects()
        Clock.schedule_once(lambda _dt: home.restore_card_positions(), 0)
        home.refresh_last_session()

    # Wraca do ekranu szczegółów projektu po zapisaniu zmian.
    def _return_to_project(self, title, uid=""):
        app = MDApp.get_running_app()
        if not app or not getattr(app, "root", None):
            return
        info = app.root.get_screen("project_info")
        info.project_uid = uid or self._original_uid or info.project_uid
        info.project_title = title
        app.root.current = "project_info"

    # Po usunięciu projektu – wraca do ekranu głównego (bo projektu już nie ma).
    def _go_home_after_delete(self):
        app = MDApp.get_running_app()
        if not app or not getattr(app, "root", None):
            return
        app.root.current = "home"

    # --- Misc ---

    def _warn(self, title, text):
        ok = MDFlatButton(text="OK")
        dlg = MDDialog(title=title, text=text, buttons=[ok])
        ok.bind(on_release=lambda *_a: dlg.dismiss())
        dlg.open()

    # Gdy użytkownik wpisuje nową nazwę projektu – zapamiętuje ją,
    # żeby można było zapisać przy kliknięciu przycisku "Zapisz".
    def on_name_input(self, value):
        self.name_text = value or ""