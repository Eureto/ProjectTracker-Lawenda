# ---------------------------------------------------------------------------
# WYBÓR KOLORU PROJEKTU – paleta barw
# ---------------------------------------------------------------------------
# Gdy użytkownik kliknie "Kolor" w formularzu projektu, otwiera się okno
# z pięcioma kolumnami kolorów: pastelowe, ciepłe, chłodne, kontrastowe
# i neutralne. Każdy kolor to kółko – kliknięcie wybiera go.
# ---------------------------------------------------------------------------

# Poniższe linie to "przyprowadzenie" narzędzi, których potrzebujemy.
# To tak jakbyśmy przed gotowaniem wyciągali z szafki garnki i patelnie.

# Kolor, koło i linia – czyli jak rysować kolorowe kółka na ekranie.
from kivy.graphics import Color, Ellipse, Line
# "dp" to jednostka rozmiaru – dzięki niej kółka wyglądają tak samo
# na małych i dużych ekranach.
from kivy.metrics import dp
# BooleanProperty i ListProperty to specjalne "właściwości" – gdy zmienią
# wartość, aplikacja automatycznie wie, że trzeba odświeżyć wygląd.
from kivy.properties import BooleanProperty, ListProperty
# Układ, który trzyma element na środku (jak ramka do obrazka).
from kivy.uix.anchorlayout import AnchorLayout
# Dzięki temu kolorowe kółko może być klikalne (jak przycisk).
from kivy.uix.behaviors import ButtonBehavior
# Widget to podstawowy budulec – wszystko co widzisz na ekranie to Widget.
from kivy.uix.widget import Widget
# Zamienia zapis koloru z "#FF0088" na liczby (czerwony, zielony, niebieski).
from kivy.utils import get_color_from_hex
# Pudełko układające elementy jeden pod drugim (pionowo) lub obok (poziomo).
from kivymd.uix.boxlayout import MDBoxLayout
# Płaski przycisk bez tła (tylko napis) – używamy go do "ANULUJ".
from kivymd.uix.button import MDFlatButton
# Okno dialogowe – wyskakujące okienko z treścią i przyciskami.
from kivymd.uix.dialog import MDDialog
# Siatka – układa kolorowe kółka w rzędy i kolumny (jak kratka w zeszycie).
from kivymd.uix.gridlayout import MDGridLayout
# Etykieta tekstowa – wyświetla napis na ekranie.
from kivymd.uix.label import MDLabel


