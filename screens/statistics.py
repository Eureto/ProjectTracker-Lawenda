# ---------------------------------------------------------------------------
# EKRAN STATYSTYK – wykres kołowy i tabela projektów
# ---------------------------------------------------------------------------
# Ten ekran pokazuje użytkownikowi podsumowanie czasu spędzonego nad
# projektami: wykres kołowy (każdy kolor to inny projekt) oraz tabelę
# z nazwami projektów i czasem. Użytkownik może wybrać okres:
# miesiąc, tydzień lub dzień.
# ---------------------------------------------------------------------------

from kivy.clock import Clock
# "Clock" – narzędzie Kivy do planowania zadań na później (np. odświeżenie ekranu za 0.1 sekundy).

from kivy.metrics import dp
# "dp" – jednostka rozmiaru niezależna od gęstości ekranu (piksele, które wyglądają tak samo na każdym ekranie).

from kivy.animation import Animation
# "Animation" – płynne animacje (np. przycisk zmienia kolor przez 0.22 sekundy, a nie skokowo).

from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
# "Properties" – specjalne właściwości Kivy. Gdy zmieniają wartość, aplikacja automatycznie wie,
# że trzeba odświeżyć wygląd. Boolean = prawda/fałsz, List = lista, Numeric = liczba, String = tekst.

from kivy.uix.button import Button
# "Button" – standardowy przycisk Kivy (do klikania).

from kivy.uix.anchorlayout import AnchorLayout
# "AnchorLayout" – układ, który umieszcza dziecko w konkretnym punkcie (np. środek, lewy górny róg).

from kivy.uix.widget import Widget
# "Widget" – podstawowy budulec Kivy. Wszystko co widzisz na ekranie to Widget.

from kivy.graphics import Color, Ellipse, RoundedRectangle
# "Color" – ustawia kolor rysowania. "Ellipse" – rysuje elipsę/koło. "RoundedRectangle" – prostokąt z zaokrąglonymi rogami.

from screens.session_store import (
    format_statistics_total,
    statistics_from_sessions,
)
# Importujemy funkcje do formatowania czasu i obliczania statystyk z pliku session_store.py.

from kivymd.uix.screen import MDScreen
# "MDScreen" – ekran z biblioteki KivyMD (Material Design). To "strona" w aplikacji.

from kivymd.uix.boxlayout import MDBoxLayout
# "MDBoxLayout" – pudełko układające elementy (pionowo lub poziomo) z KivyMD.

from kivymd.uix.label import MDLabel
# "MDLabel" – etykieta tekstowa z KivyMD.

from kivymd.uix.label import MDIcon
# "MDIcon" – ikona z biblioteki Material Design (KivyMD).


