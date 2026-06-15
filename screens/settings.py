from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.graphics import Color, RoundedRectangle
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton
from kivymd.app import MDApp

from screens.color_picker import ColorPickerPopup, hex_to_rgba


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
        self.hex_color = hex_color
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(52))
        kwargs.setdefault("spacing", dp(12))
        super().__init__(**kwargs)

    def on_hex_color(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(*hex_to_rgba(self.hex_color))
            RoundedRectangle(
                pos=(self.width - dp(44), self.y + dp(6)),
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
        for key in _THEME_LABELS:
            hex_val = getattr(app, key, "#000000")
            row = ThemeColorRow(theme_key=key, hex_color=hex_val)
            label = MDLabel(
                text=row.display_label,
                font_size=dp(15),
                halign="left",
                valign="middle",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.9),
                size_hint_x=1,
            )
            row.add_widget(label)
            container.add_widget(row)

    def reset_theme(self):
        app = MDApp.get_running_app()
        app.reset_theme_to_defaults()
        self._populate_colors()
