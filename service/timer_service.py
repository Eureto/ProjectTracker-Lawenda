# ---------------------------------------------------------------------------
# USŁUGA TIMERA NA ANDROIDZIE – powiadomienia o aktywnym stoperze
# ---------------------------------------------------------------------------
# Ten plik działa jako osobna "usługa" na Androidzie. Gdy użytkownik
# uruchomi stoper i zminimalizuje aplikację, ta usługa utrzymuje
# powiadomienie na pasku statusu, informujące że czas jest mierzony.
# Dzięki temu użytkownik wie, że stoper działa, nawet nie patrząc
# na aplikację.
#
# CO TO JEST "FOREGROUND SERVICE"?
# To specjalny rodzaj usługi na Androidzie, która pokazuje stałe
# powiadomienie. System wie, że to ważne, i nie zabija jej, nawet
# gdy potrzebuje więcej pamięci.
# ---------------------------------------------------------------------------

import os
# "os" – funkcje systemowe: dostęp do ścieżek, zmiennych środowiskowych.

import sys
# "sys" – dostęp do ustawień interpretera Pythona, np. modyfikacja ścieżek
# importów (sys.path), żeby Python widział moduły z folderu głównego.

import time
# "time" – funkcje czasu: time.sleep (czekaj sekundę), time.monotonic
# (dokładny czas do mierzenia interwałów).

import traceback
# "traceback" – zapisuje szczegółowe informacje o błędach (stack trace).
# Używane do logowania błędów, które wystąpiły w usłudze.

import zlib
# "zlib" – kompresja danych. Używamy CRC32 do generowania unikalnych
# numerów powiadomień dla celów czasowych.

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Oblicza ścieżkę do głównego folderu projektu (dwa poziomy wyżej niż ten plik).

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
    # Dodaje główny folder do ścieżek Pythona, żeby importy działały
    # (np. "from screens import active_timer").

from screens import active_timer
# Importuje moduł aktywnego timera – odczytuje stan stopera i celów.

# Identyfikatory dla powiadomień
PACKAGE = "org.stokrotka.stokrotka"
# Nazwa pakietu aplikacji (unikalny identyfikator w Androidzie).

CHANNEL_ID = "running_timers"
# ID kanału powiadomień (wymagane w Android 8+). Użytkownik może
# w ustawieniach systemu wyciszyć ten kanał.

ACTION_STOP_TIMER = f"{PACKAGE}.STOP_TIMER"
# Akcja: zatrzymaj stoper. Wysyłana gdy użytkownik kliknie "Zatrzymaj"
# w powiadomieniu stopera.

ACTION_STOP_GOAL = f"{PACKAGE}.STOP_GOAL"
# Akcja: zatrzymaj cel czasowy. Wysyłana gdy użytkownik kliknie
# "Zatrzymaj" w powiadomieniu celu.

TIMER_NOTIFICATION_ID = 1001
# ID powiadomienia stopera. Unikalny numer, żeby Android wiedział,
# które powiadomienie aktualizować.

GOAL_NOTIFICATION_BASE_ID = 1100
# Numer początkowy dla powiadomień celów. Każdy cel dostaje swój
# numer (base + hash UID), żeby można było je rozróżniać.

PLACEHOLDER_NOTIFICATION_ID = 999
# Tymczasowe powiadomienie podczas uruchamiania usługi. Pokazuje się
# tylko na ułamek sekundy, zanim pojawi się właściwe powiadomienie.

TAG = "ProjectTrackerSvc"
# Tag do logowania – wszystkie wiadomości z usługi będą oznaczone tym
# tagiem, żeby łatwo je znaleźć w logach systemowych.

IDLE_GRACE_SECONDS = 6
# Po 6 sekundach bez aktywnych timerów/celów – zatrzymaj usługę.
# Oszczędza baterię, gdy użytkownik zatrzymał wszystkie stopery.

ACCENT_COLOR = _argb(0xFF, 0x8A, 0x2B, 0xE2)
# Kolor akcentu (fioletowy) dla powiadomień

def _argb(a, r, g, b):
    # Konwertuje cztery składniki koloru (Alpha, Czerwony, Zielony, Niebieski) 
    # z zakresu 0-255 na jedną liczbę całkowitą, która reprezentuje ten kolor 
    # w formacie używanym przez system Android. Jest to potrzebne ponieważ 
    # Android API wymaga kolorów w tej specjalnej postaci liczbowej.
    val = (a << 24) | (r << 16) | (g << 8) | b
    if val >= 0x80000000:
        val -= 0x100000000
    return val


