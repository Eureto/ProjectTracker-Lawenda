import datetime
import json
import os
import re
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex
from kivy.uix.scrollview import ScrollView
from kivymd.app import MDApp
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from screens.keyboard_inset import keyboard_inset
from screens.session_store import record_session, schedule_home_last_session_refresh

# Project root = parent of `screens/` (works on device and desktop).
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _car_asset_path(filename):
    return os.path.join(_PKG_ROOT, "assets", "Progress_Car", filename)


RESET_NEVER = "never"
RESET_DAILY = "daily"
RESET_WEEKLY = "weekly"

_SHEET_FIELD_RADIUS = dp(12)
_SHEET_BTN_RADIUS = dp(12)

_PURPLE = get_color_from_hex("#7e57c2")
_GREY_NODE = get_color_from_hex("#9e9e9e")
_CHIP_INACTIVE = get_color_from_hex("#5e35b1")
_CHIP_ACTIVE = get_color_from_hex("#b388ff")
_CROWN_GOLD = get_color_from_hex("#ffc107")

ETAPY_ADD_GROUP = "Grupa etapów"
ETAPY_ADD_STEP = "Krok etapu"
ETAPY_ADD_SUB = "Podkrok"


class _RoundedSheetBackground:
    """Draw a rounded fill behind sheet inputs (TextInput / Spinner)."""

    fill_color = ListProperty([0.97, 0.97, 0.97, 1])
    corner_radius = NumericProperty(_SHEET_FIELD_RADIUS)

    def _init_rounded_bg(self):
        self.bind(pos=self._redraw_rounded_bg, size=self._redraw_rounded_bg)
        self.bind(fill_color=lambda *_: self._redraw_rounded_bg())
        self.bind(corner_radius=lambda *_: self._redraw_rounded_bg())
        Clock.schedule_once(lambda _dt: self._redraw_rounded_bg(), 0)

    def _redraw_rounded_bg(self, *_args):
        r = float(self.corner_radius)
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.fill_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[r, r, r, r])


class RoundedSheetTextInput(_RoundedSheetBackground, TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_active", "")
        super().__init__(**kwargs)
        self._init_rounded_bg()


class RoundedSheetSpinner(_RoundedSheetBackground, Spinner):
    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        super().__init__(**kwargs)
        self._init_rounded_bg()


class RoundedSheetButton(Button):
    """Rounded action button for bottom sheets (replaces flat MD buttons in sheets)."""

    bg_color = ListProperty([0.7, 0.5, 1, 1])
    text_rgb = ListProperty([1, 1, 1, 1])
    corner_radius = NumericProperty(_SHEET_BTN_RADIUS)

    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("bold", True)
        super().__init__(**kwargs)
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            state=self._redraw,
            bg_color=lambda *_: self._redraw(),
            text_rgb=lambda *_: self._redraw(),
        )
        Clock.schedule_once(lambda _dt: self._redraw(), 0)

    def _redraw(self, *_args):
        bg = list(self.bg_color)
        if self.state == "down":
            bg = [c * 0.9 for c in bg[:3]] + [bg[3]]
        r = float(self.corner_radius)
        self.color = self.text_rgb
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[r, r, r, r])


def current_period_key(reset_mode):
    """Calendar day / ISO week key used to reset progress when the period rolls over."""
    if reset_mode == RESET_NEVER:
        return "all"
    if reset_mode == RESET_DAILY:
        return datetime.date.today().isoformat()
    if reset_mode == RESET_WEEKLY:
        d = datetime.date.today()
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return "all"


def format_quota_short(seconds):
    s = int(max(1, round(float(seconds))))
    if s >= 3600 and s % 3600 == 0:
        return f"{s // 3600}h"
    if s >= 60 and s % 60 == 0:
        return f"{s // 60}min"
    return f"{s}s"


def format_goal_summary(quota_seconds, reset_mode):
    amt = format_quota_short(quota_seconds)
    if reset_mode == RESET_DAILY:
        return f"{amt} / dzień"
    if reset_mode == RESET_WEEKLY:
        return f"{amt} / tydzień"
    return amt


def parse_reset_mode(value):
    if not value:
        return RESET_WEEKLY
    v = str(value).lower()
    if v in (RESET_NEVER, "none"):
        return RESET_NEVER
    if v in (RESET_DAILY, "daily", "day", "dzien", "dziennie"):
        return RESET_DAILY
    if v in (RESET_WEEKLY, "weekly", "week", "tydzien", "tygodniowo"):
        return RESET_WEEKLY
    return RESET_WEEKLY


def parse_goal_target_seconds(goal_str):
    """Best-effort parse from strings like '1h/1d', '30min', '2h'. Defaults to 1 hour."""
    s = (goal_str or "").lower().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*h", s)
    if m:
        return max(60.0, float(m.group(1)) * 3600.0)
    m = re.search(r"(\d+(?:\.\d+)?)\s*min", s)
    if m:
        return max(60.0, float(m.group(1)) * 60.0)
    m = re.search(r"(\d+)\s*s(?:ec)?", s)
    if m:
        return max(10.0, float(m.group(1)))
    return 3600.0


def format_goal_elapsed(seconds):
    s = int(max(0, round(float(seconds))))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    h, r = divmod(s, 3600)
    m = r // 60
    # Single horizontal token (no line breaks)
    return f"{h}h{m}m" if m else f"{h}h"


class UnderlineTextBlock(BoxLayout):
    """White label with a horizontal rule underneath (mockup list / stage lines)."""

    text = StringProperty("")
    text_color = ListProperty([1, 1, 1, 1])
    font_size = NumericProperty(sp(14))

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", dp(2))
        super().__init__(**kwargs)
        self._lbl = Label(
            color=self.text_color,
            font_size=self.font_size,
            halign="left",
            valign="middle",
            size_hint_y=None,
        )
        self._rule = Widget(size_hint_y=None, height=dp(2))
        self.add_widget(self._lbl)
        self.add_widget(self._rule)
        self._rule.bind(pos=self._draw_rule, size=self._draw_rule)
        self.bind(text=self._relayout, width=self._relayout, text_color=self._relayout)
        Clock.schedule_once(lambda _dt: self._relayout(), 0)

    def _draw_rule(self, *_args):
        self._rule.canvas.clear()
        with self._rule.canvas:
            Color(1, 1, 1, 1)
            Line(
                points=[self._rule.x, self._rule.center_y, self._rule.right, self._rule.center_y],
                width=dp(1.2),
            )

    def _relayout(self, *_args):
        self._lbl.text = self.text or ""
        self._lbl.color = tuple(self.text_color)
        self._lbl.font_size = float(self.font_size)
        if self.width > 1:
            self._lbl.text_size = (self.width, None)
            self._lbl.texture_update()
            th = max(sp(16), self._lbl.texture_size[1])
            self._lbl.height = th
            self.height = th + dp(6)
        self._draw_rule()


class StatusCircleButton(Button):
    """Circle toggle on the right — white ring for checklist, purple/crown for etapy."""

    done = BooleanProperty(False)
    show_crown = BooleanProperty(True)
    white_style = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(26), dp(26)))
        super().__init__(**kwargs)
        self.bind(
            done=self._redraw,
            show_crown=self._redraw,
            white_style=self._redraw,
            pos=self._redraw,
            size=self._redraw,
        )
        Clock.schedule_once(lambda _dt: self._redraw(), 0)

    def _redraw(self, *_args):
        self.canvas.before.clear()
        if self.width < 1 or self.height < 1:
            return
        cx = self.center_x
        cy = self.center_y
        r = min(self.width, self.height) * 0.36
        ring_w = dp(2.5)
        with self.canvas.before:
            if self.white_style:
                if self.done:
                    Color(1, 1, 1, 1)
                    Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
                else:
                    Color(1, 1, 1, 1)
                    Line(circle=(cx, cy, r), width=ring_w)
            elif self.done and self.show_crown:
                Color(*_PURPLE)
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            elif self.done:
                Color(*_PURPLE)
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            else:
                Color(*_PURPLE)
                Line(circle=(cx, cy, r), width=dp(2))
        if self.done and self.show_crown:
            self.text = "\u2655"
            self.font_size = sp(12)
            self.color = _CROWN_GOLD
        else:
            self.text = ""


