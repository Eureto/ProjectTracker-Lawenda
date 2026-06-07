# ---------------------------------------------------------------------------
# EKRAN GŁÓWNY (HOME) – lista projektów i ostatnia sesja
# ---------------------------------------------------------------------------
# Ten plik definiuje ekran główny aplikacji. Zawiera klasy dla:
# - Karty projektu (ProjectCard) – każdy projekt jest widoczny jako karta
# - Karty ostatniej sesji (SessionCard) – informacja o ostatnim pomiarze
# - Paska postępu z kropek (DotProgressBar)
# - Głównego ekranu (HomeScreen) – zarządza kartami i układem
#
# CO TO JEST "WIDŻET"?
# To gotowy element interfejsu, np. przycisk, etykieta, pole tekstowe.
#---------------------------------------------------------------------------

import os
# "os" – funkcje systemowe: sprawdzanie czy plik istnieje, łączenie ścieżek.

import json
# "json" – wbudowany moduł do odczytu/zapisu plików JSON (dane projektów,
# pozycje kart).

from screens.session_store import (
    format_duration_hms,
    format_when_label,
    get_last_session,
    schedule_home_last_session_refresh,
)
# Importuje funkcje do formatowania czasu, etykiet "Dzisiaj/Wczoraj",
# pobierania ostatniej sesji i odświeżania karty sesji.

from screens.emoji_assets import resolve_emoji_source
# Importuje funkcję zamieniającą nazwę ikony na ścieżkę do pliku emoji.

from kivy.core.text import Label as CoreLabel
# "CoreLabel" – narzędzie Kivy do mierzenia tekstu (oblicza szerokość
# tekstu bez wyświetlania go). Używane do pozycjonowania ikon obok tekstu.

from kivy.uix.widget import Widget
# "Widget" – podstawowy budulec Kivy. Wszystko co widzisz na ekranie to Widget.

from kivy.properties import (
    StringProperty, NumericProperty,
    BooleanProperty, ColorProperty, AliasProperty,
)
# "Properties" – specjalne właściwości Kivy. Gdy zmieniają wartość,
# aplikacja automatycznie wie, że trzeba odświeżyć wygląd.
# AliasProperty – właściwość, która wylicza się z innych właściwości.

from kivy.metrics import dp
# "dp" – jednostka rozmiaru niezależna od gęstości ekranu (piksele, które
# wyglądają tak samo na każdym ekranie).

from kivy.clock import Clock
# "Clock" – narzędzie Kivy do planowania zadań na później.

from kivy.animation import Animation
# "Animation" – płynne animacje (np. karta drży gdy jest przeciągana).

from kivy.graphics import Color, Line, Ellipse
# "Color" – ustawia kolor rysowania. "Line" – rysuje linie.
# "Ellipse" – rysuje elipsę/koło (kropki w pasku postępu).

from kivy.utils import get_color_from_hex
# "get_color_from_hex" – zamienia kolor z zapisu szesnastkowego (#FF00FF)
# na listę liczb (R, G, B, A) zrozumiałą przez Kivy.

from kivymd.app import MDApp
# "MDApp" – główna klasa aplikacji KivyMD. Przez nią uzyskujemy dostęp
# do ustawień (np. tryb układu: siatka/swobodny).

# Kolory tekstu: ciemny na jasnym tle i biały na ciemnym
_TEXT_ON_LIGHT = (0.102, 0.102, 0.102, 1)
# Kolor ciemnego tekstu – prawie czarny, używany gdy tło jest jasne.

_TEXT_ON_DARK = (1, 1, 1, 1)
# Kolor białego tekstu – używany gdy tło jest ciemne.

GRID_COLUMNS = 2
# Liczba kolumn w widoku siatki – karty są ułożone w 2 kolumnach.

CARD_SIZE_HINT_X = 0.4
# Szerokość karty jako ułamek szerokości ekranu. 0.4 = 40% szerokości.

# Pomocnicze stałe do pozycjonowania emoji na karcie
GRID_EMOJI_TOP_EXTRA = 0.25
# Dodatkowe przesunięcie emoji do góry (ułamek wysokości karty).

GRID_EMOJI_BADGE_SCALE = 1.6
# Skala "plakietki" emoji – emoji jest większe niż standardowe ikony.


