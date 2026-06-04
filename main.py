# ---------------------------------------------------------------------------
# GŁÓWNY PLIK APLIKACJI – punkt startowy programu
# ---------------------------------------------------------------------------
# Ten plik uruchamia całą aplikację. Najpierw konfiguruje okno (miękką
# klawiaturę w trybie "resize"), a potem tworzy główny obiekt aplikacji
# i uruchamia go. Aplikacja działa na systemie Kivy – jest to framework
# do tworzenia aplikacji mobilnych i desktopowych w języku Python.
# 
# CO TO JEST "FRAMEWORK"?
# To zbiór gotowych narzędzi i reguł, które pomagają programiście budować
# aplikację szybciej – zamiast pisać wszystko od zera, korzysta się z
# gotowych elementów (np. przycisków, pól tekstowych, ekranów).
# ---------------------------------------------------------------------------

import json
import os

from kivy.config import Config

# Ta linia musi być wykonana ZANIM okno aplikacji zostanie utworzone
# (szczególnie ważne na Androidzie). Ustawia tryb miękkiej klawiatury
# na "resize" – oznacza to, że gdy klawiatura się pojawi, okno aplikacji
# zmniejszy się, aby zrobić dla niej miejsce.
Config.set("graphics", "softinput_mode", "resize")

from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.utils import platform
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.screenmanager import ScreenManager, NoTransition

# Tylko ekran główny (HomeScreen) jest importowany na starcie.
# Pozostałe ekrany są ładowane DOPIERO po wyświetleniu pierwszej klatki
# (czyli po pojawieniu się ekranu głównego). Dzięki temu użytkownik widzi
# aplikację od razu, bez czekania na ładowanie wszystkiego.
from screens.home import HomeScreen


# ---------------------------------------------------------------------------
# LENIWY MENEDŻER EKRANÓW – ładuje ekrany dopiero gdy są potrzebne
# ---------------------------------------------------------------------------
# Menedżer ekranów to element który przełącza między różnymi "ekranami"
# aplikacji (jak slajdy w prezentacji). Ten konkretny menedżer opóźnia
# tworzenie ekranów – buduje je dopiero w momencie, gdy użytkownik
# pierwszy raz chce je zobaczyć. Dzięki temu aplikacja szybciej się uruchamia.
# ---------------------------------------------------------------------------

class LazyScreenManager(ScreenManager):
    def get_screen(self, name):
        # Jeśli ekran o podanej nazwie nie istnieje, zbuduj go
        if not any(s.name == name for s in self.screens):
            app = MDApp.get_running_app()
            if app is not None:
                try:
                    app._ensure_screen(name)
                except Exception:
                    pass
        return super().get_screen(name)


# Na komputerze (Windows, Linux, Mac) ustawiamy rozmiar okna na 450x900
# żeby symulować wygląd na telefonie.
if platform in ('win', 'linux', 'macosx'):
    Window.size = (450, 900)


# Lista wszystkich ekranów które będą ładowane "leniwie" (dopiero gdy będą
# potrzebne). Każdy wpis zawiera: nazwę ekranu, ścieżkę do pliku .kv
# (opisującego wygląd), ścieżkę do modułu Python (logika) i nazwę klasy.
# Kolejność ma znaczenie – pliki .kv muszą być ładowane w odpowiedniej
# kolejności, aby elementy zdefiniowane w jednym były dostępne w drugim.
_LAZY_SCREENS = [
    ("add_project",      "kv/addProject.kv",      "screens.add_project",      "AddProjectScreen"),
    ("statistics",       "kv/statistics.kv",      "screens.statistics",       "StatisticsScreen"),
    ("project_info",     "kv/project_info.kv",    "screens.project_info",     "ProjectInfoScreen"),
    ("project_settings", "kv/projectSettings.kv", "screens.project_settings", "ProjectSettingsScreen"),
    ("geofence_picker",  None,                    "screens.geofence_picker",  "GeofencePickerScreen"),
]


# ---------------------------------------------------------------------------
# GŁÓWNA KLASA APLIKACJI
# ---------------------------------------------------------------------------
# To jest najważniejsza klasa w programie. Zawiera wszystkie ustawienia
# (np. kolory motywu) i metody do zarządzania aplikacją. Dziedziczy po
# MDApp – czyli gotowej klasie z frameworka KivyMD, która dostarcza
# podstawowe funkcje aplikacji (uruchamianie, zamykanie itp.).
# ---------------------------------------------------------------------------