class ChecklistGoalRow(MDBoxLayout):
    index_label = StringProperty("1.")
    display_text = StringProperty("")
    done = BooleanProperty(False)
    parent_screen = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(10))
        super().__init__(**kwargs)
        self.size_hint_y = None
        self._underline = None
        self._status_btn = None
        self.bind(display_text=self._sync_height, width=self._sync_height)

    def on_kv_post(self, base_widget):
        self._underline = self.ids.underline_block
        self._status_btn = self.ids.status_btn
        self._status_btn.show_crown = False
        self._status_btn.bind(on_release=self._toggle_done)
        self.ids.index_lbl.text = self.index_label
        self._underline.text = self.display_text
        self._apply_done_to_ui()
        Clock.schedule_once(self._sync_height, 0)

    def _apply_done_to_ui(self):
        btn = self._status_btn or self.ids.get("status_btn")
        if btn is not None:
            btn.done = self.done

    def _toggle_done(self, *_args):
        self.done = not self.done
        self._apply_done_to_ui()
        if self.parent_screen:
            self.parent_screen.relocate_checklist_goal(self)

    def _sync_height(self, *_args):
        if self._underline is None:
            return
        self._underline.text = self.display_text
        if "index_lbl" in self.ids:
            self.ids.index_lbl.text = self.index_label
        btn_w = dp(30)
        idx_w = dp(22) if self.index_label else 0
        if self.width > 1:
            self._underline.width = max(sp(40), self.width - idx_w - btn_w - dp(16))
        row_h = max(dp(32), self._underline.height)
        self.height = row_h
        if "index_lbl" in self.ids:
            self.ids.index_lbl.height = row_h
        if self._status_btn is not None:
            self._status_btn.size = (btn_w, btn_w)
        self._apply_done_to_ui()

    def on_touch_up(self, touch):
        if super().on_touch_up(touch):
            return True
        if not self.collide_point(*touch.pos):
            return False
        if "status_btn" in self.ids and self.ids.status_btn.collide_point(*touch.pos):
            return False
        self.open_edit()
        return True

    def open_edit(self):
        if self.parent_screen:
            self.parent_screen.open_edit_checklist_goal_sheet(self)


class ZrobioneHeaderBar(MDBoxLayout):
    """Tappable row: title + chevron (children must not steal touches)."""

    section = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(40))
        kwargs.setdefault("padding", [dp(2), 0, dp(4), 0])
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if self.collide_point(*touch.pos):
                sec = self.section
                if sec is not None:
                    sec._toggle_expanded()
            return True
        return super().on_touch_up(touch)


class ZrobioneSection(MDBoxLayout):
    """Collapsible 'Zrobione' bucket for completed checklist goals."""

    expanded = BooleanProperty(True)
    done_count = NumericProperty(0)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("spacing", dp(8))
        kwargs.setdefault("size_hint_y", None)
        super().__init__(**kwargs)
        self.bind(expanded=self._apply_expanded, done_count=self._apply_visibility)
        self._setup_attempts = 0

    def on_kv_post(self, base_widget):
        Clock.schedule_once(self._setup_after_kv, 0)

    def _setup_after_kv(self, _dt):
        if "zrobione_header" not in self.ids:
            self._setup_attempts += 1
            if self._setup_attempts < 20:
                Clock.schedule_once(self._setup_after_kv, 0.05)
            return
        header = self.ids.zrobione_header
        header.section = self
        self.bind(done_count=self._refresh_header, expanded=self._refresh_header)
        self.ids.checklist_done_list.bind(
            minimum_height=lambda *_: Clock.schedule_once(self._sync_section_height, 0)
        )
        self._refresh_all()

    def _toggle_expanded(self, *_args):
        self.expanded = not self.expanded
        self._apply_expanded()
        self._sync_section_height()

    def _refresh_header(self, *_args):
        if "zrobione_header" not in self.ids:
            return
        header = self.ids.zrobione_header
        n = int(self.done_count)
        title = f"Zrobione ({n})" if n else "Zrobione"
        if "zrobione_title" in header.ids:
            header.ids.zrobione_title.text = title
        if "zrobione_chevron" in header.ids:
            header.ids.zrobione_chevron.icon = (
                "chevron-down" if self.expanded else "chevron-right"
            )

    def _apply_visibility(self, *_args):
        visible = self.done_count > 0
        self.opacity = 1 if visible else 0
        self.disabled = False
        self.size_hint_y = None
        if not visible:
            self.height = 0
            self.collide_disabled = True
        else:
            self.collide_disabled = False
            Clock.schedule_once(self._apply_expanded, 0)
            Clock.schedule_once(self._sync_section_height, 0)

    def _apply_expanded(self, *_args):
        if self.done_count <= 0 or "checklist_done_list" not in self.ids:
            return
        lst = self.ids.checklist_done_list
        self._refresh_header()
        if self.expanded:
            lst.opacity = 1
            lst.disabled = False
            lst.height = lst.minimum_height
        else:
            lst.opacity = 0
            lst.disabled = True
            lst.height = 0
        Clock.schedule_once(self._sync_section_height, 0)

    def _sync_section_height(self, *_args):
        if self.done_count <= 0:
            self.height = 0
            return
        if "zrobione_header" not in self.ids or "checklist_done_list" not in self.ids:
            return
        header_h = self.ids.zrobione_header.height
        body_h = self.ids.checklist_done_list.height if self.expanded else 0
        self.height = header_h + body_h + float(self.spacing)

    def _refresh_all(self, *_args):
        self._apply_visibility()
        self._apply_expanded()


class StageItemRow(MDBoxLayout):
    """Timeline row: spine + underline text + status (crown when done)."""

    display_text = StringProperty("")
    done = BooleanProperty(False)
    is_sub = BooleanProperty(False)
    is_first = BooleanProperty(False)
    is_last = BooleanProperty(False)
    parent_screen = ObjectProperty(None, allownone=True)
    group_index = NumericProperty(0)
    item_index = NumericProperty(0)
    child_index = NumericProperty(-1)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)
        self.size_hint_y = None
        self._spine = None
        self.bind(display_text=self._sync_height, width=self._sync_height)

    def on_kv_post(self, base_widget):
        self._spine = self.ids.spine
        self._underline = self.ids.underline_block
        self._status_btn = self.ids.status_btn
        self._status_btn.bind(on_release=self._toggle_done)
        self.ids.sub_arrow.opacity = 1 if self.is_sub else 0
        self.ids.sub_arrow.width = dp(16) if self.is_sub else 0
        self._spine.is_sub = self.is_sub
        self._spine.is_first = self.is_first
        self._spine.is_last = self.is_last
        if self.is_sub:
            self.padding = [dp(18), 0, 0, 0]
        self._apply_done_to_ui()
        Clock.schedule_once(self._sync_height, 0)

    def _apply_done_to_ui(self):
        if self._spine is not None:
            self._spine.done = self.done
        btn = self._status_btn or self.ids.get("status_btn")
        if btn is not None:
            btn.done = self.done

    def _toggle_done(self, *_args):
        self.done = not self.done
        self._apply_done_to_ui()
        if self.parent_screen:
            self.parent_screen._set_etapy_item_done(
                self.group_index, self.item_index, self.child_index, self.done
            )

    def _sync_height(self, *_args):
        self._underline.text = self.display_text
        if self.width > 1:
            pad = dp(50) if self.is_sub else dp(34)
            self._underline.width = max(sp(40), self.width - pad)
        line_h = sp(14) * 1.45
        if self.width > 1 and self._underline.width > 1:
            from kivy.core.text import Label as CoreLabel

            lbl = CoreLabel(text=self.display_text or " ", font_size=sp(14))
            lbl.bind(size=lbl.setter("text_size"))
            lbl.text_size = (self._underline.width, None)
            lbl.refresh()
            line_h = max(line_h, lbl.texture.size[1])
        self._underline.height = line_h + dp(10)
        self.height = max(dp(40), self._underline.height + dp(4))
        self._apply_done_to_ui()