# Zamienia kolor zapisany w różnych formatach na jednolity zrozumiały dla Kivy.
# Przyjmuje: zapis szesnastkowy (#FF00FF), listę [255,0,255], listę [0-1,0-1,0-1].
def _normalize_rgba(color):
    if isinstance(color, str):
        return get_color_from_hex(color)
    channels = list(color[:4])
    # Jeśli dostałeś mniej niż 3 składowe – uzupełniamy
    while len(channels) < 3:
        channels.append(1.0)
    if len(channels) == 3:
        channels.append(1.0)
    # Jeśli wartości są > 1, to znaczy, że ktoś podał skalę 0-255
    if any(v > 1 for v in channels[:3]):
        channels = [v / 255.0 for v in channels[:3]] + [channels[3]]
    return tuple(channels[:4])


# Oblicza względną jasność koloru – im wyższa wartość, tym jaśniejszy kolor.
# Używane do automatycznego doboru: czarny tekst na jasnym tle, biały na ciemnym.
# Wzór bierze pod uwagę, że ludzkie oko różnie odbiera kolory (np. zielony jest
# jaśniejszy od niebieskiego dla oka).
def _relative_luminance(rgba):
    # Rozpakowujemy składowe (ignorujemy alfa)
    r, g, b, *_ = _normalize_rgba(rgba)

    # Przelicza składową koloru na wartość liniową – potrzebne do obliczenia jasności koloru.
    def linear(channel):
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    # Średnia ważona: oko jest najbardziej czułe na zielony, najmniej na niebieski
    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


# Wyznacza kolor tekstu: biały lub czarny – taki który będzie czytelny na danym tle.
# Używa standardu WCAG (Web Content Accessibility Guidelines).
def contrasting_text_color(background):
    # Obliczamy jasność tła
    lum = _relative_luminance(background)
    # Kontrast z bielą (1.0) i z czernią (0.0) według wzoru WCAG
    contrast_light = (1.0 + 0.05) / (lum + 0.05)
    contrast_dark = (lum + 0.05) / 0.05
    # Wybieramy ten kolor tekstu, który daje LEPSZY kontrast
    return _TEXT_ON_DARK if contrast_light >= contrast_dark else _TEXT_ON_LIGHT


from kivymd.uix.card import MDCard
# "MDCard" – karta z KivyMD (Material Design), daje zaokrąglone rogi, cień itp.

from kivymd.uix.screen import MDScreen
# "MDScreen" – ekran KivyMD. Każdy osobny widok w aplikacji to osobny MDScreen.


# ---------------------------------------------------------------------------
# PASEK POSTĘPU Z KROPEK
# ---------------------------------------------------------------------------
class DotProgressBar(Widget):
    # Pasek postępu złożony z kropek – zamiast tradycyjnego paska pokazuje
    # serię kropek. Np. jeśli jest 5 kropek i 3 są wypełnione, oznacza to
    # 60% postępu. Używane np. do pokazania postępu celów czasowych.
    # Wypełnione kropki = zrobione, puste = jeszcze przed nami.
    
    total_steps = NumericProperty(5)
    current_step = NumericProperty(2)
    active_color = ColorProperty([0.08, 0.08, 0.08, 1])
    inactive_color = ColorProperty([1, 1, 1, 1])

    # Przygotowuje pasek postępu – ustawia, że pasek ma się przerysowywać, gdy zmieni się jego położenie, rozmiar, liczba kroków lub kolory.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Rejestruje wywołania zwrotne – gdy zmieni się którakolwiek
        # z tych właściwości, pasek przerysuje się automatycznie.
        self.bind(
            pos=self.update_canvas,
            size=self.update_canvas,
            total_steps=self.update_canvas,
            current_step=self.update_canvas,
            active_color=self.update_canvas,
            inactive_color=self.update_canvas,
        )

    def update_canvas(self, *args):
        # Rysuje kropki na pasku postępu.
        # Kropki wypełnione (aktywny kolor) = zrobione kroki.
        # Kropki puste (nieaktywny kolor) = pozostałe kroki.
        # Dodatkowo rysuje linię łączącą kropki – też w odpowiednim kolorze.
        # Jeśli jest tylko 1 kropka, rysuje tylko ją (bez linii).
        # Czyści poprzednie rysunki – zaczynamy od zera
        self.canvas.clear()
        if self.width < 1 or self.total_steps < 1:
            return
        # Konwertuje kolory na krotki (Kivy czasem zwraca listę)
        active = tuple(self.active_color)
        inactive = tuple(self.inactive_color)
        # Oblicza współrzędne: początek i koniec paska, środek wysokości
        start_x = self.x + dp(5)
        end_x = self.right - dp(5)
        line_y = self.center_y
        # Zabezpiecza current_step przed wartościami spoza zakresu
        step = max(0, min(int(self.current_step), int(self.total_steps)))
        line_w = dp(2)
        with self.canvas:
            if self.total_steps > 1:
                # Odstęp między kolejnymi kropkami
                spacing = (end_x - start_x) / (self.total_steps - 1)
                # Punkt podziału: do niego linia jest aktywna, dalej nieaktywna
                split_x = start_x + spacing * max(0, step - 1)
                if step > 1:
                    Color(*active)
                    Line(points=[start_x, line_y, split_x, line_y], width=line_w)
                if step < self.total_steps:
                    Color(*inactive)
                    Line(points=[split_x, line_y, end_x, line_y], width=line_w)
                for i in range(self.total_steps):
                    Color(*(active if i < step else inactive))
                    # Środek kropki przesunięty o pół jej rozmiaru
                    dot_x = start_x + (i * spacing) - dp(6)
                    dot_y = line_y - dp(6)
                    Ellipse(pos=(dot_x, dot_y), size=(dp(12), dp(12)))
            else:
                # Gdy jest tylko 1 kropka – rysujemy ją pojedynczo, bez linii
                Color(*(active if step > 0 else inactive))
                Ellipse(pos=(start_x - dp(6), line_y - dp(6)), size=(dp(12), dp(12)))


