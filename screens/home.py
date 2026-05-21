import os
import json

from screens.session_store import (
    format_duration_hms,
    format_when_label,
    get_last_session,
    schedule_home_last_session_refresh,
)
from screens.emoji_assets import resolve_emoji_source

from kivy.core.text import Label as CoreLabel
from kivy.uix.widget import Widget
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ColorProperty, AliasProperty
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.graphics import Color, Line, Ellipse
from kivy.utils import get_color_from_hex

from kivymd.app import MDApp

_TEXT_ON_LIGHT = (0.102, 0.102, 0.102, 1)  # #1A1A1A
_TEXT_ON_DARK = (1, 1, 1, 1)

GRID_COLUMNS = 2
CARD_SIZE_HINT_X = 0.4
# Emoji badge uses pos_hint top 1.25 and size emoji_size * 1.6 — sits above the card top.
GRID_EMOJI_TOP_EXTRA = 0.25
GRID_EMOJI_BADGE_SCALE = 1.6


def _normalize_rgba(color):
    if isinstance(color, str):
        return get_color_from_hex(color)
    channels = list(color[:4])
    while len(channels) < 3:
        channels.append(1.0)
    if len(channels) == 3:
        channels.append(1.0)
    if any(v > 1 for v in channels[:3]):
        channels = [v / 255.0 for v in channels[:3]] + [channels[3]]
    return tuple(channels[:4])


def _relative_luminance(rgba):
    r, g, b, *_ = _normalize_rgba(rgba)

    def linear(channel):
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def contrasting_text_color(background):
    """Pick light or dark text for readable contrast on background (WCAG luminance)."""
    lum = _relative_luminance(background)
    contrast_light = (1.0 + 0.05) / (lum + 0.05)
    contrast_dark = (lum + 0.05) / 0.05
    return _TEXT_ON_DARK if contrast_light >= contrast_dark else _TEXT_ON_LIGHT
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
    uid = StringProperty("")
    title = StringProperty("")
    image_source = StringProperty("")
    emoji_source = StringProperty("")
    angle = NumericProperty(0)
    card_color = ColorProperty([0.7, 0.5, 1, 1])
    title_text_color = ColorProperty(_TEXT_ON_LIGHT)
    height_multiplier = NumericProperty(1.0)
    title_font_style = StringProperty("Subtitle2")
    emoji_size = NumericProperty(dp(40))
    emoji_right_hint = NumericProperty(1.05)
    emoji_right_hint_png = NumericProperty(1.05)

    def _get_effective_emoji_right_hint(self):
        src = (self.emoji_source or "").lower()
        if src.endswith(".png"):
            return self.emoji_right_hint_png
        return self.emoji_right_hint

    effective_emoji_right_hint = AliasProperty(
        _get_effective_emoji_right_hint,
        None,
        bind=("emoji_source", "emoji_right_hint", "emoji_right_hint_png"),
    )

    interactive = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._long_press_ev = None
        self._shake_anim = None
        self._update_title_text_color()

    def on_card_color(self, *_args):
        self._update_title_text_color()

    def _update_title_text_color(self):
        self.title_text_color = contrasting_text_color(self.card_color)

    def _free_layout_enabled(self):
        app = MDApp.get_running_app()
        return app is None or not app.grid_layout

    def on_touch_down(self, touch):
        if not self.interactive:
            return False
        if self.collide_point(*touch.pos):
            touch.ud["project_card_origin"] = touch.pos
            if self._free_layout_enabled():
                self._long_press_ev = Clock.schedule_once(
                    lambda _dt: self._start_drag_mode(touch), 1.0
                )
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def stop_drag_animation(self):
        if self._long_press_ev:
            Clock.unschedule(self._long_press_ev)
            self._long_press_ev = None
        if self._shake_anim:
            self._shake_anim.stop(self)
            self._shake_anim = None
        Animation(angle=0, d=0.1).start(self)

    def _start_drag_mode(self, touch):
        if not self._free_layout_enabled():
            return
        self.pos_hint = {}  # Allow free movement within the FloatLayout
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
        # ``project_uid`` is the lookup key for all per-project state. Set it
        # BEFORE the title so the title-change handler sees the new uid.
        info.project_uid = self.uid or ""
        info.project_title = self.title
        app.root.current = "project_info"

    def save_position(self):
        if not self._free_layout_enabled():
            return
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

            # Card positions are keyed by uid so duplicate-titled projects no
            # longer overwrite each other. Legacy title keys migrate during
            # active_timer.migrate_legacy_state_to_uids on startup.
            key = self.uid or self.title
            data[key] = {'x': rel_x, 'top': rel_y}

            with open(storage_path, 'w') as f:
                json.dump(data, f)

            print(f"Position saved for {self.title} ({key}): x={rel_x:.2f}, top={rel_y:.2f}")

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
        icon = resolve_emoji_source(session.get("emoji_source") or "folder-outline")
        self.emoji_source = icon if icon else "folder-outline"
        self.when_label = format_when_label(session.get("ended_at"))
        self.duration_text = f"Czas:  {format_duration_hms(session.get('duration_seconds', 0))}"
        label = self.ids.get("session_project_title")
        if label is not None:
            Clock.schedule_once(lambda _dt, lbl=label: self._sync_session_title_row(lbl), 0)


