import math
import colorsys
import os
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty, ListProperty, BooleanProperty
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle, Ellipse, Line, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.core.window import Window
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.slider import MDSlider
from kivymd.uix.textfield import MDTextField
from kivymd.app import MDApp


def hex_to_rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r / 255, g / 255, b / 255, alpha)


def rgb_to_hex(r, g, b):
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def hex_to_hsv(hex_color):
    r, g, b, _ = hex_to_rgba(hex_color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h, s, v


def hsv_to_hex(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return rgb_to_hex(r, g, b)


def contrast_text_color(bg_hex):
    r, g, b, _ = hex_to_rgba(bg_hex)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0.1, 0.1, 0.1, 1) if lum > 0.5 else (1, 1, 1, 1)


# Zwraca kolor nieco jaśniejszy od podanego tła (mieszanie w stronę bieli).
# Używane do "pudełek" sekcji, żeby odcinały się delikatnie od tła ekranu.
def lighten_color(bg_hex, amount=0.12):
    try:
        r, g, b, _ = hex_to_rgba(bg_hex)
    except Exception:
        return (1, 1, 1, 0.08)
    r = r + (1.0 - r) * amount
    g = g + (1.0 - g) * amount
    b = b + (1.0 - b) * amount
    return (r, g, b, 1)


_WHEEL_SIZE = dp(240)


class HsvWheel(Widget):
    color_hex = StringProperty("#ffffff")
    _hue = NumericProperty(0.0)
    _sat = NumericProperty(0.0)
    _val = NumericProperty(1.0)
    _dragging = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._texture = None
        self._generate_texture()
        self.bind(size=self._generate_texture)
        self.bind(pos=self.update_canvas, size=self.update_canvas,
                  _hue=self.update_canvas, _sat=self.update_canvas)

    def _generate_texture(self, *args):
        s = int(min(self.width, self.height) or _WHEEL_SIZE)
        if s < 8:
            return
        cx = cy = s / 2
        buf = bytearray(s * s * 4)
        for y in range(s):
            for x in range(s):
                dx = x - cx
                dy = y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                idx = (y * s + x) * 4
                if dist > cx:
                    buf[idx] = buf[idx + 1] = buf[idx + 2] = 0
                    buf[idx + 3] = 0
                else:
                    angle = (math.atan2(dy, dx) + math.pi) / (2 * math.pi)
                    sat = dist / cx
                    r, g, b = colorsys.hsv_to_rgb(angle, sat, self._val)
                    buf[idx] = int(r * 255)
                    buf[idx + 1] = int(g * 255)
                    buf[idx + 2] = int(b * 255)
                    buf[idx + 3] = 255
        tex = Texture.create(size=(s, s), colorfmt="rgba")
        tex.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
        self._texture = tex
        self.update_canvas()

    def set_val(self, val):
        self._val = val
        self._generate_texture()

    def update_canvas(self, *args):
        self.canvas.clear()
        if not self._texture:
            return
        with self.canvas:
            Color(1, 1, 1, 1)
            s = min(self.width, self.height)
            x = self.x + (self.width - s) / 2
            y = self.y + (self.height - s) / 2
            Rectangle(texture=self._texture, pos=(x, y), size=(s, s))
            Color(1, 1, 1, 1)
            cx = x + s / 2
            cy = y + s / 2
            angle = self._hue * 2 * math.pi - math.pi
            rad = self._sat * s / 2
            ix = cx + rad * math.cos(angle)
            iy = cy + rad * math.sin(angle)
            Color(0, 0, 0, 0.4)
            Ellipse(pos=(ix - dp(7), iy - dp(7)), size=(dp(14), dp(14)))
            Color(*hex_to_rgba(self.color_hex))
            Ellipse(pos=(ix - dp(5), iy - dp(5)), size=(dp(10), dp(10)))

    def _pos_to_color(self, tx, ty):
        s = min(self.width, self.height)
        x = self.x + (self.width - s) / 2
        y = self.y + (self.height - s) / 2
        cx = x + s / 2
        cy = y + s / 2
        dx = tx - cx
        dy = ty - cy
        dist = math.sqrt(dx * dx + dy * dy) / (s / 2)
        if dist > 1:
            return
        angle = math.atan2(dy, dx)
        self._hue = (angle + math.pi) / (2 * math.pi)
        self._sat = min(dist, 1.0)
        self.color_hex = hsv_to_hex(self._hue, self._sat, self._val)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._dragging = True
        self._pos_to_color(touch.x, touch.y)
        return True

    def on_touch_move(self, touch):
        if not self._dragging:
            return False
        self._pos_to_color(touch.x, touch.y)
        return True

    def on_touch_up(self, touch):
        self._dragging = False


class ColorPickerContent(MDBoxLayout):
    color_hex = StringProperty("#3A175C")
    _hue = NumericProperty(0.0)
    _sat = NumericProperty(0.0)
    _val = NumericProperty(1.0)
    _updating = BooleanProperty(False)

    def __init__(self, initial_color="#3A175C", **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("spacing", dp(12))
        kwargs.setdefault("padding", [dp(16), dp(8)])
        super().__init__(**kwargs)
        self.color_hex = initial_color
        h, s, v = hex_to_hsv(initial_color)
        self._hue = h
        self._sat = s
        self._val = v

    def on_color_hex(self, *args):
        if self._updating:
            return
        self._updating = True
        h, s, v = hex_to_hsv(self.color_hex)
        self._hue = h
        self._sat = s
        self._val = v
        wheel = self.ids.get("hsv_wheel")
        if wheel:
            wheel.color_hex = self.color_hex
            wheel._hue = h
            wheel._sat = s
            wheel.set_val(v)
        slider = self.ids.get("brightness_slider")
        if slider:
            slider.value = v
        hex_field = self.ids.get("hex_input")
        if hex_field:
            hex_field.text = self.color_hex.upper()
        self._update_preview()
        self._updating = False

    def _on_wheel_color(self, wheel):
        if self._updating:
            return
        self._updating = True
        self.color_hex = wheel.color_hex
        self._hue = wheel._hue
        self._sat = wheel._sat
        slider = self.ids.get("brightness_slider")
        if slider:
            slider.value = self._val
        hex_field = self.ids.get("hex_input")
        if hex_field:
            hex_field.text = self.color_hex.upper()
        self._update_preview()
        self._updating = False

    def _on_brightness(self, slider, val):
        if self._updating:
            return
        self._updating = True
        self._val = val
        wheel = self.ids.get("hsv_wheel")
        if wheel:
            wheel.set_val(val)
            self.color_hex = wheel.color_hex
        hex_field = self.ids.get("hex_input")
        if hex_field:
            hex_field.text = self.color_hex.upper()
        self._update_preview()
        self._updating = False

    def _on_hex_text(self, text):
        if self._updating:
            return
        t = text.strip().upper()
        if not t.startswith("#"):
            t = "#" + t
        if len(t) == 7 and all(c in "0123456789ABCDEF" for c in t[1:]):
            self._updating = True
            self.color_hex = t
            h, s, v = hex_to_hsv(t)
            self._hue = h
            self._sat = s
            self._val = v
            wheel = self.ids.get("hsv_wheel")
            if wheel:
                wheel.color_hex = t
                wheel._hue = h
                wheel._sat = s
                wheel.set_val(v)
            slider = self.ids.get("brightness_slider")
            if slider:
                slider.value = v
            self._update_preview()
            self._updating = False

    def _update_preview(self):
        prev = self.ids.get("preview_rect")
        if prev:
            prev.canvas.clear()
            with prev.canvas:
                Color(*hex_to_rgba(self.color_hex))
                RoundedRectangle(pos=prev.pos, size=prev.size, radius=[dp(12)])


class ColorPickerPopup(Popup):
    picked_color = StringProperty("")
    _did_pick = BooleanProperty(False)

    def __init__(self, current_color="#3A175C", **kwargs):
        kwargs.setdefault("title", "")
        kwargs.setdefault("size_hint", (0.9, 0.85))
        super().__init__(**kwargs)
        self.content = ColorPickerContent(initial_color=current_color)

        btn_box = MDBoxLayout(
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
            padding=[dp(8), 0],
            adaptive_width=True,
            pos_hint={"center_x": 0.5},
        )
        cancel_btn = MDFlatButton(
            text="ANULUJ",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.8),
            on_release=lambda x: self.dismiss(),
        )
        ok_btn = MDRaisedButton(
            text="OK",
            on_release=self._on_ok,
        )
        btn_box.add_widget(cancel_btn)
        btn_box.add_widget(ok_btn)
        self.content.add_widget(btn_box, index=1)

    def _on_ok(self, *args):
        self._did_pick = True
        self.picked_color = self.content.color_hex
        self.dismiss()

    def on_dismiss(self):
        if not self._did_pick:
            self.picked_color = ""


Builder.load_file(os.path.join(os.path.dirname(__file__), "..", "kv", "color_picker.kv"))
