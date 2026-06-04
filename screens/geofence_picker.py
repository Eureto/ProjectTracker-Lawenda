# ---------------------------------------------------------------------------
# WYBÓR LOKALIZACJI (GEOFENCE) – mapa do wyznaczania obszaru
# ---------------------------------------------------------------------------
# Ten ekran pozwala użytkownikowi wybrać miejsce na mapie i promień
# wokół niego (geofence). Służy do automatycznego mierzenia czasu
# gdy użytkownik znajduje się w wybranym miejscu.
#
# CO TO JEST GEOFENCE?
# To wirtualne ogrodzenie – obszar na mapie. Gdy telefon użytkownika
# znajduje się w tym obszarze, aplikacja może automatycznie uruchomić
# stoper. Np. użytkownik wybiera swoją siłownię jako geofence, a stoper
# włącza się sam gdy przyjdzie na trening.
# ---------------------------------------------------------------------------

import math
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.metrics import dp, sp


# Wysyła pojedyncze linie logów (do Kivy i logcat Androida) dla ekranu wyboru lokalizacji.
def _log(message):
    try:
        Logger.info("GeofencePicker: %s", message)
    except Exception:
        pass
    
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex, platform
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, Ellipse, Line
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.screen import MDScreen

from screens.project_info import RoundedSheetButton


class _TapAnchor(ButtonBehavior, AnchorLayout):
    # Klikalny AnchorLayout – odpowiednik ClickableAnchorLayout w Pythonie.
    # AnchorLayout pozwala pozycjonować element w konkretnym miejscu (np. lewy górny róg).
    pass


# Próba importu mapy (kivy_garden.mapview) – jeśli nie jest zainstalowana,
# aplikacja pokaże komunikat zamiast mapy.
try:
    from kivy_garden.mapview import MapView
    _MAPVIEW_AVAILABLE = True
    _MAPVIEW_IMPORT_ERROR = None
except Exception as _exc:
    MapView = None
    _MAPVIEW_AVAILABLE = False
    _MAPVIEW_IMPORT_ERROR = repr(_exc)


if _MAPVIEW_AVAILABLE:
    class _SmoothMapView(MapView):
        # MapView z płynnym (nie skaczącym) przybliżaniem.
        # Zwykła mapa po zdjęciu palca "wskakuje" do najbliższego stopnia
        # przybliżenia (np. z 15.7 na 16). Ta wersja tego nie robi –
        # przybliżenie zostaje dokładnie takie, jakie użytkownik ustawił.
        def on_touch_up(self, touch):
            if touch.grab_current == self:
                touch.ungrab(self)
                self._touch_count = max(0, self._touch_count - 1)
                if self._touch_count == 0:
                    self._pause = False
                return True
            return Widget.on_touch_up(self, touch)
    _StableMapView = _SmoothMapView
else:
    _StableMapView = None


class _TouchBarrierBox(MDBoxLayout):
    # Przezroczysta warstwa, która "łapie" dotknięcia, żeby nie przeszły do elementów pod spodem.
    # Dzieci wewnątrz działają normalnie, ale to co jest pod spodem – nie reaguje na dotyk.
    def on_touch_down(self, touch):
        handled = super().on_touch_down(touch)
        if handled:
            return True
        if self.collide_point(*touch.pos):
            return True
        return False
    # Gdy użytkownik przesuwa palec, ta funkcja sprawdza, czy dotknięcie
    # zostało obsłużone przez dzieci; jeśli nie – blokuje je, żeby nie
    # przeszło do elementów pod spodem.
    def on_touch_move(self, touch):
        handled = super().on_touch_move(touch)
        if handled:
            return True
        if self.collide_point(*touch.pos):
            return True
        return False
    # Gdy użytkownik puści palec, ta funkcja sprawdza, czy dotknięcie
    # zostało obsłużone przez dzieci; jeśli nie, blokuje je, żeby nie
    # przeszło do elementów pod spodem.
    def on_touch_up(self, touch):
        handled = super().on_touch_up(touch)
        if handled:
            return True
        if self.collide_point(*touch.pos):
            return True
        return False


# Domyślne współrzędne Warszawy (gdy nie można ustalić lokalizacji)
_DEFAULT_LAT = 52.2297
_DEFAULT_LON = 21.0122
_DEFAULT_ZOOM = 17
_DEFAULT_RADIUS_M = 100.0
_MAX_RADIUS_M = 1000.0  # Maksymalny promień geofence

# Średnica wizualnego koła jako ułamek krótszego boku mapy
_VIEWPORT_FRACTION = 1.0

_MIN_ZOOM = 12.0  # Minimalne przybliżenie
_MAX_ZOOM = 19.0  # Maksymalne przybliżenie