# ---------------------------------------------------------------------------
# KARTA PROJEKTU
# ---------------------------------------------------------------------------
class ProjectCard(MDCard):
    # Karta reprezentująca JEDEN projekt na ekranie głównym.
    # Wygląda jak kolorowy prostokąt z nazwą projektu i emoji.
    # Można:
    # - Kliknąć – otwiera szczegóły projektu
    # - Przeciągnąć (w trybie swobodnym) – zmienić pozycję na ekranie
    # - Automatycznie ułożyć w siatkę (w trybie siatki)
    
    # Identyfikator – unikalny dla każdego projektu (np. UUID)
    uid = StringProperty("")
    title = StringProperty("")
    image_source = StringProperty("")
    emoji_source = StringProperty("")
    # Kąt nachylenia karty – używany w animacji "drżenia"
    angle = NumericProperty(0)
    card_color = ColorProperty([0.7, 0.5, 1, 1])
    # Kolor napisu dobierany automatycznie (czarny/biały) względem tła
    title_text_color = ColorProperty(_TEXT_ON_LIGHT)
    # Proporcje karty – 1.0 = kwadrat, 1.5 = półtora raza wyższa niż szersza
    height_multiplier = NumericProperty(1.0)
    title_font_style = StringProperty("Subtitle2")
    # Rozmiar emoji na karcie (w dp)
    emoji_size = NumericProperty(dp(40))
    # Przesunięcie emoji w prawo: 1.05 = 5% poza krawędź karty
    emoji_right_hint = NumericProperty(1.05)
    # Dla plików PNG przesunięcie może być inne niż dla ikon
    emoji_right_hint_png = NumericProperty(1.05)

    # Sprawdza, czy emoji pochodzi z pliku PNG – jeśli tak, zwraca inne ustawienie pozycji niż dla zwykłej ikony.
    def _get_effective_emoji_right_hint(self):
        src = (self.emoji_source or "").lower()
        if src.endswith(".png"):
            return self.emoji_right_hint_png
        return self.emoji_right_hint

    effective_emoji_right_hint = AliasProperty(
        _get_effective_emoji_right_hint,
        None,
        bind=("emoji_source", "emoji_right_hint", "emoji_right_hint_png"),
    )

    interactive = BooleanProperty(True)

    # Przygotowuje nową kartę projektu – zapamiętuje ustawienia początkowe i dobiera kolor tekstu pasujący do tła karty.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._long_press_ev = None
        self._shake_anim = None
        self._update_title_text_color()

    # Wywołuje się automatycznie po zmianie koloru tła karty – wtedy trzeba też dobrać kolor napisu.
    def on_card_color(self, *_args):
        self._update_title_text_color()

    # Dobiera kolor napisu (czarny lub biały) tak, żeby był dobrze widoczny na tle karty.
    def _update_title_text_color(self):
        self.title_text_color = contrasting_text_color(self.card_color)

    # Sprawdza, czy karty mogą być swobodnie przesuwane (tryb swobodny, a nie siatka).
    def _free_layout_enabled(self):
        app = MDApp.get_running_app()
        return app is None or not app.grid_layout

    # Reaguje na dotknięcie karty. Jeśli karta jest w trybie swobodnym, uruchamia licznik – przytrzymanie palca przez sekundę włącza tryb przeciągania.
    def on_touch_down(self, touch):
        if not self.interactive:
            return False
        if self.collide_point(*touch.pos):
            touch.ud["project_card_origin"] = touch.pos
            if self._free_layout_enabled():
                self._long_press_ev = Clock.schedule_once(
                    lambda _dt: self._start_drag_mode(touch), 1.0
                )
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def stop_drag_animation(self):
        # Zatrzymuje animację "drżenia" karty, która sygnalizuje,
        # że karta jest w trybie przeciągania. Anuluje zaplanowane
        # zdarzenia i płynnie ustawia kąt nachylenia na 0 (prosto).
        if self._long_press_ev:
            Clock.unschedule(self._long_press_ev)
            self._long_press_ev = None
        if self._shake_anim:
            self._shake_anim.stop(self)
            self._shake_anim = None
        Animation(angle=0, d=0.1).start(self)

    # Włącza tryb przeciągania karty – karta może swobodnie poruszać się po ekranie i zaczyna lekko drżeć, żeby zasygnalizować gotowość do przesunięcia.
    def _start_drag_mode(self, touch):
        if not self._free_layout_enabled():
            return
        self.pos_hint = {}
        # Drżąca animacja: przechyla kartę na przemian w prawo i lewo,
        # co 0.08 sekundy. Petla nieskończona = drży aż do zatrzymania.
        self._shake_anim = Animation(angle=2, d=0.08) + Animation(angle=-2, d=0.08)
        self._shake_anim.repeat = True
        self._shake_anim.start(self)

    # Reaguje na przesuwanie palca po ekranie. Jeśli karta jest w trybie przeciągania, przesuwa się razem z palcem.
    def on_touch_move(self, touch):
        if not self.interactive:
            return False
        if touch.grab_current is self:
            if self._shake_anim:
                self.x += touch.dx
                self.y += touch.dy
            else:
                # Jeśli palec przesunął się o więcej niż 10 pikseli,
                # anulujemy licznik długiego przytrzymania – to na pewno
                # nie było kliknięcie, tylko zwykłe przesunięcie palca.
                if abs(touch.dx) > 10 or abs(touch.dy) > 10:
                    if self._long_press_ev:
                        Clock.unschedule(self._long_press_ev)
            return True
        return super().on_touch_move(touch)

    # Reaguje na podniesienie palca z ekranu. Jeśli karta była przeciągana – zapisuje nowe położenie. Jeśli to było zwykłe kliknięcie – otwiera szczegóły projektu.
    def on_touch_up(self, touch):
        if not self.interactive:
            return False
        if touch.grab_current is self:
            # Czy karta była w trybie przeciągania? (sprawdzamy czy drży)
            entered_drag = self._shake_anim is not None
            # Anulujemy licznik długiego przytrzymania – już niepotrzebny
            if self._long_press_ev:
                Clock.unschedule(self._long_press_ev)
                self._long_press_ev = None
            if entered_drag:
                # Zatrzymaj drżenie, wyprostuj kartę i zapisz pozycję
                self._shake_anim.stop(self)
                self._shake_anim = None
                Animation(angle=0, d=0.1).start(self)
                self.save_position()
            else:
                origin = touch.ud.get("project_card_origin")
                if origin and self.collide_point(*touch.pos):
                    dx = touch.pos[0] - origin[0]
                    dy = touch.pos[1] - origin[1]
                    # Sprawdza odległość euklidesową – jeśli palec prawie
                    # nie drgnął (<15dp), to było kliknięcie, a nie przeciąganie.
                    if (dx * dx + dy * dy) ** 0.5 < dp(15):
                        self.open_project_info()
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    # Otwiera ekran ze szczegółami tego projektu – przekazuje nazwę i identyfikator, żeby ekran wiedział, które dane pokazać.
    def open_project_info(self):
        app = MDApp.get_running_app()
        info = app.root.get_screen("project_info")
        # ``project_uid`` to unikalny identyfikator, po którym szukamy
        # wszystkich danych tego projektu. Ustaw go PRZED tytułem,
        # żeby reszta kodu od razu wiedziała, z którym projektem ma do czynienia.
        info.project_uid = self.uid or ""
        info.project_title = self.title
        app.root.current = "project_info"

    # Zapisuje aktualne położenie karty do pliku, aby po ponownym uruchomieniu aplikacji karta wróciła w to samo miejsce.
    def save_position(self):
        if not self._free_layout_enabled():
            return
        if self.parent:
            # Zapisz pozycję jako ułamek szerokości i wysokości rodzica
            # – dzięki temu karta wróci na to samo miejsce na każdym ekranie.
            rel_x = self.x / self.parent.width
            rel_y = self.top / self.parent.height

            app = MDApp.get_running_app()
            storage_path = os.path.join(app.user_data_dir, 'card_positions.json')

            data = {}
            if os.path.exists(storage_path):
                try:
                    with open(storage_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (IOError, json.JSONDecodeError):
                    pass

            # Położenie kart jest zapisywane według unikalnego identyfikatora (uid),
            # a nie według nazwy. Dzięki temu dwa projekty o tej samej nazwie
            # nie nadpisują sobie nawzajem pozycji. Stare dane (zapisane według
            # nazwy) są konwertowane przy starcie w migrate_legacy_state_to_uids.
            key = self.uid or self.title
            data[key] = {'x': rel_x, 'top': rel_y}

            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)

            print(f"Position saved for {self.title} ({key}): x={rel_x:.2f}, top={rel_y:.2f}")