# ---------------------------------------------------------------------------
# PRZYCISK WYBORU OKRESU (Miesiąc / Tydzień / Dzień)
# ---------------------------------------------------------------------------
# Każdy przycisk to "pigułka" – po kliknięciu wypełnia się na biało.
# Animacja płynnie przechodzi między stanem wybranym i niewybranym.
# Pigułkowaty przycisk wyboru okresu (Miesiąc/Tydzień/Dzień) – po kliknięciu
# wypełnia się białym tłem z płynną animacją.
class PeriodSegmentButton(Button):
    # "PeriodSegmentButton" – przycisk-wybór okresu (Dzień/Tydzień/Miesiąc)
    # który działa jak "pigułka": kliknięty wypełnia się białym tłem.

    selected = BooleanProperty(False)
    # Czy ten przycisk jest właśnie wybrany (True = tak, False = nie).
    # Tylko jeden przycisk naraz może być wybrany.

    selection_progress = NumericProperty(0)
    # Postęp wypełniania przycisku: 0.0 = przezroczysty (niewybrany),
    # 1.0 = całkowicie biały (wybrany). Animacja płynnie zmienia
    # tę wartość od 0 do 1, co daje efekt "płynnego wypełniania pigułki".

    _anim_duration = 0.22
    # Czas trwania animacji w sekundach. Im dłuższy, tym wolniej
    # przycisk zmienia kolor po kliknięciu.

    def __init__(self, **kwargs):
        # Przygotowuje przycisk wyboru okresu (Dzień/Tydzień/Miesiąc):
        # usuwa domyślne tło, ustawia rozmiar i wysokość, oraz podłącza
        # funkcje które rysują efekt "pigułki" po kliknięciu.
        kwargs.setdefault("background_normal", "")
        # Usuwa domyślne tło przycisku (przezroczysty obrazek zamiast szarego).

        kwargs.setdefault("background_down", "")
        # Usuwa tło przycisku gdy jest kliknięty (żeby nie było domyślnego efektu).

        kwargs.setdefault("background_color", (0, 0, 0, 0))
        # Ustawia kolor tła na przezroczysty (R=0, G=0, B=0, A=0 = niewidoczne).

        kwargs.setdefault("size_hint_y", None)
        # Mówi: "nie rozciągaj się w pionie automatycznie – użyj konkretnej wysokości".

        kwargs.setdefault("height", dp(40))
        # Ustawia wysokość przycisku na 40 pikseli (w jednostkach dp, czyli takie same
        # na każdym ekranie). To wysokość "pigułki" okresu.

        kwargs.setdefault("size_hint_x", 1)
        # Mówi: "rozciągnij się na całą dostępną szerokość".
        # Dzięki temu trzy przyciski obok siebie wypełnią cały pasek.

        super().__init__(**kwargs)
        # Wywołuje standardowy konstruktor Kivy (przygotowuje prawdziwy przycisk).

        self.selection_progress = 1.0 if self.selected else 0.0
        # Ustawia początkowy wygląd przycisku: jeśli jest wybrany, od razu
        # pokazuje białe tło (1.0). Jeśli nie – tło jest przezroczyste (0.0).

        self.bind(
            selected=self._on_selected_change,
            selection_progress=self._apply_visual,
            pos=self._apply_visual,
            size=self._apply_visual,
            state=self._apply_visual,
        )
        # Podłącza funkcje do właściwości:
        #   • selected → _on_selected_change (gdy stan wyboru się zmienia)
        #   • selection_progress → _apply_visual (gdy postęp animacji się zmienia)
        #   • pos/size → _apply_visual (gdy przycisk zmienia położenie/rozmiar)
        #   • state → _apply_visual (gdy przycisk jest wciskany)

        self._apply_visual()
        # Rysuje początkowy wygląd przycisku (od razu, na starcie).

    def _on_selected_change(self, *args):
        # Gdy użytkownik kliknie w przycisk okresu (Dzień/Tydzień/Miesiąc),
        # ten przycisk staje się "wybrany" (selected=True), a inne przestają.
        # Ta funkcja płynnie animuje zmianę: przycisk wypełnia się białym
        # tłem gdy jest wybrany, lub staje się przezroczysty gdy nie.
        # Animacja trwa 0.22 sekundy i wygląda jak "płynne wypełnianie pigułki".
        target = 1.0 if self.selected else 0.0
        # Cel animacji: 1.0 = wypełniony (wybrany), 0.0 = pusty (niewybrany).

        if abs(self.selection_progress - target) < 1e-4:
            return
        # Jeśli przycisk już jest w docelowym stanie (różnica mniejsza niż
        # 0.0001) – nie rób nic. To zapobiega niepotrzebnym animacjom.

        Animation.cancel_all(self, "selection_progress")
        # Zatrzymuje poprzednią animację (jeśli była uruchomiona),
        # żeby nie kolidowała z nową.

        Animation(
            selection_progress=target,
            d=self._anim_duration,
            t="out_cubic",
        ).start(self)
        # Uruchamia płynną animację: zmienia selection_progress z obecnej
        # wartości na docelową (0 lub 1). Trwa _anim_duration sekund.
        # "out_cubic" to rodzaj wygładzenia – zwalnia pod koniec.

    def _apply_visual(self, *args):
        # Rysuje tło przycisku okresu: białe gdy jest wybrany, przezroczyste
        # gdy nie. Dodatkowo przyciemnia kolor tekstu (czcionka staje się
        # ciemniejsza gdy przycisk jest aktywny, jaśniejsza gdy nie).
        # Używa RoundedRectangle do zaokrąglonych rogów.
        p = max(0.0, min(1.0, self.selection_progress))
        # "p" – postęp wypełnienia (0.0 do 1.0). Zabezpieczamy, żeby nie
        # wyleciał poza zakres (np. -0.1 lub 1.5).

        t = 0.15
        # "t" – najjaśniejszy odcień tekstu (gdy przycisk jest niewybrany).
        # Wartość 0.15 oznacza "15% bieli", czyli ciemnoszary tekst.

        self.color = (1 - (1 - t) * p, 1 - (1 - t) * p, 1 - (1 - t) * p, 1)
        # Ustawia kolor tekstu: gdy p=0 (niewybrany) kolor = (t, t, t, 1)
        # czyli ciemnoszary. Gdy p=1 (wybrany) kolor = (1, 1, 1, 1)
        # czyli biały. Wzór (1 - (1-t)*p) daje płynne przejście.

        r = dp(22)
        # Promień zaokrąglenia rogów "pigułki" – 22 piksele na każdym rogu.

        self.canvas.before.clear()
        # Czyści stare rysunki (tło przycisku). "before" = rysuj PRZED treścią
        # przycisku, żeby tło było pod tekstem.

        with self.canvas.before:
            Color(1, 1, 1, p)
            # Ustawia kolor rysowania: biały (R=1, G=1, B=1) z przezroczystością
            # p (0 = przezroczysty, 1 = całkowicie biały). Dzięki temu przycisk
            # "wypełnia się" białym kolorem.

            RoundedRectangle(pos=self.pos, size=self.size, radius=[r, r, r, r])
            # Rysuje zaokrąglony prostokąt w miejscu przycisku, o jego rozmiarze.
            # Wszystkie 4 rogi są zaokrąglone o promieniu r=22dp.