ACCENT_COLOR = _argb(0xFF, 0x8A, 0x2B, 0xE2)


def _logcat(message):
    # Zapisuje wiadomość zarówno w konsoli (print) jak i w logach systemowych Android (logcat) 
    # do celów debugowania. Dzięki temu deweloper może śledzić działanie aplikacji 
    # zarówno podczas testowania na komputerze jak i na urządzeniu Android.
    print(f"{TAG}: {message}", flush=True)
    try:
        from jnius import autoclass
        autoclass("android.util.Log").i(TAG, str(message))
    except Exception:
        pass


def _format_seconds(seconds):
    # Konwertuje liczbę sekund na czytelny format czasu HH:MM:SS (godziny:minuty:sekundy).
    # Na przykład: 3661 sekund zostanie przekonwertowane na "01:01:01" (1 godzina, 1 minuta, 1 sekunda).
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _goal_notification_id(uid):
    # Generuje unikalny numer powiadomienia dla celu czasowego na podstawie jego UID.
    # Używa algorytmu matematycznego (CRC32), który na podstawie identyfikatora celu
    # generuje liczbę – dzięki temu każdy cel dostaje inny numer powiadomienia
    # i system Android może je właściwie rozróżniać.
    return GOAL_NOTIFICATION_BASE_ID + (zlib.crc32(uid.encode("utf-8")) % 8000)


def _goal_progress(goal):
    # Oblicza postęp realizacji celu czasowego.
    # Zwraca cztery wartości:
    #   1. label - opis celu (nazwa lub tekst celu)
    #   2. pct - procent ukończenia celu (0-100)
    #   3. logged - już zalogowany czas w sekundach
    #   4. target - docelowy czas celu w sekundach
    # 
    # Przykład zwracanych wartości: ("Nauka angielskiego", 75, 3600, 4800)
    # oznacza, że cel "Nauka angielskiego" jest ukończony w 75%,
    # użytkownik już spędził na nim 3600 sekund (1 godzina),
    # a całkowity zaplanowany czas to 4800 sekund (1 godzina 20 minut).
    logged = float(goal.get("base_logged_seconds", 0.0)) + active_timer.running_seconds(goal)
    target = max(1.0, float(goal.get("target_seconds", 1.0)))
    pct = int(round(100.0 * logged / target))
    label = goal.get("goal_text") or goal.get("title") or "Cel"
    return label, pct, int(logged), int(target)


def _goal_text(goal):
    # Tworzy czytelny tekst opisujący postęp celu w formacie:
    # "Opis celu - XX% (HH:MM:SS)"
    # gdzie XX to procent ukończenia, a HH:MM:SS to już spędzony czas.
    # 
    # Przykład: "Nauka hiszpańskiego - 45% (02:30:15)"
    label, pct, logged, _ = _goal_progress(goal)
    return f"{label} - {pct}% ({_format_seconds(logged)})"


