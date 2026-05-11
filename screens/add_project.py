import os
import json
import unicodedata
from kivy.properties import StringProperty, ColorProperty, NumericProperty, ObjectProperty, ListProperty
from kivy.uix.screenmanager import Screen
from kivymd.uix.pickers import MDColorPicker
from kivymd.uix.dialog import MDDialog
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivymd.uix.label import MDIcon
from kivymd.uix.fitimage import FitImage
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import platform
from kivy.clock import Clock
from plyer import filechooser

from kivymd.app import MDApp
from kivymd.uix.behaviors import RectangularRippleBehavior
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import AsyncImage
from kivy.cache import Cache
from kivy.factory import Factory
from kivy.uix.scrollview import ScrollView

# Section: Custom button for the RecycleView using standard Image for maximum Android compatibility
class EmojiButton(RectangularRippleBehavior, ButtonBehavior, AsyncImage):
    screen = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nocache = True  # Tell Kivy not to store 4000 textures in RAM
        self.size_hint = (None, None)
        self.size = (dp(60), dp(60))
        self.allow_stretch = True
        self.keep_ratio = True

    def on_release(self):
        if self.screen:
            self.screen._on_emoji_selected(self.source)

Factory.register('EmojiButton', cls=EmojiButton)

class EmojiMetadata:
    """Builds a searchable index of emojis from unicode filenames."""
    
    @staticmethod
    def extract_unicode_codepoint(filename):
        """
        Extracts unicode codepoint from filenames like 'uni271D.png' or 'u1F197.png'
        Returns tuple: (hex_string, character, name) or (None, None, None)
        """
        base = os.path.splitext(filename)[0]  # Remove .png
        
        hex_value = None
        if base.startswith('uni') and len(base) > 3:
            hex_value = base[3:]  # uni271D -> 271D
        elif base.startswith('u') and len(base) > 1:
            hex_value = base[1:]  # u1F197 -> 1F197
        
        if not hex_value:
            return None, None, None
        
        try:
            # Convert hex to unicode character
            codepoint = int(hex_value, 16)
            char = chr(codepoint)
            
            # Try to get unicode name
            try:
                name = unicodedata.name(char).lower()
            except ValueError:
                # Some codepoints don't have names, use category
                category = unicodedata.category(char)
                name = f"category_{category}".lower()
            
            return hex_value.lower(), char, name
        except (ValueError, OverflowError):
            return None, None, None
    
    @staticmethod
    def build_emoji_index(emoji_dir):
        """
        Builds a searchable index: 
        Returns list of dicts with: {source, hex, char, name, keywords}
        """
        if not os.path.exists(emoji_dir):
            return []
        
        emoji_index = []
        for filename in sorted([f for f in os.listdir(emoji_dir) if f.lower().endswith(".png")]):
            hex_val, char, name = EmojiMetadata.extract_unicode_codepoint(filename)
            
            if hex_val:
                # Build keywords for searching: hex value + name parts
                keywords = [hex_val] + (name.split('_') if name else [])
                
                emoji_index.append({
                    'source': os.path.join(emoji_dir, filename),
                    'hex': hex_val,
                    'char': char,
                    'name': name or '',
                    'keywords': keywords,
                    'screen': None  # Will be set later
                })
        
        return emoji_index
    
    @staticmethod
    def filter_emojis(emoji_index, search_term):
        """
        Filters emoji_index by search term (hex or name keywords).
        Returns filtered list.
        """
        if not search_term or not search_term.strip():
            return emoji_index[:200]  # Return first 200 if no filter
        
        search_term = search_term.lower().strip()
        filtered = []
        
        for emoji in emoji_index:
            # Search in hex value
            if search_term in emoji['hex']:
                filtered.append(emoji)
            # Search in name keywords
            elif any(search_term in keyword for keyword in emoji['keywords']):
                filtered.append(emoji)
        
        return filtered


class AddProjectScreen(Screen):
    selected_color = ColorProperty([0.7, 0.5, 1, 1]) # Default soft purple
    selected_icon = StringProperty("emoticon-happy-outline")
    selected_image_path = StringProperty("")
    _emoji_index = [] # Full searchable index (built once)
    _filtered_emojis = [] # Current filtered results
    _search_input = None  # Reference to search box
    _recycle_view = None  # Reference to RecycleView

    def on_enter(self):
        # Required for Android to access the gallery/file system at runtime
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])

    def select_emoji(self):
        """Opens a custom emoji picker dialog with search."""
        # Clear image cache to free GPU memory
        Cache.remove('kv.image')
        Cache.remove('kv.texture')

        # Build emoji index once
        if not self._emoji_index:
            app = MDApp.get_running_app()
            emoji_dir = os.path.join(app.directory, "assets", "Emoji_PNG")
            self._emoji_index = EmojiMetadata.build_emoji_index(emoji_dir)
            print(f"[EmojiPicker] Built index with {len(self._emoji_index)} emojis")

        # Start with first 100 emojis
        self._filtered_emojis = self._emoji_index[:100]

        # Create main container
        container = MDBoxLayout(
            orientation="vertical", 
            spacing=dp(5), 
            padding=dp(5),
            size_hint_y=None,
            height=dp(600)
        )
        
        # Search box
        self._search_input = MDTextField(
            hint_text="Search emoji (hex or name)...",
            mode="rectangle",
            size_hint_y=None,
            height=dp(50)
        )
        self._search_input.bind(text=self._on_search_text)
        container.add_widget(self._search_input)
        
        # ScrollView wrapper
        scroll = ScrollView(size_hint_y=1, do_scroll_x=False)
        
        # GridLayout (simpler than RecycleView)
        self._emoji_grid = MDGridLayout(
            cols=5,
            spacing=dp(5),
            padding=dp(5),
            size_hint_y=None,
            size_hint_x=1
        )
        self._emoji_grid.bind(minimum_height=self._emoji_grid.setter('height'))
        
        # Add emojis to grid
        self._populate_emoji_grid(self._filtered_emojis)
        
        scroll.add_widget(self._emoji_grid)
        container.add_widget(scroll)
        
        # Dialog with proper size
        self.emoji_dialog = MDDialog(
            title="Wybierz ikonę projektu",
            type="custom",
            content_cls=container,
            size_hint_x=0.95,
            size_hint_y=None,
            height=dp(650)
        )
        self.emoji_dialog.open()

    def _on_search_text(self, instance, value):
        """Called when search text changes - filters emoji list."""
        filtered = EmojiMetadata.filter_emojis(self._emoji_index, value)
        
        # Repopulate grid with filtered results
        self._populate_emoji_grid(filtered)
        print(f"[EmojiPicker] Filtered to {len(filtered)} emojis")

    def _on_emoji_selected(self, emoji_val):
        self.selected_icon = emoji_val
        if hasattr(self, 'emoji_dialog'):
            self.emoji_dialog.dismiss()
        # Clear search for next time
        if self._search_input:
            self._search_input.text = ""

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

    def _populate_emoji_grid(self, emoji_list):
        """Populate grid with emoji buttons."""
        self._emoji_grid.clear_widgets()
    
        for emoji in emoji_list:
            btn = EmojiButton(
                source=emoji['source'],
                screen=self,
                size_hint=(None, None),
                size=(dp(60), dp(60))
            )
            self._emoji_grid.add_widget(btn)
