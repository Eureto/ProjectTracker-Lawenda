"""Editable project metadata: rename, photo, color, delete.

Reached from the cog button on ProjectInfoScreen. Shares the visual idiom of
AddProjectScreen (preview card + tile buttons + name input + floating confirm)
plus a red "Usuń projekt" action that requires two-step confirmation.

All edits are deferred until the user taps the checkmark; that's also the only
moment the rename propagates to every persisted JSON file. Deletion runs
through a dedicated path that scrubs sessions, project_details, card_positions
and the projects list before popping the user back to home.
"""

import json
import os

from kivy.clock import Clock
from kivy.properties import ColorProperty, StringProperty
from kivy.uix.screenmanager import Screen
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from plyer import filechooser

from screens.color_palette import open_palette_picker
from screens.emoji_assets import resolve_emoji_source
from screens.image_utils import prepare_project_image


def _user_path(*parts):
    app = MDApp.get_running_app()
    return os.path.join(app.user_data_dir, *parts)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class ProjectSettingsScreen(Screen):
    """Edit / delete a single project. ``project_title`` is the lookup key."""

    project_title = StringProperty("")
    selected_color = ColorProperty([0.7, 0.5, 1, 1])
    selected_icon = StringProperty("emoticon-happy-outline")
    selected_image_path = StringProperty("")
    name_text = StringProperty("")

    # Original key — kept so we can rewrite related JSON when the name changes.
    _original_title = ""

    def on_pre_enter(self, *_args):
        self._load_project_meta()

    def on_enter(self, *_args):
        if platform == "android":
            from android.permissions import Permission, request_permissions

            request_permissions(
                [Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE]
            )

    def _load_project_meta(self):
        """Hydrate the form with the project's current persisted state."""
        self._original_title = self.project_title or ""
        self.name_text = self._original_title
        name_input = self.ids.get("name_input")
        if name_input is not None:
            name_input.text = self._original_title

        projects = _load_json(_user_path("projects.json"), [])
        proj = next(
            (p for p in projects if p.get("title") == self._original_title),
            None,
        )
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

    # --- Photo / color pickers ---

    def select_photo(self):
        filechooser.open_file(
            title="Wybierz zdjęcie projektu",
            filters=[("Images", "*.png", "*.jpg", "*.jpeg")],
            on_selection=self._on_image_selected,
        )

    def _on_image_selected(self, selection):
        if not selection:
            return
        Clock.schedule_once(
            lambda _dt: self._apply_selected_photo(selection[0]), 0
        )

    def _apply_selected_photo(self, path):
        cache_dir = _user_path("project_images")
        try:
            path = prepare_project_image(path, cache_dir)
        except Exception as exc:
            print(f"[ProjectSettings] image normalize failed, using original: {exc}")
        self.selected_image_path = ""
        Clock.schedule_once(lambda _dt: self._set_image_path(path), 0.05)

    def _set_image_path(self, path):
        self.selected_image_path = path

    def clear_photo(self):
        self.selected_image_path = ""

    def select_color(self):
        open_palette_picker(
            default_color=tuple(self.selected_color),
            on_pick=self._apply_picked_color,
        )

    def _apply_picked_color(self, color):
        self.selected_color = list(color)

    # --- Save / cancel ---

    def cancel(self):
        # Discard pending edits; just navigate back to the project view.
        self._return_to_project(self._original_title)

    def save(self):
        new_name = (self.name_text or "").strip()
        if not new_name:
            new_name = self._original_title

        original = self._original_title
        rename = (new_name != original) and bool(original)

        # Block renaming over an existing project with the same name.
        if rename:
            projects = _load_json(_user_path("projects.json"), [])
            taken = any(
                p.get("title") == new_name and p.get("title") != original
                for p in projects
            )
            if taken:
                self._warn(
                    "Nazwa zajęta",
                    f"Projekt „{new_name}” już istnieje.",
                )
                return

        self._write_projects_json(original, new_name)
        if rename:
            self._rename_project_details(original, new_name)
            self._rename_sessions(original, new_name)
            self._rename_card_position(original, new_name)

        self._refresh_home_cards()
        self._return_to_project(new_name)

    # --- Delete with confirmation ---

    def delete_project(self):
        dlg = MDDialog(
            title="Usunąć projekt?",
            text=(
                f"Tej operacji nie da się cofnąć. Cała historia czasu, "
                f"notatki i etapy projektu „{self._original_title}” "
                f"zostaną trwale usunięte."
            ),
        )
        cancel_btn = MDFlatButton(text="ANULUJ")
        confirm_btn = MDFlatButton(text="USUŃ NA ZAWSZE")
        confirm_btn.theme_text_color = "Custom"
        confirm_btn.text_color = (0.85, 0.18, 0.18, 1)
        cancel_btn.bind(on_release=lambda *_a: dlg.dismiss())
        confirm_btn.bind(
            on_release=lambda *_a: self._confirm_delete(dlg)
        )
        dlg.buttons = [cancel_btn, confirm_btn]
        dlg.open()

    def _confirm_delete(self, dlg):
        dlg.dismiss()
        title = self._original_title
        if not title:
            return

        # 1. Remove the project metadata entry.
        projects = [
            p for p in _load_json(_user_path("projects.json"), [])
            if p.get("title") != title
        ]
        _save_json(_user_path("projects.json"), projects)

        # 2. Drop the per-project content blob.
        details = _load_json(_user_path("project_details.json"), {})
        if title in details:
            details.pop(title)
            _save_json(_user_path("project_details.json"), details)

        # 3. Strip recorded sessions for the project.
        sessions = _load_json(_user_path("sessions.json"), [])
        sessions = [
            s for s in sessions if s.get("project_title") != title
        ]
        _save_json(_user_path("sessions.json"), sessions)

        # 4. Forget the saved card position.
        positions = _load_json(_user_path("card_positions.json"), {})
        if title in positions:
            positions.pop(title)
            _save_json(_user_path("card_positions.json"), positions)

        self._refresh_home_cards()
        self._go_home_after_delete()

    # --- Persistence helpers ---

    def _write_projects_json(self, original, new_name):
        path = _user_path("projects.json")
        projects = _load_json(path, [])
        updated = False
        for p in projects:
            if p.get("title") == original:
                p["title"] = new_name
                p["color"] = list(self.selected_color)
                p["icon"] = self.selected_icon
                p["image"] = self.selected_image_path
                updated = True
                break
        if not updated:
            # First time we're persisting metadata for this project.
            projects.append(
                {
                    "title": new_name,
                    "color": list(self.selected_color),
                    "icon": self.selected_icon,
                    "image": self.selected_image_path,
                }
            )
        _save_json(path, projects)

    def _rename_project_details(self, original, new_name):
        path = _user_path("project_details.json")
        data = _load_json(path, {})
        if original in data:
            data[new_name] = data.pop(original)
            _save_json(path, data)

    def _rename_sessions(self, original, new_name):
        path = _user_path("sessions.json")
        sessions = _load_json(path, [])
        changed = False
        for s in sessions:
            if s.get("project_title") == original:
                s["project_title"] = new_name
                changed = True
        if changed:
            _save_json(path, sessions)

    def _rename_card_position(self, original, new_name):
        path = _user_path("card_positions.json")
        data = _load_json(path, {})
        if original in data:
            data[new_name] = data.pop(original)
            _save_json(path, data)

    # --- Navigation ---

    def _refresh_home_cards(self):
        """Reload home cards so the rename/delete is reflected immediately."""
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
        # Re-import locally to avoid a circular module dep at file load time.
        from screens.home import ProjectCard

        for child in list(container.children):
            if isinstance(child, ProjectCard):
                container.remove_widget(child)
        home.load_projects()
        Clock.schedule_once(lambda _dt: home.restore_card_positions(), 0)
        home.refresh_last_session()

    def _return_to_project(self, title):
        app = MDApp.get_running_app()
        if not app or not getattr(app, "root", None):
            return
        info = app.root.get_screen("project_info")
        info.project_title = title
        app.root.current = "project_info"

    def _go_home_after_delete(self):
        app = MDApp.get_running_app()
        if not app or not getattr(app, "root", None):
            return
        app.root.current = "home"

    # --- Misc ---

    def _warn(self, title, text):
        dlg = MDDialog(title=title, text=text)
        ok = MDFlatButton(text="OK")
        ok.bind(on_release=lambda *_a: dlg.dismiss())
        dlg.buttons = [ok]
        dlg.open()

    def on_name_input(self, value):
        """Mirror the TextInput value into the StringProperty for kv bindings."""
        self.name_text = value or ""