def _meters_per_pixel(lat_deg, zoom):
    # Oblicza, ile metrów w rzeczywistości odpowiada jednemu pikselowi na mapie.
    # Wartość zależy od szerokości geograficznej i aktualnego przybliżenia –
    # im bardziej przybliżona mapa, tym mniej metrów na piksel.
    return 156543.03392 * math.cos(lat_deg * math.pi / 180.0) / (2.0 ** float(zoom))


def _zoom_for_radius(radius_m, lat_deg, viewport_short_px):
    # Oblicza, jakie przybliżenie mapy jest potrzebne, żeby koło o zadanym promieniu
    # (w metrach) zmieściło się na ekranie. Im większy promień, tym bardziej trzeba oddalić mapę.
    if radius_m <= 0 or viewport_short_px <= 0:
        return _DEFAULT_ZOOM
    visual_d = viewport_short_px * _VIEWPORT_FRACTION
    if visual_d <= 0:
        return _DEFAULT_ZOOM
    target_mpp = (2.0 * radius_m) / visual_d
    base = 156543.03392 * math.cos(lat_deg * math.pi / 180.0)
    if target_mpp <= 0 or base <= 0:
        return _DEFAULT_ZOOM
    return max(_MIN_ZOOM, min(_MAX_ZOOM, math.log2(base / target_mpp)))


# Odczytuje płynną (niecałkowitą) wartość przybliżenia mapy.
# Standardowo zoom to liczba całkowita, ale mapa może mieć dodatkowy atrybut scale,
# który pozwala na płynne przybliżanie (np. 15.3 zamiast 15).
def _effective_zoom(mapview):
    z = float(getattr(mapview, "zoom", _DEFAULT_ZOOM))
    scale = getattr(mapview, "scale", None)
    if scale is None or float(scale) <= 0:
        return z
    try:
        return z + math.log2(float(scale))
    except (ValueError, TypeError):
        return z


class GeofenceCircleOverlay(Widget):
    # Półprzezroczyste koło nakładane na mapę – wizualnie pokazuje
    # wybrany obszar (geofence). Celowo nie reaguje na dotknięcia,
    # żeby można było normalnie przesuwać i przybliżać mapę pod spodem.
    # Użytkownik widzi to jako kolorowe koło z obwódką i celownikiem
    # na środku.
    
    ring_color = ObjectProperty((0.55, 0.31, 0.78, 1.0))
    fill_color = ObjectProperty((0.55, 0.31, 0.78, 0.18))
    diameter_px = NumericProperty(dp(120))

    # Przygotowuje nakładkę: zapamiętuje, że ma przerysowywać koło,
    # gdy zmieni się położenie, rozmiar, kolor lub średnica.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, 1)
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            ring_color=self._redraw,
            fill_color=self._redraw,
            diameter_px=self._redraw,
        )

    # Nie przechwytuj dotknięć — mapa sama obsługuje przesuwanie i przybliżanie.
    def on_touch_down(self, touch):
        return False

    # Gdy użytkownik przesuwa palec po ekranie – ignorujemy to,
    # żeby przesuwanie i przybliżanie mapy działało normalnie.
    def on_touch_move(self, touch):
        return False

    # Gdy użytkownik puści palec – ignorujemy to,
    # żeby mapa mogła normalnie zareagować.
    def on_touch_up(self, touch):
        return False

    def _redraw(self, *_args):
        # Rysuje wypełnione koło z obwódką na środku mapy.
        # 1. Wypełnienie: przezroczysty fiolet (żeby widzieć mapę pod spodem)
        # 2. Obwódka: cienka fioletowa linia dookoła
        # 3. Celownik: małe białe kółko z fioletową obwódką w samym środku
        #    – pokazuje dokładnie środek wybranego obszaru.
        # Rozmiar koła jest ograniczony do mniejszego z: zadanego diametru
        # lub rozmiaru widoku (minus mały margines).
        self.canvas.clear()
        if self.width < 1 or self.height < 1 or self.diameter_px < 2:
            return
        d = min(float(self.diameter_px), min(self.width, self.height) - dp(4))
        d = max(d, dp(8))
        cx = self.center_x
        cy = self.center_y
        with self.canvas:
            Color(*self.fill_color)
            Ellipse(pos=(cx - d / 2.0, cy - d / 2.0), size=(d, d))
            Color(*self.ring_color)
            Line(circle=(cx, cy, d / 2.0), width=dp(2))
            # Celownik na środku
            Color(1, 1, 1, 0.95)
            Ellipse(pos=(cx - dp(4), cy - dp(4)), size=(dp(8), dp(8)))
            Color(*self.ring_color)
            Line(circle=(cx, cy, dp(4)), width=dp(1.2))


