# ---------------------------------------------------------------------------
# WYBÓR KOLORU PROJEKTU – paleta barw
# ---------------------------------------------------------------------------
# Gdy użytkownik kliknie "Kolor" w formularzu projektu, otwiera się okno
# z pięcioma kolumnami kolorów: pastelowe, ciepłe, chłodne, kontrastowe
# i neutralne. Każdy kolor to kółko – kliknięcie wybiera go.
# ---------------------------------------------------------------------------

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


# Pięć palet kolorów, każda w osobnej kolumnie.
# Nazwy: Pastele, Ciepłe, Chłodne, Kontrast, Neutralne.
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


# ---------------------------------------------------------------------------
# PRZYCISK Z KOLOROWYM KÓŁKIEM
# ---------------------------------------------------------------------------
# Klikalne kolorowe kółko – wybór koloru projektu.
class PaletteSwatchButton(ButtonBehavior, Widget):

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
                # Biała obwódka wokół wybranego koloru
                Color(1, 1, 1, 1)
                Line(circle=(cx, cy, r + dp(3)), width=dp(2))
            Color(*self.swatch_color)
            Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))
            # Dla bardzo jasnych kolorów dodaj cienką szarą obwódkę
            # żeby nie zlewały się z białym tłem okna
            avg = sum(self.swatch_color[:3]) / 3.0
            if avg > 0.88:
                Color(0, 0, 0, 0.18)
                Line(circle=(cx, cy, r - dp(0.6)), width=dp(1.0))


def _colors_match(a, b):
    # Porównuje dwa kolory i zwraca Prawdę jeśli są praktycznie identyczne.
    # Różnica mniejsza niż 1% jest uznawana za nieistotną – to zabezpieczenie
    # przed błędami zaokrągleń przy przeliczaniu kolorów między formatami.
    # Używane do automatycznego podświetlenia aktualnie wybranego koloru
    # w palecie, żeby użytkownik od razu widział który kolor jest zaznaczony.
    return all(abs(float(a[i]) - float(b[i])) < 0.01 for i in range(3))


# ---------------------------------------------------------------------------
# GŁÓWNA FUNKCJA – otwiera okno wyboru koloru
# ---------------------------------------------------------------------------
# Główna funkcja do otwierania okna wyboru koloru.
# "default_color" – kolor który jest już wybrany (podświetli się na liście).
# "on_pick" – funkcja, która zostanie wywołana po kliknięciu koloru.
#   Dostaje kolor w formacie [r, g, b, a] (wartości 0-1).
# "title" – tytuł okna (domyślnie "Wybierz kolor").
def open_palette_picker(default_color, on_pick, title="Wybierz kolor"):
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

    # Wypełnij siatkę kolorami – wiersz po wierszu
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