import json
import os

from kivy.config import Config

# Must be set before the Window is created (critical on Android).
Config.set("graphics", "softinput_mode", "resize")

from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.utils import platform
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.screenmanager import ScreenManager, NoTransition

# Only HomeScreen is imported at startup. Every other screen module is
# imported + constructed on a deferred Clock tick AFTER the first frame
# renders, so the splash → home transition feels instant. See
# ``_finalize_startup`` and ``_ensure_screen`` below.
from screens.home import HomeScreen


class LazyScreenManager(ScreenManager):
    """ScreenManager that lazy-builds deferred screens on first access.

    Both ``get_screen(name)`` calls and ``current = name`` assignments end
    up calling ``self.get_screen(...)`` internally (Kivy's own
    ``on_current`` handler does this, see ``kivy/uix/screenmanager.py``).
    Overriding ``get_screen`` is therefore enough to make every existing
    navigation path (``app.root.current = "X"`` in KV, ``get_screen("X")``
    in Python) silently build the target screen if it hasn't been
    constructed yet.
    """

    def get_screen(self, name):
        if not any(s.name == name for s in self.screens):
            app = MDApp.get_running_app()
            if app is not None:
                try:
                    app._ensure_screen(name)
                except Exception:
                    pass
        return super().get_screen(name)

if platform in ('win', 'linux', 'macosx'):
    Window.size = (450, 900)


# (screen_name, kv_file_or_None, module_path, class_name)
# Ordered so KV dependencies resolve correctly:
#   * home.kv (loaded eagerly in build) declares ClickableAnchorLayout /
#     ClickableBoxLayout, used by every other kv.
#   * addProject.kv declares ProjectTextInput / ProjectTileButton used by
#     projectSettings.kv, so it must load first.
_LAZY_SCREENS = [
    ("add_project",      "kv/addProject.kv",      "screens.add_project",      "AddProjectScreen"),
    ("statistics",       "kv/statistics.kv",      "screens.statistics",       "StatisticsScreen"),
    ("project_info",     "kv/project_info.kv",    "screens.project_info",     "ProjectInfoScreen"),
    ("project_settings", "kv/projectSettings.kv", "screens.project_settings", "ProjectSettingsScreen"),
    ("geofence_picker",  None,                    "screens.geofence_picker",  "GeofencePickerScreen"),
]