class GeofencePickerScreen(MDScreen):
    # Ekran z mapą do wyboru miejsca i promienia geofence.
    # Użytkownik widzi mapę, może ją przesuwać i przybliżać/oddalać,
    # a aplikacja oblicza aktualny promień wybranego obszaru.
    # Obsługa GPS: próbuje znaleźć bieżącą pozycję telefonu i na nią
    # wyśrodkować mapę.

    return_screen = StringProperty("home")
    radius_text = StringProperty(f"{int(_DEFAULT_RADIUS_M)} m")

    _on_done = None
    _initial_lat = _DEFAULT_LAT
    _initial_lon = _DEFAULT_LON
    _initial_zoom = float(_DEFAULT_ZOOM)
    _initial_radius_m = _DEFAULT_RADIUS_M
    _initial_zoom_explicit = False
    _initial_location_explicit = False
    _gps_started = False
    _location_acquired = False

    # Przygotowuje ekran wyboru lokalizacji: ustawia fioletowe tło,
    # tworzy zmienne na mapę, nakładkę i etykietę, a następnie buduje cały interfejs.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.md_bg_color = get_color_from_hex("#8A2BE2")
        self._mapview = None
        self._overlay = None
        self._radius_label = None
        self._build_ui()

    def configure(self, initial_lat=None, initial_lon=None, initial_radius_m=None, initial_zoom=None, return_screen="project_info", on_done=None):
        # Przygotowuje ekran geofence przed jego otwarciem.
        # Ustawia: początkową pozycję na mapie (szerokość/długość geo.),
        # promień, przybliżenie (zoom) oraz ekran do którego wrócić
        # po zapisaniu. Wywołaj TĘ funkcję PRZED przełączeniem na ten ekran.
        # "on_done" to funkcja która zostanie wywołana z wynikiem
        # (współrzędne i promień lub anulowanie).
        self._initial_location_explicit = (initial_lat is not None and initial_lon is not None)
        self._initial_lat = float(initial_lat) if initial_lat is not None else _DEFAULT_LAT
        self._initial_lon = float(initial_lon) if initial_lon is not None else _DEFAULT_LON
        self._initial_radius_m = (
            float(initial_radius_m)
            if initial_radius_m is not None
            else _DEFAULT_RADIUS_M
        )
        if initial_zoom is not None:
            self._initial_zoom = float(initial_zoom)
            self._initial_zoom_explicit = True
        else:
            self._initial_zoom = float(_DEFAULT_ZOOM)
            self._initial_zoom_explicit = False
        self.return_screen = return_screen or "project_info"
        self._on_done = on_done
        self._location_acquired = False

    def on_pre_enter(self, *_args):
        # Tuż przed pojawieniem się ekranu geofence: ustawiamy mapę
        # na odpowiedniej pozycji i odpowiednim przybliżeniu.
        # Jeśli nie ma zapisanej lokalizacji – próbujemy znaleźć
        # bieżącą pozycję telefonu przez GPS.
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            self._kickoff_location_acquisition()
            return
        target_zoom = self._initial_zoom
        if not self._initial_zoom_explicit:
            short_px = min(self._mapview.width, self._mapview.height)
            if short_px > 1:
                target_zoom = _zoom_for_radius(
                    self._initial_radius_m, self._initial_lat, short_px
                )
        self._set_smooth_zoom(target_zoom)
        self._center_map_on(self._initial_lat, self._initial_lon)
        Clock.schedule_once(lambda _dt: self._refresh_overlay(), 0)
        self._kickoff_location_acquisition()

    # Gdy użytkownik opuszcza ten ekran – wyłączamy GPS, żeby oszczędzać baterię.
    def on_leave(self, *_args):
        self._stop_gps()

    def _kickoff_location_acquisition(self):
        # Jeśli użytkownik nie podał konkretnej lokalizacji (np. edytuje
        # istniejący geofence) – próbujemy znaleźć bieżącą pozycję telefonu
        # przez GPS. Na Androidzie najpierw prosimy o pozwolenie.
        if self._initial_location_explicit:
            _log("skip GPS bootstrap (geofence already saved)")
            self._set_status("")
            return
        self._set_status("Lokalizuję...")
        if platform == "android":
            _log("requesting location permissions on Android")
            self._request_location_permission_then_start()
        else:
            _log(f"non-Android platform ({platform!r}); trying plyer.gps directly")
            Clock.schedule_once(lambda _dt: self._start_gps(), 0)

    # Na Androidzie prosi użytkownika o zgodę na dostęp do lokalizacji.
    # Jeśli użytkownik wyrazi zgodę – uruchamia GPS. Jeśli nie – pokazuje
    # komunikat "Brak uprawnień GPS". Na innych systemach pomija ten krok.
    def _request_location_permission_then_start(self):
        used_callback = False
        # Prosi użytkownika o zgodę na dostęp do lokalizacji (wymagane
        # na Androidzie 6+). Jeśli użytkownik zezwoli – uruchamia GPS.
        # Jeśli nie – pokazuje komunikat "Brak uprawnień GPS".
        try:
            from android.permissions import Permission, request_permissions
            # Ta funkcja zostaje wywołana, gdy użytkownik odpowie na prośbę
            # o zgodę na lokalizację. Jeśli zezwolił – uruchamiamy GPS,
            # jeśli nie – pokazujemy komunikat.
            def _cb(perms, results):
                _log(f"permission callback: perms={list(perms)} results={list(results)}")
                if results and any(results):
                    Clock.schedule_once(lambda _dt: self._start_gps(), 0)
                else:
                    Clock.schedule_once(lambda _dt: self._set_status("Brak uprawnień GPS"), 0)
            request_permissions([Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION], _cb)
        except Exception as exc:
            _log(f"request_permissions with callback failed: {exc!r}")
        if not used_callback:
            try:
                from android.permissions import (
                    Permission,
                    request_permissions,
                )

                request_permissions(
                    [
                        Permission.ACCESS_FINE_LOCATION,
                        Permission.ACCESS_COARSE_LOCATION,
                    ]
                )
                _log("request_permissions (no callback) succeeded")
            except Exception as exc:
                _log(f"request_permissions (no callback) failed: {exc!r}")
            # Try to start GPS anyway — permissions may already be granted
            # from a previous session.
            Clock.schedule_once(lambda _dt: self._start_gps(), 0)

    # Włącza GPS, żeby znaleźć bieżącą pozycję telefonu.
    # Jeśli GPS jest już włączony lub pozycja już została znaleziona –
    # nic nie robi. W razie błędu pokazuje odpowiedni komunikat.
    def _start_gps(self):
        if self._gps_started or self._location_acquired:
            _log("skip _start_gps (already started or fix acquired)")
            return
        if self._initial_location_explicit:
            return
        try:
            from plyer import gps
        except Exception as exc:
            _log(f"plyer import failed: {exc!r}")
            self._set_status("Brak GPS (plyer)")
            return
        try:
            gps.configure(
                on_location=self._on_gps_location,
                on_status=self._on_gps_status,
            )
            gps.start(minTime=1000, minDistance=0)
            self._gps_started = True
            _log("plyer.gps started (requesting location updates)")
        except NotImplementedError as exc:
            _log(f"plyer.gps not implemented on this platform: {exc!r}")
            self._set_status("GPS niedostępny na tej platformie")
        except Exception as exc:
            _log(f"plyer.gps start failed: {exc!r}")
            self._set_status(f"Błąd GPS: {exc!r}")

    # Wyłącza GPS, żeby oszczędzać baterię, gdy już nie jest potrzebny.
    def _stop_gps(self):
        if not self._gps_started:
            return
        try:
            from plyer import gps
            gps.stop()
            _log("plyer.gps stopped")
        except Exception as exc:
            _log(f"plyer.gps stop failed: {exc!r}")
        self._gps_started = False

    # Otrzymuje informacje o stanie GPS (np. czy szuka sygnału).
    # Zapisuje to w dzienniku, ale nie pokazuje użytkownikowi.
    def _on_gps_status(self, status_type, status_message):
        _log(f"gps status: {status_type} {status_message}")

    def _on_gps_location(self, **kwargs):
        # Gdy GPS znajdzie naszą pozycję – przesuwamy mapę w to miejsce.
        # Otrzymujemy współrzędne (szerokość i długość geograficzną)
        # i po krótkim opóźnieniu (żeby Kivy zdążył przerysować) 
        # ustawiamy środek mapy na tych współrzędnych.
        lat = kwargs.get("lat")
        lon = kwargs.get("lon")
        _log(f"gps fix: lat={lat} lon={lon} acc={kwargs.get('accuracy')}")
        if lat is None or lon is None:
            return
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return
        Clock.schedule_once(lambda _dt: self._apply_user_location(lat_f, lon_f), 0)

    # Przesuwa mapę tak, żeby środek wskazywał bieżącą pozycję użytkownika
    # (odczytaną z GPS). Potem czyści komunikat statusu i wyłącza GPS.
    def _apply_user_location(self, lat, lon):
        if self._location_acquired or self._initial_location_explicit:
            self._stop_gps()
            return
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return
        self._location_acquired = True
        moved = self._center_map_on(lat, lon)
        if moved:
            _log(f"centered map on user location: {lat}, {lon}")
        self._refresh_overlay()
        self._set_status("")
        self._stop_gps()

    def _center_map_on(self, lat, lon):
        # Przesuwa środek mapy na podane współrzędne geograficzne.
        # Jeśli mapa jest jeszcze za mała (nie ma rozmiaru) – czeka
        # i próbuje ponownie za chwilę. To zabezpieczenie na sytuację
        # gdy funkcja jest wywołana zanim mapa została w pełni utworzona.
        mv = self._mapview
        if mv is None:
            return False
        try:
            mv.center_on(float(lat), float(lon))
        except Exception as exc:
            _log(f"center_on failed: {exc!r}")
            return False
        if mv.width <= 1 or mv.height <= 1:
            Clock.schedule_once(
                lambda _dt: self._retry_center_map_on(lat, lon), 0
            )
        return True

    # Próbuje ponownie ustawić środek mapy na podanych współrzędnych –
    # używane, gdy poprzednia próba się nie udała, bo mapa nie była jeszcze gotowa.
    def _retry_center_map_on(self, lat, lon):
        mv = self._mapview
        if mv is None or mv.width <= 1 or mv.height <= 1:
            Clock.schedule_once(lambda _dt: self._retry_center_map_on(lat, lon), 0)
            return
        try:
            mv.center_on(float(lat), float(lon))
            self._refresh_overlay()
        except Exception as exc:
            _log(f"retry center_on failed: {exc!r}")

    def _set_status(self, text):
        # Aktualizuje tekst w pasku statusu na dole ekranu.
        # Np. "Lokalizuję..." podczas szukania GPS, lub pusty tekst
        # gdy wszystko jest gotowe. Jeśli tekst jest pusty – ukrywa
        # pasek (przezroczystość 0).
        if getattr(self, "_status_lbl", None) is None:
            return
        self._status_lbl.text = text or ""
        self._status_lbl.opacity = 1.0 if text else 0.0

    def _build_ui(self):
        # Buduje cały interfejs ekranu geofence:
        # - Mapę (lub placeholder jeśli mapa nie jest dostępna)
        # - Nakładkę z przezroczystym kołem
        # - Górny pasek z przyciskiem powrotu i tytułem
        # - Dolny panel z: promieniem, statusem, zoomem i przyciskami
        # Jeśli mapa nie jest dostępna – pokazuje komunikat o błędzie.
        root = FloatLayout()
        if _MAPVIEW_AVAILABLE:
            self._mapview = _StableMapView(
                lat=self._initial_lat,
                lon=self._initial_lon,
                zoom=int(round(self._initial_zoom)),
                size_hint=(1, 1),
                pos_hint={"x": 0, "y": 0},
            )
            # Płynne (nie tylko całkowite) przybliżanie; wyłącz przypadkowe
            # przybliżanie po dotknięciu; nie zatrzymuj rysowania kafelków mapy podczas gestów.
            self._safe_set(self._mapview, "snap_to_zoom", False)
            self._safe_set(self._mapview, "double_tap_zoom", False)
            self._safe_set(self._mapview, "pause_on_action", False)
            root.add_widget(self._mapview)
            self._overlay = GeofenceCircleOverlay()
            root.add_widget(self._overlay)
            self._mapview.bind(
                lat=lambda *_a: self._refresh_overlay(),
                lon=lambda *_a: self._refresh_overlay(),
                zoom=lambda *_a: self._refresh_overlay(),
                size=lambda *_a: self._refresh_overlay(),
            )
            # mapview.scale to zwykła właściwość Pythona, a nie Kivy — dlatego
            # podpinamy się do wewnętrznego Scattera, żeby nakładka reagowała
            # na płynne zmiany przybliżenia z diff_scale_at().
            scatter = getattr(self._mapview, "_scatter", None)
            if scatter is not None:
                try:
                    scatter.bind(
                        scale=lambda *_a: self._refresh_overlay(),
                        pos=lambda *_a: self._refresh_overlay(),
                    )
                except Exception:
                    pass
        else:
            placeholder = MDLabel(
                text=(
                    "Mapa nie jest dostępna.\n\n"
                    "Zainstaluj pakiet kivy_garden.mapview, aby wybrać "
                    "lokalizację geofence.\n\n"
                    f"(import error: {_MAPVIEW_IMPORT_ERROR})"
                ),
                halign="center",
                valign="middle",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
                pos_hint={"x": 0, "y": 0},
                size_hint=(1, 1),
                padding=(dp(24), dp(24)),
            )
            root.add_widget(placeholder)

        root.add_widget(self._build_header())
        root.add_widget(self._build_bottom_panel())
        self.add_widget(root)

    # Próbuje ustawić daną właściwość na obiekcie – jeśli się nie uda,
    # po prostu pomija błąd (np. gdy dana właściwość nie istnieje).
    @staticmethod
    def _safe_set(obj, attr, value):
        try:
            setattr(obj, attr, value)
        except Exception:
            pass

    # Ustawia przybliżenie mapy na podaną wartość (w dozwolonym zakresie 12–19).
    # Najpierw próbuje ustawić płynnie, a jeśli się nie uda – skokowo.
    def _set_smooth_zoom(self, zoom):
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return
        z = max(_MIN_ZOOM, min(_MAX_ZOOM, float(zoom)))
        # Właściwość `zoom` w MapView to NumericProperty (często liczba
        # zmiennoprzecinkowa, gdy snap_to_zoom=False). Jeśli źródło mapy
        # obsługuje tylko liczby całkowite, rzutowanie poniżej zapewni poprawną wartość.
        try:
            self._mapview.zoom = z
        except Exception:
            self._mapview.zoom = int(round(z))

    # Tworzy górny pasek ekranu: przycisk powrotu (strzałka w lewo)
    # oraz tytuł "Wybierz miejsce".
    def _build_header(self):
        header = _TouchBarrierBox(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(60),
            pos_hint={"x": 0, "top": 1},
            padding=(0, 0, 0, 0),
            spacing=0,
        )
        header.md_bg_color = (0, 0, 0, 0.35)

        # Same back-affordance as Project Settings / Add Project headers:
        # a tappable anchor with a white chevron-left MDIcon.
        back_anchor = _TapAnchor(
            size_hint_x=None,
            width=dp(56),
            anchor_x="left",
            anchor_y="center",
        )
        back_anchor.add_widget(
            MDIcon(
                icon="chevron-left",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
                font_size=sp(50),
                adaptive_size=True,
            )
        )
        back_anchor.bind(on_release=lambda *_a: self._cancel())
        header.add_widget(back_anchor)

        title = Label(
            text="Wybierz miejsce",
            font_size=sp(20),
            bold=True,
            color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
        )
        title.bind(size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size))
        header.add_widget(title)

        # Niewidzialny odstęp, który równoważy szerokość przycisku powrotu,
        # żeby tytuł pozostał wyśrodkowany.
        spacer = Widget(size_hint_x=None, width=dp(56))
        header.add_widget(spacer)

        return header

    # Tworzy dolny panel ekranu: etykietę z promieniem, pasek statusu,
    # przyciski przybliżania/oddalania oraz przyciski "Wyczyść" i "Zapisz".
    def _build_bottom_panel(self):
        panel = _TouchBarrierBox(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(196),
            pos_hint={"x": 0, "y": 0},
            padding=(dp(16), dp(14), dp(16), dp(18)),
            spacing=dp(8),
        )
        panel.md_bg_color = (0, 0, 0, 0.55)

        radius_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(30),
            spacing=dp(10),
        )
        radius_caption = Label(
            text="Promień:",
            font_size=sp(15),
            color=(1, 1, 1, 1),
            size_hint_x=None,
            width=dp(90),
            halign="left",
            valign="middle",
        )
        radius_caption.bind(
            size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size)
        )
        self._radius_label = Label(
            text=self.radius_text,
            font_size=sp(15),
            bold=True,
            color=(1, 1, 1, 1),
            halign="right",
            valign="middle",
        )
        self._radius_label.bind(
            size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size)
        )
        radius_row.add_widget(radius_caption)
        radius_row.add_widget(self._radius_label)
        panel.add_widget(radius_row)

        # Linia statusu — pokazuje stan uruchamiania GPS, żeby użytkownik
        # wiedział, czy aplikacja właśnie próbuje ustalić jego lokalizację.
        self._status_lbl = Label(
            text="",
            font_size=sp(12),
            color=(1, 1, 1, 0.85),
            size_hint=(1, None),
            height=dp(18),
            halign="left",
            valign="middle",
            opacity=0.0,
        )
        self._status_lbl.bind(
            size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size)
        )
        panel.add_widget(self._status_lbl)

        # Przyciski przybliżania — główny sposób na zmianę rozmiaru obszaru.
        # Ściskanie dwoma palcami (pinch-to-zoom) jest wyłączone, więc
        # użytkownik używa tych przycisków. Zoom jest płynny (bez skoków).
        # Krótkie dotknięcie = mały krok, przytrzymanie = szybkie płynne zbliżanie.
        zoom_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(40),
            spacing=dp(12),
        )
        btn_zoom_out = self._make_zoom_button("−", direction=-1)
        zoom_row.add_widget(btn_zoom_out)

        hint = Label(
            text="Przybliż/oddal aby ustawić obszar (maks. 1000 m)",
            font_size=sp(12),
            color=(1, 1, 1, 0.85),
            size_hint=(1, 1),
            halign="center",
            valign="middle",
        )
        hint.bind(size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size))
        zoom_row.add_widget(hint)
        btn_zoom_in = self._make_zoom_button("+", direction=1)
        zoom_row.add_widget(btn_zoom_in)
        panel.add_widget(zoom_row)

        button_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(44),
            spacing=dp(12),
        )

        # Kolor motywu używany dla głównych przycisków w całej aplikacji.
        app = MDApp.get_running_app()
        primary_bg = list(
            get_color_from_hex(
                getattr(app, "theme_card_bg", "#B388FF") if app else "#B388FF"
            )
        )

        # Destrukcyjny — ten sam czerwony kolor co przycisk "Usuń" w innych
        # miejscach. Strzałka w nagłówku już umożliwia anulowanie, więc
        # tutaj potrzebujemy tylko "Wyczyść" i "Zapisz".
        clear_btn = RoundedSheetButton(
            text="Wyczyść",
            font_size=sp(15),
            size_hint_x=None,
            width=dp(96),
            bg_color=list(get_color_from_hex("#e53935")),
        )
        clear_btn.bind(on_release=lambda *_a: self._clear_and_return())
        button_row.add_widget(clear_btn)
        button_row.add_widget(Widget(size_hint_x=1))

        save_btn = RoundedSheetButton(
            text="Zapisz",
            font_size=sp(15),
            size_hint_x=None,
            width=dp(104),
            bg_color=primary_bg,
        )
        save_btn.bind(on_release=lambda *_a: self._save_and_return())
        button_row.add_widget(save_btn)
        panel.add_widget(button_row)
        return panel

    def _make_zoom_button(self, glyph, direction):
        # Tworzy przycisk do przybliżania (+) lub oddalania (-) mapy.
        # "glyph" to symbol na przycisku, "direction" to kierunek:
        # 1 = przybliż, -1 = oddal.
        # Przytrzymanie przycisku powoduje płynne przybliżanie.
        app = MDApp.get_running_app()
        bg = list(
            get_color_from_hex(
                getattr(app, "theme_card_bg", "#B388FF") if app else "#B388FF"
            )
        )
        btn = RoundedSheetButton(
            text=glyph,
            font_size=sp(22),
            size_hint=(None, 1),
            width=dp(56),
            bg_color=bg,
        )
        # Przytrzymanie = płynne ciągłe przybliżanie; dotknięcie = mały krok.
        btn.bind(
            on_press=lambda *_a, _d=direction: self._zoom_press_start(_d),
            on_release=lambda *_a: self._zoom_press_stop(),
        )
        return btn

    # Krótkie dotknięcie przycisku zoomu zmienia przybliżenie o 18%.
    # Przytrzymanie przycisku powoduje płynne przybliżanie z szybkością ok. 4× na sekundę.
    # Pierwszy skok jest stosowany od razu po dotknięciu, żeby reakcja była natychmiastowa.
    _ZOOM_TAP_STEP = 0.18
    _ZOOM_TICK = 0.035
    
    def _zoom_press_start(self, direction):
        # Gdy użytkownik przytrzyma przycisk zoomu – zaczynamy płynnie
        # przybliżać lub oddalać mapę. Od razu robimy jeden skok
        # (0.18 poziomu zoomu), a potem kontynuujemy co klatkę animacji
        # (60 razy na sekundę) z mniejszym przyrostem (0.035).
        self._zoom_press_stop()
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return
        self._zoom_direction = int(1 if direction > 0 else -1)
        self._apply_smooth_zoom_delta(self._zoom_direction * 0.18)
        self._zoom_clock = Clock.schedule_interval(self._zoom_tick, 1.0 / 60.0)

    # Wywoływana przy każdym "tiknięciu" zegara podczas przytrzymania
    # przycisku zoomu – dodaje mały przyrost przybliżenia (ok. 0.035),
    # co daje efekt płynnego przybliżania.
    def _zoom_tick(self, _dt):
        if (
            not _MAPVIEW_AVAILABLE
            or self._mapview is None
            or getattr(self, "_zoom_direction", 0) == 0
        ):
            return False
        self._apply_smooth_zoom_delta(self._zoom_direction * self._ZOOM_TICK)
        return None  # keep scheduling

    # Gdy użytkownik puści przycisk zoomu – zatrzymujemy płynne
    # przybliżanie i wyłączamy zegar, który je napędzał.
    def _zoom_press_stop(self, *_):
        self._zoom_direction = 0
        clk = getattr(self, "_zoom_clock", None)
        if clk is not None:
            try:
                clk.cancel()
            except Exception:
                pass
            self._zoom_clock = None

    def _apply_smooth_zoom_delta(self, d):
        # Stosuje płynną zmianę przybliżenia mapy.
        # Sprawdza czy nie wyjeżdżamy poza dozwolony zakres (zoom 12-19).
        # Próbuje najpierw użyć diff_scale_at (płynna zmiana), a jeśli
        # się nie uda – zmienia zoom skokowo (awaryjnie).
        # Po zmianie odświeża nakładkę koła.
        mv = self._mapview
        if mv is None or abs(d) < 1e-6:
            return
        eff = _effective_zoom(mv)
        if d > 0 and eff >= _MAX_ZOOM:
            return
        if d < 0 and eff <= _MIN_ZOOM:
            return
        cx, cy = mv.center_x, mv.center_y
        try:
            mv.diff_scale_at(float(d), cx, cy)
        except Exception:
            try:
                mv.zoom = int(round(float(mv.zoom) + (1 if d > 0 else -1)))
            except Exception:
                pass
        self._refresh_overlay()

    def _current_radius_m(self):
        # Oblicza aktualny promień geofence w metrach na podstawie tego
        # jak bardzo mapa jest przybliżona. Im bardziej oddalona mapa,
        # tym większy obszar koła w rzeczywistości.
        # Wzór: promień = (widoczny obszar / 2) * metry na piksel
        # Maksymalny promień to 1000 metrów.
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return _DEFAULT_RADIUS_M
        short_px = min(self._mapview.width, self._mapview.height)
        if short_px <= 1:
            return _DEFAULT_RADIUS_M
        zoom = _effective_zoom(self._mapview)
        lat = float(self._mapview.lat)
        mpp = _meters_per_pixel(lat, zoom)
        if mpp <= 0:
            return _DEFAULT_RADIUS_M
        visual_d_px = short_px * _VIEWPORT_FRACTION
        radius_m = (visual_d_px / 2.0) * mpp
        return max(1.0, min(_MAX_RADIUS_M, radius_m))

    def _refresh_overlay(self):
        # Odświeża nakładkę koła i etykietę z promieniem.
        # Gdy użytkownik przesuwa mapę lub zmienia zoom, koło musi
        # zmienić swój rozmiar (bo ten sam obszar w metrach to inna
        # liczba pikseli na ekranie przy różnym przybliżeniu).
        # Aktualizuje też tekst z promieniem (np. "150 m").
        if not _MAPVIEW_AVAILABLE or self._mapview is None or self._overlay is None:
            return
        short_px = min(self._mapview.width, self._mapview.height)
        if short_px <= 1:
            return
        zoom = _effective_zoom(self._mapview)
        lat = float(self._mapview.lat)
        mpp = _meters_per_pixel(lat, zoom)
        if mpp <= 0:
            return
        target_radius_m = (short_px * _VIEWPORT_FRACTION / 2.0) * mpp
        actual_radius_m = max(1.0, min(_MAX_RADIUS_M, target_radius_m))
        diameter_px = max(dp(12), (2.0 * actual_radius_m) / mpp)
        self._overlay.pos = self._mapview.pos
        self._overlay.size = self._mapview.size
        self._overlay.diameter_px = diameter_px
        self.radius_text = f"{int(round(actual_radius_m))} m"
        if self._radius_label is not None:
            self._radius_label.text = self.radius_text

    # Próbuje ustawić daną właściwość na obiekcie – jeśli się nie uda,
    # po prostu pomija błąd (zabezpieczenie przed brakującą właściwością).
    @staticmethod
    def _safe_set(obj, attr, value):
        try:
            setattr(obj, attr, value)
        except Exception:
            pass

    # Ustawia przybliżenie mapy na podaną wartość (w zakresie 12–19).
    def _set_smooth_zoom(self, zoom):
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return
        z = max(_MIN_ZOOM, min(_MAX_ZOOM, float(zoom)))
        try:
            self._mapview.zoom = z
        except Exception:
            self._mapview.zoom = int(round(z))

    # Zwraca aktualne ustawienia geofence: szerokość i długość geograficzną
    # środka, promień w metrach oraz poziom przybliżenia mapy.
    def _current_result(self):
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return None
        return {
            "lat": float(self._mapview.lat),
            "lon": float(self._mapview.lon),
            "radius_m": float(self._current_radius_m()),
            "zoom": float(_effective_zoom(self._mapview)),
        }

    # Zapisuje wybrany geofence i wraca do poprzedniego ekranu.
    # Jeśli mapa nie jest dostępna – anuluje bez zapisu.
    def _save_and_return(self):
        gf = self._current_result()
        if gf is None:
            self._finish({"action": "cancel"})
        else:
            self._finish({"action": "save", "geofence": gf})

    # Czyści zaznaczony geofence (usuwa) i wraca do poprzedniego ekranu.
    def _clear_and_return(self):
        self._finish({"action": "clear"})

    # Anuluje wybór i wraca do poprzedniego ekranu bez zapisywania.
    def _cancel(self):
        self._finish({"action": "cancel"})

    # Kończy działanie ekranu geofence: wywołuje funkcję zwrotną
    # z wynikiem (zapis, wyczyszczenie lub anulowanie), a potem wraca
    # do poprzedniego ekranu.
    def _finish(self, result):
        cb = self._on_done
        self._on_done = None
        try:
            if cb is not None:
                cb(result)
        finally:
            self._navigate_back()

    # Przełącza aplikację z powrotem na ekran, z którego przyszliśmy
    # (np. ekran projektu lub strony głównej).
    def _navigate_back(self):
        app = MDApp.get_running_app()
        if app is None or app.root is None:
            return
        target = self.return_screen or "home"
        try:
            app.root.current = target
        except Exception:
            app.root.current = "home"