class TimelineSpine(Widget):
    is_sub = BooleanProperty(False)
    is_first = BooleanProperty(False)
    is_last = BooleanProperty(False)
    done = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", dp(22))
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, is_sub=self._redraw)
        self.bind(is_first=self._redraw, is_last=self._redraw, done=self._redraw)

    def _redraw(self, *_args):
        self.canvas.clear()
        if self.height < 1:
            return
        cx = self.center_x
        node_r = dp(5) if self.is_sub else dp(6)
        node_cy = self.center_y
        with self.canvas:
            if not self.is_sub:
                Color(*_GREY_NODE)
                Line(points=[cx, self.top, cx, self.y], width=dp(1.5))
            Color(*(_PURPLE if self.done else _GREY_NODE))
            Ellipse(
                pos=(cx - node_r, node_cy - node_r),
                size=(2 * node_r, 2 * node_r),
            )


class EtapyFinishRow(MDBoxLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(44))
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)


class ProjectInfoScreen(MDScreen):
    """Project detail panel: dynamic notes & goals, timer, bottom nav like home."""

    project_title = StringProperty("")
    timer_display = StringProperty("00:00:00")
    timer_running = BooleanProperty(False)
    timer_button_caption = StringProperty("start")

    _timer_ev = None
    _timer_elapsed_seconds = 0
    _run_base_elapsed = 0
    _run_started_at = None
    _etapy_groups = []
    _etapy_selected_index = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._checklist_sheet = None
        self._etapy_sheet = None
        self._add_note_sheet = None
        self._goal_sheet = None
        self.bind(project_title=self._on_project_title_changed)

    def _on_project_title_changed(self, *_args):
        mgr = self.manager
        if mgr is not None and mgr.current == self.name:
            self.load_project_content()

    def on_enter(self):
        Window.bind(on_keyboard=self._on_keyboard)
        self.load_project_content()

    def on_leave(self):
        Window.unbind(on_keyboard=self._on_keyboard)
        if self.timer_running:
            self._finish_timer_run()
            self.timer_running = False
            self.timer_button_caption = "start"
        self._stop_timer_event()
        self._stop_all_goal_trackers()
        self.save_project_content()

    def _stop_all_goal_trackers(self):
        for row in list(self.ids.goals_list.children):
            if isinstance(row, TimeGoalTrackRow):
                row.stop_tracking()

    def _on_keyboard(self, window, key, scancode, codepoint, modifier):
        if key == 27:
            self._finalize_and_go_home()
            return True
        return False

    # --- Storage ---

    def _state_path(self):
        return os.path.join(MDApp.get_running_app().user_data_dir, "project_details.json")

    def _read_all_states(self):
        path = self._state_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_all_states(self, data):
        path = self._state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_project_content(self):
        key = self.project_title or "_"
        data = self._read_all_states()
        data[key] = {
            "timer_elapsed": self._timer_elapsed_seconds,
            "notes": self._serialize_notes(),
            "goals": self._serialize_goals(),
            "checklist_goals": self._serialize_checklist_goals(),
            "etapy": self._serialize_etapy(),
        }
        self._write_all_states(data)

    def load_project_content(self):
        if self.timer_running:
            self._finish_timer_run()
            self.timer_running = False
            self.timer_button_caption = "start"
            self._stop_timer_event()
        self._run_started_at = None
        self._clear_dynamic_widgets()
        key = self.project_title or "_"
        blob = self._read_all_states().get(key)
        if blob:
            self._timer_elapsed_seconds = int(blob.get("timer_elapsed", 0))
            self._refresh_timer_label()
            for n in blob.get("notes") or []:
                t = (n.get("text") or "").strip()
                if not t:
                    continue
                self.add_note(text=n.get("text", ""), tall=bool(n.get("tall", False)))
            for g in blob.get("goals") or []:
                goal = g.get("goal", "1h/tydzień")
                tgt = g.get("goal_target_seconds")
                if tgt is None:
                    tgt = parse_goal_target_seconds(goal)
                logged = float(g.get("logged_seconds", 0))
                if logged <= 0 and "percent" in g:
                    try:
                        p = float(g.get("percent", 0))
                        logged = max(0.0, (p / 100.0) * float(tgt))
                    except (TypeError, ValueError):
                        logged = 0.0
                rm = parse_reset_mode(g.get("reset_mode", ""))
                saved_pk = g.get("period_key")
                cur = current_period_key(rm)
                if rm != RESET_NEVER and saved_pk is not None and saved_pk != cur:
                    logged = 0.0
                    pk = cur
                elif saved_pk is None:
                    pk = cur
                else:
                    pk = saved_pk
                self.add_time_goal(
                    title=g.get("title", ""),
                    goal=goal,
                    goal_target_seconds=float(tgt),
                    logged_seconds=logged,
                    reset_mode=rm,
                    period_key=pk,
                )
            for cg in blob.get("checklist_goals") or []:
                t = (cg.get("text") or "").strip()
                if t:
                    self.add_checklist_goal(text=t, done=bool(cg.get("done", False)))
            et = blob.get("etapy") or {}
            self._etapy_groups = et.get("groups") or []
            self._etapy_selected_index = int(et.get("selected_index", 0))
        else:
            self._timer_elapsed_seconds = 0
            self._refresh_timer_label()
            self._etapy_groups = []
            self._etapy_selected_index = 0
        self._run_base_elapsed = self._timer_elapsed_seconds
        self._clamp_etapy_selection()
        self._rebuild_etapy_chips()
        self._rebuild_etapy_timeline()

    def _clear_dynamic_widgets(self):
        for c in list(self.ids.notes_list.children):
            self.ids.notes_list.remove_widget(c)
        for c in list(self.ids.goals_list.children):
            self.ids.goals_list.remove_widget(c)
        cl = self.ids.get("checklist_goals_list")
        if cl is not None:
            for c in list(cl.children):
                cl.remove_widget(c)
        dl = self._checklist_done_list()
        if dl is not None:
            for c in list(dl.children):
                dl.remove_widget(c)
        zr = self.ids.get("zrobione_section")
        if zr is not None:
            zr.done_count = 0
        self._etapy_groups = []
        self._etapy_selected_index = 0

    def _serialize_notes(self):
        out = []
        for row in self.ids.notes_list.children:
            if isinstance(row, ProjectNoteRow):
                out.append(
                    {
                        "text": row.display_text or "",
                        "tall": bool(row.tall),
                    }
                )
        return out

    def _serialize_goals(self):
        out = []
        for row in self.ids.goals_list.children:
            if isinstance(row, TimeGoalTrackRow):
                out.append(
                    {
                        "title": row.title_text,
                        "goal": row.goal_text,
                        "goal_target_seconds": row.goal_target_seconds,
                        "logged_seconds": row.logged_seconds,
                        "reset_mode": row.reset_mode,
                        "period_key": row.period_key,
                    }
                )
        return out

    def _iter_checklist_rows(self):
        lists = [self.ids.get("checklist_goals_list"), self._checklist_done_list()]
        for cl in lists:
            if cl is None:
                continue
            for c in reversed(cl.children):
                if isinstance(c, ChecklistGoalRow):
                    yield c

    def _serialize_checklist_goals(self):
        out = []
        for row in self._iter_checklist_rows():
            t = (row.display_text or "").strip()
            if t:
                out.append({"text": t, "done": bool(row.done)})
        return out

    def _serialize_etapy(self):
        return {
            "selected_index": int(self._etapy_selected_index),
            "groups": self._etapy_groups,
        }

    # --- Lista celów (checklist) ---

    def _checklist_done_list(self):
        zr = self.ids.get("zrobione_section")
        if zr is None:
            return None
        return zr.ids.get("checklist_done_list")

    def _clear_stale_checklist_sheet(self):
        sheet = getattr(self, "_checklist_sheet", None)
        if sheet is None:
            return
        if getattr(sheet, "parent", None) is None:
            self._checklist_sheet = None

    def open_add_checklist_goal_sheet(self, *_args):
        self._clear_stale_checklist_sheet()
        if self._checklist_sheet is not None:
            return
        sheet = AddChecklistGoalBottomSheet(self, goal_row=None)

        def _cleared(*_a):
            self._checklist_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._checklist_sheet = sheet
        try:
            sheet.open()
        except Exception:
            self._checklist_sheet = None
            raise

    def open_edit_checklist_goal_sheet(self, row):
        self._clear_stale_checklist_sheet()
        if self._checklist_sheet is not None:
            return
        sheet = AddChecklistGoalBottomSheet(self, goal_row=row)

        def _cleared(*_a):
            self._checklist_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._checklist_sheet = sheet
        try:
            sheet.open()
        except Exception:
            self._checklist_sheet = None
            raise

    def add_checklist_goal(self, text="", done=False):
        row = ChecklistGoalRow(
            display_text=text,
            done=done,
            parent_screen=self,
        )
        target = self._checklist_done_list() if done else self.ids.checklist_goals_list
        if target is None:
            return
        target.add_widget(row)
        self._renumber_checklist_goals()
        self._refresh_zrobione_section()
        self.save_project_content()

    def remove_checklist_goal_row(self, row):
        parent = row.parent
        if parent is not None:
            parent.remove_widget(row)
        self._renumber_checklist_goals()
        self._refresh_zrobione_section()
        self.save_project_content()

    def relocate_checklist_goal(self, row):
        active = self.ids.checklist_goals_list
        done_box = self._checklist_done_list()
        if done_box is None:
            return
        if row.parent is not None:
            row.parent.remove_widget(row)
        if row.done:
            done_box.add_widget(row)
            row.index_label = ""
            row.opacity = 0.72
        else:
            active.add_widget(row)
            row.opacity = 1.0
        self._renumber_checklist_goals()
        self._refresh_zrobione_section()
        zr = self.ids.get("zrobione_section")
        if zr is not None and row.done:
            zr.expanded = True
        self.save_project_content()

    def _refresh_zrobione_section(self):
        done_box = self._checklist_done_list()
        zr = self.ids.get("zrobione_section")
        if done_box is None or zr is None:
            return
        n = sum(1 for c in done_box.children if isinstance(c, ChecklistGoalRow))
        zr.done_count = n
        for row in done_box.children:
            if isinstance(row, ChecklistGoalRow):
                row.index_label = ""
                row.opacity = 0.72

    def _renumber_checklist_goals(self):
        cl = self.ids.get("checklist_goals_list")
        if cl is None:
            return
        rows = [c for c in reversed(cl.children) if isinstance(c, ChecklistGoalRow)]
        for i, row in enumerate(rows, start=1):
            row.index_label = f"{i}."
            row.opacity = 1.0
            row._sync_height()

    # --- Etapy ---

    _etapy_sheet = None

    def open_add_etapy_sheet(self):
        if self._etapy_sheet is not None:
            return
        sheet = AddEtapyBottomSheet(self)

        def _cleared(*_a):
            self._etapy_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._etapy_sheet = sheet
        sheet.open()

    def _clamp_etapy_selection(self):
        if not self._etapy_groups:
            self._etapy_selected_index = 0
            return
        self._etapy_selected_index = max(
            0, min(self._etapy_selected_index, len(self._etapy_groups) - 1)
        )

    def _selected_etapy_group(self):
        self._clamp_etapy_selection()
        if not self._etapy_groups:
            return None
        return self._etapy_groups[self._etapy_selected_index]

    def select_etapy_group(self, index):
        self._etapy_selected_index = int(index)
        self._clamp_etapy_selection()
        self._rebuild_etapy_chips()
        self._rebuild_etapy_timeline()
        self.save_project_content()

    def _set_etapy_item_done(self, group_index, item_index, child_index, done):
        try:
            group = self._etapy_groups[group_index]
            if child_index >= 0:
                group["items"][item_index]["children"][child_index]["done"] = done
            else:
                group["items"][item_index]["done"] = done
        except (IndexError, KeyError, TypeError):
            return
        self.save_project_content()

    def add_etapy_group(self, name):
        name = (name or "").strip() or "Etap"
        self._etapy_groups.append({"name": name, "items": []})
        self._etapy_selected_index = len(self._etapy_groups) - 1
        self._rebuild_etapy_chips()
        self._rebuild_etapy_timeline()
        self.save_project_content()

    def add_etapy_step(self, text, parent_item_index=None):
        text = (text or "").strip()
        if not text:
            return
        group = self._selected_etapy_group()
        if group is None:
            self.add_etapy_group("Ogólne")
            group = self._selected_etapy_group()
        if parent_item_index is None:
            group["items"].append({"text": text, "done": False, "children": []})
        else:
            try:
                children = group["items"][parent_item_index].setdefault("children", [])
                children.append({"text": text, "done": False})
            except (IndexError, KeyError):
                group["items"].append({"text": text, "done": False, "children": []})
        self._rebuild_etapy_timeline()
        self.save_project_content()

    def _rebuild_etapy_chips(self):
        box = self.ids.get("etapy_chips_box")
        if box is None:
            return
        box.clear_widgets()
        if not self._etapy_groups:
            hint = MDLabel(
                text="Dodaj grupę etapów przyciskiem +",
                font_size=sp(13),
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.65),
                size_hint=(None, None),
                height=dp(32),
            )
            hint.texture_update()
            hint.width = hint.texture_size[0] + dp(16)
            box.add_widget(hint)
            return
        for idx, group in enumerate(self._etapy_groups):
            active = idx == self._etapy_selected_index
            chip = Button(
                text=group.get("name", "Etap"),
                size_hint=(None, None),
                height=dp(32),
                padding=(dp(14), dp(6)),
                background_normal="",
                background_color=(0, 0, 0, 0),
                color=(0.12, 0.12, 0.12, 1) if active else (1, 1, 1, 1),
                font_size=sp(13),
            )
            chip.texture_update()
            chip.width = chip.texture_size[0] + dp(28)

            def _paint_chip(btn, is_active, *_a):
                btn.canvas.before.clear()
                bg = _CHIP_ACTIVE if is_active else _CHIP_INACTIVE
                with btn.canvas.before:
                    Color(*bg)
                    RoundedRectangle(
                        pos=btn.pos,
                        size=btn.size,
                        radius=[dp(16), dp(16), dp(16), dp(16)],
                    )

            _paint_chip(chip, active)
            chip.bind(pos=lambda b, *a, ia=active: _paint_chip(b, ia))
            chip.bind(size=lambda b, *a, ia=active: _paint_chip(b, ia))
            gi = idx
            chip.bind(on_release=lambda *a, i=gi: self.select_etapy_group(i))
            box.add_widget(chip)

    def _rebuild_etapy_timeline(self):
        timeline = self.ids.get("etapy_timeline_list")
        if timeline is None:
            return
        timeline.clear_widgets()
        group = self._selected_etapy_group()
        if group is None:
            timeline.add_widget(
                MDLabel(
                    text="Dodaj grupę etapów przyciskiem +",
                    font_size=sp(13),
                    theme_text_color="Custom",
                    text_color=(1, 1, 1, 0.65),
                    size_hint_y=None,
                    height=dp(36),
                )
            )
            return
        items = group.get("items") or []
        flat_count = sum(1 + len(it.get("children") or []) for it in items)
        if flat_count == 0:
            empty = MDLabel(
                text="Brak kroków — dodaj krok etapu przyciskiem +",
                font_size=sp(13),
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.65),
                size_hint_y=None,
                height=dp(36),
            )
            timeline.add_widget(empty)
        else:
            gi = self._etapy_selected_index
            seq = 0
            for ii, item in enumerate(items):
                seq += 1
                timeline.add_widget(
                    StageItemRow(
                        display_text=item.get("text", ""),
                        done=bool(item.get("done", False)),
                        is_sub=False,
                        is_first=(seq == 1),
                        is_last=False,
                        parent_screen=self,
                        group_index=gi,
                        item_index=ii,
                        child_index=-1,
                    )
                )
                for ci, child in enumerate(item.get("children") or []):
                    seq += 1
                    timeline.add_widget(
                        StageItemRow(
                            display_text=child.get("text", ""),
                            done=bool(child.get("done", False)),
                            is_sub=True,
                            is_first=False,
                            is_last=False,
                            parent_screen=self,
                            group_index=gi,
                            item_index=ii,
                            child_index=ci,
                        )
                    )
            children = timeline.children
            if children and isinstance(children[0], StageItemRow):
                children[0].is_last = False
        timeline.add_widget(EtapyFinishRow())

    # --- Notes ---

    _add_note_sheet = None

    def open_add_note_sheet(self):
        if self._add_note_sheet is not None:
            return
        sheet = AddNoteBottomSheet(self, note_row=None)

        def _cleared(*_a):
            self._add_note_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._add_note_sheet = sheet
        sheet.open()

    def open_edit_note_sheet(self, row):
        if self._add_note_sheet is not None:
            return
        sheet = AddNoteBottomSheet(self, note_row=row)

        def _cleared(*_a):
            self._add_note_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._add_note_sheet = sheet
        sheet.open()

    def add_note(self, text="", tall=False):
        row = ProjectNoteRow(tall=tall, display_text=text or "", parent_screen=self)
        self.ids.notes_list.add_widget(row)

    def remove_note_row(self, row):
        notes = self.ids.get("notes_list")
        if notes is None:
            return
        if row.parent is notes:
            notes.remove_widget(row)
        elif row.parent is not None:
            row.parent.remove_widget(row)
        self.save_project_content()

    # --- Time goals ---

    _goal_sheet = None

    def on_goals_add_clicked(self):
        self.open_add_goal_sheet()

    def open_add_goal_sheet(self):
        if self._goal_sheet is not None:
            return
        sheet = AddTimeGoalBottomSheet(self)

        def _cleared(*_a):
            self._goal_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._goal_sheet = sheet
        sheet.open()

    def add_time_goal(
        self,
        title="",
        goal="",
        goal_target_seconds=None,
        logged_seconds=0.0,
        reset_mode=RESET_WEEKLY,
        period_key=None,
    ):
        tgt = float(goal_target_seconds) if goal_target_seconds is not None else parse_goal_target_seconds(goal)
        tgt = max(10.0, tgt)
        if period_key is None:
            period_key = current_period_key(reset_mode) if reset_mode != RESET_NEVER else "all"
        disp = (goal or "").strip() or format_goal_summary(tgt, reset_mode)
        row = TimeGoalTrackRow(
            title_text=title.strip() or "Cel",
            goal_text=disp,
            goal_target_seconds=tgt,
            logged_seconds=max(0.0, float(logged_seconds)),
            reset_mode=reset_mode,
            period_key=period_key,
        )
        row.apply_logged_to_ui()
        self.ids.goals_list.add_widget(row)

    # --- Timer ---

    def _refresh_timer_label(self):
        s = self._timer_elapsed_seconds
        h, r = divmod(s, 3600)
        m, sec = divmod(r, 60)
        self.timer_display = f"{h:02d}:{m:02d}:{sec:02d}"

    def _finish_timer_run(self):
        if self._run_started_at is None:
            return
        duration = self._timer_elapsed_seconds - int(self._run_base_elapsed)
        if duration >= 1:
            record_session(
                self.project_title,
                duration,
                started_at=self._run_started_at,
            )
        self._run_started_at = None
        self._run_base_elapsed = self._timer_elapsed_seconds

    def toggle_timer(self):
        if self.timer_running:
            self._stop_timer_event()
            self._finish_timer_run()
            self.timer_running = False
            self.timer_button_caption = "start"
            self.save_project_content()
        else:
            self._stop_timer_event()
            self._run_base_elapsed = self._timer_elapsed_seconds
            self._run_started_at = datetime.datetime.now()
            self._timer_ev = Clock.schedule_interval(self._on_timer_tick, 1.0)
            self.timer_running = True
            self.timer_button_caption = "stop"

    def _stop_timer_event(self):
        if self._timer_ev is not None:
            self._timer_ev.cancel()
            self._timer_ev = None

    def _on_timer_tick(self, _dt):
        self._timer_elapsed_seconds += 1
        self._refresh_timer_label()

    # --- Bottom bar / settings ---

    def _finalize_and_go_home(self):
        if self.timer_running:
            self._finish_timer_run()
            self.timer_running = False
            self.timer_button_caption = "start"
            self._stop_timer_event()
        self.save_project_content()
        MDApp.get_running_app().root.current = "home"
        schedule_home_last_session_refresh()

    def go_home(self):
        self._finalize_and_go_home()

    def go_statistics(self):
        MDApp.get_running_app().root.current = "statistics"

    def open_project_settings(self):
        dlg = MDDialog(
            title="Ustawienia projektu",
            text=f"Projekt: {self.project_title or '—'}\n\nTu pojawią się opcje projektu.",
        )
        btn = MDFlatButton(
            text="OK",
            theme_text_color="Custom",
            text_color=(0.2, 0.2, 0.2, 1),
        )
        btn.bind(on_release=lambda *a: dlg.dismiss())
        dlg.buttons = [btn]
        dlg.open()


