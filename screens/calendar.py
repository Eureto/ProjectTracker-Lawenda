import datetime
import calendar as cal_mod
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty, ObjectProperty
from kivy.uix.button import Button
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle, Line, Ellipse, Rectangle
from kivy.core.text import Label as CoreLabel

from screens.session_store import (
    get_sessions_in_date_range,
    format_duration_hms,
    _parse_ended,
    _parse_started,
)

from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard

_HEADER_HEIGHT = dp(48)
_HOUR_HEIGHT = dp(60)
_HOURS_START = 0
_HOURS_END = 24
_TOTAL_HOURS = _HOURS_END - _HOURS_START
_TOTAL_MINUTES = _TOTAL_HOURS * 60

_MONTHS_PL = (
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
)
_DAYS_PL = ("Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd")


class ViewSegmentButton(Button):
    selected = BooleanProperty(False)
    selection_progress = NumericProperty(0)

    _anim_duration = 0.22

    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(36))
        kwargs.setdefault("size_hint_x", 1)
        super().__init__(**kwargs)
        self.selection_progress = 1.0 if self.selected else 0.0
        self.bind(
            selected=self._on_selected_change,
            selection_progress=self._apply_visual,
            pos=self._apply_visual,
            size=self._apply_visual,
            state=self._apply_visual,
        )
        self._apply_visual()

    def _on_selected_change(self, *args):
        target = 1.0 if self.selected else 0.0
        if abs(self.selection_progress - target) < 1e-4:
            return
        from kivy.animation import Animation
        Animation.cancel_all(self, "selection_progress")
        Animation(
            selection_progress=target,
            d=self._anim_duration,
            t="out_cubic",
        ).start(self)

    def _apply_visual(self, *args):
        p = max(0.0, min(1.0, self.selection_progress))
        t = 0.15
        self.color = (1 - (1 - t) * p, 1 - (1 - t) * p, 1 - (1 - t) * p, 1)
        r = dp(18)
        self.canvas.before.clear()
        with self.canvas.before:
            Color(1, 1, 1, p)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[r, r, r, r])


