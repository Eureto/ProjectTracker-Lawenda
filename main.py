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
# "json" – wbudowany moduł do odczytu/zapisu plików w formacie JSON
# (zapisuje i odczytuje np. preferencje układu ekranu głównego).

import os
# "os" – funkcje systemowe: sprawdzanie czy plik istnieje, łączenie ścieżek.

from kivy.config import Config
# "Config" – ustawienia Kivy (np. jak ma działać klawiatura).

# Ta linia musi być wykonana ZANIM okno aplikacji zostanie utworzone
# (szczególnie ważne na Androidzie). Ustawia tryb miękkiej klawiatury
# na "resize" – oznacza to, że gdy klawiatura się pojawi, okno aplikacji
# zmniejszy się, aby zrobić dla niej miejsce.
Config.set("graphics", "softinput_mode", "resize")
# Mówi Kivy: "Gdy klawiatura się pojawi – zmniejsz okno, żeby było miejsce".
# Dzięki temu pola tekstowe nie są zasłonięte przez klawiaturę.

from kivymd.app import MDApp
# "MDApp" – główna klasa aplikacji KivyMD. Zawiera podstawowe funkcje
# (uruchamianie, zamykanie) i zarządza ustawieniami (motyw, kolory).

from kivy.lang import Builder
# "Builder" – wczytuje pliki .kv (opisujące wygląd ekranów) i tworzy
# z nich prawdziwe widoki.

from kivy.core.window import Window
# "Window" – okno aplikacji. Możemy ustawić jego rozmiar, zachowanie
# klawiatury itp.

from kivy.utils import platform
# "platform" – mówi na jakim systemie działa aplikacja
# ("android", "ios", "linux", "win").

from kivy.clock import Clock
# "Clock" – narzędzie Kivy do planowania zadań na później
# (np. odświeżenie ekranu po zapisaniu danych).

from kivy.properties import StringProperty, BooleanProperty
# "StringProperty" – właściwość przechowująca tekst.
# "BooleanProperty" – właściwość przechowująca prawda/fałsz.
# Gdy zmieniają wartość – Kivy automatycznie odświeża ekran.

from kivy.uix.screenmanager import ScreenManager, NoTransition
# "ScreenManager" – przełącznik ekranów. Przechowuje wszystkie ekrany
# i umożliwia przełączanie między nimi (jak slajdy).
# "NoTransition" – przejście bez animacji (natychmiastowe).

# Tylko ekran główny (HomeScreen) jest importowany na starcie.
# Pozostałe ekrany są ładowane DOPIERO po wyświetleniu pierwszej klatki
# (czyli po pojawieniu się ekranu głównego). Dzięki temu użytkownik widzi
# aplikację od razu, bez czekania na ładowanie wszystkiego.
from screens.home import HomeScreen
# Importuje klasę ekranu głównego – to jedyny ekran ładowany od razu.


# ---------------------------------------------------------------------------
# LENIWY MENEDŻER EKRANÓW – ładuje ekrany dopiero gdy są potrzebne
# ---------------------------------------------------------------------------
# Menedżer ekranów to element który przełącza między różnymi "ekranami"
# aplikacji (jak slajdy w prezentacji). Ten konkretny menedżer opóźnia
# tworzenie ekranów – buduje je dopiero w momencie, gdy użytkownik
# pierwszy raz chce je zobaczyć. Dzięki temu aplikacja szybciej się uruchamia.
# ---------------------------------------------------------------------------

class LazyScreenManager(ScreenManager):
    # "LazyScreenManager" – menedżer ekranów, który tworzy ekrany dopiero
    # gdy są potrzebne (leniwe ładowanie). Dzięki temu aplikacja uruchamia
    # się szybciej, bo nie ładuje od razu wszystkich ekranów.

    def get_screen(self, name):
        # Jeśli ekran o podanej nazwie nie istnieje, zbuduj go
        # (dopiero gdy użytkownik pierwszy raz chce go zobaczyć).
        if not any(s.name == name for s in self.screens):
            app = MDApp.get_running_app()
            # Pobiera aktualnie uruchomioną aplikację.

            if app is not None:
                try:
                    app._ensure_screen(name)
                    # Jeśli ekran nie istnieje – buduje go (ładuje plik .kv
                    # i tworzy klasę Python).
                except Exception:
                    pass
        return super().get_screen(name)
        # Wywołuje standardowe get_screen z ScreenManager (zwraca ekran).