class TimeTrackerApp(MDApp):
    theme_bg = StringProperty('#8A2BE2')
    theme_card_bg = StringProperty('#B388FF')
    theme_session_bg = StringProperty('#5E35B1')
    theme_session_header = StringProperty('#E8D5FC')
    theme_text_dark = StringProperty('#212121')
    grid_layout = BooleanProperty(False)

    def build(self):
        # Load only the home screen's KV at startup; everything else is
        # deferred to a post-first-frame Clock tick so the user sees the
        # home screen as fast as possible.
        Builder.load_file("kv/home.kv")

        # NoTransition = instant screen swap, no slide/fade animation.
        # Swap for SlideTransition / FadeTransition / SwapTransition /
        # WipeTransition / CardTransition / FallOutTransition / RiseInTransition
        # to try a different effect (all from kivy.uix.screenmanager).
        self.screen_manager = LazyScreenManager(transition=NoTransition())
        self.screen_manager.add_widget(HomeScreen(name='home'))
        return self.screen_manager

    def on_start(self):
        if platform == "android":
            try:
                Window.softinput_mode = "resize"
            except Exception:
                pass
        # One-time data migration: backfill ``uid`` on every projects.json
        # entry and re-key title-keyed state files (project_details,
        # active_timer, active_goals, card_positions, sessions) to uid keys.
        # Must run BEFORE load_projects() so the home cards pick up the uids.
        # Idempotent: a no-op once every project already has a uid.
        try:
            from screens import active_timer
            active_timer.migrate_legacy_state_to_uids()
        except Exception as exc:
            print(f"[main] uid migration failed: {exc!r}")
        # Critical for the first frame: layout pref + project cards visible.
        # Everything else (emoji unpack, other screens, statistics refresh,
        # notification permission, intent handling, timer service kick) is
        # deferred to ``_finalize_startup`` so the splash → home transition
        # isn't blocked by it.
        home_screen = self.screen_manager.get_screen('home')
        self.load_layout_pref()
        home_screen.load_projects()
        home_screen.schedule_initial_layout()
        home_screen.refresh_last_session()
        # Schedule deferred initialization. delay=0 = next frame.
        Clock.schedule_once(self._finalize_startup, 0)

    def _finalize_startup(self, *_args):
        """Post-first-frame init. Each step is short (<one frame on a fast
        device) and we yield between heavy steps so the UI stays
        responsive while the user is exploring the home screen."""
        if platform == "android":
            self._request_android_notification_permission()

        # Emoji asset extraction: fast (~ms) when the zip stamp matches; can
        # take ~hundreds of ms on first launch after install. Worst case is
        # absorbed here, off the critical path.
        try:
            from screens.emoji_assets import ensure_emoji_assets
            ensure_emoji_assets()
        except Exception:
            pass

        # Build remaining screens one per Clock tick to avoid stalling the
        # UI thread with several screen constructors back-to-back.
        self._lazy_build_queue = list(_LAZY_SCREENS)
        Clock.schedule_once(self._build_next_lazy_screen, 0)

    def _build_next_lazy_screen(self, *_args):
        queue = getattr(self, "_lazy_build_queue", None)
        if not queue:
            self._after_all_screens_built()
            return
        name, kv, module_path, class_name = queue.pop(0)
        self._ensure_screen(name, kv, module_path, class_name)
        # Yield to the UI thread between screens.
        Clock.schedule_once(self._build_next_lazy_screen, 0)

    def _ensure_screen(self, name, kv=None, module_path=None, class_name=None):
        """Build a deferred screen and add it to the ScreenManager. Idempotent.

        If called with only ``name``, looks the rest up from ``_LAZY_SCREENS``.
        Safe to call from navigation entry points as a defensive fallback in
        case the user navigates before ``_finalize_startup`` has finished
        building everything.
        """
        for s in self.screen_manager.screens:
            if s.name == name:
                return s
        if kv is None and module_path is None:
            for spec_name, spec_kv, spec_mod, spec_cls in _LAZY_SCREENS:
                if spec_name == name:
                    kv, module_path, class_name = spec_kv, spec_mod, spec_cls
                    break
        if module_path is None:
            return None
        if kv:
            try:
                Builder.load_file(kv)
            except Exception:
                pass
        try:
            mod = __import__(module_path, fromlist=[class_name])
            cls = getattr(mod, class_name)
            screen = cls(name=name)
            self.screen_manager.add_widget(screen)
            return screen
        except Exception:
            return None

    def _after_all_screens_built(self):
        # Statistics: only matters when the user navigates there; the
        # screen's own ``on_enter`` would refresh anyway, but doing it once
        # here keeps the first navigation snappy.
        try:
            self.screen_manager.get_screen("statistics").refresh_statistics()
        except Exception:
            pass
        # Timer service + Android intent handling.
        try:
            from screens import active_timer
            if active_timer.has_active_items():
                from screens.project_info import ensure_android_timer_service
                ensure_android_timer_service()
        except Exception:
            pass
        Clock.schedule_once(
            lambda _dt: self._open_project_from_android_intent_or_active(), 0
        )

    def on_resume(self):
        Clock.schedule_once(lambda _dt: self._open_project_from_android_intent_or_active(prefer_active=False), 0)
        return True

    def _request_android_notification_permission(self):
        try:
            from jnius import autoclass

            version = autoclass("android.os.Build$VERSION")
            if int(version.SDK_INT) < 33:
                return
            from android.permissions import request_permissions

            request_permissions(["android.permission.POST_NOTIFICATIONS"])
        except Exception:
            pass

    def _android_intent_project(self):
        if platform != "android":
            return ""
        try:
            from jnius import autoclass

            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            intent = activity.getIntent()
            project = intent.getStringExtra("project") or ""
            if project:
                intent.removeExtra("project")
            return project
        except Exception:
            return ""

    def _open_project_from_android_intent_or_active(self, prefer_active=True):
        from screens import active_timer

        project = self._android_intent_project()
        project_uid = ""
        if not project and prefer_active:
            timer_state = active_timer.read_project_timer()
            project = timer_state.get("project_title", "")
            project_uid = timer_state.get("project_uid", "")
            if not project:
                goals = active_timer.read_goals()
                if goals:
                    project = goals[0].get("project_title", "")
                    project_uid = goals[0].get("project_uid", "")
        if not project_uid and project:
            # Best-effort title -> uid lookup so the project_info screen keys
            # state by the right project even when the Android intent (which
            # only carries the title) is the entry point.
            for meta in active_timer._read_projects():
                if meta.get("title") == project:
                    project_uid = meta.get("uid", "")
                    break
        if project:
            info = self._ensure_screen("project_info")
            if info is None:
                return
            info.project_uid = project_uid
            info.project_title = project
            self.screen_manager.current = "project_info"

    def _layout_pref_path(self):
        return os.path.join(self.user_data_dir, "layout_pref.json")

    def load_layout_pref(self):
        path = self._layout_pref_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.grid_layout = bool(data.get("grid_layout", False))
        except (OSError, json.JSONDecodeError):
            pass

    def save_layout_pref(self):
        path = self._layout_pref_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"grid_layout": self.grid_layout}, f)
        except OSError:
            pass

    def toggle_layout_menu(self):
        self.grid_layout = not self.grid_layout
        self.save_layout_pref()
        home = self.screen_manager.get_screen("home")
        if self.grid_layout:
            home.apply_grid_layout()
        else:
            home.restore_card_positions()

if __name__ == '__main__':
    #test()
    TimeTrackerApp().run()
