import datetime
import json
import os
import re
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex
from kivy.uix.scrollview import ScrollView
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from screens.keyboard_inset import keyboard_inset

# Project root = parent of `screens/` (works on device and desktop).
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _car_asset_path(filename):
    return os.path.join(_PKG_ROOT, "assets", "Progress_Car", filename)


RESET_NEVER = "never"
RESET_DAILY = "daily"
RESET_WEEKLY = "weekly"


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


class ProjectInfoScreen(MDScreen):
    """Project detail panel: dynamic notes & goals, timer, bottom nav like home."""

    project_title = StringProperty("")
    timer_display = StringProperty("00:00:00")
    timer_running = BooleanProperty(False)
    timer_button_caption = StringProperty("start")

    _timer_ev = None
    _timer_elapsed_seconds = 0

    def on_enter(self):
        Window.bind(on_keyboard=self._on_keyboard)
        self.load_project_content()

    def on_leave(self):
        Window.unbind(on_keyboard=self._on_keyboard)
        if self.timer_running:
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
            MDApp.get_running_app().root.current = "home"
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
        }
        self._write_all_states(data)

    def load_project_content(self):
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
        else:
            self._timer_elapsed_seconds = 0
            self._refresh_timer_label()

    def _clear_dynamic_widgets(self):
        for c in list(self.ids.notes_list.children):
            self.ids.notes_list.remove_widget(c)
        for c in list(self.ids.goals_list.children):
            self.ids.goals_list.remove_widget(c)

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

    def toggle_timer(self):
        if self.timer_running:
            self._stop_timer_event()
            self.timer_running = False
            self.timer_button_caption = "start"
            self.save_project_content()
        else:
            self._stop_timer_event()
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

    def go_home(self):
        MDApp.get_running_app().root.current = "home"

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

        self.field = TextInput(
            hint_text="Treść notatki…",
            text=note_row.display_text if note_row else "",
            multiline=True,
            size_hint_y=None,
            height=self._note_field_height(),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            background_color=(0.97, 0.97, 0.97, 1),
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
            btn_delete = MDRaisedButton(
                text="Usuń",
                md_bg_color=get_color_from_hex("#e53935"),
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
            )
            btn_delete.bind(on_release=lambda *a: self._delete_note_and_close())
            bar.add_widget(btn_delete)
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = MDFlatButton(text="Anuluj")
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        add_label = "Zapisz" if note_row else "Dodaj"
        btn_add = MDRaisedButton(
            text=add_label,
            md_bg_color=get_color_from_hex(app.theme_card_bg),
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
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

        self.title_field = TextInput(
            hint_text="Nazwa celu",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            font_size=sp(16),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            background_color=(0.97, 0.97, 0.97, 1),
            foreground_color=get_color_from_hex("#222222"),
        )
        self._body.add_widget(self.title_field)

        self.goal_field = TextInput(
            hint_text="Ile czasu (np. 3h, 15min)",
            text="1h",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            font_size=sp(15),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            background_color=(0.97, 0.97, 0.97, 1),
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
        self.freq_spinner = Spinner(
            text="Tygodniowo",
            values=("Codziennie", "Tygodniowo", "Bez resetu"),
            size_hint_x=1,
            size_hint_y=None,
            height=dp(44),
            background_color=(0.95, 0.95, 0.97, 1),
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
        btn_cancel = MDFlatButton(text="Anuluj")
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_add = MDRaisedButton(
            text="Dodaj cel",
            md_bg_color=get_color_from_hex(app.theme_card_bg),
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
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