class SessionCard(MDCard):
    # Karta pokazująca informację o OSTATNIO zakończonej sesji czasowej.
    # Wyświetla: nazwę projektu, czas trwania i kiedy sesja się zakończyła
    # (np. "Dzisiaj", "Wczoraj" lub data). Jeśli nie ma żadnej sesji –
    # pokazuje pustą kartę z informacją "Brak ostatniej sesji".
    
    has_session = BooleanProperty(False)
    project_name = StringProperty("")
    emoji_source = StringProperty("folder-outline")
    when_label = StringProperty("")
    duration_text = StringProperty("Czas:  00:00:00")

    # Wywołuje się po utworzeniu karty ostatniej sesji na ekranie. Podłącza mechanizm, który ustawia ikonę tuż obok tekstu z nazwą projektu.
    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        label = self.ids.session_project_title
        # Gdy zmieni się tekst, jego rozmiar lub położenie – przelicz pozycję ikony
        label.bind(
            texture_size=self._sync_session_title_row,
            text=self._sync_session_title_row,
            size=self._sync_session_title_row,
        )
        # Wywołaj raz na starcie, żeby od razu ustawić ikonę na dobrym miejscu
        Clock.schedule_once(lambda _dt: self._sync_session_title_row(label), 0)

    # Oblicza "rzeczywistą" szerokość tekstu – taką jaką miałby bez ograniczeń.
    # Używane do pozycjonowania ikony dokładnie obok tekstu.
    # "CoreLabel" – to narzędzie wbudowane w Kivy (silnik graficzny aplikacji), które pozwala
    # zmierzyć tekst, zanim zostanie wyświetlony na ekranie.
    def _title_text_width(self, label):
        if not label.text:
            return 0
        core = CoreLabel(
            text=label.text,
            font_size=label.font_size,
            bold=label.bold,
        )
        if label.font_name:
            core.font_name = label.font_name
        # Znajdź plik czcionki na dysku i wyrenderuj tekst w pamięci
        core.resolve_font_name()
        core.refresh()
        # Zwróć rzeczywistą szerokość wyrenderowanego tekstu
        return core.texture.size[0]

    def _sync_session_title_row(self, label, *_args):
        # Ustawia pozycję ikony (emoji) dokładnie obok tekstu nazwy projektu
        # w karcie ostatniej sesji. Oblicza rzeczywistą szerokość tekstu
        # (używając CoreLabel – narzędzia Kivy do pomiaru tekstu bez rysowania)
        # i umieszcza ikonę tuż za tekstem, z małym odstępem.
        icon = self.ids.get("session_project_icon")
        if icon is None:
            return
        text_w = min(self._title_text_width(label), label.width)
        if text_w <= 0:
            return
        gap = dp(10)
        icon.size = (dp(28), dp(28))
        # Wyśrodkuj ikonę w pionie względem tekstu
        icon.y = label.y + (label.height - icon.height) * 0.5
        # Umieść ikonę tuż za końcem tekstu (z odstępem `gap`)
        icon.x = label.right - text_w - gap - icon.width

    # Wypełnia kartę danymi z ostatniej sesji.
    # Jeśli nie ma sesji (session = None) – pokazuje komunikat "Brak ostatniej sesji".
    def apply_last_session(self, session):
        if not session:
            self.has_session = False
            self.project_name = ""
            self.when_label = ""
            self.duration_text = "Czas:  00:00:00"
            self.emoji_source = "folder-outline"
            return
        self.has_session = True
        self.project_name = session.get("project_title", "")
        # resolve_emoji_source może zwrócić None, więc mamy fallback
        icon = resolve_emoji_source(session.get("emoji_source") or "folder-outline")
        self.emoji_source = icon if icon else "folder-outline"
        self.when_label = format_when_label(session.get("ended_at"))
        self.duration_text = f"Czas:  {format_duration_hms(session.get('duration_seconds', 0))}"
        label = self.ids.get("session_project_title")
        if label is not None:
            Clock.schedule_once(lambda _dt, lbl=label: self._sync_session_title_row(lbl), 0)