class _BottomSheetKeyboardMixin:
    """Keep bottom-sheet panels above the soft keyboard with room for fields + actions."""

    _KB_RELAYOUT_DELAYS = (0.0, 0.2, 0.35, 0.5, 0.7, 0.9, 1.15)

    def _sheet_bind_keyboard(self):
        if getattr(self, "_sheet_kb_bound", False):
            return
        self._win_h_baseline = float(Window.height or 0)
        self._kb_lift_peak = 0.0
        self._kb_relayout_ev = []
        Window.bind(keyboard_height=self._on_sheet_keyboard)
        Window.bind(size=self._on_sheet_window_resize)
        self._sheet_kb_bound = True
        self._kb_poll_ev = Clock.schedule_interval(self._poll_keyboard_layout, 0.2)
        self._sync_modal_height()

    def _sheet_unbind_keyboard(self):
        poll = getattr(self, "_kb_poll_ev", None)
        if poll is not None:
            poll.cancel()
            self._kb_poll_ev = None
        for ev in getattr(self, "_kb_relayout_ev", []):
            ev.cancel()
        self._kb_relayout_ev = []
        if getattr(self, "_sheet_kb_bound", False):
            Window.unbind(keyboard_height=self._on_sheet_keyboard)
            Window.unbind(size=self._on_sheet_window_resize)
            self._sheet_kb_bound = False

    def _keyboard_unreserved_gap(self):
        """
        How far the Kivy window bottom sits above the real keyboard top.
        Trimming the modal by this removes the visible gap on adjustResize devices.
        """
        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        win_h = float(Window.height or 0)
        shrink = max(0.0, baseline - win_h) if baseline > win_h + dp(8) else 0.0
        inset = keyboard_inset(baseline) if baseline > 0 else 0.0
        kh = float(Window.keyboard_height or 0)

        gap = max(0.0, inset - shrink)
        if kh > shrink + dp(4):
            gap = max(gap, kh - shrink)

        if self._sheet_input_focused() and gap < dp(16):
            gap = dp(20)

        return min(gap + dp(5), dp(27))

    def _sync_modal_height(self):
        h = float(Window.height or 0)
        if h <= 0:
            return
        gap = 0.0
        if (
            self._sheet_input_focused()
            or self._window_shrunk_for_keyboard()
            or float(Window.keyboard_height or 0) > dp(48)
        ):
            gap = self._keyboard_unreserved_gap()

        self.size_hint = (1, None)
        self.size_hint_y = None
        self.height = max(dp(160), h - gap)
        self.pos_hint = {"x": 0, "y": 0}
        self.x = 0
        self.y = 0

    def _schedule_keyboard_relayout(self, animate=True):
        if getattr(self, "_closing", False):
            return
        for ev in getattr(self, "_kb_relayout_ev", []):
            ev.cancel()
        self._kb_relayout_ev = []
        for delay in self._KB_RELAYOUT_DELAYS:
            ev = Clock.schedule_once(
                lambda _dt, anim=animate: self._relayout_for_keyboard(anim),
                delay,
            )
            self._kb_relayout_ev.append(ev)

    def _on_sheet_keyboard(self, *_args):
        if getattr(self, "_closing", False):
            return
        self._schedule_keyboard_relayout(True)

    def _on_sheet_window_resize(self, *_args):
        if getattr(self, "_closing", False):
            return
        self._sync_modal_height()
        self._schedule_keyboard_relayout(True)

    def _poll_keyboard_layout(self, _dt):
        if getattr(self, "_closing", False):
            return False
        self._relayout_for_keyboard(True)
        return True

    def _enable_resize_softinput(self):
        try:
            Window.softinput_mode = "resize"
        except Exception:
            pass

    def _sheet_input_focused(self):
        for name in ("field", "title_field", "goal_field"):
            w = getattr(self, name, None)
            if w is not None and getattr(w, "focus", False):
                return True
        return False

    def _window_shrunk_for_keyboard(self):
        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        win_h = float(Window.height or 0)
        return baseline > win_h + dp(40)

    def _keyboard_lift(self):
        """Extra bottom inset only when the window did NOT shrink (keyboard overlays full screen)."""
        if self._window_shrunk_for_keyboard():
            return 0.0

        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        kh = keyboard_inset(baseline)
        peak = float(getattr(self, "_kb_lift_peak", 0) or 0)
        if kh > peak:
            self._kb_lift_peak = kh
        lift = max(kh, peak)

        if self._sheet_input_focused() and lift < dp(200):
            win_h = float(Window.height or 640)
            lift = max(lift, win_h * 0.36)
        return lift

    def _measure_panel_chrome(self, panel, exclude=()):
        """Sum fixed chrome (padding, title, buttons) so the field does not cover the action bar."""
        chrome = float(panel.padding[1]) + float(panel.padding[3])
        excluded = set(exclude)
        for child in panel.children:
            if child in excluded:
                continue
            chrome += float(child.height)
        n = len(panel.children)
        if n > 1:
            chrome += float(panel.spacing) * (n - 1)
        return chrome + dp(4)

    def _sheet_bottom_y(self, win_h):
        """Panel bottom edge — anchor to modal bottom (modal height trimmed to keyboard)."""
        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        shrink = max(0.0, baseline - win_h) if baseline > 0 else 0.0
        inset = keyboard_inset(baseline) if baseline > 0 else float(Window.keyboard_height or 0)

        if not (
            self._sheet_input_focused()
            or shrink > dp(40)
            or inset > dp(48)
        ):
            return 0.0

        if shrink > dp(40):
            return 0.0

        lift = max(inset, float(Window.keyboard_height or 0), self._keyboard_lift())
        gap = self._keyboard_unreserved_gap()
        return max(0.0, lift - gap)

    def _sheet_panel_geometry(
        self, max_panel_dp, chrome_dp, field_max_dp=None, fill_available=False
    ):
        """Return (panel_height, target_y, inner_height) for the sheet body."""
        win_h = float(self.height or Window.height or 640)
        chrome = float(chrome_dp)
        target_y = self._sheet_bottom_y(win_h)
        keyboard_up = target_y > 0 or self._sheet_input_focused()

        if keyboard_up:
            available = max(dp(160), win_h - target_y - dp(4))
        else:
            available = min(float(max_panel_dp), win_h * 0.85)
            target_y = dp(8)

        panel_h = min(float(max_panel_dp), available)
        inner_h = max(dp(44), panel_h - chrome)

        if keyboard_up and fill_available:
            panel_h = available
            inner_h = max(dp(44), panel_h - chrome)
        elif keyboard_up and field_max_dp is not None:
            inner_h = min(inner_h, float(field_max_dp))
            panel_h = chrome + inner_h
        else:
            panel_h = max(dp(180), panel_h)
            inner_h = max(dp(44), panel_h - chrome)

        if panel_h > available:
            inner_h = max(dp(44), available - chrome)
            panel_h = chrome + inner_h

        return panel_h, target_y, inner_h

    def _panel_height_for_content(self, panel, body_height, body_scroll=None):
        """Panel height = padding + fixed children + body (no extra slack)."""
        pad = float(panel.padding[1]) + float(panel.padding[3])
        spacing = float(panel.spacing)
        n = len(panel.children)
        chrome = pad + (spacing * (n - 1) if n > 1 else 0.0)
        for child in panel.children:
            if child is body_scroll:
                chrome += float(body_height)
            else:
                chrome += float(child.height)
        return chrome