# Na komputerze (Windows, Linux, Mac) ustawiamy rozmiar okna na 450x900
# żeby symulować wygląd na telefonie.
if platform in ('win', 'linux', 'macosx'):
    Window.size = (450, 900)
    # Ustawia rozmiar okna na 450x900 pikseli (jak smartfon).
    # Dzięki temu aplikacja wygląda na komputerze podobnie jak na telefonie.


# Lista wszystkich ekranów które będą ładowane "leniwie" (dopiero gdy będą
# potrzebne). Każdy wpis zawiera: nazwę ekranu, ścieżkę do pliku .kv
# (opisującego wygląd), ścieżkę do modułu Python (logika) i nazwę klasy.
# Kolejność ma znaczenie – pliki .kv muszą być ładowane w odpowiedniej
# kolejności, aby elementy zdefiniowane w jednym były dostępne w drugim.
_LAZY_SCREENS = [
    ("add_project",      os.path.join("kv", "addProject.kv"),      "screens.add_project",      "AddProjectScreen"),
    ("statistics",       os.path.join("kv", "statistics.kv"),      "screens.statistics",       "StatisticsScreen"),
    ("project_info",     os.path.join("kv", "project_info.kv"),    "screens.project_info",     "ProjectInfoScreen"),
    ("project_settings", os.path.join("kv", "projectSettings.kv"), "screens.project_settings", "ProjectSettingsScreen"),
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
    # "TimeTrackerApp" – główna klasa aplikacji. Dziedziczy po MDApp
    # (KivyMD). Zarządza ekranami, ustawieniami i inicjalizacją.

    # Właściwości (kolory motywu) – zmieniają wygląd całej aplikacji

    theme_bg = StringProperty('#8A2BE2')
    # Kolor tła aplikacji – fioletowy (#8A2BE2 = BlueViolet).

    theme_card_bg = StringProperty('#B388FF')
    # Kolor tła kart projektów – jasny fiolet.

    theme_session_bg = StringProperty('#5E35B1')
    # Kolor tła karty ostatniej sesji – ciemniejszy fiolet.

    theme_session_header = StringProperty('#E8D5FC')
    # Kolor nagłówka karty sesji – bardzo jasny fiolet.

    theme_text_dark = StringProperty('#212121')
    # Kolor ciemnego tekstu – prawie czarny (#212121).

    grid_layout = BooleanProperty(False)
    # Czy karty na ekranie głównym są w siatce (True) czy swobodnie (False).
    # Użytkownik może przełączać między tymi trybami.

    def build(self):
        # Na starcie ładujemy tylko plik wyglądu ekranu głównego (home.kv).
        # Reszta zostanie załadowana później (patrz _finalize_startup).
        Builder.load_file(os.path.join("kv", "home.kv"))
        # Wczytuje plik home.kv (wygląd ekranu głównego) z folderu "kv".

        # Tworzymy menedżer ekranów z płynnym przejściem (NoTransition =
        # brak animacji, ekran zmienia się natychmiast).
        self.screen_manager = LazyScreenManager(transition=NoTransition())
        # Tworzy menedżer ekranów bez animacji przejścia.

        self.screen_manager.add_widget(HomeScreen(name='home'))
        # Dodaje ekran główny do menedżera. "name" to identyfikator ekranu.

        return self.screen_manager
        # Zwraca menedżer ekranów – Kivy wyświetli go jako główny widok.

    def on_start(self):
        # Ta funkcja uruchamia się PO tym, jak aplikacja się już pokazała.
        if platform == "android":
            try:
                Window.softinput_mode = "resize"
                # Na Androidzie ustawiam tryb klawiatury na "resize"
                # (okno zmniejsza się gdy klawiatura się pojawi).
            except Exception:
                pass

        # Migracja danych: nadaje każdemu projektowi unikalny identyfikator
        # (UID). Wcześniej projekty były rozpoznawane po nazwie, ale to
        # powodowało problemy gdy dwa projekty miały tę samą nazwę.
        # Teraz każdy projekt ma swój niepowtarzalny numer.
        try:
            from screens import active_timer
            active_timer.migrate_legacy_state_to_uids()
            # Nadaje UID wszystkim projektom, które go jeszcze nie mają.
        except Exception as exc:
            print(f"[main] uid migration failed: {exc!r}")

        # Ładujemy zapisane projekty i odświeżamy ekran główny
        home_screen = self.screen_manager.get_screen('home')
        # Pobiera ekran główny.

        self.load_layout_pref()
        # Wczytuje preferencję układu (siatka/swobodny) z pliku.

        home_screen.load_projects()
        # Ładuje karty projektów na ekran główny.

        home_screen.schedule_initial_layout()
        # Planuje początkowe ułożenie kart (zgodnie z preferencją).

        home_screen.refresh_last_session()
        # Odświeża kartę ostatniej sesji.

        # Reszta inicjalizacji (wczytywanie emoji, budowanie pozostałych
        # ekranów) jest odkładana na następną klatkę – dzięki temu
        # użytkownik od razu widzi ekran główny.
        Clock.schedule_once(self._finalize_startup, 0)
        # Planuje dalszą inicjalizację na "za chwilę" (0 sekund).

    # Inicjalizacja po pierwszej klatce – rzeczy które nie muszą być
    # zrobione natychmiast, ale są potrzebne później.
    def _finalize_startup(self, *_args):
        if platform == "android":
            self._request_android_notification_permission()
            # Prosi o pozwolenie na powiadomienia (Android 13+).

        # Rozpakowanie plików z emoji (jeśli jeszcze nie były rozpakowane)
        try:
            from screens.emoji_assets import ensure_emoji_assets
            ensure_emoji_assets()
            # Rozpakowuje pliki PNG z emoji do folderu aplikacji.
        except Exception:
            pass

        # Budowanie pozostałych ekranów – jeden ekran na jedną klatkę
        # (żeby nie zamrozić interfejsu)
        self._lazy_build_queue = list(_LAZY_SCREENS)
        # Tworzy kolejkę ekranów do zbudowania (kopię listy _LAZY_SCREENS).

        Clock.schedule_once(self._build_next_lazy_screen, 0)
        # Zaczyna budować pierwszy ekran z kolejki.

    # Buduje kolejny ekran z kolejki. Gdy wszystkie gotowe, wywołuje
    # funkcję _after_all_screens_built.
    def _build_next_lazy_screen(self, *_args):
        queue = getattr(self, "_lazy_build_queue", None)
        # Pobiera kolejkę ekranów do zbudowania.

        if not queue:
            self._after_all_screens_built()
            return
            # Jeśli kolejka jest pusta (wszystkie ekrany gotowe) –
            # wywołuje funkcję końcową i kończy.

        name, kv, module_path, class_name = queue.pop(0)
        # Pobiera dane pierwszego ekranu z kolejki i usuwa go.

        self._ensure_screen(name, kv, module_path, class_name)
        # Buduje ekran (ładuje plik .kv i tworzy klasę).

        Clock.schedule_once(self._build_next_lazy_screen, 0)
        # Planuje budowę kolejnego ekranu na następną klatkę
        # (żeby nie zamrozić interfejsu).

    # Tworzy ekran jeśli jeszcze nie istnieje. Można ją wywołać z
    # samą nazwą ekranu, a resztę parametrów odczyta z listy _LAZY_SCREENS.
    # Funkcja jest "bezpieczna do wielokrotnego wywołania" – jeśli ekran już istnieje, nic nie robi.
    def _ensure_screen(self, name, kv=None, module_path=None, class_name=None):
        for s in self.screen_manager.screens:
            if s.name == name:
                return s
                # Jeśli ekran już istnieje – zwróć go (nic nie rób).

        if kv is None and module_path is None:
            for spec_name, spec_kv, spec_mod, spec_cls in _LAZY_SCREENS:
                if spec_name == name:
                    kv, module_path, class_name = spec_kv, spec_mod, spec_cls
                    break
                    # Jeśli nie podano pliku .kv ani modułu – szukamy
                    # w liście _LAZY_SCREENS.

        if module_path is None:
            return None
            # Jeśli nadal nie ma modułu – nie da się zbudować ekranu.

        if kv:
            try:
                Builder.load_file(kv)
                # Ładuje plik .kv z wyglądem ekranu.
            except Exception:
                pass

        try:
            mod = __import__(module_path, fromlist=[class_name])
            # Importuje moduł Python (np. "screens.add_project").

            cls = getattr(mod, class_name)
            # Pobiera klasę ekranu z modułu (np. AddProjectScreen).

            screen = cls(name=name)
            # Tworzy instancję ekranu z podaną nazwą.

            self.screen_manager.add_widget(screen)
            # Dodaje ekran do menedżera ekranów.

            return screen
            # Zwraca nowo utworzony ekran.
        except Exception:
            return None
            # Jeśli coś poszło nie tak – zwraca None.

    # Po zbudowaniu wszystkich ekranów: odśwież statystyki,
    # uruchom usługę timera (na Androidzie) i obsłuż intencję.
    def _after_all_screens_built(self):
        try:
            self.screen_manager.get_screen("statistics").refresh_statistics()
            # Odświeża dane na ekranie statystyk.
        except Exception:
            pass

        try:
            from screens import active_timer
            if active_timer.has_active_items():
                from screens.project_info import ensure_android_timer_service
                ensure_android_timer_service()
                # Jeśli jest aktywny timer – uruchamia usługę timera
                # (na Androidzie, żeby timer działał w tle).
        except Exception:
            pass

        Clock.schedule_once(
            lambda _dt: self._open_project_from_android_intent_or_active(), 0
        )
        # Sprawdza czy aplikacja została otwarta z powiadomienia
        # (np. kliknięcie w notyfikację) i otwiera odpowiedni projekt.

    # Gdy aplikacja wraca na pierwszy plan (np. po minimalizacji),
    # sprawdź czy nie powinniśmy otworzyć projektu z intencji.
    def on_resume(self):
        Clock.schedule_once(
            lambda _dt: self._open_project_from_android_intent_or_active(prefer_active=False), 0
        )
        # Planuje sprawdzenie intencji na następną klatkę.
        return True
        # Mówi Kivy: "kontynuuj wznawianie aplikacji".

    # Prosi o pozwolenie na wyświetlanie powiadomień (tylko Android 13+).
    # Wcześniejsze wersje Androida nie wymagają tego pozwolenia.
    def _request_android_notification_permission(self):
        try:
            from jnius import autoclass
            version = autoclass("android.os.Build$VERSION")
            # Pobiera wersję Androida (SDK_INT).

            if int(version.SDK_INT) < 33:
                return
                # Jeśli Android jest starszy niż 13 (API 33) – nie trzeba
                # pytać o pozwolenie na powiadomienia.

            from android.permissions import request_permissions
            request_permissions(["android.permission.POST_NOTIFICATIONS"])
            # Prosi użytkownika o pozwolenie na powiadomienia.
        except Exception:
            pass

    # Sprawdza czy aplikacja została otwarta z powiadomienia
    # (np. kliknięcie w notyfikację o aktywnym timerze) i zwraca
    # nazwę projektu, który należy otworzyć.
    # Na Androidzie Intent może przekazać dodatkowe dane (extras).
    def _android_intent_project(self):
        if platform != "android":
            return ""
            # Jeśli nie Android – nie ma intencji.

        try:
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            # Pobiera aktywność Androida (okno aplikacji).

            intent = activity.getIntent()
            # Pobiera intencję (dane przekazane przy otwarciu aplikacji).

            project = intent.getStringExtra("project") or ""
            # Wyciąga nazwę projektu z intencji (jeśli była przekazana).

            if project:
                intent.removeExtra("project")
                # Usuwa dane z intencji (żeby nie otwierać ponownie).

            return project
            # Zwraca nazwę projektu do otwarcia.
        except Exception:
            return ""

    # Otwiera ekran projektu – albo z intencji (powiadomienie),
    # albo aktywnego timera jeśli jakiś jest włączony.
    # "prefer_active" – jeśli True, gdy nie ma intencji, otwiera projekt
    # z aktywnego timera. Jeśli False, otwiera tylko z intencji.
    def _open_project_from_android_intent_or_active(self, prefer_active=True):
        from screens import active_timer
        # Importuje moduł aktywnego timera.

        project = self._android_intent_project()
        # Sprawdza czy aplikacja została otwarta z powiadomienia.

        project_uid = ""
        # Na razie nie znamy UID projektu.

        if not project and prefer_active:
            # Jeśli nie ma intencji i preferujemy aktywny timer...
            timer_state = active_timer.read_project_timer()
            # Sprawdza czy jest aktywny timer projektu.

            project = timer_state.get("project_title", "")
            project_uid = timer_state.get("project_uid", "")
            # Pobiera nazwę i UID projektu z aktywnego timera.

            if not project:
                goals = active_timer.read_goals()
                if goals:
                    project = goals[0].get("project_title", "")
                    project_uid = goals[0].get("project_uid", "")
                    # Jeśli nie ma timera – sprawdza czy są aktywne cele
                    # czasowe i otwiera projekt z pierwszego celu.

        if not project_uid and project:
            for meta in active_timer._read_projects():
                if meta.get("title") == project:
                    project_uid = meta.get("uid", "")
                    break
                    # Jeśli znamy nazwę projektu ale nie UID – szukamy UID
                    # w liście projektów.

        if project:
            info = self._ensure_screen("project_info")
            # Upewnia się, że ekran projektu istnieje (jeśli nie – buduje go).

            if info is None:
                return
                # Jeśli ekran nie istnieje – przerwij.

            info.project_uid = project_uid
            info.project_title = project
            # Ustawia dane projektu na ekranie szczegółów.

            self.screen_manager.current = "project_info"
            # Przełącza na ekran szczegółów projektu.

    # Zwraca ścieżkę do pliku layout_pref.json, który przechowuje
    # preferencję użytkownika: czy karty na ekranie głównym mają być
    # ułożone w siatkę czy swobodnie.
    def _layout_pref_path(self):
        return os.path.join(self.user_data_dir, "layout_pref.json")
        # Łączy: prywatny folder aplikacji + "layout_pref.json".

    # Wczytuje preferencję układu (siatka/swobodny) z pliku.
    # Plik zawiera JSON z kluczem "grid_layout" (True/False).
    def load_layout_pref(self):
        path = self._layout_pref_path()
        # Pobiera ścieżkę do pliku z preferencją.

        if not os.path.exists(path):
            return
            # Jeśli plik nie istnieje – nie ma co wczytywać.

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Otwiera plik i odczytuje JSON.

            self.grid_layout = bool(data.get("grid_layout", False))
            # Ustawia grid_layout na wartość z pliku (lub False jeśli brak).
        except (OSError, json.JSONDecodeError):
            pass
            # Jeśli plik jest uszkodzony – ignorujemy.

    # Zapisuje preferencję układu (siatka/swobodny) do pliku.
    def save_layout_pref(self):
        path = self._layout_pref_path()
        # Pobiera ścieżkę do pliku z preferencją.

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"grid_layout": self.grid_layout}, f)
                # Zapisuje aktualne ustawienie grid_layout do pliku JSON.
        except OSError:
            pass
            # Jeśli nie da się zapisać – ignorujemy.

    # Przełącza między widokiem siatki a widokiem swobodnym
    # (karty można przeciągać). Po przełączeniu natychmiast układa karty.
    def toggle_layout_menu(self):
        self.grid_layout = not self.grid_layout
        # Odwraca wartość: jeśli była siatka → będzie swobodny i odwrotnie.

        self.save_layout_pref()
        # Zapisuje preferencję do pliku.

        home = self.screen_manager.get_screen("home")
        # Pobiera ekran główny.

        if self.grid_layout:
            home.apply_grid_layout()
            # Jeśli siatka – układa karty w równych rzędach.
        else:
            home.restore_card_positions()
            # Jeśli swobodny – przywraca zapisane pozycje kart.


# ---------------------------------------------------------------------------
# URUCHOMIENIE APLIKACJI
# ---------------------------------------------------------------------------
# Ta część wykonuje się gdy plik main.py jest uruchomiony bezpośrednio
# (python main.py). Tworzy obiekt aplikacji i uruchamia ją.
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    TimeTrackerApp().run()