# ---------------------------------------------------------------------------
# GŁÓWNY EKRAN (HOME SCREEN)
# ---------------------------------------------------------------------------
class HomeScreen(MDScreen):
    # GŁÓWNY EKRAN APLIKACJI – to co użytkownik widzi po uruchomieniu.
    # Zawiera:
    # - Listę projektów (każdy jako karta ProjectCard)
    # - Kartę ostatniej sesji (SessionCard)
    # - Przyciski do zmiany trybu widoku (siatka / swobodny)
    # Zarządza ładowaniem, układaniem i odświeżaniem kart projektów.

    _last_grid_container_width = 0

    # Wywołuje się po utworzeniu ekranu głównego. Ustawia nasłuchiwanie zmian rozmiaru pojemnika na projekty i trybu widoku.
    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        container = self.ids.projects_container
        container.bind(size=self._on_projects_container_resize)
        app = MDApp.get_running_app()
        if app is not None:
            # Nasłuchuj zmiany trybu widoku (siatka ↔ swobodny) – lambda
            # opakowuje wywołanie, bo Kivy przekazuje zbędne argumenty.
            app.bind(grid_layout=lambda *_a: self._on_layout_mode_changed())

    def _on_layout_mode_changed(self):
        # Gdy użytkownik zmieni tryb układu (siatka ↔ swobodny),
        # przełączamy widok kart. W trybie siatki karty są automatycznie
        # rozmieszczone w dwóch kolumnach. W trybie swobodnym karty
        # wracają do pozycji zapamiętanych przez użytkownika.
        if MDApp.get_running_app().grid_layout:
            self.apply_grid_layout()
        else:
            self.restore_card_positions()

    def _on_projects_container_resize(self, container, size):
        # Gdy zmienia się rozmiar pojemnika na projekty (np. po obrocie
        # telefonu) – przeliczamy układ kart. W trybie siatki odświeżamy
        # pozycje kart, żeby dopasowały się do nowej szerokości.
        # W trybie swobodnym sprawdzamy czy to pierwsze uruchomienie
        # i jeśli tak – przywracamy zapisane pozycje.
        w = size[0]
        if w < 1:
            return
        app = MDApp.get_running_app()
        if app.grid_layout:
            # Jeśli szerokość zmieniła się o mniej niż 1dp – pomijamy
            if abs(w - self._last_grid_container_width) < 1:
                return
            self._last_grid_container_width = w
            Clock.schedule_once(lambda _dt: self.apply_grid_layout(), 0)
        elif not getattr(self, "_free_layout_ready", False):
            # Przy pierwszym uruchomieniu w trybie swobodnym przywracamy pozycje
            self._free_layout_ready = True
            Clock.schedule_once(lambda _dt: self.restore_card_positions(), 0)

    def _project_cards(self):
        # Zwraca wszystkie karty projektów znajdujące się w pojemniku,
        # posortowane alfabetycznie po nazwie projektu. Dzięki temu
        # w trybie siatki projekty są wyświetlane w kolejności A-Z.
        container = self.ids.projects_container
        cards = [c for c in container.children if isinstance(c, ProjectCard)]
        cards.sort(key=lambda c: c.title.lower())
        return cards

    # Odstępy dla układu dwukolumnowego; top_pad robi miejsce na znaczek emoji nad każdą kartą.
    def _grid_layout_metrics(self, container, cards):
        margin_x = dp(16)
        gutter = dp(12)
        row_gap = dp(16)
        base_top = dp(6)

        card_w = container.width * CARD_SIZE_HINT_X
        if not cards:
            return card_w, 0, base_top, margin_x, gutter, row_gap

        # Wysokość karty = szerokość × współczynnik proporcji
        mult = max(c.height_multiplier for c in cards)
        card_h = card_w * mult
        emoji_sz = max(c.emoji_size for c in cards)
        badge_h = emoji_sz * GRID_EMOJI_BADGE_SCALE
        # Miejsce nad kartą na emoji: część nad kartą + część plakietki
        badge_above = (card_h * GRID_EMOJI_TOP_EXTRA + badge_h * 0.35) * 0.5
        top_pad = base_top + badge_above
        return card_w, card_h, top_pad, margin_x, gutter, row_gap

    # Planuje pierwsze ułożenie kart na ekranie – wykona się przy najbliższej okazji, gdy ekran będzie już w pełni gotowy.
    def schedule_initial_layout(self):
        Clock.schedule_once(lambda _dt: self.apply_initial_layout(), 0)

    # Uruchamia układ siatki lub swobodny, gdy kontener projektów ma już ustalony rozmiar na ekranie – dopiero wtedy można prawidłowo rozłożyć karty.
    def apply_initial_layout(self):
        container = self.ids.projects_container
        # Jeśli kontener nie ma jeszcze rozmiaru – spróbuj ponownie za chwilę
        if container.width < 1:
            Clock.schedule_once(lambda _dt: self.apply_initial_layout(), 0)
            return
        app = MDApp.get_running_app()
        if app.grid_layout:
            self.apply_grid_layout()
        else:
            self.restore_card_positions()

    def apply_grid_layout(self):
        # Układa karty projektów w dwóch kolumnach (widok siatki).
        # Oblicza:
        # - Szerokość każdej kolumny na podstawie dostępnej przestrzeni
        # - Wysokość kart (proporcjonalnie do szerokości)
        # - Odstępy między kartami (marginesy)
        # - Pozycję emoji na karcie (przesunięcie do góry)
        # Jeśli pojemnik jest za wąski – czeka i próbuje ponownie za chwilę.
        container = self.ids.projects_container
        if container.width < 1:
            Clock.schedule_once(lambda _dt: self.apply_grid_layout(), 0)
            return
        cards = self._project_cards()
        if not cards:
            container.height = dp(200)
            return

        card_w, _card_h, top_pad, margin_x, gutter, row_gap = self._grid_layout_metrics(
            container, cards
        )
        # Szerokość dostępna na obie kolumny (minus marginesy i odstęp)
        col_width = (container.width - 2 * margin_x - gutter) / GRID_COLUMNS
        # x lewej i prawej kolumny – karty wyśrodkowane w każdej kolumnie
        col_x = [
            margin_x + (col_width - card_w) * 0.5,
            margin_x + col_width + gutter + (col_width - card_w) * 0.5,
        ]

        # Dzielenie z zaokrągleniem w górę: 5 kart → 3 wiersze
        rows = (len(cards) + GRID_COLUMNS - 1) // GRID_COLUMNS
        row_heights = []
        for row in range(rows):
            chunk = cards[row * GRID_COLUMNS : (row + 1) * GRID_COLUMNS]
            # Każdy wiersz ma wysokość najwyższej karty w tym wierszu
            row_heights.append(card_w * max(c.height_multiplier for c in chunk))

        # Całkowita wysokość: padding górny + wiersze + odstępy między wierszami
        content_h = top_pad + sum(row_heights) + max(0, rows - 1) * row_gap
        container.height = max(dp(200), content_h + dp(150))

        y_cursor = container.height - top_pad
        for i, card in enumerate(cards):
            card.stop_drag_animation()
            col = i % GRID_COLUMNS
            row = i // GRID_COLUMNS
            if col == 0 and row > 0:
                # Zaczynamy nowy wiersz – przesuwamy kursor w dół
                y_cursor -= row_heights[row - 1] + row_gap
            card.pos_hint = {}
            card.x = col_x[col]
            card.top = y_cursor

    def refresh_last_session(self):
        # Odświeża kartę ostatniej sesji na ekranie głównym.
        # Pobiera najnowszą sesję z pliku i wypełnia nią kartę.
        # Jeśli nie ma żadnej sesji – pokazuje pustą kartę.
        card = self.ids.last_session_card
        if card is not None:
            card.apply_last_session(get_last_session())

    # Po wejściu na ekran – odśwież ostatnią sesję i zaplanuj układ.
    def on_enter(self, *_args):
        schedule_home_last_session_refresh()
        self.schedule_initial_layout()

    # Wczytuje zapisane projekty z pliku i dodaje ich karty na ekran główny.
    def load_projects(self):
        app = MDApp.get_running_app()
        storage_path = os.path.join(app.user_data_dir, 'projects.json')
        if os.path.exists(storage_path):
            try:
                with open(storage_path, 'r', encoding='utf-8') as f:
                    projects = json.load(f)
                for p in projects:
                    # uid='' to stary format – nowe projekty mają uid
                    self.add_project_card(
                        p['title'], p['image'], resolve_emoji_source(p['icon']), p['color'],
                        0.1, 0.9,
                        uid=p.get('uid', ''),
                    )
            except (IOError, json.JSONDecodeError) as e:
                print(f"Error loading projects: {e}")

    def restore_card_positions(self):
        # Przywraca zapisane pozycje kart w trybie swobodnym.
        # Odczytuje plik card_positions.json i ustawia każdą kartę
        # w miejscu, w którym użytkownik ją wcześniej umieścił.
        # Jeśli dla danej karty nie ma zapisanej pozycji – umieszcza
        # ją w domyślnym miejscu (lewy górny róg, 10% od brzegów).
        app = MDApp.get_running_app()
        if app.grid_layout:
            return
        container = self.ids.projects_container
        # Jeśli kontener nie ma jeszcze rozmiaru – odłóż na później
        if container.width < 1:
            Clock.schedule_once(lambda _dt: self.restore_card_positions(), 0)
            return
        storage_path = os.path.join(app.user_data_dir, "card_positions.json")
        data = {}
        if os.path.exists(storage_path):
            try:
                with open(storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Error restoring positions: {e}")
        for card in self._project_cards():
            card.stop_drag_animation()
            pos = None
            # Najpierw szukamy po uid (nowy format), potem po tytule (stary)
            if card.uid and card.uid in data:
                pos = data[card.uid]
            elif card.title in data:
                pos = data[card.title]
            if pos is not None:
                card.pos_hint = {
                    "x": float(pos.get("x", 0.1)),
                    "top": float(pos.get("top", 0.9)),
                }
            else:
                card.pos_hint = {"x": 0.1, "top": 0.9}
        self.update_container_height()

    def add_project_card(self, title, image, emoji, color, x_pos, y_top, uid=""):
        # Dodaje nową kartę projektu na ekran główny.
        # Tworzy nowy ProjectCard z podanymi danymi (nazwa, obrazek, emoji,
        # kolor tła, pozycja) i dodaje go do pojemnika z projektami.
        # Po dodaniu aktualizuje układ (siatkę lub wysokość pojemnika)
        # w zależności od aktualnego trybu widoku.
        container = self.ids.projects_container
        new_card = ProjectCard(
            uid=uid or "",
            title=title, image_source=image, emoji_source=resolve_emoji_source(emoji),
            card_color=color,
            pos_hint={'x': x_pos, 'top': y_top}
        )
        container.add_widget(new_card)
        app = MDApp.get_running_app()
        if app.grid_layout:
            self.apply_grid_layout()
        else:
            self.update_container_height()

    # Dopasowuje wysokość pojemnika (projects_container) do pozycji kart.
    # W widoku siatki – oblicza wysokość na podstawie liczby wierszy.
    # W widoku swobodnym – znajduje najwyższą kartę i dodaje margines.
    def update_container_height(self):
        container = self.ids.projects_container
        cards = self._project_cards()
        app = MDApp.get_running_app()
        if app.grid_layout and cards and container.width > 0:
            card_w, card_h, top_pad, _mx, _gut, row_gap = self._grid_layout_metrics(
                container, cards
            )
            # Dzielenie z zaokrągleniem w górę – ceiling division
            rows = (len(cards) + GRID_COLUMNS - 1) // GRID_COLUMNS
            grid_h = top_pad + rows * card_h + max(0, rows - 1) * row_gap + dp(150)
            container.height = max(self.height, grid_h)
            return
        min_h = self.height
        for child in container.children:
            if child.top > min_h:
                min_h = child.top
        container.height = min_h + dp(150)