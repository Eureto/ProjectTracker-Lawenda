import os
import json

from screens.session_store import (
    format_duration_hms,
    format_when_label,
    get_last_session,
    schedule_home_last_session_refresh,
)

from kivy.core.text import Label as CoreLabel
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
    active_color = ColorProperty([0.08, 0.08, 0.08, 1])
    inactive_color = ColorProperty([1, 1, 1, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            pos=self.update_canvas,
            size=self.update_canvas,
            total_steps=self.update_canvas,
            current_step=self.update_canvas,
            active_color=self.update_canvas,
            inactive_color=self.update_canvas,
        )

    def update_canvas(self, *args):
        self.canvas.clear()
        if self.width < 1 or self.total_steps < 1:
            return

        active = tuple(self.active_color)
        inactive = tuple(self.inactive_color)
        start_x = self.x + dp(5)
        end_x = self.right - dp(5)
        line_y = self.center_y
        step = max(0, min(int(self.current_step), int(self.total_steps)))
        line_w = dp(2)

        with self.canvas:
            if self.total_steps > 1:
                spacing = (end_x - start_x) / (self.total_steps - 1)
                split_x = start_x + spacing * max(0, step - 1)
                if step > 1:
                    Color(*active)
                    Line(points=[start_x, line_y, split_x, line_y], width=line_w)
                if step < self.total_steps:
                    Color(*inactive)
                    Line(points=[split_x, line_y, end_x, line_y], width=line_w)
                for i in range(self.total_steps):
                    Color(*(active if i < step else inactive))
                    dot_x = start_x + (i * spacing) - dp(6)
                    dot_y = line_y - dp(6)
                    Ellipse(pos=(dot_x, dot_y), size=(dp(12), dp(12)))
            else:
                Color(*(active if step > 0 else inactive))
                Ellipse(
                    pos=(start_x - dp(6), line_y - dp(6)),
                    size=(dp(12), dp(12)),
                )

class ProjectCard(MDCard):
    title = StringProperty("")
    image_source = StringProperty("")
    emoji_source = StringProperty("")
    angle = NumericProperty(0)
    card_color = ColorProperty([0.7, 0.5, 1, 1])
    height_multiplier = NumericProperty(1.0)
    title_font_style = StringProperty("Subtitle2")
    emoji_size = NumericProperty(dp(40))
    interactive = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._long_press_ev = None
        self._shake_anim = None

    def on_touch_down(self, touch):
        if not self.interactive:
            return False
        if self.collide_point(*touch.pos):
            touch.ud["project_card_origin"] = touch.pos
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
        if not self.interactive:
            return False
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
        if not self.interactive:
            return False
        if touch.grab_current is self:
            entered_drag = self._shake_anim is not None
            if self._long_press_ev:
                Clock.unschedule(self._long_press_ev)
                self._long_press_ev = None
            if entered_drag:
                self._shake_anim.stop(self)
                self._shake_anim = None
                Animation(angle=0, d=0.1).start(self)
                self.save_position()
            else:
                origin = touch.ud.get("project_card_origin")
                if origin and self.collide_point(*touch.pos):
                    dx = touch.pos[0] - origin[0]
                    dy = touch.pos[1] - origin[1]
                    if (dx * dx + dy * dy) ** 0.5 < dp(15):
                        self.open_project_info()
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def open_project_info(self):
        app = MDApp.get_running_app()
        info = app.root.get_screen("project_info")
        info.project_title = self.title
        app.root.current = "project_info"

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
    has_session = BooleanProperty(False)
    project_name = StringProperty("")
    emoji_source = StringProperty("folder-outline")
    when_label = StringProperty("")
    duration_text = StringProperty("Czas:  00:00:00")
    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        label = self.ids.session_project_title
        label.bind(
            texture_size=self._sync_session_title_row,
            text=self._sync_session_title_row,
            size=self._sync_session_title_row,
        )
        Clock.schedule_once(lambda _dt: self._sync_session_title_row(label), 0)

    def _title_text_width(self, label):
        """Rendered text width (not the full label box — texture_size uses full width)."""
        if not label.text:
            return 0
        core = CoreLabel(
            text=label.text,
            font_size=label.font_size,
            bold=label.bold,
        )
        if label.font_name:
            core.font_name = label.font_name
        core.resolve_font_name()
        core.refresh()
        return core.texture.size[0]

    def _sync_session_title_row(self, label, *_args):
        """Full-width title (same as Czas row); icon sits ~10dp left of the text."""
        icon = self.ids.get("session_project_icon")
        if icon is None:
            return
        text_w = min(self._title_text_width(label), label.width)
        if text_w <= 0:
            return
        gap = dp(10)
        icon.size = (dp(28), dp(28))
        icon.y = label.y + (label.height - icon.height) * 0.5
        icon.x = label.right - text_w - gap - icon.width

    def apply_last_session(self, session):
        if not session:
            self.has_session = False
            self.project_name = ""
            self.when_label = ""
            self.duration_text = "Czas:  00:00:00"
            self.emoji_source = "folder-outline"
            return
        self.has_session = True
        self.project_name = session.get("project_title", "")
        icon = session.get("emoji_source") or "folder-outline"
        self.emoji_source = icon if icon else "folder-outline"
        self.when_label = format_when_label(session.get("ended_at"))
        self.duration_text = f"Czas:  {format_duration_hms(session.get('duration_seconds', 0))}"
        label = self.ids.get("session_project_title")
        if label is not None:
            Clock.schedule_once(lambda _dt, lbl=label: self._sync_session_title_row(lbl), 0)


class HomeScreen(MDScreen):
    def refresh_last_session(self):
        card = self.ids.last_session_card
        if card is not None:
            card.apply_last_session(get_last_session())

    def on_enter(self, *_args):
        # Delayed refresh covers home entering before project_info.on_leave records.
        schedule_home_last_session_refresh()
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