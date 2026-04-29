import os
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.utils import platform
# Import ScreenManager
from kivy.uix.screenmanager import ScreenManager, Screen
from screens.home import HomeScreen
from screens.add_project import AddProjectScreen # Import the new screen class

# Window size for testing on pc
if platform in ('win', 'linux', 'macosx'):
    Window.size = (360, 740)

class TimeTrackerApp(MDApp):
    def build(self):
        base_path = os.path.dirname(__file__)
        # Load all KV files
        Builder.load_file(os.path.join(base_path, "kv/home.kv"))
        Builder.load_file(os.path.join(base_path, "kv/addProject.kv")) # Load the new KV file

        self.screen_manager = ScreenManager()
        self.screen_manager.add_widget(HomeScreen(name='home'))
        self.screen_manager.add_widget(AddProjectScreen(name='add_project'))
        return self.screen_manager

if __name__ == '__main__':
    #test()
    TimeTrackerApp().run()