def _make_segment_color_dot(rgba, size_dp=20):
    # Tworzy małe kolorowe kółko, które pojawia się obok nazwy projektu
    # w tabeli statystyk. Kolor kółka odpowiada kolorowi danego wycinka
    # na wykresie kołowym – dzięki temu widać który wycinek reprezentuje
    # który projekt. Gdy kolor nie ma przezroczystości – dodaje ją.
    dot = Widget(size_hint=(None, None), size=(dp(size_dp), dp(size_dp)))
    # Tworzy pusty widget (niewidzialny prostokąt) o dokładnym rozmiarze
    # size_dp x size_dp pikseli. To będzie "płótno" dla kolorowego kółka.
    # size_hint=(None, None) oznacza "nie rozciągaj się – mam własny rozmiar".

    rgba = tuple(rgba) if len(rgba) >= 4 else (*rgba[:3], 1.0)
    # Upewnia się, że kolor ma 4 składowe: (R, G, B, A – przezroczystość).
    # Jeśli dostał tylko 3 (R, G, B) – dodaje A=1.0 (całkowicie nieprzezroczysty).

    def redraw(*_):
        # Rysuje kolorowe kółko od nowa przy każdej zmianie położenia
        # lub rozmiaru. Czyści stare rysunki i tworzy nowe kółko
        # w aktualnej pozycji i rozmiarze.
        dot.canvas.clear()
        # Usuwa stare rysunki z płótna (żeby nie nakładały się na siebie).

        with dot.canvas:
            Color(*rgba)
            # Ustawia kolor rysowania na kolor projektu (np. niebieski, czerwony).

            Ellipse(pos=dot.pos, size=dot.size)
            # Rysuje wypełnione kółko (Ellipse) w miejscu widgetu i jego rozmiarze.

    dot.bind(pos=redraw, size=redraw)
    # Podłącza funkcję redraw do właściwości pozycji i rozmiaru – gdy zmieniają
    # się (np. podczas przewijania), kółko jest rysowane od nowa w dobrym miejscu.

    redraw()
    # Rysuje kółko pierwszy raz (od razu, żeby było widoczne).

    return dot
    # Zwraca gotowy widget z kolorowym kółkiem, który trafi do tabeli statystyk.


