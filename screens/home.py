import os
import json

from kivy.uix.widget import Widget
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ColorProperty
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.graphics import Color, Line, Ellipse
from kivy.utils import get_color_from_hex

from kivymd.app import MDApp
from kivymd.uix.card import MDCard
from kivymd.uix.screen import MDScreen

class DotProgressBar(Widget):
    total_steps = NumericProperty(5)
    current_step = NumericProperty(2)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.update_canvas, size=self.update_canvas, 
                  total_steps=self.update_canvas, current_step=self.update_canvas)

    def update_canvas(self, *args):
        app = MDApp.get_running_app()
        color_dark = get_color_from_hex(app.theme_text_dark) if hasattr(app, 'theme_text_dark') else (0.1, 0.1, 0.1, 1)
        color_light = get_color_from_hex("#E0E0E0") 
        
        self.canvas.clear()
        with self.canvas:
            Color(*color_dark)
            start_x = self.x + dp(5)
            end_x = self.right - dp(5)
            line_y = self.center_y
            Line(points=[start_x, line_y, end_x, line_y], width=dp(1.5))
            
            if self.total_steps > 1:
                spacing = (end_x - start_x) / (self.total_steps - 1)
                for i in range(self.total_steps):
                    Color(*(color_dark if i < self.current_step else color_light))
                    dot_x = start_x + (i * spacing) - dp(6)
                    dot_y = line_y - dp(6)
                    Ellipse(pos=(dot_x, dot_y), size=(dp(12), dp(12)))

class ProjectCard(MDCard):
    title = StringProperty("")
    image_source = StringProperty("")
    emoji_source = StringProperty("")
    angle = NumericProperty(0)
    card_color = ColorProperty([0.7, 0.5, 1, 1])
    height_multiplier = NumericProperty(1.0)
    title_font_style = StringProperty("Subtitle2")
    emoji_size = NumericProperty(dp(40))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._long_press_ev = None
        self._shake_anim = None
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            # Start 2s timer for long press detection
            self._long_press_ev = Clock.schedule_once(lambda dt: self._start_drag_mode(touch), 1.0)
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def _start_drag_mode(self, touch):
        self.pos_hint = {}  # Allow free movement within the FloatLayout
        # Start Shaking animation
        self._shake_anim = Animation(angle=2, d=0.08) + Animation(angle=-2, d=0.08)
        self._shake_anim.repeat = True
        self._shake_anim.start(self)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self._shake_anim:
                self.x += touch.dx
                self.y += touch.dy
            else:
                if abs(touch.dx) > 10 or abs(touch.dy) > 10:
                    if self._long_press_ev:
                        Clock.unschedule(self._long_press_ev)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if self._long_press_ev:
                Clock.unschedule(self._long_press_ev)
            if self._shake_anim:
                self._shake_anim.stop(self)
                self._shake_anim = None
                Animation(angle=0, d=0.1).start(self)
                self.save_position()
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def save_position(self):
        if self.parent:
            rel_x = self.x / self.parent.width
            rel_y = self.top / self.parent.height

            app = MDApp.get_running_app()
            storage_path = os.path.join(app.user_data_dir, 'card_positions.json')

            data = {}
            if os.path.exists(storage_path):
                try:
                    with open(storage_path, 'r') as f:
                        data = json.load(f)
                except (IOError, json.JSONDecodeError):
                    pass

            data[self.title] = {'x': rel_x, 'top': rel_y}

            with open(storage_path, 'w') as f:
                json.dump(data, f)

            print(f"Position saved for {self.title}: x={rel_x:.2f}, top={rel_y:.2f}")

class SessionCard(MDCard):
    pass

class HomeScreen(MDScreen):
    def load_projects(self):
        """Loads project definitions from storage and adds them to the UI."""
        app = MDApp.get_running_app()
        storage_path = os.path.join(app.user_data_dir, 'projects.json')

        if os.path.exists(storage_path):
            try:
                with open(storage_path, 'r') as f:
                    projects = json.load(f)
                for p in projects:
                    self.add_project_card(
                        p['title'], p['image'], p['icon'], p['color'],
                        0.1, 0.9 # Default pos, restore_card_positions will fix this
                    )
            except (IOError, json.JSONDecodeError) as e:
                print(f"Error loading projects: {e}")

    def restore_card_positions(self):
        app = MDApp.get_running_app()
        storage_path = os.path.join(app.user_data_dir, 'card_positions.json')

        if os.path.exists(storage_path):
            try:
                with open(storage_path, 'r') as f:
                    data = json.load(f)
                for card in self.ids.projects_container.children:
                    if isinstance(card, ProjectCard) and card.title in data:
                        card.pos_hint = data[card.title]
            except (IOError, json.JSONDecodeError) as e:
                print(f"Error restoring positions: {e}")

    def add_project_card(self, title, image, emoji, color, x_pos, y_top):
        container = self.ids.projects_container
        new_card = ProjectCard(
            title=title, image_source=image, emoji_source=emoji,
            card_color=color,
            pos_hint={'x': x_pos, 'top': y_top}
        )
        container.add_widget(new_card)
        self.update_container_height()

    def update_container_height(self):
        container = self.ids.projects_container
        # Ensure height is at least the height of the screen
        min_h = self.height
        for child in container.children:
            if child.top > min_h:
                min_h = child.top
        container.height = min_h + dp(150) # Add buffer for the bottom navbar