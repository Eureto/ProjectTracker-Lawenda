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
from kivy.uix.screenmanager import ScreenManager, Screen
from screens.home import HomeScreen
from screens.add_project import AddProjectScreen
from screens.statistics import StatisticsScreen
from screens.project_info import ProjectInfoScreen, ensure_android_timer_service
from screens.project_settings import ProjectSettingsScreen
from screens import active_timer
from screens.emoji_assets import ensure_emoji_assets

# Window size for testing on pc
if platform in ('win', 'linux', 'macosx'):
    Window.size = (450, 900)

class TimeTrackerApp(MDApp):
    theme_bg = StringProperty('#8A2BE2')
    theme_card_bg = StringProperty('#B388FF')
    theme_session_bg = StringProperty('#5E35B1')
    theme_session_header = StringProperty('#E8D5FC')
    theme_text_dark = StringProperty('#212121')
    grid_layout = BooleanProperty(False)

    def build(self):
        base_path = os.path.dirname(__file__)
        # Load all KV files. projectSettings.kv depends on ProjectTextInput /
        # ProjectTileButton / ClickableAnchorLayout / ClickableBoxLayout
        # declared inside addProject.kv, so it must load after.
        Builder.load_file("kv/home.kv")
        Builder.load_file("kv/addProject.kv")
        Builder.load_file("kv/statistics.kv")
        Builder.load_file("kv/project_info.kv")
        Builder.load_file("kv/projectSettings.kv")

        self.screen_manager = ScreenManager()
        self.screen_manager.add_widget(HomeScreen(name='home'))
        self.screen_manager.add_widget(AddProjectScreen(name='add_project'))
        self.screen_manager.add_widget(StatisticsScreen(name='statistics'))
        self.screen_manager.add_widget(ProjectInfoScreen(name='project_info'))
        self.screen_manager.add_widget(ProjectSettingsScreen(name='project_settings'))
        return self.screen_manager

    def on_start(self):
        if platform == "android":
            try:
                Window.softinput_mode = "resize"
            except Exception:
                pass
            self._request_android_notification_permission()
        # Initialize the 3 samples once the app starts
        home_screen = self.screen_manager.get_screen('home')
        ensure_emoji_assets()
        self.load_layout_pref()
        home_screen.load_projects()
        home_screen.schedule_initial_layout()
        home_screen.refresh_last_session()
        self.screen_manager.get_screen("statistics").refresh_statistics()
        if active_timer.has_active_items():
            ensure_android_timer_service()
        Clock.schedule_once(lambda _dt: self._open_project_from_android_intent_or_active(), 0)

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
        project = self._android_intent_project()
        if not project and prefer_active:
            timer_state = active_timer.read_project_timer()
            project = timer_state.get("project_title", "")
            if not project:
                goals = active_timer.read_goals()
                project = goals[0].get("project_title", "") if goals else ""
        if project:
            info = self.screen_manager.get_screen("project_info")
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
