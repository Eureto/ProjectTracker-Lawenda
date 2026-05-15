from kivy.clock import Clock
from kivy.metrics import dp
from kivy.animation import Animation
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.button import Button
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, RoundedRectangle

from screens.session_store import (
    format_statistics_total,
    statistics_from_sessions,
)

from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.label import MDIcon


class PeriodSegmentButton(Button):
    """
    Pill-shaped period choice. `selected` is bound from KV to `root.selected_period`
    so the background is not overwritten by KivyMD ripple logic (fixes two-tap).
    """
    selected = BooleanProperty(False)
    selection_progress = NumericProperty(0)

    _anim_duration = 0.22

    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(40))
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
        Animation.cancel_all(self, "selection_progress")
        Animation(
            selection_progress=target,
            d=self._anim_duration,
            t="out_cubic",
        ).start(self)

    def _apply_visual(self, *args):
        p = max(0.0, min(1.0, self.selection_progress))
        # Text: white -> dark gray
        t = 0.15
        self.color = (1 - (1 - t) * p, 1 - (1 - t) * p, 1 - (1 - t) * p, 1)
        r = dp(22)
        self.canvas.before.clear()
        with self.canvas.before:
            Color(1, 1, 1, p)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[r, r, r, r])


def _make_segment_color_dot(rgba, size_dp=20):
    dot = Widget(size_hint=(None, None), size=(dp(size_dp), dp(size_dp)))
    rgba = tuple(rgba) if len(rgba) >= 4 else (*rgba[:3], 1.0)

    def redraw(*_):
        dot.canvas.clear()
        with dot.canvas:
            Color(*rgba)
            Ellipse(pos=dot.pos, size=dot.size)

    dot.bind(pos=redraw, size=redraw)
    redraw()
    return dot


class StatisticsDetailRow(MDBoxLayout):
    """One project row in the stats table; properties so time text always updates."""

    project_name = StringProperty("")
    time_text = StringProperty("0 s")
    icon_name = StringProperty("folder-outline")
    icon_rgba = ListProperty([1, 1, 1, 1])
    segment_rgba = ListProperty([0.6, 0.4, 0.8, 1])

    def __init__(self, row_data, **kwargs):
        self._row_data = row_data
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(36))
        kwargs.setdefault("spacing", dp(6))
        super().__init__(**kwargs)

    def on_kv_post(self, base_widget):
        self.apply_row(self._row_data)
        self.bind(segment_rgba=self._redraw_segment_dot)
        if "segment_dot" in self.ids:
            self.ids.segment_dot.bind(pos=self._redraw_segment_dot, size=self._redraw_segment_dot)
        Clock.schedule_once(self._redraw_segment_dot, 0)

    def apply_row(self, row_data):
        self.project_name = row_data.get("name", "")
        self.time_text = row_data.get("time", "0 s")
        self.icon_name = row_data.get("icon", "folder-outline")
        self.icon_rgba = list(row_data.get("icon_color", (1, 1, 1, 1)))
        self.segment_rgba = list(row_data.get("segment_color", (0.6, 0.4, 0.8, 1)))

    def _redraw_segment_dot(self, *_args):
        if "segment_dot" not in self.ids:
            return
        dot = self.ids.segment_dot
        rgba = self.segment_rgba
        if len(rgba) == 3:
            rgba = (*rgba, 1.0)
        dot.canvas.clear()
        with dot.canvas:
            Color(*rgba)
            Ellipse(pos=dot.pos, size=dot.size)


class PieChart(Widget):
    """
    Niestandardowy wykres kołowy napisany w czystym Kivy.
    Przyjmuje listę słowników w formacie:
    [{'color': (r, g, b, a), 'percent': wartość_procentowa}, ...]
    """
    data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.update_canvas, size=self.update_canvas, data=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.clear()
        with self.canvas:
            angle_start = 0
            for item in self.data:
                Color(*item.get("color", (1, 1, 1, 1)))
                percent = item.get("percent", 0)
                angle_end = angle_start + (percent / 100.0) * 360
                Ellipse(pos=self.pos, size=self.size, angle_start=angle_start, angle_end=angle_end)
                angle_start = angle_end


class StatisticsScreen(MDScreen):
    selected_period = StringProperty("Miesiąc")
    total_time_text = StringProperty("suma: 0 s")
    has_data = BooleanProperty(False)
    empty_hint_text = StringProperty("Brak czasu w tym okresie.\nUruchom timer w projekcie.")
    stats_card_height = NumericProperty(dp(120))

    def set_period(self, label: str):
        if label not in ("Dzień", "Tydzień", "Miesiąc"):
            return
        self.selected_period = label
        Clock.schedule_once(lambda _dt: self.refresh_statistics(), 0)

    def set_statistics_rows(self, rows):
        """Fill the details panel; always rebuild rows for the active period."""
        cont = self.ids.stats_rows_container
        while cont.children:
            cont.remove_widget(cont.children[0])
        rows = list(rows or [])
        for r in reversed(rows):
            cont.add_widget(StatisticsDetailRow(r))
        cont.height = max(dp(36), cont.minimum_height)
        self._layout_stats_card()
        Clock.schedule_once(self._relayout_stats_scroll, 0)

    def _layout_stats_card(self):
        card = self.ids.stats_card
        cont = self.ids.stats_rows_container
        pad = card.padding
        if isinstance(pad, (int, float)):
            pt = pr = pb = pl = float(pad)
        else:
            pl, pt, pr, pb = pad[0], pad[1], pad[2], pad[3]
        header_h = dp(26)
        gap = card.spacing
        if isinstance(gap, (list, tuple)):
            gap = float(gap[1]) if len(gap) > 1 else float(gap[0])
        else:
            gap = float(gap)
        row_spacing = cont.spacing
        if isinstance(row_spacing, (list, tuple)):
            row_spacing = float(row_spacing[1]) if len(row_spacing) > 1 else float(row_spacing[0])
        else:
            row_spacing = float(row_spacing)
        row_heights = sum(float(c.height) for c in cont.children)
        row_gaps = row_spacing * max(0, len(cont.children) - 1)
        empty_h = dp(48) if not self.has_data else 0
        self.stats_card_height = pt + pb + header_h + gap + row_heights + row_gaps + empty_h

    def _relayout_stats_scroll(self, _dt=None):
        if "stats_scroll_content" in self.ids:
            grid = self.ids.stats_scroll_content
            grid.height = grid.minimum_height

    def refresh_statistics(self):
        period = self.selected_period
        pie, rows, total_sec = statistics_from_sessions(period)
        self.total_time_text = format_statistics_total(total_sec)
        self.has_data = total_sec > 0
        self.ids.pie_chart.data = list(pie) if pie else []
        self.set_statistics_rows(rows)
        self._relayout_stats_scroll()

    def on_selected_period(self, _instance, value):
        if value in ("Dzień", "Tydzień", "Miesiąc"):
            self.refresh_statistics()

    def on_enter(self):
        self.refresh_statistics()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(selected_period=self.on_selected_period)
