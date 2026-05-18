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
from screens.project_info import ProjectInfoScreen

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
        # Load all KV files
        Builder.load_file("kv/home.kv")
        Builder.load_file("kv/addProject.kv")
        Builder.load_file("kv/statistics.kv")
        Builder.load_file("kv/project_info.kv")

        self.screen_manager = ScreenManager()
        self.screen_manager.add_widget(HomeScreen(name='home'))
        self.screen_manager.add_widget(AddProjectScreen(name='add_project'))
        self.screen_manager.add_widget(StatisticsScreen(name='statistics'))
        self.screen_manager.add_widget(ProjectInfoScreen(name='project_info'))
        return self.screen_manager

    def on_start(self):
        if platform == "android":
            try:
                Window.softinput_mode = "resize"
            except Exception:
                pass
        # Initialize the 3 samples once the app starts
        home_screen = self.screen_manager.get_screen('home')
        self.load_layout_pref()
        home_screen.load_projects()
        if self.grid_layout:
            Clock.schedule_once(lambda _dt: home_screen.apply_grid_layout(), 0)
        else:
            home_screen.restore_card_positions()
        home_screen.refresh_last_session()
        self.screen_manager.get_screen("statistics").refresh_statistics()

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