class CalendarScreen(MDScreen):
    view_mode = StringProperty("month")
    selected_date = ObjectProperty(None)
    period_label = StringProperty("")
    current_day_label = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_date = datetime.date.today()
        self._update_period_label()
        self._update_current_day_label()

    def set_view_mode(self, mode):
        if mode not in ("month", "week", "3day"):
            return
        self.view_mode = mode
        self._update_period_label()
        self._update_current_day_label()
        Clock.schedule_once(lambda _dt: self.refresh_calendar(), 0)

    def go_prev(self):
        d = self.selected_date
        if self.view_mode == "month":
            first = d.replace(day=1)
            self.selected_date = first - datetime.timedelta(days=1)
            self.selected_date = self.selected_date.replace(day=1)
        elif self.view_mode == "week":
            self.selected_date = d - datetime.timedelta(days=7)
        else:
            self.selected_date = d - datetime.timedelta(days=3)
        self._update_period_label()
        self._update_current_day_label()
        Clock.schedule_once(lambda _dt: self.refresh_calendar(), 0)

    def go_next(self):
        d = self.selected_date
        if self.view_mode == "month":
            _, days = cal_mod.monthrange(d.year, d.month)
            first = d.replace(day=1)
            self.selected_date = first + datetime.timedelta(days=days)
            self.selected_date = self.selected_date.replace(day=1)
        elif self.view_mode == "week":
            self.selected_date = d + datetime.timedelta(days=7)
        else:
            self.selected_date = d + datetime.timedelta(days=3)
        self._update_period_label()
        self._update_current_day_label()
        Clock.schedule_once(lambda _dt: self.refresh_calendar(), 0)

    def go_today(self):
        self.selected_date = datetime.date.today()
        self._update_period_label()
        self._update_current_day_label()
        Clock.schedule_once(lambda _dt: self.refresh_calendar(), 0)

    def _update_period_label(self):
        d = self.selected_date or datetime.date.today()
        if self.view_mode == "month":
            self.period_label = f"{_MONTHS_PL[d.month - 1]} {d.year}"
        elif self.view_mode == "week":
            monday = d - datetime.timedelta(days=d.weekday())
            sunday = monday + datetime.timedelta(days=6)
            if monday.month == sunday.month:
                self.period_label = f"{monday.day} – {sunday.day} {_MONTHS_PL[monday.month - 1][:3]}"
            else:
                m_str = f"{monday.day} {_MONTHS_PL[monday.month - 1][:3]}"
                s_str = f"{sunday.day} {_MONTHS_PL[sunday.month - 1][:3]}"
                self.period_label = f"{m_str} – {s_str}"
        else:
            d2 = d - datetime.timedelta(days=2)
            d_str = f"{d2.day} {_MONTHS_PL[d2.month - 1][:3]}"
            d3_str = f"{d.day} {_MONTHS_PL[d.month - 1][:3]}"
            self.period_label = f"{d_str} – {d3_str}"

    def _update_current_day_label(self):
        d = self.selected_date or datetime.date.today()
        today = datetime.date.today()
        if d == today:
            self.current_day_label = "Dzisiaj"
        else:
            self.current_day_label = f"{d.day} {_MONTHS_PL[d.month - 1]}"

    def refresh_calendar(self):
        container = self.ids.get("calendar_content")
        if container is None:
            Clock.schedule_once(lambda _dt: self.refresh_calendar(), 0.05)
            return
        container.clear_widgets()
        if self.view_mode == "month":
            self._build_month_view(container)
        elif self.view_mode == "week":
            self._build_week_view(container)
        else:
            self._build_3day_view(container)

    def _get_days_for_view(self):
        d = self.selected_date or datetime.date.today()
        if self.view_mode == "month":
            cal = cal_mod.Calendar(firstweekday=0)
            return list(cal.itermonthdates(d.year, d.month))
        elif self.view_mode == "week":
            monday = d - datetime.timedelta(days=d.weekday())
            return [monday + datetime.timedelta(days=i) for i in range(7)]
        else:
            return [d - datetime.timedelta(days=2), d - datetime.timedelta(days=1), d]

    def _build_month_view(self, container):
        days = self._get_days_for_view()
        today = datetime.date.today()
        start = days[0]
        end = days[-1]
        sessions = get_sessions_in_date_range(start, end)

        sessions_by_day = {}
        for s in sessions:
            ended = _parse_ended(s)
            if ended is None:
                continue
            d = ended.date()
            if d not in sessions_by_day:
                sessions_by_day[d] = []
            sessions_by_day[d].append(s)

        header = MDBoxLayout(size_hint_y=None, height=dp(36), spacing=0)
        for day_name in _DAYS_PL:
            lbl = MDLabel(
                text=day_name,
                halign="center",
                valign="middle",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.7),
                font_size=dp(13),
                bold=True,
            )
            header.add_widget(lbl)
        container.add_widget(header)

        grid = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(2),
        )
        grid.bind(minimum_height=grid.setter("height"))

        row = None
        for i, day in enumerate(days):
            if i % 7 == 0:
                row = MDBoxLayout(size_hint_y=None, height=dp(56), spacing=dp(2))
                grid.add_widget(row)
            is_current = day == today
            is_current_month = day.month == (self.selected_date or today).month
            day_sessions = sessions_by_day.get(day, [])

            cell = MonthDayCell(
                date=day,
                day_number=day.day,
                is_current=is_current,
                is_current_month=is_current_month,
                sessions=day_sessions,
                size_hint_x=1,
                size_hint_y=1,
            )
            row.add_widget(cell)

        container.add_widget(grid)

    def _build_week_view(self, container):
        self._build_time_grid_view(container, 7)

    def _build_3day_view(self, container):
        self._build_time_grid_view(container, 3)

    def _build_time_grid_view(self, container, num_days):
        days = self._get_days_for_view()
        if self.view_mode == "3day":
            days = days[-3:]

        today = datetime.date.today()
        start = days[0]
        end = days[-1]
        sessions = get_sessions_in_date_range(start, end)

        grid_height = _TOTAL_HOURS * _HOUR_HEIGHT

        grid_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=_HEADER_HEIGHT + grid_height,
            spacing=0,
        )

        day_header = MDBoxLayout(size_hint_y=None, height=_HEADER_HEIGHT, spacing=dp(2))
        time_label_header = Widget(size_hint_x=None, width=dp(48))
        day_header.add_widget(time_label_header)
        for day in days:
            is_today = day == today
            lbl = MDLabel(
                text=f"{_DAYS_PL[day.weekday()]}\n{day.day}",
                halign="center",
                valign="middle",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1) if is_today else (1, 1, 1, 0.7),
                font_size=dp(12),
                bold=is_today,
                size_hint_x=1,
                markup=True,
            )
            day_header.add_widget(lbl)
        grid_box.add_widget(day_header)

        sessions_by_day = {}
        for s in sessions:
            ended = _parse_ended(s)
            if ended is None:
                continue
            d = ended.date()
            if d not in sessions_by_day:
                sessions_by_day[d] = []
            sessions_by_day[d].append(s)

        time_area = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=grid_height,
            spacing=dp(2),
        )

        time_labels = MDBoxLayout(
            orientation="vertical",
            size_hint_x=None,
            width=dp(48),
            spacing=0,
        )
        for h in range(_HOURS_START, _HOURS_END):
            lbl = MDLabel(
                text=f"{h:02d}:00",
                halign="center",
                valign="top",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.5),
                font_size=dp(10),
                size_hint_y=None,
                height=_HOUR_HEIGHT,
            )
            time_labels.add_widget(lbl)
        time_area.add_widget(time_labels)

        for day in days:
            col = MDFloatLayout(
                size_hint_x=1,
                size_hint_y=None,
                height=grid_height,
            )
            day_sessions = sessions_by_day.get(day, [])
            if day_sessions:
                self._add_session_blocks(col, day_sessions)
            time_area.add_widget(col)

        def _redraw_full_lines(inst, _):
            inst.canvas.before.clear()
            w = inst.width
            if w < 1:
                return
            with inst.canvas.before:
                for i in range(1, _TOTAL_HOURS):
                    y = i * _HOUR_HEIGHT
                    Color(1, 1, 1, 0.08)
                    Line(points=[0, y, w, y], width=dp(0.5))

        time_area.bind(size=_redraw_full_lines, pos=_redraw_full_lines)
        Clock.schedule_once(lambda _dt: _redraw_full_lines(time_area, None), 0)

        grid_box.add_widget(time_area)
        container.add_widget(grid_box)

    def _add_session_blocks(self, col, sessions):
        for s in sessions:
            ended = _parse_ended(s)
            started = _parse_started(s)
            if ended is None or started is None:
                continue

            duration = int(s.get("duration_seconds", 0))
            color = s.get("color", [0.6, 0.4, 0.8, 1])
            title = s.get("project_title", "")

            start_minutes = (started.hour - _HOURS_START) * 60 + started.minute
            total_minutes = max(duration / 60, 15)
            end_minutes = start_minutes + total_minutes

            if end_minutes > _TOTAL_MINUTES:
                end_minutes = _TOTAL_MINUTES
            if start_minutes < 0:
                start_minutes = 0

            y_ratio = 1.0 - (end_minutes / _TOTAL_MINUTES)
            h_ratio = (end_minutes - start_minutes) / _TOTAL_MINUTES

            block = MDBoxLayout(
                orientation="vertical",
                size_hint=(0.95, None),
                height=_HOUR_HEIGHT * _TOTAL_HOURS * h_ratio,
                padding=[dp(4), dp(1)],
            )
            block.pos_hint = {"center_x": 0.5, "y": y_ratio}
            with block.canvas.before:
                Color(*color[:3], 0.85)
                RoundedRectangle(pos=block.pos, size=block.size, radius=[dp(6)])

            def update_block_bg(inst, _):
                inst.canvas.before.clear()
                with inst.canvas.before:
                    Color(*color[:3], 0.85)
                    RoundedRectangle(pos=inst.pos, size=inst.size, radius=[dp(6)])
            block.bind(pos=update_block_bg, size=update_block_bg)

            label = MDLabel(
                text=title,
                font_size=dp(10),
                halign="left",
                valign="top",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
                shorten=True,
            )
            block.add_widget(label)
            col.add_widget(block)

    def on_enter(self):
        self._update_period_label()
        self._update_current_day_label()
        Clock.schedule_once(lambda _dt: self.refresh_calendar(), 0)

    def on_leave(self):
        pass


