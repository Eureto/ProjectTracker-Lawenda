from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton
from kivymd.app import MDApp

from screens.color_picker import ColorPickerPopup, hex_to_rgba


def _contrast_text_color(bg_hex):
    r, g, b, _ = hex_to_rgba(bg_hex)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0.1, 0.1, 0.1, 1) if lum > 0.5 else (1, 1, 1, 1)


_THEME_LABELS = {
    "theme_bg": "Tło aplikacji",
    "theme_card_bg": "Tło kart",
    "theme_session_bg": "Tło sesji",
    "theme_session_header": "Nagłówek sesji",
    "theme_text_dark": "Ciemny tekst",
}


class ThemeColorRow(BoxLayout):
    theme_key = StringProperty("")
    display_label = StringProperty("")
    hex_color = StringProperty("#000000")

    def __init__(self, theme_key, hex_color, **kwargs):
        self.theme_key = theme_key
        self.display_label = _THEME_LABELS.get(theme_key, theme_key)
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
        txt_color = _contrast_text_color(app.theme_bg)
        for key in _THEME_LABELS:
            hex_val = getattr(app, key, "#000000")
            row = ThemeColorRow(theme_key=key, hex_color=hex_val)
            label = Label(
                text=_THEME_LABELS[key],
                font_size=dp(15),
                color=txt_color,
                size_hint_x=1,
            )
            row.add_widget(label)
            container.add_widget(row)

    def reset_theme(self):
        app = MDApp.get_running_app()
        app.reset_theme_to_defaults()
        self._populate_colors()