class TimeTrackerApp(MDApp):
    # Właściwości (kolory motywu) – zmieniają wygląd całej aplikacji
    theme_bg = StringProperty('#8A2BE2')
    theme_card_bg = StringProperty('#B388FF')
    theme_session_bg = StringProperty('#5E35B1')
    theme_session_header = StringProperty('#E8D5FC')
    theme_text_dark = StringProperty('#212121')
    grid_layout = BooleanProperty(False)

    def build(self):
        # Na starcie ładujemy tylko plik wyglądu ekranu głównego (home.kv).
        # Reszta zostanie załadowana później (patrz _finalize_startup).
        Builder.load_file("kv/home.kv")

        # Tworzymy menedżer ekranów z płynnym przejściem (NoTransition =
        # brak animacji, ekran zmienia się natychmiast).
        self.screen_manager = LazyScreenManager(transition=NoTransition())
        self.screen_manager.add_widget(HomeScreen(name='home'))
        return self.screen_manager

    def on_start(self):
        # Ta funkcja uruchamia się PO tym, jak aplikacja się już pokazała.
        if platform == "android":
            try:
                Window.softinput_mode = "resize"
            except Exception:
                pass

        # Migracja danych: nadaje każdemu projektowi unikalny identyfikator
        # (UID). Wcześniej projekty były rozpoznawane po nazwie, ale to
        # powodowało problemy gdy dwa projekty miały tę samą nazwę.
        # Teraz każdy projekt ma swój niepowtarzalny numer.
        try:
            from screens import active_timer
            active_timer.migrate_legacy_state_to_uids()
        except Exception as exc:
            print(f"[main] uid migration failed: {exc!r}")

        # Ładujemy zapisane projekty i odświeżamy ekran główny
        home_screen = self.screen_manager.get_screen('home')
        self.load_layout_pref()
        home_screen.load_projects()
        home_screen.schedule_initial_layout()
        home_screen.refresh_last_session()

        # Reszta inicjalizacji (wczytywanie emoji, budowanie pozostałych
        # ekranów) jest odkładana na następną klatkę – dzięki temu
        # użytkownik od razu widzi ekran główny.
        Clock.schedule_once(self._finalize_startup, 0)

    # Inicjalizacja po pierwszej klatce – rzeczy które nie muszą być
    # zrobione natychmiast, ale są potrzebne później.
    def _finalize_startup(self, *_args):
        
        if platform == "android":
            self._request_android_notification_permission()

        # Rozpakowanie plików z emoji (jeśli jeszcze nie były rozpakowane)
        try:
            from screens.emoji_assets import ensure_emoji_assets
            ensure_emoji_assets()
        except Exception:
            pass

        # Budowanie pozostałych ekranów – jeden ekran na jedną klatkę
        # (żeby nie zamrozić interfejsu)
        self._lazy_build_queue = list(_LAZY_SCREENS)
        Clock.schedule_once(self._build_next_lazy_screen, 0)

    # Buduje kolejny ekran z kolejki. Gdy wszystkie gotowe, wywołuje
    # funkcję _after_all_screens_built.
    def _build_next_lazy_screen(self, *_args):
        queue = getattr(self, "_lazy_build_queue", None)
        if not queue:
            self._after_all_screens_built()
            return
        name, kv, module_path, class_name = queue.pop(0)
        self._ensure_screen(name, kv, module_path, class_name)
        Clock.schedule_once(self._build_next_lazy_screen, 0)

    # Tworzy ekran jeśli jeszcze nie istnieje. Można ją wywołać z
    # samą nazwą ekranu, a resztę parametrów odczyta z listy _LAZY_SCREENS.
    # Funkcja jest "bezpieczna do wielokrotnego wywołania" – jeśli ekran już istnieje, nic nie robi.
    def _ensure_screen(self, name, kv=None, module_path=None, class_name=None):
        for s in self.screen_manager.screens:
            if s.name == name:
                return s
        if kv is None and module_path is None:
            for spec_name, spec_kv, spec_mod, spec_cls in _LAZY_SCREENS:
                if spec_name == name:
                    kv, module_path, class_name = spec_kv, spec_mod, spec_cls
                    break
        if module_path is None:
            return None
        if kv:
            try:
                Builder.load_file(kv)
            except Exception:
                pass
        try:
            mod = __import__(module_path, fromlist=[class_name])
            cls = getattr(mod, class_name)
            screen = cls(name=name)
            self.screen_manager.add_widget(screen)
            return screen
        except Exception:
            return None

    # Po zbudowaniu wszystkich ekranów: odśwież statystyki,
    # uruchom usługę timera (na Androidzie) i obsłuż intencję.
    def _after_all_screens_built(self):
        try:
            self.screen_manager.get_screen("statistics").refresh_statistics()
        except Exception:
            pass
        try:
            from screens import active_timer
            if active_timer.has_active_items():
                from screens.project_info import ensure_android_timer_service
                ensure_android_timer_service()
        except Exception:
            pass
        Clock.schedule_once(
            lambda _dt: self._open_project_from_android_intent_or_active(), 0
        )

    # Gdy aplikacja wraca na pierwszy plan (np. po minimalizacji),
    # sprawdź czy nie powinniśmy otworzyć projektu z intencji.
    def on_resume(self):
        Clock.schedule_once(
            lambda _dt: self._open_project_from_android_intent_or_active(prefer_active=False), 0
        )
        return True

    # Prosi o pozwolenie na wyświetlanie powiadomień (tylko Android 13+).
    # Wcześniejsze wersje Androida nie wymagają tego pozwolenia.
    def _request_android_notification_permission(self):
        try:
            from jnius import autoclass
            version = autoclass("android.os.Build$VERSION")
            if int(version.SDK_INT) < 33:
                return
            from android.permissions import request_permissions
            request_permissions(["android.permission.POST_NOTIFICATIONS"])
        except Exception:
            pass

    # Sprawdza czy aplikacja została otwarta z powiadomienia
    # (np. kliknięcie w notyfikację o aktywnym timerze) i zwraca
    # nazwę projektu, który należy otworzyć.
    # Na Androidzie Intent może przekazać dodatkowe dane (extras).
    def _android_intent_project(self):
        if platform != "android":
            return ""
        try:
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            intent = activity.getIntent()
            project = intent.getStringExtra("project") or ""
            if project:
                intent.removeExtra("project")
            return project
        except Exception:
            return ""

    # Otwiera ekran projektu – albo z intencji (powiadomienie),
    # albo aktywnego timera jeśli jakiś jest włączony.
    # "prefer_active" – jeśli True, gdy nie ma intencji, otwiera projekt
    # z aktywnego timera. Jeśli False, otwiera tylko z intencji.
    def _open_project_from_android_intent_or_active(self, prefer_active=True):
        from screens import active_timer
        project = self._android_intent_project()
        project_uid = ""
        if not project and prefer_active:
            timer_state = active_timer.read_project_timer()
            project = timer_state.get("project_title", "")
            project_uid = timer_state.get("project_uid", "")
            if not project:
                goals = active_timer.read_goals()
                if goals:
                    project = goals[0].get("project_title", "")
                    project_uid = goals[0].get("project_uid", "")
        if not project_uid and project:
            for meta in active_timer._read_projects():
                if meta.get("title") == project:
                    project_uid = meta.get("uid", "")
                    break
        if project:
            info = self._ensure_screen("project_info")
            if info is None:
                return
            info.project_uid = project_uid
            info.project_title = project
            self.screen_manager.current = "project_info"

    # Zwraca ścieżkę do pliku layout_pref.json, który przechowuje
    # preferencję użytkownika: czy karty na ekranie głównym mają być
    # ułożone w siatkę czy swobodnie.
    def _layout_pref_path(self):
        return os.path.join(self.user_data_dir, "layout_pref.json")

    # Wczytuje preferencję układu (siatka/swobodny) z pliku.
    # Plik zawiera JSON z kluczem "grid_layout" (True/False).
    def load_layout_pref(self):
        path = self._layout_pref_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.grid_layout = bool(data.get("grid_layout", False))
        except (OSError, json.JSONDecodeError):
            pass

    # Zapisuje preferencję układu (siatka/swobodny) do pliku.
    def save_layout_pref(self):
        path = self._layout_pref_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"grid_layout": self.grid_layout}, f)
        except OSError:
            pass

    # Przełącza między widokiem siatki a widokiem swobodnym
    # (karty można przeciągać). Po przełączeniu natychmiast układa karty.
    def toggle_layout_menu(self):
        self.grid_layout = not self.grid_layout
        self.save_layout_pref()
        home = self.screen_manager.get_screen("home")
        if self.grid_layout:
            home.apply_grid_layout()
        else:
            home.restore_card_positions()


# ---------------------------------------------------------------------------
# URUCHOMIENIE APLIKACJI
# ---------------------------------------------------------------------------
# Ta część wykonuje się gdy plik main.py jest uruchomiony bezpośrednio
# (python main.py). Tworzy obiekt aplikacji i uruchamia ją.
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    TimeTrackerApp().run()