class AddNoteBottomSheet(ModalView, _BottomSheetKeyboardMixin):
    """Slides up from the bottom with a text field and add action; requests keyboard via focus."""

    _NOTE_FIELD_LINES = 4

    def _note_field_height(self):
        line_h = sp(16) * 1.35
        return dp(24) + line_h * self._NOTE_FIELD_LINES

    def _apply_note_layout(self, animate=False):
        self._sync_modal_height()
        field_h = self._note_field_height()
        self.field.height = field_h
        self.panel.height = self._panel_height_for_content(self.panel, field_h)
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    def __init__(self, project_screen, note_row=None, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self.note_row = note_row
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        self._fl = root

        dim = Button(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            background_normal="",
            background_color=(0, 0, 0, 0.45),
        )
        dim.bind(on_release=lambda *a: self.dismiss())
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(400),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        title = "Edytuj notatkę" if note_row else "Nowa notatka"
        self.panel.add_widget(
            MDLabel(
                text=title,
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
                valign="middle",
            )
        )

        self.field = RoundedSheetTextInput(
            hint_text="Treść notatki…",
            text=note_row.display_text if note_row else "",
            multiline=True,
            size_hint_y=None,
            height=self._note_field_height(),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
            hint_text_color=(0.55, 0.55, 0.55, 1),
        )
        self.panel.add_widget(self.field)

        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(12),
        )
        if note_row is not None:
            btn_delete = RoundedSheetButton(
                text="Usuń",
                size_hint_x=None,
                width=dp(88),
                bg_color=list(get_color_from_hex("#e53935")),
            )
            btn_delete.bind(on_release=lambda *a: self._delete_note_and_close())
            bar.add_widget(btn_delete)
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        add_label = "Zapisz" if note_row else "Dodaj"
        btn_add = RoundedSheetButton(
            text=add_label,
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)

        self.add_widget(root)

    def _relayout_for_keyboard(self, animate=False):
        self._apply_note_layout(animate)

    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(500)
        Clock.schedule_once(self._open_start, 0)

    def _open_start(self, _dt):
        self._apply_note_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_keyboard_focus, 0.35)

    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    def _request_keyboard_focus(self, _dt):
        self.field.focus = True
        self._schedule_keyboard_relayout(True)
        if self.field.text:
            self.field.cursor = (len(self.field.text), 0)

    def _delete_note_and_close(self):
        if self.note_row is not None and self.project_screen is not None:
            self.project_screen.remove_note_row(self.note_row)
        self.dismiss()

    def _commit_and_close(self):
        raw = self.field.text or ""
        text = raw.strip()
        tall = bool(text) and (("\n" in raw) or len(text) > 100)
        if self.note_row is not None:
            self.note_row.display_text = text
            self.note_row.tall = tall
            self.project_screen.save_project_content()
            self.dismiss()
            return
        if not text:
            self.dismiss()
            return
        self.project_screen.add_note(text=text, tall=tall)
        self.field.text = ""
        self.dismiss()

    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddNoteBottomSheet, self).dismiss())
        anim.start(self.panel)


