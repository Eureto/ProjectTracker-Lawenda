import os
import json
from kivy.properties import StringProperty, ColorProperty, NumericProperty, ObjectProperty
from kivy.uix.screenmanager import Screen
from kivymd.uix.pickers import MDColorPicker
from kivymd.uix.dialog import MDDialog
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivymd.uix.button import MDIconButton
from kivy.uix.image import AsyncImage
from kivymd.uix.label import MDIcon
from kivymd.uix.fitimage import FitImage
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import platform
from kivy.clock import Clock
from plyer import filechooser
from kivy.logger import Logger
from kivymd.app import MDApp
from kivymd.uix.behaviors import RectangularRippleBehavior
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.factory import Factory

# Section: Custom button for the RecycleView using standard Image for maximum Android compatibility
class EmojiButton(ButtonBehavior, AsyncImage):
    screen = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nocache = True # Helps memory with 4000+ files
        self.allow_stretch = True
        self.keep_ratio = True

    def on_release(self):
        if self.screen:
            self.screen._on_emoji_selected(self.source)

Factory.register('EmojiButton', cls=EmojiButton)

class AddProjectScreen(Screen):
    selected_color = ColorProperty([0.7, 0.5, 1, 1]) # Default soft purple
    selected_icon = StringProperty("emoticon-happy-outline")
    selected_image_path = StringProperty("")

    def on_enter(self):
        # Required for Android to access the gallery/file system at runtime
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])

    def select_emoji(self):
        """Opens a custom emoji picker dialog."""
        

    def _on_emoji_selected(self, emoji_val):
        self.selected_icon = emoji_val
        self.emoji_dialog.dismiss()

    def select_photo(self):
        # Opens the native Android Gallery/File picker
        filechooser.open_file(
            title="Select Project Image",
            filters=[("Images", "*.png", "*.jpg", "*.jpeg")],
            on_selection=self._on_image_selected
        )

    def _on_image_selected(self, selection):
        if selection:
            # Android callbacks often run outside the main thread.
            # We use Clock to ensure the UI updates correctly.
            Clock.schedule_once(lambda dt: self._update_image_preview(selection[0]))

    def _update_image_preview(self, path):
        # Briefly clear path to force Kivy to reload the image widget
        self.selected_image_path = ""
        
        # Tiny delay ensures the property change is broadcasted 
        # before we set the real path, forcing a refresh on Android.
        def reapply_path(dt):
            self.selected_image_path = path
            print(f"Image updated in preview: {path}")
        Clock.schedule_once(reapply_path, 0.1)

    def save_project(self):
        """Saves the project data to disk and adds it to the Home Screen."""
        app = MDApp.get_running_app()
        project_name = self.ids.project_name_input.text.strip()

        if not project_name:
            return # Could add a Toast here for "Name required"

        project_data = {
            "title": project_name,
            "color": list(self.selected_color),
            "icon": self.selected_icon,
            "image": self.selected_image_path
        }

        # 1. Persistent storage of project metadata
        storage_path = os.path.join(app.user_data_dir, 'projects.json')
        projects = []
        if os.path.exists(storage_path):
            try:
                with open(storage_path, 'r') as f:
                    projects = json.load(f)
            except (IOError, json.JSONDecodeError):
                pass
        
        projects.append(project_data)
        with open(storage_path, 'w') as f:
            json.dump(projects, f)

        # 2. Add to active HomeScreen UI
        home_screen = app.root.get_screen('home')
        home_screen.add_project_card(
            project_name, self.selected_image_path, self.selected_icon, 
            self.selected_color, 0.1, 0.9
        )

        # 3. Cleanup and Navigation
        self.ids.project_name_input.text = ""
        self.selected_image_path = ""
        self.selected_icon = "emoticon-happy-outline"
        self.selected_color = [0.7, 0.5, 1, 1]
        app.root.current = "home"

    def select_color(self):
        # Reverting to the full MDColorPicker which includes the color wheel
        color_picker = MDColorPicker(
            size_hint=(0.8, 0.85),
            default_color=self.selected_color,
            text_button_ok="WYBIERZ",
            text_button_cancel="ANULUJ",
            type_color="HEX",
            # Smaller values create a much smoother, longer gradient without hitting "white" too fast.
            # These values provide a subtle but modern shift in hue.
            adjacent_color_constants=[0.15, 0.3, 0.25],
            # Makes the color bars and selection elements rounded and modern.
            radius_color_scale=dp(15)
        )
        color_picker.open()
        # The on_release event is fired only when the "SELECT" button is clicked
        color_picker.bind(on_release=self._confirm_color)

    def _confirm_color(self, instance, type_color, color):
        # Update property when the SELECT button is clicked
        self.selected_color = color
        instance.dismiss()
