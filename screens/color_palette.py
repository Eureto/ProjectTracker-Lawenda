"""Lightweight swatch-grid color picker.

A drop-in replacement for `MDColorPicker` that shows a curated 5-column grid
of circular swatches grouped by mood: pastels, warm monochrome, cool
analogous, contrast pop, and neutral / dark.

Open via :func:`open_palette_picker(default_color, on_pick)` — ``on_pick`` is
called with an ``[r, g, b, a]`` list when the user taps a swatch, and the
dialog auto-dismisses.
"""

from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel


# Five 10-color palettes. Laid out so each palette occupies one column of the
# 5-column grid — i.e. column 0 is Pastele, column 1 is Ciepłe, etc.
PALETTES = (
    ("Pastele", (
        "#F3E8FF", "#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3",
        "#E0E7FF", "#F0FDF4", "#FFF1F2", "#EFF6FF", "#FFF7ED",
    )),
    ("Ciepłe", (
        "#EC4899", "#F43F5E", "#D946EF", "#A855F7", "#FF007F",
        "#FF66B2", "#E0115F", "#FF1493", "#C71585", "#FF69B4",
    )),
    ("Chłodne", (
        "#3B82F6", "#06B6D4", "#14B8A6", "#0EA5E9", "#6366F1",
        "#01579B", "#00838F", "#00695C", "#1D4ED8", "#2563EB",
    )),
    ("Kontrast", (
        "#22C55E", "#EAB308", "#F97316", "#84CC16", "#10B981",
        "#FF5722", "#FFC107", "#CDDC39", "#FF9800", "#A3E635",
    )),
    ("Neutralne", (
        "#FFFFFF", "#F9FAFB", "#E5E7EB", "#111827", "#1F2937",
        "#0F172A", "#334155", "#4B5563", "#9CA3AF", "#1E1B4B",
    )),
)


class PaletteSwatchButton(ButtonBehavior, Widget):
    """A tappable circular color swatch with a ring when selected."""

    swatch_color = ListProperty([1, 1, 1, 1])
    selected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(40), dp(40))
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            swatch_color=self._redraw,
            selected=self._redraw,
        )

    def _redraw(self, *_args):
        self.canvas.clear()
        if self.width < 1 or self.height < 1:
            return
        r = min(self.width, self.height) / 2.0
        cx = self.center_x
        cy = self.center_y
        with self.canvas:
            if self.selected:
                Color(1, 1, 1, 1)
                Line(circle=(cx, cy, r + dp(3)), width=dp(2))
            Color(*self.swatch_color)
            Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))
            # Hairline ring for very-light swatches so they don't vanish on
            # the white dialog background.
            avg = sum(self.swatch_color[:3]) / 3.0
            if avg > 0.88:
                Color(0, 0, 0, 0.18)
                Line(circle=(cx, cy, r - dp(0.6)), width=dp(1.0))


def _colors_match(a, b):
    return all(abs(float(a[i]) - float(b[i])) < 0.01 for i in range(3))


def open_palette_picker(default_color, on_pick, title="Wybierz kolor"):
    """Show the swatch grid and call ``on_pick([r, g, b, a])`` on selection.

    ``default_color`` highlights the matching swatch (if any) so the user
    can see which color is currently in use.
    """
    default_rgba = list(default_color) if default_color else [1, 1, 1, 1]
    if len(default_rgba) == 3:
        default_rgba.append(1.0)

    content = MDBoxLayout(
        orientation="vertical",
        size_hint_y=None,
        spacing=dp(10),
        padding=(dp(4), dp(4), dp(4), dp(4)),
    )
    content.bind(minimum_height=content.setter("height"))

    swatch_size = dp(40)
    grid_spacing = dp(12)
    grid_padding = dp(4)
    grid_cols = len(PALETTES)
    grid_width = (
        grid_cols * swatch_size
        + max(0, grid_cols - 1) * grid_spacing
        + 2 * grid_padding
    )

    grid = MDGridLayout(
        cols=grid_cols,
        spacing=grid_spacing,
        size_hint=(None, None),
        width=grid_width,
        padding=(grid_padding, grid_padding, grid_padding, grid_padding),
    )
    grid.bind(minimum_height=grid.setter("height"))

    grid_wrapper = AnchorLayout(
        anchor_x="center",
        anchor_y="top",
        size_hint_y=None,
    )
    grid.bind(height=grid_wrapper.setter("height"))

    dialog = MDDialog(
        title=title,
        type="custom",
        content_cls=content,
        size_hint_x=0.9,
    )

    title_lbl = dialog.ids.get("title") if hasattr(dialog, "ids") else None
    if title_lbl is not None:
        title_lbl.halign = "center"

    swatches = []

    def select(btn, color, *_args):
        for sw in swatches:
            sw.selected = (sw is btn)
        rgba = list(color)
        if len(rgba) == 3:
            rgba.append(1.0)
        dialog.dismiss()
        on_pick(rgba)

    max_rows = max(len(hexes) for _name, hexes in PALETTES)
    for row in range(max_rows):
        for _name, hexes in PALETTES:
            if row < len(hexes):
                color = list(get_color_from_hex(hexes[row]))
                btn = PaletteSwatchButton(swatch_color=color)
                btn.selected = _colors_match(default_rgba, color)
                btn.bind(on_release=lambda b, c=color: select(b, c))
                grid.add_widget(btn)
                swatches.append(btn)
            else:
                grid.add_widget(
                    Widget(size_hint=(None, None), size=(swatch_size, swatch_size))
                )

    hint = MDLabel(
        text="Dotknij koła, aby wybrać kolor.",
        font_size="12sp",
        theme_text_color="Hint",
        size_hint_y=None,
        height=dp(20),
        halign="center",
    )
    hint.bind(size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size))

    grid_wrapper.add_widget(grid)
    content.add_widget(grid_wrapper)
    content.add_widget(hint)

    cancel = MDFlatButton(text="ANULUJ")
    cancel.bind(on_release=lambda *_a: dialog.dismiss())
    dialog.buttons = [cancel]

    dialog.open()
    return dialog