class AddTimeGoalBottomSheet(ModalView, _BottomSheetKeyboardMixin):
    """Bottom sheet: title + goal string (e.g. 1h/1d); target duration parsed for the car progress."""

    def __init__(self, project_screen, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        dim = Button(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            background_normal="",
            background_color=(0, 0, 0, 0.45),
        )
        dim.bind(on_release=lambda *a: self.dismiss())
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(12), dp(8), dp(12), 0],
            spacing=dp(6),
            size_hint=(1, None),
            height=dp(360),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        self.panel.add_widget(
            MDLabel(
                text="Nowy cel czasowy",
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(22),
                valign="middle",
            )
        )

        self._body_scroll = ScrollView(
            size_hint_y=None,
            height=dp(220),
            do_scroll_x=False,
            bar_width=dp(4),
        )
        self._body = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(210),
        )

        self.title_field = RoundedSheetTextInput(
            hint_text="Nazwa celu",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            font_size=sp(16),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            foreground_color=get_color_from_hex("#222222"),
        )
        self._body.add_widget(self.title_field)

        self.goal_field = RoundedSheetTextInput(
            hint_text="Ile czasu (np. 3h, 15min)",
            text="1h",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            font_size=sp(15),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            foreground_color=get_color_from_hex("#222222"),
        )
        self._body.add_widget(self.goal_field)

        self._body.add_widget(
            MDLabel(
                text="Reset postępu",
                font_style="Caption",
                theme_text_color="Custom",
                text_color=(0.25, 0.25, 0.28, 1),
                size_hint_y=None,
                height=dp(18),
            )
        )

        self._mode_by_label = {
            "Codziennie": RESET_DAILY,
            "Tygodniowo": RESET_WEEKLY,
            "Bez resetu": RESET_NEVER,
        }
        self.freq_spinner = RoundedSheetSpinner(
            text="Tygodniowo",
            values=("Codziennie", "Tygodniowo", "Bez resetu"),
            size_hint_x=1,
            size_hint_y=None,
            height=dp(44),
            fill_color=[0.95, 0.95, 0.97, 1],
            color=(0.1, 0.1, 0.1, 1),
        )
        self._body.add_widget(self.freq_spinner)

        self._body.add_widget(
            MDLabel(
                text="Codziennie / tygodniowo / bez resetu — krótszy cel = szybszy przejazd auta.",
                font_style="Caption",
                theme_text_color="Custom",
                text_color=(0.35, 0.35, 0.38, 1),
                size_hint_x=1,
                size_hint_y=None,
                height=dp(32),
                shorten=True,
                shorten_from="right",
            )
        )

        self._body_scroll.add_widget(self._body)
        self.panel.add_widget(self._body_scroll)
        self._sync_goal_body_height()

        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8),
        )
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_add = RoundedSheetButton(
            text="Dodaj cel",
            size_hint_x=None,
            width=dp(112),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)

        self.add_widget(root)

    def _sync_goal_body_height(self):
        spacing = float(self._body.spacing)
        n = len(self._body.children)
        body_h = sum(float(c.height) for c in self._body.children)
        if n > 1:
            body_h += spacing * (n - 1)
        self._body.height = body_h

    def _apply_goal_layout(self, animate=False):
        self._sync_modal_height()
        self._sync_goal_body_height()
        body_h = float(self._body.height)
        self._body_scroll.height = body_h
        self.panel.height = self._panel_height_for_content(
            self.panel, body_h, body_scroll=self._body_scroll
        )
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        max_h = win_h - target_y
        if self.panel.height > max_h:
            chrome = self._measure_panel_chrome(
                self.panel, exclude=(self._body_scroll,)
            )
            self._body_scroll.height = max(dp(80), max_h - chrome)
            self.panel.height = self._panel_height_for_content(
                self.panel, self._body_scroll.height, body_scroll=self._body_scroll
            )
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    def _relayout_for_keyboard(self, animate=False):
        self._apply_goal_layout(animate)

    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(600)
        Clock.schedule_once(self._open_start, 0)

    def _open_start(self, _dt):
        self._apply_goal_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_goal_focus, 0.35)

    def _request_goal_focus(self, _dt):
        self.title_field.focus = True
        self._schedule_keyboard_relayout(True)

    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    def _commit(self):
        title = (self.title_field.text or "").strip()
        qty = (self.goal_field.text or "").strip() or "1h"
        if not title:
            self.dismiss()
            return
        mode = self._mode_by_label.get(self.freq_spinner.text, RESET_WEEKLY)
        quota = parse_goal_target_seconds(qty)
        summary = format_goal_summary(quota, mode)
        self.project_screen.add_time_goal(
            title=title,
            goal=summary,
            goal_target_seconds=quota,
            logged_seconds=0.0,
            reset_mode=mode,
        )
        self.dismiss()

    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.title_field.focus = False
        self.goal_field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddTimeGoalBottomSheet, self).dismiss())
        anim.start(self.panel)