# ---------------------------------------------------------------------------
# WIERSZ Z DANYMI JEDNEGO PROJEKTU W TABELI
# ---------------------------------------------------------------------------
# Jeden wiersz w tabeli statystyk: ikona projektu, nazwa i czas.
class StatisticsDetailRow(MDBoxLayout):
    # "StatisticsDetailRow" – jeden wiersz w tabeli na ekranie statystyk.
    # Pokazuje: kolorową kropkę, ikonę projektu, nazwę projektu i czas.

    project_name = StringProperty("")
    # Nazwa projektu do wyświetlenia w wierszu (np. "Strona WWW").

    time_text = StringProperty("0 s")
    # Czas spędzony nad projektem (np. "2 h 15 min").

    icon_name = StringProperty("folder-outline")
    # Nazwa ikony Material Design dla projektu (np. "web", "android").

    icon_rgba = ListProperty([1, 1, 1, 1])
    # Kolor ikony (R, G, B, A). Domyślnie biały.

    segment_rgba = ListProperty([0.6, 0.4, 0.8, 1])
    # Kolor wycinka projektu na wykresie kołowym. Domyślnie fioletowy.

    def __init__(self, row_data, **kwargs):
        # Przygotowuje wiersz w tabeli statystyk: zapamiętuje dane projektu
        # (nazwę, czas, ikonę, kolor) i ustawia jego wygląd.
        self._row_data = row_data
        # Zapamiętuje słownik z danymi projektu (nazwa, czas, kolor itp.),
        # żeby użyć ich później, gdy Kivy załaduje wygląd z pliku KV.

        kwargs.setdefault("orientation", "horizontal")
        # Ustawia układ poziomy – ikona, nazwa i czas będą obok siebie.

        kwargs.setdefault("size_hint_y", None)
        # Mówi: "nie rozciągaj się w pionie – użyj konkretnej wysokości".

        kwargs.setdefault("height", dp(36))
        # Ustawia wysokość wiersza na 36 pikseli.

        kwargs.setdefault("spacing", dp(6))
        # Odstęp między elementami w wierszu (ikona, nazwa, czas) – 6 pikseli.

        super().__init__(**kwargs)
        # Wywołuje standardowy konstruktor KivyMD (tworzy prawdziwy MDBoxLayout).

    def on_kv_post(self, base_widget):
        # Po załadowaniu wyglądu wiersza z pliku KV – wypełnia go danymi
        # projektu (nazwa, czas, ikona) i przygotowuje kolorową kropkę.
        self.apply_row(self._row_data)
        # Wypełnia wiersz danymi projektu (nazwa, czas, ikona, kolor).

        self.bind(segment_rgba=self._redraw_segment_dot)
        # Gdy zmieni się kolor segmentu – przerysowuje kropkę obok nazwy.

        if "segment_dot" in self.ids:
            self.ids.segment_dot.bind(pos=self._redraw_segment_dot, size=self._redraw_segment_dot)
            # Gdy kropka zmieni położenie lub rozmiar (np. przy przewijaniu)
            # – przerysowuje ją w nowym miejscu.

        Clock.schedule_once(self._redraw_segment_dot, 0)
        # Planuje przerysowanie kropki na "za chwilę" (0 sekund = przy
        # najbliższej okazji). Dzięki temu kropka pojawi się od razu
        # po załadowaniu wiersza.

    def apply_row(self, row_data):
        # Wypełnia pojedynczy wiersz w tabeli statystyk danymi projektu:
        # nazwa projektu, przepracowany czas, ikona (emoji) i jej kolor,
        # oraz kolor segmentu na wykresie kołowym.
        # Jeden wiersz = jeden projekt w wybranym okresie.
        self.project_name = row_data.get("name", "")
        # Nazwa projektu (np. "Strona WWW"). Jeśli brak danych – pusty tekst.

        self.time_text = row_data.get("time", "0 s")
        # Czas spędzony nad projektem (np. "2 h 15 min"). Jeśli brak – "0 s".

        self.icon_name = row_data.get("icon", "folder-outline")
        # Ikona projektu (np. "web", "android"). Jeśli brak – domyślna ikona.

        self.icon_rgba = list(row_data.get("icon_color", (1, 1, 1, 1)))
        # Kolor ikony projektu (R, G, B, A). Jeśli brak – biały.

        self.segment_rgba = list(row_data.get("segment_color", (0.6, 0.4, 0.8, 1)))
        # Kolor wycinka na wykresie kołowym. Jeśli brak – fioletowy.

    def _redraw_segment_dot(self, *_args):
        # Odświeża wygląd kolorowej kropki obok nazwy projektu.
        # Kropka jest rysowana jako kolorowe kółko (Ellipse) na płótnie
        # Kivy. Jej kolor pochodzi z danych statystyk – to ten sam kolor
        # co dany wycinek na wykresie kołowym obok.
        if "segment_dot" not in self.ids:
            return
        # Jeśli w tym wierszu nie ma widgetu o ID "segment_dot" (np. plik
        # KV nie został jeszcze załadowany) – przerwij, nic nie rób.

        dot = self.ids.segment_dot
        # Pobiera widget kropki (mały pusty Widget, który będzie płótnem).

        rgba = self.segment_rgba
        # Pobiera kolor wycinka projektu z danych (np. niebieski, czerwony).

        if len(rgba) == 3:
            rgba = (*rgba, 1.0)
            # Jeśli kolor ma tylko 3 składowe (R, G, B) – dodaj przezroczystość
            # 1.0 (całkowicie nieprzezroczysty). Kivy potrzebuje 4 wartości.

        dot.canvas.clear()
        # Czyści stare rysunki (usuwamy starą kropkę, żeby narysować nową).

        with dot.canvas:
            Color(*rgba)
            # Ustawia kolor rysowania na kolor wycinka projektu.

            Ellipse(pos=dot.pos, size=dot.size)
            # Rysuje kolorowe kółko w miejscu widgetu i jego rozmiarze.


