import os
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.utils import platform
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.screenmanager import ScreenManager, Screen
from screens.home import HomeScreen
from screens.add_project import AddProjectScreen # Import the new screen class

# Window size for testing on pc
if platform in ('win', 'linux', 'macosx'):
    Window.size = (360, 740)

class TimeTrackerApp(MDApp):
    theme_bg = StringProperty('#8A2BE2')
    theme_card_bg = StringProperty('#B388FF')
    theme_session_bg = StringProperty('#5E35B1')
    theme_text_dark = StringProperty('#212121')
    edit_mode = BooleanProperty(False)

    def build(self):
        base_path = os.path.dirname(__file__)
        # Load all KV files
        Builder.load_file("kv/home.kv")
        Builder.load_file("kv/addProject.kv")

        self.screen_manager = ScreenManager()
        self.screen_manager.add_widget(HomeScreen(name='home'))
        self.screen_manager.add_widget(AddProjectScreen(name='add_project'))
        return self.screen_manager

    def on_start(self):
        # Initialize the 3 samples once the app starts
        home_screen = self.screen_manager.get_screen('home')
        home_screen.load_projects()
        home_screen.restore_card_positions()


    def toggle_layout_menu(self):
        self.edit_mode = not self.edit_mode

if __name__ == '__main__':
    #test()
    TimeTrackerApp().run()