class AddChecklistGoalBottomSheet(ModalView, _BottomSheetKeyboardMixin):
    """Add or edit a simple checklist goal (Lista celów)."""

    def __init__(self, project_screen, goal_row=None, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self.goal_row = goal_row
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        dim = Button(
            size_hint=(1, 1),
            background_normal="",
            background_color=(0, 0, 0, 0.45),
            on_release=lambda *a: self.dismiss(),
        )
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(220),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        title = "Edytuj cel" if goal_row else "Nowy cel"
        self.panel.add_widget(
            MDLabel(
                text=title,
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
            )
        )
        self.field = RoundedSheetTextInput(
            hint_text="Opis celu…",
            text=goal_row.display_text if goal_row else "",
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
        )
        self.panel.add_widget(self.field)

        bar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(12))
        if goal_row is not None:
            btn_delete = RoundedSheetButton(
                text="Usuń",
                size_hint_x=None,
                width=dp(88),
                bg_color=list(get_color_from_hex("#e53935")),
            )
            btn_delete.bind(on_release=lambda *a: self._delete_and_close())
            bar.add_widget(btn_delete)
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_add = RoundedSheetButton(
            text="Zapisz" if goal_row else "Dodaj",
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)
        self.add_widget(root)

    def _apply_sheet_layout(self, animate=False):
        self._sync_modal_height()
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        self.panel.height = self._panel_height_for_content(self.panel, 0)
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    def _relayout_for_keyboard(self, animate=False):
        self._apply_sheet_layout(animate)

    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(300)
        Clock.schedule_once(self._open_anim, 0)

    def _open_anim(self, _dt):
        self.panel.height = max(
            dp(220),
            self._panel_height_for_content(self.panel, 0),
        )
        self._apply_sheet_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_focus, 0.3)

    def _request_focus(self, _dt):
        self.field.focus = True
        self._schedule_keyboard_relayout(True)

    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    def _delete_and_close(self):
        if self.goal_row is not None:
            self.project_screen.remove_checklist_goal_row(self.goal_row)
        self.dismiss()

    def _commit_and_close(self):
        text = (self.field.text or "").strip()
        if self.goal_row is not None:
            self.goal_row.display_text = text
            self.goal_row._sync_height()
            self.project_screen._renumber_checklist_goals()
            self.project_screen.save_project_content()
            self.dismiss()
            return
        if text:
            self.project_screen.add_checklist_goal(text=text)
            self.project_screen.save_project_content()
        self.dismiss()

    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddChecklistGoalBottomSheet, self).dismiss())
        anim.start(self.panel)


class AddEtapyBottomSheet(ModalView, _BottomSheetKeyboardMixin):
    """Add etapy group, main step, or sub-step."""

    def __init__(self, project_screen, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        dim = Button(
            size_hint=(1, 1),
            background_normal="",
            background_color=(0, 0, 0, 0.45),
            on_release=lambda *a: self.dismiss(),
        )
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(300),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        self.panel.add_widget(
            MDLabel(
                text="Dodaj do etapów",
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
            )
        )

        self.type_spinner = RoundedSheetSpinner(
            text=ETAPY_ADD_STEP,
            values=[ETAPY_ADD_GROUP, ETAPY_ADD_STEP, ETAPY_ADD_SUB],
            size_hint_y=None,
            height=dp(44),
            font_size=sp(15),
        )
        self.type_spinner.bind(text=self._on_type_changed)
        self.panel.add_widget(self.type_spinner)

        self.parent_spinner = RoundedSheetSpinner(
            text="",
            values=[""],
            size_hint_y=None,
            height=dp(44),
            font_size=sp(15),
            opacity=0,
            disabled=True,
        )
        self.panel.add_widget(self.parent_spinner)

        self.field = RoundedSheetTextInput(
            hint_text="Nazwa…",
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
        )
        self.panel.add_widget(self.field)

        bar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(12))
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_add = RoundedSheetButton(
            text="Dodaj",
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)
        self.add_widget(root)
        self._refresh_parent_spinner()

    def _apply_sheet_layout(self, animate=False):
        self._sync_modal_height()
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        self.panel.height = self._panel_height_for_content(self.panel, 0)
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        max_h = win_h - target_y
        if self.panel.height > max_h:
            self.panel.height = max(dp(180), max_h)
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    def _relayout_for_keyboard(self, animate=False):
        self._apply_sheet_layout(animate)

    def _on_type_changed(self, _spinner, value):
        sub = value == ETAPY_ADD_SUB
        self.parent_spinner.opacity = 1 if sub else 0
        self.parent_spinner.disabled = not sub
        self.parent_spinner.height = dp(44) if sub else 0
        if sub:
            self._refresh_parent_spinner()
        if value == ETAPY_ADD_GROUP:
            self.field.hint_text = "Nazwa grupy (np. Salto)…"
        elif value == ETAPY_ADD_SUB:
            self.field.hint_text = "Nazwa podkroku…"
        else:
            self.field.hint_text = "Nazwa kroku…"
        Clock.schedule_once(lambda _dt: self._apply_sheet_layout(True), 0)

    def _refresh_parent_spinner(self):
        group = self.project_screen._selected_etapy_group()
        labels = []
        if group:
            for i, it in enumerate(group.get("items") or []):
                t = (it.get("text") or f"Krok {i + 1}").strip()
                labels.append(f"{i + 1}. {t[:40]}")
        if not labels:
            labels = ["(najpierw dodaj krok)"]
        self.parent_spinner.values = labels
        self.parent_spinner.text = labels[0]

    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(400)
        Clock.schedule_once(self._open_anim, 0)

    def _open_anim(self, _dt):
        self._apply_sheet_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_focus, 0.3)

    def _request_focus(self, _dt):
        self.field.focus = True
        self._schedule_keyboard_relayout(True)

    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    def _commit_and_close(self):
        kind = self.type_spinner.text
        text = (self.field.text or "").strip()
        if not text:
            self.dismiss()
            return
        if kind == ETAPY_ADD_GROUP:
            self.project_screen.add_etapy_group(text)
        elif kind == ETAPY_ADD_SUB:
            parent_txt = self.parent_spinner.text or ""
            if parent_txt.startswith("("):
                self.dismiss()
                return
            try:
                idx = int(parent_txt.split(".", 1)[0]) - 1
            except ValueError:
                idx = 0
            self.project_screen.add_etapy_step(text, parent_item_index=idx)
        else:
            self.project_screen.add_etapy_step(text)
        self.dismiss()

    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddEtapyBottomSheet, self).dismiss())
        anim.start(self.panel)


