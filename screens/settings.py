from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton
from kivymd.app import MDApp

from screens.color_picker import ColorPickerPopup, hex_to_rgba, contrast_text_color


_THEME_SECTIONS = [
    ("Ogólne", [
        ("theme_bg", "Tło aplikacji"),
    ]),
    ("Navigation Bar", [
        ("nav_bg", "Tło"),
        ("nav_icon", "Ikony i tekst"),
        ("nav_mid_btn_bg", "Przycisk środkowy"),
    ]),
    ("Sesje", [
        ("theme_session_bg", "Tło sesji"),
        ("theme_session_header", "Nagłówek sesji"),
    ]),
]


class ThemeColorRow(BoxLayout):
    theme_key = StringProperty("")
    display_label = StringProperty("")
    hex_color = StringProperty("#000000")

    def __init__(self, theme_key, display_label, hex_color, **kwargs):
        self.theme_key = theme_key
        self.display_label = display_label
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(52))
        kwargs.setdefault("spacing", dp(12))
        super().__init__(**kwargs)
        self.hex_color = hex_color
        self.bind(pos=self._redraw_swatch, size=self._redraw_swatch)
        Clock.schedule_once(lambda _dt: self._redraw_swatch(), 0)

    def on_hex_color(self, *args):
        self._redraw_swatch()

    def _redraw_swatch(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*hex_to_rgba(self.hex_color))
            RoundedRectangle(
                pos=(self.x + self.width - dp(44), self.y + dp(6)),
                size=(dp(36), dp(36)),
                radius=[dp(8)],
            )
            Color(1, 1, 1, 0.3)
            Line(
                rounded_rectangle=(
                    self.x + self.width - dp(44),
                    self.y + dp(6),
                    dp(36), dp(36), dp(8),
                ),
                width=dp(1.5),
            )

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return
        app = MDApp.get_running_app()
        popup = ColorPickerPopup(current_color=self.hex_color)
        popup.bind(on_dismiss=lambda p: self._on_picker_closed(p))
        popup.open()

    def _on_picker_closed(self, popup):
        if popup.picked_color:
            self.hex_color = popup.picked_color
            app = MDApp.get_running_app()
            app.set_theme_color(self.theme_key, popup.picked_color)


class SettingsScreen(MDScreen):
    def on_enter(self):
        Clock.schedule_once(lambda _dt: self._populate_colors(), 0)

    def _populate_colors(self):
        container = self.ids.get("theme_colors_container")
        if container is None:
            return
        container.clear_widgets()
        app = MDApp.get_running_app()
        txt_color = contrast_text_color(app.theme_bg)
        for idx, (section_name, items) in enumerate(_THEME_SECTIONS):
            header = Label(
                text=section_name,
                font_size=dp(16),
                bold=True,
                color=txt_color,
                size_hint_y=None,
                height=dp(32),
                padding=(dp(4), 0),
            )
            container.add_widget(header)
            for key, label_text in items:
                hex_val = getattr(app, key, "#000000")
                row = ThemeColorRow(
                    theme_key=key,
                    display_label=label_text,
                    hex_color=hex_val,
                )
                label = Label(
                    text=label_text,
                    font_size=dp(15),
                    color=txt_color,
                    size_hint_x=1,
                )
                row.add_widget(label)
                container.add_widget(row)
            if idx < len(_THEME_SECTIONS) - 1:
                sep = Widget(size_hint_y=None, height=dp(1))
                with sep.canvas:
                    Color(*hex_to_rgba(app.theme_bg, 0.4))
                    rect = Rectangle(pos=sep.pos, size=sep.size)
                def update_sep(w, _, r=rect):
                    r.pos = (w.x + dp(12), w.y)
                    r.size = (w.width - dp(24), w.height)
                sep.bind(pos=update_sep, size=update_sep)
                Clock.schedule_once(lambda dt: update_sep(sep, None), 0)
                container.add_widget(sep)

    def reset_theme(self):
        app = MDApp.get_running_app()
        app.reset_theme_to_defaults()
        self._populate_colors()