class TimerNotificationService:
    # Usługa która zarządza powiadomieniami o aktywnym stoperze projektu oraz celach czasowych.
    # Jej głównym zadaniem jest wyświetlanie stałego powiadomienia w pasku statusu Androida,
    # które informuje użytkownika o aktualnie mierzonej aktywności (stopercie lub celach czasowych).
    # Dzięki temu użytkownik wie, że czas jest mierzony nawet gdy aplikacja jest zminimalizowana
    # lub nie jest widoczna na ekranie.
    
    def __init__(self):
        # Przygotowuje usługę poprzez:
        #   1. Połączenie się z Androidem i załadowanie potrzebnych klas
        #   2. Utworzenie kanału powiadomień (wymagane w Android 8.0+)
        #   3. Ustawienie folderu do zapisu danych (takiego samego jak używa główna aplikacja)
        #   4. Uruchomienie nasłuchiwania na przyciski w powiadomieniach (np. "Stop")
        from jnius import autoclass
        # Importuje bibliotekę do łączenia Pythona z Javą (Android).

        self.autoclass = autoclass
        # Zapisuje referencję do funkcji ładującej klasy Javy.

        self.Context = autoclass("android.content.Context")
        self.Intent = autoclass("android.content.Intent")
        self.PendingIntent = autoclass("android.app.PendingIntent")
        self.JavaString = autoclass("java.lang.String")
        self.BuildVersion = autoclass("android.os.Build$VERSION")
        self.sdk_int = int(self.BuildVersion.SDK_INT)
        self.NotificationBuilder = autoclass("android.app.Notification$Builder")
        self.NotificationChannel = autoclass("android.app.NotificationChannel")
        self.NotificationManagerClass = autoclass("android.app.NotificationManager")
        self.BigTextStyle = autoclass("android.app.Notification$BigTextStyle")
        # Ładuje klasy Androida potrzebne do tworzenia powiadomień:
        # Context – dostęp do systemu, Intent – sygnały, PendingIntent –
        # intencje do wykonania później, NotificationBuilder – budowanie
        # powiadomień, NotificationChannel – kanał powiadomień (Android 8+),
        # NotificationManager – zarządzanie powiadomieniami.

        try:
            self.BitmapFactory = autoclass("android.graphics.BitmapFactory")
        except Exception:
            self.BitmapFactory = None
            # Próbuje załadować klasę do tworzenia obrazków (Bitmap).
            # Jeśli nie działa – zapisuje None (powiadomienia będą bez ikony).

        try:
            self.ServiceInfo = autoclass("android.content.pm.ServiceInfo")
        except Exception:
            self.ServiceInfo = None
            # Klasa z informacjami o usługach. Opcjonalna.

        self.PythonActivity = autoclass("org.kivy.android.PythonActivity")
        # Klasa głównego okna aplikacji Kivy na Androidzie.

        self.PythonService = autoclass("org.kivy.android.PythonService")
        # Klasa usługi Kivy na Androidzie (umożliwia działanie w tle).

        self.service = self.PythonService.mService
        # Pobiera obiekt aktualnie uruchomionej usługi Androida.

        self.context = self.service.getApplicationContext()
        # Pobiera kontekst aplikacji (dostęp do systemowych usług).

        self.package_name = self.context.getPackageName()
        # Pobiera nazwę pakietu (np. "org.stokrotka.stokrotka").

        self.manager = self.service.getSystemService(self.Context.NOTIFICATION_SERVICE)
        # Pobiera menedżera powiadomień – przez niego wysyłamy i usuwamy notyfikacje.

        self.icon = self.context.getApplicationInfo().icon
        # Pobiera ikonę aplikacji z zasobów Androida.

        self._receiver = None
        self._foreground_id = None
        self._last_goal_ids = set()
        self._idle_since = None
        self._seen_active = False
        # Inicjalizuje zmienne pomocnicze:
        # _receiver – nasłuchiwacz przycisków w powiadomieniach
        # _foreground_id – ID aktualnego powiadomienia pierwszoplanowego
        # _last_goal_ids – zbiór ID powiadomień celów (do porównania)
        # _idle_since – czas od ostatniej aktywności (do zatrzymania usługi)
        # _seen_active – czy kiedykolwiek była aktywność

        self._large_icon = self._load_large_icon()
        # Ładuje dużą ikonę aplikacji do wyświetlania w powiadomieniach.

        # Ustaw folder do zapisu danych (taki sam jak aplikacja)
        try:
            base_dir = self.service.getFilesDir().getAbsolutePath()
            # Pobiera ścieżkę do prywatnego folderu aplikacji.

            active_timer.set_base_dir(base_dir)
            # Ustawia ten folder jako bazowy dla modułu active_timer.

            _logcat(f"using base_dir={base_dir}")
        except Exception as exc:
            _logcat(f"set_base_dir failed: {exc!r}")

        self._create_channel()
        # Tworzy kanał powiadomień (Android 8+).

        self._start_foreground(PLACEHOLDER_NOTIFICATION_ID, self._placeholder_notification())
        # Uruchamia usługę na pierwszym planie z tymczasowym powiadomieniem.

        self._register_stop_receiver()
        # Rejestruje nasłuchiwacz na przycisk "Zatrzymaj" w powiadomieniach.

    def _jstr(self, value):
        # Pomocnicza funkcja do zamiany wartości Pythona na tekst (String) dla Javy.
        return self.JavaString(str(value or ""))
        # JavaString to klasa Javy, która tworzy tekst zrozumiały dla Androida.
        # Jeśli wartość jest None – zamieniamy na pusty string.

    def _load_large_icon(self):
        # Wczytuje dużą ikonę aplikacji z zasobów Androida, która będzie wyświetlana
        # w powiadomieniu jako większe obrazki. Jeśli BitmapFactory nie jest dostępna
        # (co może się zdarzyć w niektórych środowiskach testowych), zwraca None.
        if self.BitmapFactory is None:
            return None
            # Jeśli klasa BitmapFactory nie jest dostępna – nie ma jak wczytać ikony.

        try:
            return self.BitmapFactory.decodeResource(
                self.context.getResources(), self.icon
            )
            # Wczytuje obrazek ikony z zasobów Androida i zwraca jako Bitmap.
        except Exception as exc:
            _logcat(f"large icon load failed: {exc!r}")
            return None

    def _create_channel(self):
        # Tworzy kanał powiadomień – wymagany w Androidzie 8.0 i nowszych.
        # Kanał pozwala użytkownikowi kontrolować ustawienia powiadomień
        # (ważność, dźwięk itp.) dla tej aplikacji w ustawieniach systemu.
        if self.sdk_int < 26:
            return
            # Android starszy niż 8.0 (API 26) – nie obsługuje kanałów.

        channel = self.NotificationChannel(
            CHANNEL_ID,
            self._jstr("Aktywne stopery"),
            self.NotificationManagerClass.IMPORTANCE_LOW,
        )
        # Tworzy kanał o ID "running_timers", nazwie "Aktywne stopery"
        # i niskim priorytecie (nie będzie głośno dzwonić).

        channel.setDescription(self._jstr("Trwa odliczanie czasu projektu."))
        # Ustawia opis kanału (widoczny w ustawieniach systemu).

        try:
            channel.setShowBadge(False)
            # Ukrywa badge (małą cyferkę) na ikonie aplikacji.
        except Exception:
            pass

        self.manager.createNotificationChannel(channel)
        # Rejestruje kanał w systemie Android.

    def _jstr(self, value):
        # Konwertuje tekst (string) Pythona na tekst zrozumiały dla Javy.
        # Jest to potrzebne, ponieważ Android API działa na stringach Javy,
        # a nie na stringach Pythona.
        return self.JavaString(str(value or ""))

    def _pending_flags(self):
        # Zwraca odpowiednie flagi (ustawienia) dla PendingIntent w zależności
        # od wersji Androida. To zabezpieczenie: nowsze wersje wymagają
        # FLAG_IMMUTABLE, żeby intencji nie można było modyfikować z zewnątrz.
        flags = self.PendingIntent.FLAG_UPDATE_CURRENT
        # FLAG_UPDATE_CURRENT – jeśli PendingIntent już istnieje, zaktualizuj go.

        if self.sdk_int >= 23:
            flags |= self.PendingIntent.FLAG_IMMUTABLE
            # FLAG_IMMUTABLE (API 23+) – intencji nie można modyfikować
            # z zewnątrz. Wymagane dla bezpieczeństwa w nowszych Androidach.

        return flags

    def _activity_intent(self, project_title):
        # Tworzy intencję (sygnał), która po kliknięciu w powiadomienie
        # otwiera główną aplikację na ekranie wybranego projektu.
        intent = self.Intent(self.context, self.PythonActivity)
        # Tworzy intencję, która otwiera główną aktywność Androida.

        intent.setFlags(
            self.Intent.FLAG_ACTIVITY_CLEAR_TOP | self.Intent.FLAG_ACTIVITY_SINGLE_TOP
        )
        # Ustawia flagi: CLEAR_TOP – zamknij inne okna nad aplikacją,
        # SINGLE_TOP – nie twórz nowej instancji jeśli już istnieje.

        intent.putExtra("project", project_title or "")
        # Dodaje nazwę projektu jako dodatkowy parametr (extra).

        return intent

    def _stop_intent(self, action, uid=""):
        # Tworzy intencję (sygnał) dla przycisku "Zatrzymaj" w powiadomieniu.
        # Gdy użytkownik kliknie "Zatrzymaj" – ten sygnał trafia do usługi,
        # która zatrzymuje stoper lub cel czasowy o podanym UID.
        intent = self.Intent(self._jstr(action))
        # Tworzy intencję z akcją (STOP_TIMER lub STOP_GOAL).

        intent.setPackage(self._jstr(self.package_name))
        # Ustawia pakiet odbiorcy – tylko nasza aplikacja odbierze ten sygnał.

        if uid:
            intent.putExtra(self._jstr("uid"), self._jstr(uid))
            # Jeśli podano UID celu – dodajemy go do intencji (żeby wiedzieć
            # który cel zatrzymać).

        return intent

    def _builder(self):
        # Tworzy obiekt do budowania powiadomień (Notification.Builder)
        # w zależności od wersji Androida. W Android 8.0+ trzeba podać
        # kanał powiadomień, inaczej powiadomienie nie będzie działać.
        if self.sdk_int >= 26:
            return self.NotificationBuilder(self.context, CHANNEL_ID)
            # Android 8+ – wymaga kanału powiadomień.

        return self.NotificationBuilder(self.context)
        # Starsze Androidy – bez kanału.

    def _apply_style(self, builder, title, expanded_text):
        # Stosuje styl BigTextStyle do powiadomienia, żeby można było
        # rozwinąć i zobaczyć więcej treści.
        try:
            style = self.BigTextStyle()
            # Tworzy styl rozwijanego tekstu.

            style.setBigContentTitle(self._jstr(title))
            style.bigText(self._jstr(expanded_text))
            # Ustawia tytuł i rozszerzoną treść.

            builder.setStyle(style)
            # Dodaje styl do powiadomienia.
        except Exception as exc:
            _logcat(f"BigTextStyle failed: {exc!r}")

    def _notification_builder(
        self,
        title,
        text,
        project_title,
        stop_intent,
        request_code,
        expanded_text=None,
        sub_text=None,
    ):
        # Wspólna funkcja do tworzenia powiadomień dla stopera i celów.
        builder = self._builder()
        # Tworzy pusty obiekt do budowania powiadomienia.

        tap = self.PendingIntent.getActivity(
            self.context,
            request_code,
            self._activity_intent(project_title),
            self._pending_flags(),
        )
        # Tworzy PendingIntent – sygnał, który otworzy aplikację po kliknięciu
        # powiadomienia. "request_code" to unikalny numer rozpoznawczy.

        stop = self.PendingIntent.getBroadcast(
            self.context,
            request_code + 50000,
            stop_intent,
            self._pending_flags(),
        )
        # Tworzy PendingIntent dla przycisku "Zatrzymaj" – wysyła sygnał
        # do BroadcastReceiver (nasłuchiwacza) w usłudze.
        # request_code + 50000 = inny numer niż tap (żeby nie kolidować).

        builder.setSmallIcon(self.icon)
        # Ustawia małą ikonę w powiadomieniu (na pasku statusu).

        if self._large_icon is not None:
            try:
                builder.setLargeIcon(self._large_icon)
                # Dodaje dużą ikonę w rozszerzonym powiadomieniu.
            except Exception:
                pass

        try:
            builder.setColor(ACCENT_COLOR)
            # Ustawia kolor akcentu powiadomienia (fioletowy).
        except Exception:
            pass
        try:
            builder.setColorized(True)
            # Koloruje ikonę powiadomienia na fioletowo.
        except Exception:
            pass
        if self.sdk_int >= 21:
            try:
                builder.setVisibility(1)
                # Ustawia widoczność na "publiczną" – treść widoczna
                # na zablokowanym ekranie. 1 = PUBLIC.
            except Exception:
                pass

        builder.setContentTitle(self._jstr(title))
        # Tytuł powiadomienia (np. "Stoper - Strona WWW").

        builder.setContentText(self._jstr(text))
        # Treść powiadomienia (np. "01:30:00").

        if sub_text:
            try:
                builder.setSubText(self._jstr(sub_text))
                # Dodatkowy, mniejszy tekst (np. "Lawenda").
            except Exception:
                pass

        builder.setContentIntent(tap)
        # Ustawia akcję po kliknięciu w powiadomienie (otwiera aplikację).

        builder.setOngoing(True)
        # "Ongoing" – powiadomienie nie można zsunąć (usunąć palcem).
        # Trwa dopóki stoper działa.

        builder.setOnlyAlertOnce(True)
        # Dźwięk/wibracja tylko przy pierwszym wyświetleniu,
        # nie przy każdej aktualizacji.

        builder.setShowWhen(False)
        # Nie pokazuj czasu wyświetlenia powiadomienia.

        builder.addAction(self.icon, self._jstr("Zatrzymaj"), stop)
        # Dodaje przycisk "Zatrzymaj" do powiadomienia.

        if expanded_text:
            self._apply_style(builder, title, expanded_text)
            # Jeśli jest rozszerzona treść – dodaje styl BigTextStyle.

        return builder
        # Zwraca gotowy obiekt do budowania powiadomienia (jeszcze nie zbudowany).

    def _placeholder_notification(self):
        # Tworzy tymczasowe powiadomienie widoczne na pasku statusu tylko
        # podczas uruchamiania usługi, zanim zacznie działać właściwy stoper.
        # To mignięcie trwa ułamek sekundy – potem jest zastępowane
        # prawdziwym powiadomieniem z czasem projektu.
        # Wyświetla: ikonę aplikacji, tytuł "Lawenda" i napis "Trwa uruchamianie stopera..."
        builder = self._builder()
        # Tworzy pusty obiekt do budowania.

        builder.setSmallIcon(self.icon)
        if self._large_icon is not None:
            try:
                builder.setLargeIcon(self._large_icon)
            except Exception:
                pass
        try:
            builder.setColor(ACCENT_COLOR)
        except Exception:
            pass
        # Ustawia ikonę, dużą ikonę i kolor (tak jak w normalnych powiadomieniach).

        builder.setContentTitle(self._jstr("Lawenda"))
        # Tytuł: nazwa aplikacji.

        builder.setContentText(self._jstr("Trwa uruchamianie stopera..."))
        # Treść: informacja dla użytkownika.

        builder.setOngoing(True)
        builder.setOnlyAlertOnce(True)
        builder.setShowWhen(False)
        # Ustawia właściwości: nieusuwalne, alarm tylko raz, bez czasu.

        return builder.build()
        # Buduje i zwraca gotowe powiadomienie.

    def _timer_notification(self, state):
        # Tworzy powiadomienie dla uruchomionego stopera projektu (usługa na pierwszym planie).
        project = state.get("project_title", "") or "Projekt"
        # Pobiera nazwę projektu z danych stopera.

        elapsed = active_timer.elapsed_from_state(state)
        # Oblicza czas, który upłynął od uruchomienia stopera.

        elapsed_text = _format_seconds(elapsed)
        # Formatuje czas na HH:MM:SS.

        expanded = (
            f"Projekt: {project}\n"
            f"Stoper: {elapsed_text}"
        )
        # Rozszerzona treść (widoczna po rozwinięciu powiadomienia).

        return self._notification_builder(
            f"Stoper - {project}",
            elapsed_text,
            project,
            self._stop_intent(ACTION_STOP_TIMER),
            TIMER_NOTIFICATION_ID,
            expanded_text=expanded,
            sub_text="Lawenda",
        ).build()
        # Tworzy powiadomienie stopera z:
        #   tytuł: "Stoper - [nazwa projektu]"
        #   treść: "HH:MM:SS"
        #   przycisk "Zatrzymaj" z akcją STOP_TIMER

    def _goal_notification(self, goal):
        # Tworzy powiadomienie dla aktywnego celu czasowego.
        uid = str(goal.get("uid", "") or "")
        # Pobiera UID celu.

        project = goal.get("project_title", "") or "Projekt"
        # Pobiera nazwę projektu.

        goal_name = (goal.get("title") or "").strip()
        # Pobiera nazwę celu (np. "Nauka hiszpańskiego").

        label, pct, logged, _ = _goal_progress(goal)
        # Oblicza postęp celu: opis, procent, zalogowany czas.

        collapsed = f"{label} - {pct}% ({_format_seconds(logged)})"
        # Zwięzła treść: "Nauka hiszpańskiego - 45% (02:30:15)".

        title_parts = ["Cel", project]
        if goal_name and goal_name.lower() != "cel":
            title_parts.append(goal_name)
        title = " - ".join(title_parts)
        # Buduje tytuł: np. "Cel - Strona WWW - Nauka hiszpańskiego".

        header = project
        if goal_name and goal_name.lower() != "cel":
            header = f"{project} - {goal_name}"
        expanded = f"{header}\n{label} - {pct}% - {_format_seconds(logged)}"
        # Rozszerzona treść: projekt, cel, postęp.

        return self._notification_builder(
            title,
            collapsed,
            project,
            self._stop_intent(ACTION_STOP_GOAL, uid),
            _goal_notification_id(uid),
            expanded_text=expanded,
            sub_text="Lawenda",
        ).build()
        # Tworzy powiadomienie celu z przyciskiem "Zatrzymaj" i akcją STOP_GOAL.

    def _start_foreground(self, notification_id, notification):
        # Uruchamia usługę Android na pierwszym planie ("foreground service").
        # To specjalny rodzaj usługi, która pokazuje stałe powiadomienie
        # na pasku statusu – system wie, że to ważne, i nie zabija jej.
        # Jeśli usługa już działa z innym ID powiadomienia – anuluje stare
        # i zastępuje nowym. Dzięki temu zawsze mamy tylko jedno aktywne
        # powiadomienie dla stopera lub celu.
        if self._foreground_id == notification_id:
            try:
                self.manager.notify(notification_id, notification)
                # Jeśli to to samo ID co obecne – tylko aktualizujemy
                # powiadomienie (nie restartujemy usługi).
            except Exception:
                pass
            return

        try:
            self.service.startForeground(notification_id, notification)
            # Uruchamia usługę na pierwszym planie z tym powiadomieniem.
            # Android wyświetli je na pasku statusu.
        except Exception as exc:
            _logcat(f"startForeground failed: {exc!r}")
            return

        if self._foreground_id is not None and self._foreground_id != notification_id:
            try:
                self.manager.cancel(self._foreground_id)
                # Jeśli było poprzednie powiadomienie (inne ID) – usuwa je.
            except Exception:
                pass

        self._foreground_id = notification_id
        # Zapamiętuje ID nowego powiadomienia.

    def _stop_foreground(self):
        # Zatrzymuje usługę pierwszoplanową i usuwa jej powiadomienie.
        # Android wymaga specjalnego wywołania (stopForeground) żeby
        # poinformować system, że usługa nie jest już ważna.
        # Czyści też zapamiętane ID powiadomienia.
        try:
            if self.sdk_int >= 24:
                self.service.stopForeground(1)
                # Android 7+ (API 24): 1 = REMOVE_NOTIFICATION (usuń powiadomienie).
            else:
                self.service.stopForeground(True)
                # Starsze wersje: True = usuń powiadomienie.
        except Exception:
            pass

        if self._foreground_id is not None:
            try:
                self.manager.cancel(self._foreground_id)
                # Anuluje powiadomienie (na wszelki wypadek).
            except Exception:
                pass
            self._foreground_id = None
            # Czyści zapamiętane ID.

    def _register_stop_receiver(self):
        # Rejestruje "nasłuchiwacz" (BroadcastReceiver), który wyłapuje
        # kliknięcia przycisku "Zatrzymaj" w powiadomieniach Androida.
        # Gdy użytkownik kliknie "Zatrzymaj" w powiadomieniu:
        # - Dla stopera: zatrzymuje pomiar czasu projektu
        # - Dla celu czasowego: zatrzymuje śledzenie konkretnego celu
        try:
            from android.broadcast import BroadcastReceiver
            # Importuje klasę BroadcastReceiver z biblioteki Androida.
        except Exception as exc:
            _logcat(f"BroadcastReceiver unavailable: {exc!r}")
            return

        def _on_receive(context, intent):
            # Gdy użytkownik kliknie "Zatrzymaj" w powiadomieniu – odbiera
            # ten sygnał. Jeśli dotyczy stopera – zatrzymuje pomiar czasu
            # projektu. Jeśli dotyczy celu czasowego – zatrzymuje śledzenie
            # konkretnego celu na podstawie jego numeru (UID).
            action = str(intent.getAction() or "")
            # Pobiera akcję z intencji (STOP_TIMER lub STOP_GOAL).

            _logcat(f"received {action}")
            try:
                if action == ACTION_STOP_TIMER:
                    active_timer.finalize_project_timer()
                    # Zatrzymuje stoper i zapisuje sesję.

                    self.manager.cancel(TIMER_NOTIFICATION_ID)
                    # Usuwa powiadomienie stopera.

                elif action == ACTION_STOP_GOAL:
                    raw_uid = intent.getStringExtra(self._jstr("uid"))
                    uid = str(raw_uid) if raw_uid is not None else ""
                    # Pobiera UID celu z intencji.

                    _logcat(f"STOP_GOAL uid={uid!r}")
                    if uid:
                        result = active_timer.finalize_goal(uid)
                        # Zatrzymuje cel czasowy.

                        _logcat(f"finalize_goal({uid!r}) -> {result!r}")
                        self.manager.cancel(_goal_notification_id(uid))
                        # Usuwa powiadomienie tego celu.
                    else:
                        _logcat("STOP_GOAL received without uid extra")
            except Exception:
                _logcat(traceback.format_exc())

        self._receiver = BroadcastReceiver(
            _on_receive, actions=[ACTION_STOP_TIMER, ACTION_STOP_GOAL]
        )
        # Tworzy obiekt BroadcastReceiver nasłuchujący na dwie akcje.

        try:
            self._receiver.start()
            # Uruchamia nasłuchiwanie.
        except Exception as exc:
            _logcat(f"BroadcastReceiver.start failed: {exc!r}")
            self._receiver = None

    def _unregister_stop_receiver(self):
        # Odłącza nasłuchiwacz kliknięć w powiadomieniach – przestaje
        # reagować na przycisk "Zatrzymaj" w powiadomieniach.
        if self._receiver is None:
            return
            # Jeśli nie ma zarejestrowanego nasłuchiwacza – nic nie rób.

        try:
            self._receiver.stop()
            # Zatrzymuje nasłuchiwanie.
        except Exception:
            pass
        self._receiver = None
        # Czyści referencję.

    def _tick_once(self):
        # Wykonuje pojedynczy cykl aktualizacji: odświeża powiadomienia
        # dla stopera i celów. Wywoływane co 1 sekundę.
        timer_state = active_timer.read_project_timer()
        # Sprawdza czy jest aktywny stoper.

        goals = active_timer.read_goals()
        # Sprawdza czy są aktywne cele czasowe.

        active_ids = []
        # Lista ID aktywnych powiadomień (do porównania z poprzednim stanem).

        if timer_state:
            notification = self._timer_notification(timer_state)
            # Tworzy powiadomienie stopera z aktualnym czasem.

            self._start_foreground(TIMER_NOTIFICATION_ID, notification)
            # Uruchamia usługę na pierwszym planie (jeśli nie działa).

            self.manager.notify(TIMER_NOTIFICATION_ID, notification)
            # Wyświetla/aktualizuje powiadomienie stopera.

            active_ids.append(TIMER_NOTIFICATION_ID)
        else:
            self.manager.cancel(TIMER_NOTIFICATION_ID)
            # Jeśli nie ma stopera – usuwa jego powiadomienie.

        for goal in goals:
            uid = goal.get("uid", "")
            if not uid:
                continue
                # Jeśli cel nie ma UID – pomijamy.

            notification_id = _goal_notification_id(uid)
            notification = self._goal_notification(goal)
            # Tworzy powiadomienie dla celu.

            if not active_ids:
                self._start_foreground(notification_id, notification)
                # Jeśli nie ma stopera – pierwszy cel uruchamia usługę.

            self.manager.notify(notification_id, notification)
            # Wyświetla/aktualizuje powiadomienie celu.

            active_ids.append(notification_id)

        for old_id in self._last_goal_ids - set(active_ids):
            self.manager.cancel(old_id)
            # Usuwa powiadomienia celów, które zostały zakończone
            # (były w poprzednim cyklu, ale nie ma ich w obecnym).

        self._last_goal_ids = {nid for nid in active_ids if nid != TIMER_NOTIFICATION_ID}
        # Zapisuje ID aktywnych powiadomień celów (bez stopera) do porównania
        # w następnym cyklu.

        return bool(active_ids)
        # Zwraca True jeśli są aktywne timery (stoper lub cele).

    def run(self):
        # Główna pętla usługi – działa w tle na Androidzie.
        # Co sekundę:
        # 1. Odświeża powiadomienia (wywołuje _tick_once)
        # 2. Jeśli są aktywne timery – kontynuuje działanie
        # 3. Jeśli nie ma aktywnych timerów przez 6 sekund –
        #    zatrzymuje się (żeby nie marnować baterii)
        _logcat("service started")
        # Zapisuje w logu, że usługa została uruchomiona.

        try:
            while True:
                try:
                    has_active = self._tick_once()
                    # Wykonuje cykl aktualizacji powiadomień.
                except Exception:
                    _logcat(traceback.format_exc())
                    has_active = True
                    # Jeśli wystąpił błąd – nie zatrzymuj usługi,
                    # spróbuj ponownie w następnej sekundzie.

                if has_active:
                    self._seen_active = True
                    self._idle_since = None
                    # Jeśli są aktywne timery – zapamiętujemy to
                    # i zerujemy licznik bezczynności.
                else:
                    if self._seen_active:
                        # Jeśli była aktywność, ale teraz nie ma –
                        # zatrzymaj usługę od razu.
                        _logcat("no active timers - stopping service")
                        self._stop_foreground()
                        try:
                            self.service.stopSelf()
                            # Zatrzymuje usługę Androida.
                        except Exception:
                            pass
                        return

                    if self._idle_since is None:
                        self._idle_since = time.monotonic()
                        # Jeśli to pierwszy cykl bez aktywności –
                        # zapamiętujemy czas.
                    elif time.monotonic() - self._idle_since >= IDLE_GRACE_SECONDS:
                        # Jeśli minęło 6 sekund bez aktywności –
                        # zatrzymaj usługę.
                        _logcat("idle - stopping service")
                        self._stop_foreground()
                        try:
                            self.service.stopSelf()
                        except Exception:
                            pass
                        return

                time.sleep(1)
                # Czeka 1 sekundę przed następnym cyklem.
        finally:
            self._unregister_stop_receiver()
            # Przy zakończeniu usługi – odłącza nasłuchiwacz przycisków.


def main():
    # Punkt wejścia dla usługi Androida – to jest wywoływane przez
    # system Android gdy uruchamia usługę w tle. Tworzy obiekt
    # TimerNotificationService i uruchamia jego główną pętlę.
    # Jeśli coś pójdzie nie tak – zapisuje błąd do logów.
    try:
        TimerNotificationService().run()
    except Exception:
        _logcat(traceback.format_exc())


if __name__ == "__main__":
    main()