class ProjectNoteRow(MDBoxLayout):
    """Tap note body to edit; × on the right deletes."""

    tall = BooleanProperty(False)
    display_text = StringProperty("")
    parent_screen = ObjectProperty(None, allownone=True)

    NOTE_SCROLL_MAX = dp(280)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(10))
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.bind(display_text=self._schedule_layout)
        self.bind(tall=self._schedule_layout)
        self.bind(width=self._schedule_layout)

    def _touch_key(self):
        return "_pnr_%d" % id(self)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if "delete_btn" in self.ids and self.ids.delete_btn.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if super().on_touch_down(touch):
            return True
        if "note_scroll" in self.ids and self.ids.note_scroll.collide_point(*touch.pos):
            touch.ud[self._touch_key()] = touch.pos
        return False

    def on_touch_up(self, touch):
        if super().on_touch_up(touch):
            return True
        key = self._touch_key()
        start = touch.ud.pop(key, None)
        if start and self.collide_point(*touch.pos):
            if "delete_btn" in self.ids and self.ids.delete_btn.collide_point(*touch.pos):
                return False
            dx = touch.pos[0] - start[0]
            dy = touch.pos[1] - start[1]
            if dx * dx + dy * dy < dp(14) ** 2:
                self.open_edit_from_row()
                return True
        return False

    def request_delete(self, *_args):
        scr = self.parent_screen
        if scr is None:
            w = self.parent
            while w is not None:
                if isinstance(w, ProjectInfoScreen):
                    scr = w
                    break
                w = w.parent
        if scr is not None:
            scr.remove_note_row(self)

    def on_kv_post(self, base_widget):
        self.ids.note_scroll.bind(width=self._schedule_layout)
        self.ids.note_label.bind(texture_size=self._schedule_layout)
        self.ids.delete_btn.bind(on_press=lambda *_a: self.request_delete())
        Clock.schedule_once(self._sync_note_layout, 0)

    def _schedule_layout(self, *args):
        Clock.schedule_once(self._sync_note_layout, 0)

    def _sync_note_layout(self, *args):
        sc = self.ids.note_scroll
        lbl = self.ids.note_label
        aw = max(self.width - dp(74), sc.width - dp(16), sp(20))
        if aw <= sp(20) or self.width <= 1:
            Clock.schedule_once(self._sync_note_layout, 0.05)
            return
        lbl.text_size = (aw, None)
        lbl.texture_update()
        content_h = lbl.texture_size[1] + dp(24)
        cap = self.NOTE_SCROLL_MAX + dp(24)
        self.height = max(dp(52), min(cap, max(dp(48), content_h)))

    def open_edit_from_row(self):
        scr = self.parent_screen
        if scr:
            scr.open_edit_note_sheet(self)


class CarProgressButton(ButtonBehavior, Image):
    """Tappable car sprite. Plain Image so the track RelativeLayout can move it via pos_hint center_x."""

    def __init__(self, **kwargs):
        kwargs.setdefault("nocache", True)
        kwargs.setdefault("allow_stretch", True)
        kwargs.setdefault("keep_ratio", True)
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        if hasattr(self, "fit_mode"):
            self.fit_mode = "contain"


class TimeGoalTrackRow(MDBoxLayout):
    """Time goal track: tap car to start/pause; optional daily/weekly reset of progress."""

    title_text = StringProperty("")
    goal_text = StringProperty("")
    goal_target_seconds = NumericProperty(3600.0)
    logged_seconds = NumericProperty(0.0)
    tracking_active = BooleanProperty(False)
    car_hint_x = NumericProperty(0.08)
    percent_text = StringProperty("0%")
    elapsed_text = StringProperty("")
    reset_mode = StringProperty(RESET_WEEKLY)
    period_key = StringProperty("")
    car_source_idle = StringProperty(_car_asset_path("CCcc 1.png"))
    car_source_active = StringProperty(_car_asset_path("ZZzz 1.png"))

    _tick_ev = None
    _caption_scheduled = False

    def on_kv_post(self, base_widget):
        self.fbind("title_text", self._schedule_goal_caption_refresh)
        self.fbind("goal_text", self._schedule_goal_caption_refresh)
        self.fbind("width", self._schedule_goal_caption_refresh)
        self.fbind("width", lambda *a: self.apply_logged_to_ui())
        Clock.schedule_once(self._bind_caption_box_width, 0)
        Clock.schedule_once(self._refresh_goal_caption_layout, 0)

    def _bind_caption_box_width(self, *args):
        box = self.ids.get("goal_caption_box")
        if box is not None:
            box.fbind("width", self._schedule_goal_caption_refresh)

    def _schedule_goal_caption_refresh(self, *args):
        if self._caption_scheduled:
            return
        self._caption_scheduled = True
        Clock.schedule_once(self._refresh_goal_caption_layout, 0)

    def _refresh_goal_caption_layout(self, *args):
        self._caption_scheduled = False
        if "goal_title_lbl" not in self.ids or "goal_period_lbl" not in self.ids:
            return
        title_lbl = self.ids.goal_title_lbl
        period_lbl = self.ids.goal_period_lbl
        box = self.ids.goal_caption_box
        inner_w = box.width - box.padding[0] - box.padding[2] - box.spacing
        if inner_w <= 1:
            Clock.schedule_once(self._refresh_goal_caption_layout, 0.08)
            return
        period_lbl.text_size = (None, None)
        period_lbl.texture_update()
        pw = max(dp(44), min(inner_w * 0.42, period_lbl.texture_size[0] + dp(10)))
        period_lbl.width = pw
        period_lbl.text_size = (pw, None)
        tw = max(sp(16), inner_w - pw)
        title_lbl.text_size = (tw, None)

    def _ensure_period(self):
        if self.reset_mode == RESET_NEVER:
            if not self.period_key:
                self.period_key = "all"
            return
        cur = current_period_key(self.reset_mode)
        if not self.period_key:
            self.period_key = cur
            return
        if self.period_key != cur:
            self.logged_seconds = 0.0
            self.period_key = cur

    def apply_logged_to_ui(self):
        self._update_progress_from_time()

    def _update_progress_from_time(self):
        self._ensure_period()
        t = max(10.0, float(self.goal_target_seconds))
        p = min(100.0, 100.0 * float(self.logged_seconds) / t)
        w = max(200.0, float(self.width or 300))
        px = 10.0 / w
        start = 0.08 + px
        span = max(0.2, 0.84 - px)
        self.car_hint_x = min(0.93, start + (p / 100.0) * span)
        self.percent_text = f"{int(round(p))}%"
        self.elapsed_text = format_goal_elapsed(self.logged_seconds) if self.logged_seconds >= 1 else ""

    def on_car_button_release(self, *args):
        if self.tracking_active:
            self.stop_tracking()
        else:
            self.start_tracking()

    def start_tracking(self):
        if self._tick_ev is not None:
            return
        self.tracking_active = True
        self._tick_ev = Clock.schedule_interval(self._on_track_tick, 0.05)

    def stop_tracking(self):
        if self._tick_ev is not None:
            self._tick_ev.cancel()
            self._tick_ev = None
        self.tracking_active = False

    def _on_track_tick(self, dt):
        self._ensure_period()
        self.logged_seconds += float(dt)
        self._update_progress_from_time()

    def on_parent(self, *_args):
        if self.parent is None:
            self.stop_tracking()