# Pięć palet kolorów, każda w osobnej kolumnie.
# Nazwy: Pastele, Ciepłe, Chłodne, Kontrast, Neutralne.
# Każdy kolor zapisany jest jako kod zaczynający się od "#" – tak komputery
# mówią o kolorach. Np. #FF0000 to czerwony, #0000FF to niebieski.
PALETTES = (
    # Paleta pierwsza: pastele – delikatne, jasne kolory, jak pastelowe kredki.
    ("Pastele", (
        "#F3E8FF", "#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3",
        "#E0E7FF", "#F0FDF4", "#FFF1F2", "#EFF6FF", "#FFF7ED",
    )),
    # Paleta druga: ciepłe – intensywne róże, czerwienie i purpury.
    ("Ciepłe", (
        "#EC4899", "#F43F5E", "#D946EF", "#A855F7", "#FF007F",
        "#FF66B2", "#E0115F", "#FF1493", "#C71585", "#FF69B4",
    )),
    # Paleta trzecia: chłodne – błękity, turkusy i granaty.
    ("Chłodne", (
        "#3B82F6", "#06B6D4", "#14B8A6", "#0EA5E9", "#6366F1",
        "#01579B", "#00838F", "#00695C", "#1D4ED8", "#2563EB",
    )),
    # Paleta czwarta: kontrastowe – jaskrawe, rzucające się w oczy kolory.
    ("Kontrast", (
        "#22C55E", "#EAB308", "#F97316", "#84CC16", "#10B981",
        "#FF5722", "#FFC107", "#CDDC39", "#FF9800", "#A3E635",
    )),
    # Paleta piąta: neutralne – biele, szarości i czernie, od najjaśniejszego
    # do najciemniejszego. Przydają się jako tło lub subtelny akcent.
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

    # Przechowuje kolor tego kółka (czerwony, zielony, niebieski, przezroczystość).
    # Gdy kolor się zmienia – kółko samo się przerysowuje.
    swatch_color = ListProperty([1, 1, 1, 1])
    # Czy to kółko jest aktualnie wybrane (zakreślone obwódką).
    selected = BooleanProperty(False)

    # Przygotowuje przycisk z kolorowym kółkiem.
    # Ustawia jego rozmiar (40x40 punktów) i podłącza funkcję,
    # która odrysowuje kółko przy każdej zmianie położenia,
    # rozmiaru, koloru lub stanu zaznaczenia.
    def __init__(self, **kwargs):
        # Wywołuje przygotowanie odziedziczone po ButtonBehavior i Widget.
        super().__init__(**kwargs)
        # Kółko nie ma się rozciągać – ma mieć stały rozmiar.
        self.size_hint = (None, None)
        # Ustawia rozmiar kółka na 40 na 40 punktów (wielkość monety).
        self.size = (dp(40), dp(40))
        # Podłącza przerysowywanie: gdy zmieni się położenie, rozmiar,
        # kolor albo zaznaczenie – kółko zostanie narysowane od nowa.
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            swatch_color=self._redraw,
            selected=self._redraw,
        )

    # Rysuje kolorowe kółko od nowa przy każdej zmianie.
    # Dla wybranego koloru dodaje białą obwódkę wokół.
    # Dla bardzo jasnych kolorów dodaje cienką szarą obwódkę,
    # żeby kółko nie zlewało się z białym tłem okna.
    def _redraw(self, *_args):
        # Czyści poprzedni rysunek – zaczynamy od zera.
        self.canvas.clear()
        # Jeśli kółko jest za małe (np. jeszcze się nie pojawiło) – pomiń.
        if self.width < 1 or self.height < 1:
            return
        # Promień kółka: połowa mniejszego boku (średnica / 2).
        r = min(self.width, self.height) / 2.0
        # Środek kółka (po X i po Y).
        cx = self.center_x
        cy = self.center_y
        # Otwiera blok rysowania – wszystko w środku zostanie narysowane na ekranie.
        with self.canvas:
            # Jeśli kółko jest zaznaczone (wybrane) – narysuj białą obwódkę.
            if self.selected:
                # Ustaw kolor na biały (1,1,1) w pełni widoczny.
                Color(1, 1, 1, 1)
                # Rysuj okrąg (białą linię) wokół kółka, 3 punkty od niego.
                Line(circle=(cx, cy, r + dp(3)), width=dp(2))
            # Ustaw kolor wypełnienia kółka na ten, który wybrał użytkownik.
            Color(*self.swatch_color)
            # Rysuj wypełnione koło na środku.
            Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))
            # Dla bardzo jasnych kolorów dodaj cienką szarą obwódkę,
            # żeby nie zlewały się z białym tłem okna.
            # Oblicz średnią jasność koloru (0 = czarny, 1 = biały).
            avg = sum(self.swatch_color[:3]) / 3.0
            # Jeśli kolor jest bardzo jasny (powyżej 88% bieli)...
            if avg > 0.88:
                # ...narysuj cienką, półprzezroczystą szarą obwódkę.
                Color(0, 0, 0, 0.18)
                Line(circle=(cx, cy, r - dp(0.6)), width=dp(1.0))


# Porównuje dwa kolory i mówi, czy są praktycznie identyczne.
# Różnica mniejsza niż 1% jest uznawana za nieistotną.
# To zabezpieczenie przed błędami zaokrągleń przy przeliczaniu kolorów
# między różnymi formatami (szesnastkowym #FF0088 a zwykłymi liczbami).
# Używane do automatycznego podświetlenia aktualnie wybranego koloru
# w palecie – żeby użytkownik od razu widział, który kolor jest zaznaczony.
def _colors_match(a, b):
    # Sprawdza dla każdego z trzech składników (czerwony, zielony, niebieski),
    # czy różnica między kolorem a a kolorem b jest mniejsza niż 0.01 (czyli 1%).
    # all() zwraca Prawdę tylko jeśli wszystkie trzy składniki się zgadzają.
    return all(abs(float(a[i]) - float(b[i])) < 0.01 for i in range(3))