# ---------------------------------------------------------------------------
# WYKRES KOŁOWY
# ---------------------------------------------------------------------------
# Niestandardowy wykres kołowy – rysowany bezpośrednio na płótnie (canvas).
# Przyjmuje dane: [{'color': (r,g,b,a), 'percent': 25}, ...]
# Każdy wycinek to procent z 360 stopni koła.
class PieChart(Widget):
    # "PieChart" – wykres kołowy rysowany na płótnie Kivy.
    # Każdy kolor to inny projekt, a wielkość wycinka = % czasu.

    data = ListProperty([])
    # Lista danych do wyświetlenia na wykresie. Każdy element to słownik:
    # {"color": (r,g,b,a), "percent": 25.0}. Gdy lista się zmieni,
    # wykres automatycznie się odświeży.

    def __init__(self, **kwargs):
        # Przygotowuje wykres kołowy – odświeża go przy zmianie pozycji,
        # rozmiaru lub danych.
        super().__init__(**kwargs)
        # Wywołuje standardowy konstruktor Kivy.

        self.bind(pos=self.update_canvas, size=self.update_canvas, data=self.update_canvas)
        # Gdy zmieni się położenie (pos), rozmiar (size) lub dane (data) –
        # automatycznie przerysowuje wykres od nowa.

    def update_canvas(self, *args):
        # Rysuje wykres kołowy – każdy kolor to inny projekt.
        # Działa to tak:
        # 1. Zaczynamy od kąta 0° (góra koła) i idziemy zgodnie z ruchem
        #    wskazówek zegara
        # 2. Każdy projekt dostaje wycinek koła proporcjonalny do swojego czasu
        #    Np. jeśli projekt A ma 25% czasu, dostanie 25% z 360° = 90° wycinka
        # 3. angle_start = gdzie zaczął się poprzedni wycinek
        #    angle_end = angle_start + (procent projektu * 360°)
        # 4. Kolejny projekt zaczyna się tam, gdzie skończył poprzedni
        # 5. Po wszystkich projektach koło jest w 100% wypełnione
        self.canvas.clear()
        # Usuwa stare rysunki (żeby nie nakładały się na siebie przy odświeżaniu).

        with self.canvas:
            angle_start = 0
            # Kąt początkowy – zaczynamy od 0° (godzina 12 na zegarze).

            for item in self.data:
                # Dla każdego projektu w danych...

                Color(*item.get("color", (1, 1, 1, 1)))
                # Ustawia kolor rysowania na kolor danego projektu
                # (np. niebieski, czerwony). Jeśli kolor nie istnieje – biały.

                percent = item.get("percent", 0)
                # Pobiera procent czasu dla tego projektu (np. 25 = 25%).

                angle_end = angle_start + (percent / 100.0) * 360
                # Oblicza koniec wycinka: start + (procent * 360°).
                # Np. 25% = 0 + 0.25 * 360 = 90° (ćwierć koła).

                Ellipse(
                    pos=self.pos, size=self.size,
                    angle_start=angle_start, angle_end=angle_end,
                )
                # Rysuje wycinek koła (Ellipse z ograniczeniem kąta) od
                # angle_start do angle_end w bieżącym kolorze.

                angle_start = angle_end
                # Przesuwa kąt startowy na koniec tego wycinka – kolejny
                # projekt zacznie się tam, gdzie poprzedni się skończył.


