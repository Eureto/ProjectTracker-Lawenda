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
import sys
import time
import traceback
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from screens import active_timer

# Identyfikatory dla powiadomień
PACKAGE = "org.stokrotka.stokrotka"
CHANNEL_ID = "running_timers"
ACTION_STOP_TIMER = f"{PACKAGE}.STOP_TIMER"  # Akcja: zatrzymaj stoper
ACTION_STOP_GOAL = f"{PACKAGE}.STOP_GOAL"    # Akcja: zatrzymaj cel czasowy
TIMER_NOTIFICATION_ID = 1001                  # ID powiadomienia stopera
GOAL_NOTIFICATION_BASE_ID = 1100              # Numer początkowy dla celów (każdy dostaje swój numer)
PLACEHOLDER_NOTIFICATION_ID = 999             # Tymczasowe powiadomienie podczas uruchamiania
TAG = "ProjectTrackerSvc"
IDLE_GRACE_SECONDS = 6  # Po 6 sekundach bez aktywności zatrzymaj usługę

# Kolor akcentu (fioletowy) dla powiadomień
ACCENT_COLOR = _argb(0xFF, 0x8A, 0x2B, 0xE2)


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


# Log a message to both stdout and Android logcat (if available).
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
    # Generuje unikalny numer powiadomienia dla celu czasowego na podstawie jego UID (unikalnego identyfikatora).
    # Używa algorytmu CRC32 do stworzenia rozproszenia liczb, dzięki czemu różne cele otrzymują 
    # różne numery powiadomień, co pozwala systemowi Android na właściwe zarządzanie nimi.
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
        # Inicjalizuje usługę poprzez:
        #   1. Ładowanie potrzebnych klas Androida przez JNI
        #   2. Tworzenie kanału powiadomień (wymagane w Android 8.0+)
        #   3. Ustawianie folderu do zapisu danych (takiego samego jak używa główna aplikacja)
        #   4. Rejestrację odbiornika szerokiastreamowego do obsługi przycisków w powiadomieniach
        from jnius import autoclass

        self.autoclass = autoclass
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
        try:
            self.BitmapFactory = autoclass("android.graphics.BitmapFactory")
        except Exception:
            self.BitmapFactory = None
        try:
            self.ServiceInfo = autoclass("android.content.pm.ServiceInfo")
        except Exception:
            self.ServiceInfo = None
        self.PythonActivity = autoclass("org.kivy.android.PythonActivity")
        self.PythonService = autoclass("org.kivy.android.PythonService")
        self.service = self.PythonService.mService
        self.context = self.service.getApplicationContext()
        self.package_name = self.context.getPackageName()
        self.manager = self.service.getSystemService(self.Context.NOTIFICATION_SERVICE)
        self.icon = self.context.getApplicationInfo().icon
        self._receiver = None
        self._foreground_id = None
        self._last_goal_ids = set()
        self._idle_since = None
        self._seen_active = False
        self._large_icon = self._load_large_icon()

        # Ustaw folder do zapisu danych (taki sam jak aplikacja)
        try:
            base_dir = self.service.getFilesDir().getAbsolutePath()
            active_timer.set_base_dir(base_dir)
            _logcat(f"using base_dir={base_dir}")
        except Exception as exc:
            _logcat(f"set_base_dir failed: {exc!r}")

        self._create_channel()
        self._start_foreground(PLACEHOLDER_NOTIFICATION_ID, self._placeholder_notification())
        self._register_stop_receiver()

    # Helper to convert a Python value to a Java String.
    def _jstr(self, value):
        return self.JavaString(str(value or ""))

    # Load the app's large icon bitmap for notifications.
    def _load_large_icon(self):
        # Wczytuje dużą ikonę aplikacji z zasobów Androida, która będzie wyświetlana
        # w powiadomieniu jako większe obrazki. Jeśli BitmapFactory nie jest dostępna
        # (co może się zdarzyć w niektórych środowiskach testowych), zwraca None.
        if self.BitmapFactory is None:
            return None
        try:
            return self.BitmapFactory.decodeResource(
                self.context.getResources(), self.icon
            )
        except Exception as exc:
            _logcat(f"large icon load failed: {exc!r}")
            return None

    def _create_channel(self):
        # Tworzy kanał powiadomień, który jest wymagany w Androidzie 8.0 (API level 26) i nowszych.
        # Kanał powiadomień pozwala użytkownikowi na kontrolowanie ustawień powiadomień
        # dla tej konkretnej aplikacji (jak ważność, dźwięk, itp.).
        if self.sdk_int < 26:
            return
        channel = self.NotificationChannel(
            CHANNEL_ID,
            self._jstr("Aktywne stopery"),
            self.NotificationManagerClass.IMPORTANCE_LOW,
        )
        channel.setDescription(self._jstr("Trwa odliczanie czasu projektu."))
        try:
            channel.setShowBadge(False)
        except Exception:
            pass
        self.manager.createNotificationChannel(channel)

    def _jstr(self, value):
        # Konwertuje string Pythona na obiekt string Javy, który jest wymagany
        # przy wywoływaniu metod Androida przez JNI (Java Native Interface).
        # Jest to konieczne ponieważ Android API pracuje ze stringami Javy,
        # a nie ze stringami Pythona.
        return self.JavaString(str(value or ""))

    def _pending_flags(self):
        # Zwraca odpowiednie flagi dla PendingIntent w zależności od wersji SDK Androida.
        # FLAG_UPDATE_CURRENT zapewnia aktualizację istniejącego intencji.
        # FLAG_IMMUTABLE (dla API 23+) sprawia, że PendingIntent jest niezmienialny
        # ze względów bezpieczeństwa.
        flags = self.PendingIntent.FLAG_UPDATE_CURRENT
        if self.sdk_int >= 23:
            flags |= self.PendingIntent.FLAG_IMMUTABLE
        return flags

    def _activity_intent(self, project_title):
        # Tworzy intencję (intention) która po kliknięciu w powiadomienie
        # otwiera główną aplikację na ekranie wybranego projektu.
        # Intent to obiekt Androida używany do uruchamiania aktywności
        # lub przekazywania danych między komponentami aplikacji.
        intent = self.Intent(self.context, self.PythonActivity)
        intent.setFlags(
            self.Intent.FLAG_ACTIVITY_CLEAR_TOP | self.Intent.FLAG_ACTIVITY_SINGLE_TOP
        )
        intent.putExtra("project", project_title or "")
        return intent

    def _stop_intent(self, action, uid=""):
        # Tworzy intencję która po kliknięciu przycisku 'Zatrzymaj' w powiadomieniu
        # wysyła sygnał do usługi aby zatrzymać stoper lub cel czasowy.
        # Action określa jaką akcję wykonać (zatrzymanie stopera czy celu),
        # a UID identyfikuje konkretny cel czasowy (jeśli dotyczy).
        intent = self.Intent(self._jstr(action))
        intent.setPackage(self._jstr(self.package_name))
        if uid:
            intent.putExtra(self._jstr("uid"), self._jstr(uid))
        return intent

    def _builder(self):
        # Tworzy odpowiedni obiekt Notification.Builder w zależności od wersji SDK Androida.
        # W Androidzie 8.0 (API level 26) i nowszych należy podać kanał powiadomień.
        if self.sdk_int >= 26:
            return self.NotificationBuilder(self.context, CHANNEL_ID)
        return self.NotificationBuilder(self.context)

    # Apply a BigTextStyle to a notification builder for expanded view.
    def _apply_style(self, builder, title, expanded_text):
        try:
            style = self.BigTextStyle()
            style.setBigContentTitle(self._jstr(title))
            style.bigText(self._jstr(expanded_text))
            builder.setStyle(style)
        except Exception as exc:
            _logcat(f"BigTextStyle failed: {exc!r}")

    # Common builder for timer and goal notifications.
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
        builder = self._builder()
        tap = self.PendingIntent.getActivity(
            self.context,
            request_code,
            self._activity_intent(project_title),
            self._pending_flags(),
        )
        stop = self.PendingIntent.getBroadcast(
            self.context,
            request_code + 50000,
            stop_intent,
            self._pending_flags(),
        )
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
        try:
            builder.setColorized(True)
        except Exception:
            pass
        if self.sdk_int >= 21:
            try:
                builder.setVisibility(1)
            except Exception:
                pass
        builder.setContentTitle(self._jstr(title))
        builder.setContentText(self._jstr(text))
        if sub_text:
            try:
                builder.setSubText(self._jstr(sub_text))
            except Exception:
                pass
        builder.setContentIntent(tap)
        builder.setOngoing(True)
        builder.setOnlyAlertOnce(True)
        builder.setShowWhen(False)
        builder.addAction(self.icon, self._jstr("Zatrzymaj"), stop)
        if expanded_text:
            self._apply_style(builder, title, expanded_text)
        return builder

    # Build a placeholder notification shown while the service starts.
    def _placeholder_notification(self):
        # Tworzy tymczasowe powiadomienie widoczne na pasku statusu tylko
        # podczas uruchamiania usługi, zanim zacznie działać właściwy stoper.
        # To mignięcie trwa ułamek sekundy – potem jest zastępowane
        # prawdziwym powiadomieniem z czasem projektu.
        # Wyświetla: ikonę aplikacji, tytuł "Lawenda" i napis "Trwa uruchamianie stopera..."
        builder = self._builder()
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
        builder.setContentTitle(self._jstr("Lawenda"))
        builder.setContentText(self._jstr("Trwa uruchamianie stopera..."))
        builder.setOngoing(True)
        builder.setOnlyAlertOnce(True)
        builder.setShowWhen(False)
        return builder.build()

    # Build the foreground notification for the running project timer.
    def _timer_notification(self, state):
        project = state.get("project_title", "") or "Projekt"
        elapsed = active_timer.elapsed_from_state(state)
        elapsed_text = _format_seconds(elapsed)
        expanded = (
            f"Projekt: {project}\n"
            f"Stoper: {elapsed_text}"
        )
        return self._notification_builder(
            f"Stoper - {project}",
            elapsed_text,
            project,
            self._stop_intent(ACTION_STOP_TIMER),
            TIMER_NOTIFICATION_ID,
            expanded_text=expanded,
            sub_text="Lawenda",
        ).build()

    # Build a notification for an active goal.
    def _goal_notification(self, goal):
        uid = str(goal.get("uid", "") or "")
        project = goal.get("project_title", "") or "Projekt"
        goal_name = (goal.get("title") or "").strip()
        label, pct, logged, _ = _goal_progress(goal)
        collapsed = f"{label} - {pct}% ({_format_seconds(logged)})"

        title_parts = ["Cel", project]
        if goal_name and goal_name.lower() != "cel":
            title_parts.append(goal_name)
        title = " - ".join(title_parts)

        header = project
        if goal_name and goal_name.lower() != "cel":
            header = f"{project} - {goal_name}"
        expanded = f"{header}\n{label} - {pct}% - {_format_seconds(logged)}"

        return self._notification_builder(
            title,
            collapsed,
            project,
            self._stop_intent(ACTION_STOP_GOAL, uid),
            _goal_notification_id(uid),
            expanded_text=expanded,
            sub_text="Lawenda",
        ).build()

    # Start or update the foreground service with the given notification.
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
            except Exception:
                pass
            return
        try:
            self.service.startForeground(notification_id, notification)
        except Exception as exc:
            _logcat(f"startForeground failed: {exc!r}")
            return
        if self._foreground_id is not None and self._foreground_id != notification_id:
            try:
                self.manager.cancel(self._foreground_id)
            except Exception:
                pass
        self._foreground_id = notification_id

    def _stop_foreground(self):
        # Zatrzymuje usługę pierwszoplanową i usuwa jej powiadomienie.
        # Android wymaga specjalnego wywołania (stopForeground) żeby
        # poinformować system, że usługa nie jest już ważna.
        # Czyści też zapamiętane ID powiadomienia.
        try:
            if self.sdk_int >= 24:
                self.service.stopForeground(1)
            else:
                self.service.stopForeground(True)
        except Exception:
            pass
        if self._foreground_id is not None:
            try:
                self.manager.cancel(self._foreground_id)
            except Exception:
                pass
            self._foreground_id = None

    def _register_stop_receiver(self):
        # Rejestruje "nasłuchiwacz" (BroadcastReceiver), który wyłapuje
        # kliknięcia przycisku "Zatrzymaj" w powiadomieniach Androida.
        # Gdy użytkownik kliknie "Zatrzymaj" w powiadomieniu:
        # - Dla stopera: zatrzymuje pomiar czasu projektu
        # - Dla celu czasowego: zatrzymuje śledzenie konkretnego celu
        # BroadcastReceiver to mechanizm Androida do odbierania sygnałów
        # między różnymi częściami systemu i aplikacji.
        try:
            from android.broadcast import BroadcastReceiver
        except Exception as exc:
            _logcat(f"BroadcastReceiver unavailable: {exc!r}")
            return

        def _on_receive(context, intent):
            action = str(intent.getAction() or "")
            _logcat(f"received {action}")
            try:
                if action == ACTION_STOP_TIMER:
                    active_timer.finalize_project_timer()
                    self.manager.cancel(TIMER_NOTIFICATION_ID)
                elif action == ACTION_STOP_GOAL:
                    raw_uid = intent.getStringExtra(self._jstr("uid"))
                    uid = str(raw_uid) if raw_uid is not None else ""
                    _logcat(f"STOP_GOAL uid={uid!r}")
                    if uid:
                        result = active_timer.finalize_goal(uid)
                        _logcat(f"finalize_goal({uid!r}) -> {result!r}")
                        self.manager.cancel(_goal_notification_id(uid))
                    else:
                        _logcat("STOP_GOAL received without uid extra")
            except Exception:
                _logcat(traceback.format_exc())

        self._receiver = BroadcastReceiver(
            _on_receive, actions=[ACTION_STOP_TIMER, ACTION_STOP_GOAL]
        )
        try:
            self._receiver.start()
        except Exception as exc:
            _logcat(f"BroadcastReceiver.start failed: {exc!r}")
            self._receiver = None

    def _unregister_stop_receiver(self):
        if self._receiver is None:
            return
        try:
            self._receiver.stop()
        except Exception:
            pass
        self._receiver = None

    # Perform a single update cycle: refresh notifications for timer and goals.
    def _tick_once(self):
        # Odświeża wszystkie powiadomienia na pasku statusu.
        # Sprawdza:
        # 1. Czy jest aktywny stoper projektu? Jeśli tak – aktualizuje
        #    jego powiadomienie z nowym czasem.
        # 2. Czy są aktywne cele czasowe? Dla każdego aktualizuje
        #    osobne powiadomienie.
        # 3. Czy jakiś cel został zakończony? Usuwa jego powiadomienie.
        # Wywoływane co 1 sekundę przez główną pętlę usługi.
        timer_state = active_timer.read_project_timer()
        goals = active_timer.read_goals()
        active_ids = []

        if timer_state:
            notification = self._timer_notification(timer_state)
            self._start_foreground(TIMER_NOTIFICATION_ID, notification)
            self.manager.notify(TIMER_NOTIFICATION_ID, notification)
            active_ids.append(TIMER_NOTIFICATION_ID)
        else:
            self.manager.cancel(TIMER_NOTIFICATION_ID)

        for goal in goals:
            uid = goal.get("uid", "")
            if not uid:
                continue
            notification_id = _goal_notification_id(uid)
            notification = self._goal_notification(goal)
            if not active_ids:
                self._start_foreground(notification_id, notification)
            self.manager.notify(notification_id, notification)
            active_ids.append(notification_id)

        for old_id in self._last_goal_ids - set(active_ids):
            self.manager.cancel(old_id)
        self._last_goal_ids = {nid for nid in active_ids if nid != TIMER_NOTIFICATION_ID}
        return bool(active_ids)

    def run(self):
        # Główna pętla usługi – działa w tle na Androidzie.
        # Co sekundę:
        # 1. Odświeża powiadomienia (wywołuje _tick_once)
        # 2. Jeśli są aktywne timery – kontynuuje działanie
        # 3. Jeśli nie ma aktywnych timerów przez 6 sekund –
        #    zatrzymuje się (żeby nie marnować baterii)
        # Dzięki temu usługa działa tylko gdy jest potrzebna.
        _logcat("service started")
        try:
            while True:
                try:
                    has_active = self._tick_once()
                except Exception:
                    _logcat(traceback.format_exc())
                    has_active = True

                if has_active:
                    self._seen_active = True
                    self._idle_since = None
                else:
                    if self._seen_active:
                        _logcat("no active timers - stopping service")
                        self._stop_foreground()
                        try:
                            self.service.stopSelf()
                        except Exception:
                            pass
                        return
                    if self._idle_since is None:
                        self._idle_since = time.monotonic()
                    elif time.monotonic() - self._idle_since >= IDLE_GRACE_SECONDS:
                        _logcat("idle - stopping service")
                        self._stop_foreground()
                        try:
                            self.service.stopSelf()
                        except Exception:
                            pass
                        return
                time.sleep(1)
        finally:
            self._unregister_stop_receiver()


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