# ---------------------------------------------------------------------------
# GŁÓWNA FUNKCJA – otwiera okno wyboru koloru
# ---------------------------------------------------------------------------
# To jest najważniejsza część tego pliku. Gdy użytkownik chce zmienić kolor
# projektu, aplikacja wywołuje tę funkcję, a ta pokazuje okno z kolorami.
#
# "default_color" – kolor, który jest już teraz wybrany w projekcie.
#                   Zostanie podświetlony w palecie, żeby użytkownik widział,
#                   jaki kolor ma obecnie projekt.
# "on_pick" – funkcja, która zostanie wywołana po kliknięciu koloru.
#             To taki "callback" – aplikacja mówi: "jak wybierzesz kolor,
#             powiedz mi, a ja go zapamiętam". Funkcja dostaje kolor
#             w formacie [czerwony, zielony, niebieski, przezroczystość]
#             gdzie każda wartość to liczba od 0 do 1.
# "title" – tytuł okna (domyślnie "Wybierz kolor").
def open_palette_picker(default_color, on_pick, title="Wybierz kolor"):
    # Przygotuj kolor domyślny (ten, który jest teraz wybrany).
    # Jeśli nie ma żadnego – użyj białego.
    default_rgba = list(default_color) if default_color else [1, 1, 1, 1]
    # Jeśli kolor ma tylko 3 składniki (R,G,B) – dodaj czwarty:
    # przezroczystość (1.0 = całkowicie widoczny).
    if len(default_rgba) == 3:
        default_rgba.append(1.0)

    # Pudełko na zawartość okna – wszystko będzie ułożone pionowo,
    # jedno pod drugim: siatka kolorów, potem podpowiedź.
    content = MDBoxLayout(
        # Pionowe ułożenie: elementy jeden pod drugim.
        orientation="vertical",
        # Pudełko ma mieć wysokość dopasowaną do zawartości
        # (nie może się rozciągać w nieskończoność).
        size_hint_y=None,
        # Odstęp między elementami: 10 punktów przerwy.
        spacing=dp(10),
        # Wewnętrzny margines: 4 punkty ze wszystkich stron.
        padding=(dp(4), dp(4), dp(4), dp(4)),
    )
    # Gdy zawartość pudełka zmieni wysokość (np. dodamy kółka),
    # automatycznie dopasuj wysokość pudełka.
    content.bind(minimum_height=content.setter("height"))

    # Wielkość jednego kolorowego kółka (w punktach ekranu).
    swatch_size = dp(40)
    # Odstęp między kółkami.
    grid_spacing = dp(12)
    # Wewnętrzny margines siatki.
    grid_padding = dp(4)
    # Liczba kolumn = tyle, ile mamy palet (5).
    grid_cols = len(PALETTES)
    # Oblicz całkowitą szerokość siatki:
    #   szerokość wszystkich kółek +
    #   odstępy między nimi +
    #   marginesy z lewej i prawej.
    grid_width = (
        grid_cols * swatch_size
        + max(0, grid_cols - 1) * grid_spacing
        + 2 * grid_padding
    )

    # Siatka, która przechowa kolorowe kółka w kolumnach.
    grid = MDGridLayout(
        # Liczba kolumn (5 – po jednej na każdą paletę).
        cols=grid_cols,
        # Odstęp między kółkami.
        spacing=grid_spacing,
        # Siatka nie ma się rozciągać – ma mieć obliczoną szerokość.
        size_hint=(None, None),
        # Ustaw obliczoną szerokość siatki.
        width=grid_width,
        # Margines wewnątrz siatki.
        padding=(grid_padding, grid_padding, grid_padding, grid_padding),
    )
    # Gdy wysokość siatki się zmieni (po dodaniu kółek) – dopasuj pudełko.
    grid.bind(minimum_height=grid.setter("height"))

    # Opakowacz do siatki – trzyma ją na środku w poziomie.
    grid_wrapper = AnchorLayout(
        # Wyśrodkuj w poziomie.
        anchor_x="center",
        # Przyklej do góry.
        anchor_y="top",
        # Wysokość dopasowana do zawartości.
        size_hint_y=None,
    )
    # Gdy siatka zmieni wysokość – opakowacz też.
    grid.bind(height=grid_wrapper.setter("height"))

    # Okno dialogowe – wyskakujące okienko.
    dialog = MDDialog(
        # Tytuł okna (np. "Wybierz kolor").
        title=title,
        # Typ "custom" – sami przygotowujemy zawartość.
        type="custom",
        # Włóż przygotowane wcześniej pudełko z zawartością.
        content_cls=content,
        # Szerokość okna: 90% szerokości ekranu (0.9 = 90%).
        size_hint_x=0.9,
    )

    # Znajdź tytuł okna (etykietę z napisem).
    title_lbl = dialog.ids.get("title") if hasattr(dialog, "ids") else None
    # Jeśli udało się znaleźć tytuł – wyśrodkuj go.
    if title_lbl is not None:
        title_lbl.halign = "center"

    # Lista, w której zapamiętamy wszystkie kolorowe kółka.
    # Będzie potrzebna, żeby odznaczyć poprzednio wybrane
    # gdy użytkownik kliknie w inne.
    swatches = []

    # Gdy użytkownik kliknie w kolorowe kółko – ta funkcja się uruchomi.
    # Zaznacza kliknięte kółko, odznacza inne, zamyka okno i przekazuje
    # wybrany kolor do funkcji "on_pick", która zapamięta go dla projektu.
    def select(btn, color, *_args):
        # Przejdź przez wszystkie kółka i zaznacz tylko to kliknięte.
        for sw in swatches:
            sw.selected = (sw is btn)
        # Przekonwertuj kolor z palety na listę (R, G, B).
        rgba = list(color)
        # Jeśli brak przezroczystości – dodaj (w pełni widoczny).
        if len(rgba) == 3:
            rgba.append(1.0)
        # Zamknij okno wyboru koloru.
        dialog.dismiss()
        # Wywołaj funkcję "on_pick" z wybranym kolorem.
        # To właśnie ta funkcja zapamięta kolor dla projektu.
        on_pick(rgba)

    # Wypełnij siatkę kolorami – wiersz po wierszu.
    # Najpierw policz, ile wierszy potrzeba (najdłuższa paleta ma 10 kolorów).
    max_rows = max(len(hexes) for _name, hexes in PALETTES)
    # Dla każdego wiersza...
    for row in range(max_rows):
        # ...i dla każdej palety (kolumny)...
        for _name, hexes in PALETTES:
            # Jeśli w tym wierszu jest jeszcze kolor w tej palecie...
            if row < len(hexes):
                # ...przekonwertuj kod koloru (#FF0088) na liczby (R,G,B).
                color = list(get_color_from_hex(hexes[row]))
                # Stwórz klikalne kółko w tym kolorze.
                btn = PaletteSwatchButton(swatch_color=color)
                # Jeśli ten kolor jest tym, który projekt ma teraz – zaznacz go.
                btn.selected = _colors_match(default_rgba, color)
                # Gdy użytkownik kliknie to kółko – wywołaj funkcję select.
                btn.bind(on_release=lambda b, c=color: select(b, c))
                # Dodaj kółko do siatki.
                grid.add_widget(btn)
                # Zapamiętaj kółko w liście (do odznaczania).
                swatches.append(btn)
            else:
                # Jeśli w tym wierszu brakuje koloru w tej kolumnie –
                # dodaj pusty, niewidoczny kwadracik o takim samym rozmiarze.
                # To potrzebne, żeby siatka miała równy układ (nie brakowało
                # komórek w wierszach, gdzie jedna paleta jest krótsza).
                grid.add_widget(
                    Widget(size_hint=(None, None), size=(swatch_size, swatch_size))
                )

    # Podpowiedź na dole okna – krótki tekst dla użytkownika.
    hint = MDLabel(
        # Tekst przypominający, co zrobić: dotknij koła, aby wybrać kolor.
        text="Dotknij koła, aby wybrać kolor.",
        # Rozmiar czcionki: 12 punktów skalowalnych.
        font_size="12sp",
        # Styl kolorystyczny: "Hint" – delikatny, wyblakły kolor.
        theme_text_color="Hint",
        # Wysokość dopasowana do tekstu.
        size_hint_y=None,
        # Wysokość etykiety: 20 punktów.
        height=dp(20),
        # Tekst wyśrodkowany w poziomie.
        halign="center",
    )
    # Gdy etykieta zmieni rozmiar – ustaw obszar tekstu na jej rozmiar,
    # żeby tekst ładnie się zawijał (gdyby był za długi).
    hint.bind(size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size))

    # Włóż siatkę (opakowaną w AnchorLayout) do pudełka z zawartością.
    grid_wrapper.add_widget(grid)
    content.add_widget(grid_wrapper)
    # Włóż podpowiedź do pudełka (pod siatkę).
    content.add_widget(hint)

    # Przycisk "ANULUJ" – płaski przycisk tylko z napisem.
    cancel = MDFlatButton(text="ANULUJ")
    # Po kliknięciu "ANULUJ" – zamknij okno bez wybierania koloru.
    cancel.bind(on_release=lambda *_a: dialog.dismiss())
    # Umieść przycisk "ANULUJ" na dole okna.
    dialog.buttons = [cancel]

    # Pokaż okno wyboru koloru użytkownikowi.
    dialog.open()
    # Zwróć okno (na wypadek, gdyby ktoś chciał je później zamknąć z kodu).
    return dialog
