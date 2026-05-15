from kivy.metrics import dp
from kivy.animation import Animation
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.button import Button
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, RoundedRectangle

from screens.session_store import statistics_from_sessions

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


def build_statistics_detail_row(
    name,
    icon,
    segment_rgba,
    time_text,
    icon_rgba=(1, 1, 1, 1),
):
    """
    One statistics table row: icon+name | color dot | time.
    segment_rgba: color shown on the pie / legend dot (r, g, b, a).
    """
    row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(6))

    left = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_x=1)
    ic = MDIcon(
        icon=icon,
        theme_text_color="Custom",
        text_color=icon_rgba,
        size_hint=(None, None),
        size=(dp(28), dp(28)),
        pos_hint={"center_y": 0.5},
    )
    lbl = MDLabel(
        text=name,
        theme_text_color="Custom",
        text_color=(1, 1, 1, 1),
        valign="middle",
        shorten=True,
        shorten_from="right",
    )
    left.add_widget(ic)
    left.add_widget(lbl)

    mid = AnchorLayout(size_hint_x=1, anchor_x="center", anchor_y="center")
    mid.add_widget(_make_segment_color_dot(segment_rgba))

    right = MDLabel(
        text=time_text,
        theme_text_color="Custom",
        text_color=(1, 1, 1, 1),
        size_hint_x=1,
        halign="right",
        valign="middle",
    )

    row.add_widget(left)
    row.add_widget(mid)
    row.add_widget(right)
    return row


def set_screen_statistics(screen, pie_slices, detail_rows):
    """Update pie chart and detail rows in one call."""
    screen.ids.pie_chart.data = pie_slices
    screen.set_statistics_rows(detail_rows)


def sample_statistics_rows():
    """Demo data; replace with real aggregation later."""
    return [
        {
            "name": "Projekt A",
            "icon": "folder-outline",
            "segment_color": (0.13, 0.59, 0.95, 1),
            "time": "12:30",
            "icon_color": (1, 1, 1, 1),
        },
        {
            "name": "Dojazdy",
            "icon": "car-sports",
            "segment_color": (0.85, 0.19, 0.19, 1),
            "time": "08:15",
            "icon_color": (0.85, 0.19, 0.19, 1),
        },
        {
            "name": "Inne",
            "icon": "star-outline",
            "segment_color": (0.6, 0.4, 0.8, 1),
            "time": "04:00",
            "icon_color": (0.6, 0.4, 0.8, 1),
        },
    ]


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

    def set_period(self, label: str):
        self.selected_period = label

    def set_statistics_rows(self, rows):
        """
        Fill the details panel from a list of dicts with keys:
        name, icon, segment_color (rgba tuple), time;
        optional: icon_color (rgba), defaults to white.
        """
        cont = self.ids.stats_rows_container
        cont.clear_widgets()
        for r in rows:
            row = build_statistics_detail_row(
                r["name"],
                r["icon"],
                r["segment_color"],
                r["time"],
                r.get("icon_color", (1, 1, 1, 1)),
            )
            cont.add_widget(row)
        self._layout_stats_card()

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
        row_heights = sum(c.height for c in cont.children)
        row_gaps = row_spacing * max(0, len(cont.children) - 1)
        card.height = pt + pb + header_h + gap + row_heights + row_gaps

    def refresh_statistics(self):
        pie, rows = statistics_from_sessions(self.selected_period)
        if not pie:
            set_screen_statistics(self, [], [])
            return
        set_screen_statistics(self, pie, rows)

    def on_selected_period(self, _instance, value):
        self.refresh_statistics()

    def on_enter(self):
        self.refresh_statistics()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(selected_period=self.on_selected_period)