class HomeScreen(MDScreen):
    _last_grid_container_width = 0

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        container = self.ids.projects_container
        container.bind(size=self._on_projects_container_resize)
        app = MDApp.get_running_app()
        if app is not None:
            app.bind(grid_layout=lambda *_a: self._on_layout_mode_changed())

    def _on_layout_mode_changed(self):
        if MDApp.get_running_app().grid_layout:
            self.apply_grid_layout()
        else:
            self.restore_card_positions()

    def _on_projects_container_resize(self, container, size):
        w = size[0]
        if w < 1:
            return
        app = MDApp.get_running_app()
        if app.grid_layout:
            if abs(w - self._last_grid_container_width) < 1:
                return
            self._last_grid_container_width = w
            Clock.schedule_once(lambda _dt: self.apply_grid_layout(), 0)
        elif not getattr(self, "_free_layout_ready", False):
            self._free_layout_ready = True
            Clock.schedule_once(lambda _dt: self.restore_card_positions(), 0)

    def _project_cards(self):
        container = self.ids.projects_container
        cards = [c for c in container.children if isinstance(c, ProjectCard)]
        cards.sort(key=lambda c: c.title.lower())
        return cards

    def _grid_layout_metrics(self, container, cards):
        """Spacing for 2-column grid; top_pad clears the emoji badge above each card."""
        margin_x = dp(16)
        gutter = dp(12)
        row_gap = dp(16)
        base_top = dp(6)

        card_w = container.width * CARD_SIZE_HINT_X
        if not cards:
            return card_w, 0, base_top, margin_x, gutter, row_gap

        mult = max(c.height_multiplier for c in cards)
        card_h = card_w * mult
        emoji_sz = max(c.emoji_size for c in cards)
        badge_h = emoji_sz * GRID_EMOJI_BADGE_SCALE
        badge_above = (card_h * GRID_EMOJI_TOP_EXTRA + badge_h * 0.35) * 0.5
        top_pad = base_top + badge_above
        return card_w, card_h, top_pad, margin_x, gutter, row_gap

    def schedule_initial_layout(self):
        Clock.schedule_once(lambda _dt: self.apply_initial_layout(), 0)

    def apply_initial_layout(self):
        """Run grid or free layout once the projects container has a real width."""
        container = self.ids.projects_container
        if container.width < 1:
            Clock.schedule_once(lambda _dt: self.apply_initial_layout(), 0)
            return
        app = MDApp.get_running_app()
        if app.grid_layout:
            self.apply_grid_layout()
        else:
            self.restore_card_positions()

    def apply_grid_layout(self):
        """Place project cards in a fixed 2-column grid."""
        container = self.ids.projects_container
        if container.width < 1:
            Clock.schedule_once(lambda _dt: self.apply_grid_layout(), 0)
            return

        cards = self._project_cards()
        if not cards:
            container.height = dp(200)
            return

        card_w, _card_h, top_pad, margin_x, gutter, row_gap = self._grid_layout_metrics(
            container, cards
        )
        col_width = (container.width - 2 * margin_x - gutter) / GRID_COLUMNS
        col_x = [
            margin_x + (col_width - card_w) * 0.5,
            margin_x + col_width + gutter + (col_width - card_w) * 0.5,
        ]

        rows = (len(cards) + GRID_COLUMNS - 1) // GRID_COLUMNS
        row_heights = []
        for row in range(rows):
            chunk = cards[row * GRID_COLUMNS : (row + 1) * GRID_COLUMNS]
            row_heights.append(card_w * max(c.height_multiplier for c in chunk))

        content_h = top_pad + sum(row_heights) + max(0, rows - 1) * row_gap
        container.height = max(dp(200), content_h + dp(150))

        y_cursor = container.height - top_pad
        for i, card in enumerate(cards):
            card.stop_drag_animation()
            col = i % GRID_COLUMNS
            row = i // GRID_COLUMNS
            if col == 0 and row > 0:
                y_cursor -= row_heights[row - 1] + row_gap
            card.pos_hint = {}
            card.x = col_x[col]
            card.top = y_cursor

    def refresh_last_session(self):
        card = self.ids.last_session_card
        if card is not None:
            card.apply_last_session(get_last_session())

    def on_enter(self, *_args):
        # Delayed refresh covers home entering before project_info.on_leave records.
        schedule_home_last_session_refresh()
        self.schedule_initial_layout()
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
                        p['title'], p['image'], resolve_emoji_source(p['icon']), p['color'],
                        0.1, 0.9,
                        uid=p.get('uid', ''),
                    )
            except (IOError, json.JSONDecodeError) as e:
                print(f"Error loading projects: {e}")

    def restore_card_positions(self):
        app = MDApp.get_running_app()
        if app.grid_layout:
            return
        container = self.ids.projects_container
        if container.width < 1:
            Clock.schedule_once(lambda _dt: self.restore_card_positions(), 0)
            return

        storage_path = os.path.join(app.user_data_dir, "card_positions.json")
        data = {}
        if os.path.exists(storage_path):
            try:
                with open(storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Error restoring positions: {e}")

        for card in self._project_cards():
            card.stop_drag_animation()
            # Prefer the uid key (new format); fall back to title for unmigrated
            # installs the first time the new code runs.
            pos = None
            if card.uid and card.uid in data:
                pos = data[card.uid]
            elif card.title in data:
                pos = data[card.title]
            if pos is not None:
                card.pos_hint = {
                    "x": float(pos.get("x", 0.1)),
                    "top": float(pos.get("top", 0.9)),
                }
            else:
                card.pos_hint = {"x": 0.1, "top": 0.9}

        self.update_container_height()

    def add_project_card(self, title, image, emoji, color, x_pos, y_top, uid=""):
        container = self.ids.projects_container
        new_card = ProjectCard(
            uid=uid or "",
            title=title, image_source=image, emoji_source=resolve_emoji_source(emoji),
            card_color=color,
            pos_hint={'x': x_pos, 'top': y_top}
        )
        container.add_widget(new_card)
        app = MDApp.get_running_app()
        if app.grid_layout:
            self.apply_grid_layout()
        else:
            self.update_container_height()

    def update_container_height(self):
        container = self.ids.projects_container
        cards = self._project_cards()
        app = MDApp.get_running_app()

        if app.grid_layout and cards and container.width > 0:
            card_w, card_h, top_pad, _mx, _gut, row_gap = self._grid_layout_metrics(
                container, cards
            )
            rows = (len(cards) + GRID_COLUMNS - 1) // GRID_COLUMNS
            grid_h = top_pad + rows * card_h + max(0, rows - 1) * row_gap + dp(150)
            container.height = max(self.height, grid_h)
            return

        min_h = self.height
        for child in container.children:
            if child.top > min_h:
                min_h = child.top
        container.height = min_h + dp(150)