class MonthDayCell(Widget):
    date = ObjectProperty(None)
    day_number = NumericProperty(0)
    is_current = BooleanProperty(False)
    is_current_month = BooleanProperty(True)
    sessions = ListProperty([])

    _day_label = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._day_label = CoreLabel(
            text=str(self.day_number),
            font_size=dp(14),
            bold=self.is_current,
            color=(1, 1, 1, 1),
        )
        self.bind(
            pos=self.redraw,
            size=self.redraw,
            is_current=self.redraw,
            is_current_month=self.redraw,
            sessions=self.redraw,
            day_number=self.redraw,
        )

    def redraw(self, *args):
        if self._day_label:
            self._day_label.text = str(self.day_number)
            self._day_label.bold = self.is_current
            text_color = (1, 1, 1, 1) if self.is_current_month else (1, 1, 1, 0.3)
            if self.is_current:
                text_color = (0.1, 0.1, 0.1, 1)
            self._day_label.color = text_color
            self._day_label.refresh()

        self.canvas.clear()
        with self.canvas:
            w = self.width
            h = self.height
            cx = self.x + w / 2
            cy = self.y + h / 2

            if self.is_current:
                Color(1, 1, 1, 1)
                Ellipse(pos=(cx - dp(12), cy - dp(12)), size=(dp(24), dp(24)))

            if self._day_label and self._day_label.texture:
                tex = self._day_label.texture
                tex_w = tex.width
                tex_h = tex.height
                Color(1, 1, 1, 1)
                Rectangle(
                    pos=(cx - tex_w / 2, cy - tex_h / 2),
                    size=(tex_w, tex_h),
                    texture=tex,
                )

            dot_y = self.y + dp(4)
            colors_shown = 0
            seen = set()
            for s in self.sessions:
                if colors_shown >= 3:
                    break
                color = tuple(s.get("color", [0.6, 0.4, 0.8, 1]))
                p_title = s.get("project_title", "")
                if p_title in seen:
                    continue
                seen.add(p_title)
                dot_x = self.x + dp(6) + colors_shown * dp(12)
                Color(*color[:3], 0.9)
                Ellipse(pos=(dot_x, dot_y), size=(dp(8), dp(8)))
                colors_shown += 1

            remaining = 0
            if len(self.sessions) - len(seen) > 0:
                remaining = len(self.sessions) - len(seen)
            elif len(self.sessions) > 3:
                remaining = len(self.sessions) - 3
            if remaining > 0 and colors_shown > 0:
                dot_x = self.x + dp(6) + colors_shown * dp(12)
                Color(1, 1, 1, 0.5)
                RoundedRectangle(pos=(dot_x, dot_y), size=(dp(8), dp(8)), radius=[dp(4)])