# ---------------------------------------------------------------------------
# GŁÓWNY EKRAN STATYSTYK
# ---------------------------------------------------------------------------
class StatisticsScreen(MDScreen):
    # "StatisticsScreen" – główny ekran statystyk. Pokazuje wykres kołowy,
    # tabelę z czasem projektów i przyciski do wyboru okresu.

    selected_period = StringProperty("Miesiąc")
    # Wybrany okres: "Dzień", "Tydzień" lub "Miesiąc". Domyślnie "Miesiąc".

    total_time_text = StringProperty("suma: 0 s")
    # Tekst z łącznym czasem wszystkich projektów (np. "suma: 5 h 30 min").

    has_data = BooleanProperty(False)
    # Czy są jakieś dane do pokazania? True = są sesje, False = brak.

    empty_hint_text = StringProperty("Brak czasu w tym okresie.\nUruchom timer w projekcie.")
    # Tekst wyświetlany gdy nie ma żadnych danych w wybranym okresie.

    stats_card_height = NumericProperty(dp(120))
    # Wysokość karty z tabelą statystyk. Obliczana automatycznie na podstawie
    # liczby wierszy. Domyślnie 120 pikseli (mieści kilka wierszy).

    def set_period(self, label: str):
        # Zmienia okres dla którego pokazujemy statystyki.
        # Użytkownik może wybrać: Dzień (od północy), Tydzień (od poniedziałku)
        # lub Miesiąc (od 1. dnia miesiąca). Po zmianie odświeża wszystkie dane
        # na ekranie: wykres kołowy, tabelę i sumę całkowitą.
        if label not in ("Dzień", "Tydzień", "Miesiąc"):
            return
        # Jeśli ktoś wywołał tę funkcję z nieprawidłowym okresem – ignorujemy.

        self.selected_period = label
        # Zapisuje wybrany okres. Kivy automatycznie wywoła on_selected_period.

        Clock.schedule_once(lambda _dt: self.refresh_statistics(), 0)
        # Planuje odświeżenie statystyk na "za chwilę" (0 sekund = przy
        # najbliższej okazji). Dzięki temu dane odświeżą się po zmianie okresu.

    def set_statistics_rows(self, rows):
        # Wypełnia tabelę na ekranie statystyk wierszami z danymi projektów.
        # Najpierw czyści stare wiersze, potem dodaje nowe (w odwrotnej
        # kolejności – Kivy układa od góry do dołu). Na koniec przelicza
        # wysokość karty statystyk i przewijanej zawartości.
        cont = self.ids.stats_rows_container
        # Pobiera kontener (MDBoxLayout) z tabelą statystyk z pliku KV.

        while cont.children:
            cont.remove_widget(cont.children[0])
        # Usuwa wszystkie stare wiersze z tabeli (czyści przed dodaniem nowych).

        rows = list(rows or [])
        # Zamienia dane na listę. Jeśli nie ma danych – pusta lista.

        for r in reversed(rows):
            cont.add_widget(StatisticsDetailRow(r))
            # Dodaje każdy wiersz od DOŁU do GÓRY (reversed). Kivy układa
            # ostatnio dodany element na górze, więc odwracamy kolejność.

        cont.height = max(dp(36), cont.minimum_height)
        # Ustawia wysokość kontenera na co najmniej 36 pikseli (albo więcej,
        # jeśli wiersze się nie mieszczą – minimum_height to suma wysokości
        # wszystkich wierszy).

        self._layout_stats_card()
        # Przelicza wysokość karty statystyk (żeby zmieścić wszystkie wiersze).

        Clock.schedule_once(self._relayout_stats_scroll, 0)
        # Planuje odświeżenie przewijanej zawartości (żeby scroll działał).

    def _layout_stats_card(self):
        # Oblicza jak wysoka ma być karta z statystykami, żeby zmieściły
        # się w niej wszystkie wiersze projektów. Bierze pod uwagę:
        # nagłówek, odstępy między wierszami, wysokość każdego wiersza
        # oraz ewentualny pusty obszar (gdy brak danych).
        card = self.ids.stats_card
        # Pobiera kartę (MDCard) z ekranu statystyk – to biały prostokąt.

        cont = self.ids.stats_rows_container
        # Pobiera kontener z wierszami (znajduje się wewnątrz karty).

        pad = card.padding
        # Pobiera odstęp wewnętrzny karty (margines między krawędzią karty
        # a jej zawartością).

        if isinstance(pad, (int, float)):
            pt = pr = pb = pl = float(pad)
            # Jeśli padding to jedna liczba (np. 10) – wszystkie strony
            # mają ten sam odstęp.
        else:
            pl, pt, pr, pb = pad[0], pad[1], pad[2], pad[3]
            # Jeśli padding to lista 4 liczb – [lewy, górny, prawy, dolny].

        header_h = dp(26)
        # Wysokość nagłówka tabeli ("Projekt | Czas") – 26 pikseli.

        gap = card.spacing
        # Odstęp między nagłówkiem a wierszami wewnątrz karty.

        if isinstance(gap, (list, tuple)):
            gap = float(gap[1]) if len(gap) > 1 else float(gap[0])
            # Jeśli spacing to lista [poziomy, pionowy] – bierzemy pionowy.
        else:
            gap = float(gap)
            # Jeśli spacing to jedna liczba – używamy jej.

        row_spacing = cont.spacing
        # Odstęp między poszczególnymi wierszami w kontenerze.

        if isinstance(row_spacing, (list, tuple)):
            row_spacing = float(row_spacing[1]) if len(row_spacing) > 1 else float(row_spacing[0])
            # Analogicznie – bierzemy odstęp pionowy.
        else:
            row_spacing = float(row_spacing)

        row_heights = sum(float(c.height) for c in cont.children)
        # Suma wysokości wszystkich wierszy (każdy ma 36 pikseli).

        row_gaps = row_spacing * max(0, len(cont.children) - 1)
        # Łączna wysokość odstępów między wierszami (liczba_przerw * odstęp).

        empty_h = dp(48) if not self.has_data else 0
        # Jeśli brak danych – dodajemy 48 pikseli na tekst "Brak czasu...".

        self.stats_card_height = pt + pb + header_h + gap + row_heights + row_gaps + empty_h
        # Oblicza całkowitą wysokość karty: padding górny + dolny + nagłówek
        # + odstęp + wiersze + odstępy między wierszami + pusty tekst (jeśli trzeba).

    def _relayout_stats_scroll(self, _dt=None):
        # Aktualizuje wysokość przewijanej zawartości statystyk.
        # Kivy czasem nie przelicza automatycznie wysokości gdy dodajemy
        # lub usuwamy elementy – to wymusza poprawne odświeżenie,
        # dzięki czemu cała zawartość jest widoczna i przewijalna.
        if "stats_scroll_content" in self.ids:
            grid = self.ids.stats_scroll_content
            # Pobiera siatkę (GridLayout) z przewijaną zawartością.

            grid.height = grid.minimum_height
            # Ustawia wysokość siatki na jej minimalną wysokość (tyle, ile
            # potrzebują wszystkie elementy). Dzięki temu scroll działa
            # prawidłowo.

    def refresh_statistics(self):
        # Główna funkcja odświeżająca cały ekran statystyk.
        # 1. Pobiera dane z pliku (sesje i cele czasowe)
        # 2. Przygotowuje dane dla wykresu kołowego (kolory + procenty)
        # 3. Przygotowuje dane dla tabeli (nazwy, czasy, ikony)
        # 4. Oblicza łączny czas wszystkich projektów
        # 5. Aktualizuje wszystkie elementy na ekranie
        period = self.selected_period
        # Pobiera wybrany okres (np. "Miesiąc").

        pie, rows, total_sec = statistics_from_sessions(period)
        # Wywołuje funkcję z session_store.py, która:
        #   pie  – lista dla wykresu kołowego (kolory + procenty)
        #   rows – lista wierszy dla tabeli (nazwy, czasy, ikony)
        #   total_sec – łączny czas wszystkich projektów w sekundach

        self.total_time_text = format_statistics_total(total_sec)
        # Formatuje łączny czas (np. 7500 sekund → "2 h 5 min").

        self.has_data = total_sec > 0
        # Jeśli łączny czas > 0, ustawia has_data na True (są dane do pokazania).

        self.ids.pie_chart.data = list(pie) if pie else []
        # Przekazuje dane do wykresu kołowego. Jeśli brak danych – pusta lista.

        self.set_statistics_rows(rows)
        # Wypełnia tabelę wierszami z danymi projektów.

        self._relayout_stats_scroll()
        # Odświeża przewijaną zawartość (żeby scroll działał poprawnie).

    def on_selected_period(self, _instance, value):
        # Gdy użytkownik zmieni wybrany okres (Dzień/Tydzień/Miesiąc) –
        # automatycznie odświeża statystyki, żeby pokazać dane z nowego okresu.
        if value in ("Dzień", "Tydzień", "Miesiąc"):
            self.refresh_statistics()
            # Jeśli nowy okres jest prawidłowy – odśwież dane.

    def on_enter(self):
        # Gdy użytkownik wchodzi na ekran statystyk – automatycznie
        # odświeżamy wszystkie dane. Dzięki temu zawsze widzi aktualne
        # informacje, nawet jeśli coś zmieniło się na innych ekranach.
        self.refresh_statistics()
        # Odświeża statystyki przy wejściu na ekran.

    def __init__(self, **kwargs):
        # Przygotowuje ekran statystyk: uruchamia standardową inicjalizację
        # Kivy i ustawia nasłuchiwanie na zmianę wybranego okresu
        # (Dzień/Tydzień/Miesiąc), żeby automatycznie odświeżać dane.
        super().__init__(**kwargs)
        # Wywołuje standardowy konstruktor Kivy (przygotowuje prawdziwy ekran).

        self.bind(selected_period=self.on_selected_period)
        # Gdy zmieni się selected_period – automatycznie wywołaj
        # on_selected_period, która odświeży statystyki.