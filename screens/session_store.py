# ---------------------------------------------------------------------------
# PRZECHOWYWANIE SESJI CZASOWYCH I STATYSTYKI
# ---------------------------------------------------------------------------
# Ten plik odpowiada za zapisywanie i odczytywanie "sesji" – czyli
# zakończonych pomiarów czasu (np. "dzisiaj pracowałem 30 minut nad
# projektem X"). Służy też do obliczania statystyk dla ekranu statystyk.
#
# CO TO JEST "SESJA"?
# To pojedynczy okres mierzonego czasu. Za każdym razem gdy użytkownik
# uruchomi stoper, a potem go zatrzyma, powstaje jedna sesja.
# ---------------------------------------------------------------------------

import datetime
# "datetime" – wbudowany moduł do obsługi dat i czasu.
# Używamy go do zapisywania kiedy sesja się zaczęła i skończyła,
# oraz do obliczania okresów (dziś, ten tydzień, ten miesiąc).

import json
# "json" – wbudowany moduł do odczytu/zapisu plików JSON.
# Wszystkie dane (sesje, projekty) są przechowywane jako JSON.

import os
# "os" – funkcje systemowe: sprawdzanie czy plik istnieje, tworzenie folderów,
# łączenie ścieżek.

from kivy.clock import Clock
# "Clock" – narzędzie Kivy do planowania zadań na później
# (np. odświeżenie ekranu po zapisaniu nowej sesji).

from kivymd.app import MDApp
# "MDApp" – główna klasa aplikacji KivyMD. Przez nią uzyskujemy
# dostęp do ekranów i ustawień.

from screens.emoji_assets import resolve_emoji_source
# Importujemy funkcję, która zamienia nazwę ikony na ścieżkę do pliku
# z emoji. Używamy jej przy zapisywaniu sesji, żeby zapamiętać ikonę.


# Zwraca ścieżkę do pliku sessions.json, który przechowuje historię
# wszystkich zakończonych pomiarów czasu (sesji).
def _sessions_path():
    # Zwraca ścieżkę do pliku sessions.json, który przechowuje historię
    # wszystkich zakończonych pomiarów czasu (sesji).
    return os.path.join(MDApp.get_running_app().user_data_dir, "sessions.json")
    # Łączy: prywatny folder aplikacji + "sessions.json".


def _projects_path():
    # Zwraca ścieżkę do pliku projects.json, który przechowuje listę
    # wszystkich zapisanych projektów (nazwy, kolory, emoji, zdjęcia).
    return os.path.join(MDApp.get_running_app().user_data_dir, "projects.json")
    # Łączy: prywatny folder aplikacji + "projects.json".


def load_sessions():
    # Wczytuje wszystkie zapisane sesje z pliku sessions.json.
    # Jeśli plik nie istnieje lub jest uszkodzony – zwraca pustą listę.
    path = _sessions_path()
    # Pobiera ścieżkę do pliku sessions.json.

    if not os.path.exists(path):
        return []
        # Jeśli plik nie istnieje (pierwsze uruchomienie) – zwraca pustą listę.

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Otwiera plik i odczytuje jego zawartość jako JSON.

        if isinstance(data, list):
            return data
            # Jeśli dane to lista – zwraca ją. Jeśli to coś innego
            # (np. słownik z innej wersji) – ignoruje.
    except (OSError, json.JSONDecodeError):
        pass
        # Jeśli plik jest uszkodzony lub nie dało się go przeczytać –
        # ignorujemy błąd (nie chcemy wywalać aplikacji).

    return []
    # Domyślnie zwraca pustą listę.


def save_sessions(sessions):
    # Zapisuje listę sesji do pliku sessions.json.
    # "os.makedirs(exist_ok=True)" – utwórz folder do zapisu jeśli nie istnieje.
    path = _sessions_path()
    # Pobiera ścieżkę do pliku sessions.json.

    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Tworzy folder, w którym ma być plik, jeśli nie istnieje.
    # "exist_ok=True" = nie wywołuj błędu jeśli folder już istnieje.

    with open(path, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)
        # Zapisuje sesje do pliku w formacie JSON.
        # indent=2 = ładne wcięcia. ensure_ascii=False = polskie znaki.


def find_project_meta(project_title):
    # Szuka projektu po nazwie w pliku projects.json i zwraca jego dane.
    # Zwraca: emoji, kolor tła, zdjęcie itp. – wszystko co jest potrzebne
    # do wyświetlenia karty projektu. Jeśli nie znajdzie – zwraca pusty słownik.
    # Używane np. przy tworzeniu statystyk, żeby pokazać kolor projektu.
    path = _projects_path()
    # Pobiera ścieżkę do pliku projects.json.

    if not os.path.exists(path):
        return {}
        # Jeśli plik nie istnieje – zwraca pusty słownik.

    try:
        with open(path, "r", encoding="utf-8") as f:
            projects = json.load(f)
            # Otwiera plik i odczytuje listę projektów.

        for p in projects:
            if p.get("title") == project_title:
                return p
                # Przechodzi przez wszystkie projekty i szuka tego
                # o podanej nazwie. Jeśli znajdzie – zwraca jego dane.
    except (OSError, json.JSONDecodeError):
        pass
        # Jeśli plik jest uszkodzony – ignoruje błąd.

    return {}
    # Jeśli nie znaleziono projektu – zwraca pusty słownik.


def record_session(project_title, duration_seconds, started_at=None, ended_at=None, project_uid=""):
    # Dodaje nową sesję na początek listy (najnowsze pierwsze).
    # Parametry:
    #   project_title – nazwa projektu
    #   duration_seconds – czas trwania w sekundach
    #   started_at / ended_at – opcjonalne daty rozpoczęcia i zakończenia
    #   project_uid – identyfikator projektu (jeśli znany)
    # Funkcja odświeża też ekran główny i statystyki po dodaniu.
    if not project_title or duration_seconds < 1:
        return None
        # Jeśli nie ma nazwy projektu lub czas jest krótszy niż 1 sekunda
        # – nie zapisujemy (taka sesja nie ma sensu).

    ended = ended_at or datetime.datetime.now()
    # Jeśli nie podano daty zakończenia – używamy aktualnego czasu ("teraz").

    if isinstance(ended, str):
        ended = datetime.datetime.fromisoformat(ended)
        # Jeśli data zakończenia to tekst (np. "2026-06-07T12:00:00")
        # – zamieniamy ją na obiekt daty.

    started = started_at or (ended - datetime.timedelta(seconds=int(duration_seconds)))
    # Jeśli nie podano daty rozpoczęcia – obliczamy: data zakończenia - czas trwania.

    if isinstance(started, str):
        started = datetime.datetime.fromisoformat(started)
        # Jeśli data rozpoczęcia to tekst – zamieniamy na obiekt daty.

    meta = find_project_meta(project_title)
    # Szuka danych projektu (emoji, kolor, zdjęcie) w pliku projects.json.

    entry = {
        "project_uid": project_uid or meta.get("uid", ""),
        # UID projektu – jeśli nie ma, bierzemy z metadanych.

        "project_title": project_title,
        # Nazwa projektu.

        "emoji_source": resolve_emoji_source(meta.get("icon", "emoticon-happy-outline")),
        # Ścieżka do pliku emoji projektu (lub domyślna uśmiechnięta buźka).

        "image": meta.get("image", ""),
        # Ścieżka do zdjęcia projektu (jeśli jest).

        "color": meta.get("color", [0.7, 0.5, 1, 1]),
        # Kolor projektu (domyślnie fioletowy).

        "started_at": started.isoformat(),
        # Data rozpoczęcia w formacie ISO (np. "2026-06-07T10:30:00").

        "ended_at": ended.isoformat(),
        # Data zakończenia w formacie ISO.

        "duration_seconds": int(duration_seconds),
        # Czas trwania sesji w sekundach (zaokrąglony do pełnej liczby).
    }

    sessions = load_sessions()
    # Wczytuje wszystkie istniejące sesje z pliku.

    sessions.insert(0, entry)
    # Wstawia nową sesję na POCZĄTEK listy (najnowsze jako pierwsze).

    save_sessions(sessions)
    # Zapisuje zaktualizowaną listę sesji do pliku.

    # Odśwież ekran główny i statystyki (mogą być widoczne)
    schedule_home_last_session_refresh()
    schedule_statistics_refresh()
    # Planuje odświeżenie ekranu głównego (karta ostatniej sesji)
    # i ekranu statystyk (wykres kołowy i tabela).

    return entry
    # Zwraca zapisaną sesję (na wypadek gdyby ktoś potrzebował jej danych).


# Zwraca ścieżkę do pliku project_details.json, który przechowuje
# szczegółowe dane projektów (notatki, cele, listy zadań, etapy).
def _project_details_path():
    # Zwraca ścieżkę do pliku project_details.json, który przechowuje
    # szczegółowe dane projektów (notatki, cele, listy zadań, etapy).
    return os.path.join(MDApp.get_running_app().user_data_dir, "project_details.json")


def load_project_details():
    # Wczytuje z pliku project_details.json wszystkie szczegóły projektów:
    # notatki, cele czasowe, listę celów (checklistę) i etapy.
    # Zwraca słownik gdzie kluczem jest nazwa (lub UID) projektu.
    # Jeśli plik nie istnieje lub jest uszkodzony – zwraca pusty słownik.
    path = _project_details_path()
    if not os.path.exists(path):
        return {}
        # Jeśli plik nie istnieje – zwraca pusty słownik.

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
            # Jeśli dane to słownik – zwraca go.
    except (OSError, json.JSONDecodeError):
        pass
        # Jeśli plik jest uszkodzony – ignoruje błąd.

    return {}
    # Domyślnie zwraca pusty słownik.


def period_range_start(period_label):
    # Zwraca datę początku okresu dla statystyk.
    # "Dzień" – początek dzisiejszego dnia (00:00:00).
    # "Tydzień" – początek bieżącego tygodnia (poniedziałek 00:00:00).
    # "Miesiąc" – pierwszy dzień miesiąca (00:00:00).
    now = datetime.datetime.now()
    # Pobiera aktualną datę i czas.

    if period_label == "Dzień":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Ustawia godzinę na 00:00:00 dzisiaj.

    if period_label == "Tydzień":
        start = now - datetime.timedelta(days=now.weekday())
        # Cofamy się do poniedziałku (weekday() = 0 dla poniedziałku).
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
        # Ustawia godzinę na 00:00:00 w poniedziałek.

    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Domyślnie: pierwszy dzień miesiąca o 00:00:00.


def _goal_period_key(reset_mode):
    # Tworzy "identyfikator okresu" dla celu czasowego na podstawie trybu resetowania.
    # Np. dla trybu "codziennie" zwróci datę typu "2026-06-04",
    # dla "co tydzień" zwróci "2026-W23" (rok i numer tygodnia).
    # Dzięki temu wiemy, w którym okresie cel został zalogowany
    # i czy trzeba go zresetować (gdy okres się zmienił).
    now = datetime.datetime.now()
    # Pobiera aktualną datę.

    if reset_mode == "daily":
        return now.date().isoformat()
        # Zwraca datę jako tekst (np. "2026-06-04").

    if reset_mode == "weekly":
        iso = now.isocalendar()
        # Pobiera (rok, numer tygodnia, dzień tygodnia).
        return f"{iso.year}-W{iso.week:02d}"
        # Zwraca np. "2026-W23" (rok 2026, tydzień 23).

    return "all"
    # Dla pozostałych trybów (never) – zwraca "all" (jeden okres na zawsze).


def _parse_goal_reset_mode(value):
    # Zamienia tekstowy opis trybu resetowania celu na wewnętrzny kod, który program rozumie.
    # Przykłady: "daily", "dziennie", "day" → "daily" (codziennie)
    #            "weekly", "tygodniowo" → "weekly" (co tydzień)
    #            "never", "none" → "never" (nigdy nie resetuj)
    # Jeśli nie rozpozna wartości – domyślnie ustawia "weekly".
    if not value:
        return "weekly"
        # Jeśli nie ma wartości – domyślnie co tydzień.

    v = str(value).lower()
    # Zamienia na małe litery (żeby "Dziennie" i "dziennie" działały tak samo).

    if v in ("never", "none"):
        return "never"
    if v in ("daily", "day", "dzien", "dziennie"):
        return "daily"
    if v in ("weekly", "week", "tydzien", "tygodniowo"):
        return "weekly"
    return "weekly"
    # Jeśli nie rozpoznał – domyślnie "weekly".


def _goal_logged_for_period(period_label, goal):
    # Sprawdza ile czasu z danego celu czasowego należy do wybranego okresu
    # statystyk (Dzień/Tydzień/Miesiąc). Cel może być resetowany codziennie,
    # co tydzień lub nigdy – to wpływa na to, w których statystykach się pojawi.
    # Np. cel tygodniowy pokaże się tylko w statystykach "Tydzień" i "Miesiąc",
    # ale nie w "Dzień".
    logged = int(float(goal.get("logged_seconds", 0)))
    # Pobiera zalogowane sekundy z celu. Jeśli brak – 0.

    if logged <= 0:
        return 0
        # Jeśli nie ma czasu w celu – zwraca 0.

    rm = _parse_goal_reset_mode(goal.get("reset_mode", ""))
    # Tłumaczy tryb resetowania na wewnętrzny kod (daily/weekly/never).

    pk = (goal.get("period_key") or "").strip()
    # Pobiera identyfikator okresu, w którym cel został zalogowany.

    day_key = _goal_period_key("daily")
    week_key = _goal_period_key("weekly")
    # Oblicza aktualne klucze okresu dla "dzisiaj" i "tego tygodnia".

    if rm == "never":
        return logged if period_label == "Miesiąc" else 0
        # Cel "nigdy nie resetuj" – pokazuje się tylko w statystykach miesięcznych.

    if rm == "daily":
        if pk != day_key:
            return 0
            # Jeśli cel był logowany w innym dniu – nie pokazuj.
        # Cel dzienny pokazuje się we wszystkich okresach (dzień, tydzień, miesiąc).
        if period_label == "Dzień":
            return logged
        if period_label == "Tydzień":
            return logged
        return logged

    if rm == "weekly":
        if pk != week_key:
            return 0
            # Jeśli cel był logowany w innym tygodniu – nie pokazuj.
        if period_label == "Dzień":
            return 0
            # Cel tygodniowy NIE pokazuje się w statystykach dziennych.
        return logged
        # Pokazuje się w tygodniowych i miesięcznych.

    return 0
    # Domyślnie – nie pokazuj.


def goal_seconds_by_project(period_label):
    # Przechodzi przez wszystkie projekty i sumuje czas spędzony na celach czasowych
    # w wybranym okresie (Dzień/Tydzień/Miesiąc). Wynik to słownik, gdzie kluczem
    # jest nazwa projektu, a wartością łączna liczba sekund z celów czasowych.
    # Te dane są dodawane do zwykłych sesji w statystykach.
    totals = {}
    # Pusty słownik: klucz = nazwa projektu, wartość = suma sekund z celów.

    for key, blob in load_project_details().items():
        # Przechodzi przez wszystkie projekty w szczegółach (notatki, cele).

        if not key or key == "_":
            continue
            # Pomija puste klucze i ukryty wpis "_".

        project_title = key
        # Domyślnie używamy klucza jako nazwy projektu.

        if key.startswith("proj-"):
            # Jeśli klucz wygląda jak UID (zaczyna się od "proj-")...
            projects_path = _projects_path()
            if os.path.exists(projects_path):
                try:
                    with open(projects_path, "r", encoding="utf-8") as f:
                        projects = json.load(f)
                    for p in projects:
                        if p.get("uid") == key:
                            project_title = p.get("title", key)
                            break
                            # ...szukamy projektu po UID i pobieramy jego nazwę.
                except (OSError, json.JSONDecodeError):
                    pass

        sec = 0
        for g in blob.get("goals") or []:
            sec += _goal_logged_for_period(period_label, g)
            # Sumuje czas z wszystkich celów tego projektu (w wybranym okresie).

        if sec > 0:
            totals[project_title] = totals.get(project_title, 0) + sec
            # Jeśli jest jakiś czas z celów – dodajemy do sumy projektu.

    return totals
    # Zwraca słownik: np. {"Strona WWW": 3600, "Aplikacja": 1800}


def format_statistics_duration(seconds):
    # Zamienia liczbę sekund na tekst zrozumiały dla człowieka.
    # Np. 3661 → "1:01:01" (1 godzina, 1 minuta, 1 sekunda).
    # Jeśli czas jest krótszy niż minuta – pokazuje tylko sekundy ("45 s").
    # Jeśli krótszy niż godzina – pokazuje minuty i sekundy ("30:15").
    s = max(0, int(seconds))
    # Zaokrągla sekundy do liczby całkowitej, minimum 0.

    if s < 60:
        return f"{s} s"
        # Mniej niż 60 sekund → "X s" (np. "45 s").

    h, r = divmod(s, 3600)
    # Dzieli sekundy na godziny i resztę. divmod(3661, 3600) = (1, 61).
    m, sec = divmod(r, 60)
    # Dzieli resztę na minuty i sekundy. divmod(61, 60) = (1, 1).

    if h:
        return f"{h}:{m:02d}:{sec:02d}"
        # Jeśli są godziny → "1:01:01" (godz:min:sek z zerami wiodącymi).

    return f"{m}:{sec:02d}"
    # Tylko minuty i sekundy → "30:15" (min:sek).


def format_statistics_total(seconds):
    return f"suma: {format_statistics_duration(seconds)}"
    # Zwraca tekst "suma: X" gdzie X to sformatowany czas całkowity
    # (np. "suma: 1:30:00" dla 5400 sekund). Używane na ekranie statystyk.


# ---------------------------------------------------------------------------
# FUNKCJE DO ODŚWIEŻANIA EKRANÓW
# ---------------------------------------------------------------------------

def schedule_statistics_refresh():
    # Odświeża ekran statystyk, ale z małym opóźnieniem.
    # To ważne, bo gdy dopiero co zapisaliśmy nową sesję, plik może być
    # jeszcze niegotowy do odczytu. Wywołujemy odświeżenie kilka razy
    # (po 0, 0.05 i 0.15 sekundy) żeby na pewno dane się załadowały.
    app = MDApp.get_running_app()
    # Pobiera aktualnie uruchomioną aplikację.

    if not app or not getattr(app, "root", None):
        return
        # Jeśli aplikacja nie istnieje lub nie ma głównego widoku – przerwij.

    try:
        stats = app.root.get_screen("statistics")
        # Próbuje pobrać ekran statystyk.
    except Exception:
        return
        # Jeśli ekran nie istnieje – przerwij.

    if stats is None:
        return

    for delay in (0, 0.05, 0.15):
        Clock.schedule_once(lambda _dt, s=stats: s.refresh_statistics(), delay)
        # Planuje odświeżenie statystyk trzy razy: od razu (0s),
        # po 0.05s i po 0.15s. Dzięki temu na pewno dane się załadują.


def schedule_home_last_session_refresh():
    # Odświeża kartę "ostatnia sesja" na ekranie głównym.
    # Robi to z opóźnieniem, żeby plik z sesjami zdążył się zapisać
    # zanim spróbujemy go odczytać. Podobnie jak w przypadku statystyk. 
    app = MDApp.get_running_app()
    # Pobiera aktualnie uruchomioną aplikację.

    if not app or not getattr(app, "root", None):
        return
        # Jeśli aplikacja nie istnieje – przerwij.

    try:
        home = app.root.get_screen("home")
        # Próbuje pobrać ekran główny.
    except Exception:
        return
        # Jeśli ekran nie istnieje – przerwij.

    if home is None:
        return

    for delay in (0, 0.05, 0.2):
        Clock.schedule_once(lambda _dt, h=home: h.refresh_last_session(), delay)
        # Planuje odświeżenie ostatniej sesji trzy razy z opóźnieniami.


def get_last_session():
    # Zwraca ostatnią (najnowszą) sesję z pliku, lub None jeśli nie ma żadnej.
    # Uzupełnia dane o emoji i kolorze z metadanych projektu.
    sessions = load_sessions()
    # Wczytuje wszystkie sesje.

    if not sessions:
        return None
        # Jeśli nie ma żadnej sesji – zwraca None.

    session = dict(sessions[0])
    # Bierze pierwszą sesję (najnowszą) i tworzy jej kopię.

    meta = find_project_meta(session.get("project_title", ""))
    # Szuka aktualnych danych projektu (emoji, kolor) w pliku projects.json.

    if meta.get("icon"):
        session["emoji_source"] = meta["icon"]
        # Jeśli projekt ma zdefiniowaną ikonę – używamy jej zamiast starej.

    session["emoji_source"] = resolve_emoji_source(
        session.get("emoji_source") or "folder-outline"
    )
    # Zamienia nazwę ikony na ścieżkę do pliku emoji.

    return session
    # Zwraca sesję z uzupełnionymi danymi.


def format_duration_hms(seconds):
    # Formatuje liczbę sekund w formacie HH:MM:SS (np. "01:30:00" = 1 godzina 30 minut).
    s = max(0, int(seconds))
    # Zaokrągla do liczby całkowitej, minimum 0.

    h, r = divmod(s, 3600)
    # Dzieli na godziny i resztę.
    m, sec = divmod(r, 60)
    # Dzieli resztę na minuty i sekundy.

    return f"{h:02d}:{m:02d}:{sec:02d}"
    # Zwraca "HH:MM:SS" (zawsze 2 cyfry, z zerami wiodącymi).


def format_when_label(iso_dt):
    # Tworzy polską etykietę opisującą kiedy sesja się zakończyła.
    # Jeśli dzisiaj – "Dzisiaj". Jeśli wczoraj – "Wczoraj".
    # W przeciwnym razie – dzień i miesiąc (np. "3 cze").
    if not iso_dt:
        return ""
        # Jeśli nie ma daty – zwraca pusty tekst.

    if isinstance(iso_dt, str):
        try:
            dt = datetime.datetime.fromisoformat(iso_dt)
            # Jeśli data to tekst (np. "2026-06-07T12:00:00") – zamieniamy na obiekt.
        except ValueError:
            return iso_dt
            # Jeśli format daty jest nieprawidłowy – zwracamy oryginalny tekst.
    else:
        dt = iso_dt
        # Jeśli to już obiekt datetime – używamy bezpośrednio.

    now = datetime.datetime.now()
    day = dt.date()
    today = now.date()
    # Pobiera samą datę (bez godziny) do porównania.

    if day == today:
        return "Dzisiaj"
        # Jeśli sesja zakończyła się dzisiaj.

    if day == today - datetime.timedelta(days=1):
        return "Wczoraj"
        # Jeśli sesja zakończyła się wczoraj.

    months = (
        "sty", "lut", "mar", "kwi", "maj", "cze",
        "lip", "sie", "wrz", "paź", "lis", "gru",
    )
    # Polski słownik miesięcy (skrócone nazwy).

    return f"{dt.day} {months[dt.month - 1]}"
    # Zwraca np. "3 cze" (3 czerwca). months[dt.month - 1] bo lista zaczyna się od 0.


def _parse_ended(session):
    # Wyciąga datę zakończenia sesji z jej danych.
    # Najpierw sprawdza pole "ended_at" (kiedy się zakończyła),
    # a jeśli go nie ma – używa "started_at" (kiedy się zaczęła).
    # To zabezpieczenie dla starszych wersji pliku, które nie miały
    # osobnego pola zakończenia. Jeśli daty są nieprawidłowe – zwraca None.
    raw = session.get("ended_at") or session.get("started_at")
    # Próbuje pobrać "ended_at", jeśli nie ma – "started_at".

    if not raw:
        return None
        # Jeśli nie ma żadnej daty – zwraca None.

    try:
        return datetime.datetime.fromisoformat(raw)
        # Próbuje zamienić tekst na obiekt daty.
    except ValueError:
        return None
        # Jeśli format jest nieprawidłowy – zwraca None.


def sessions_in_period(sessions, period_label):
    # Filtruje listę sesji – zostawia tylko te, które zakończyły się
    # w wybranym okresie (dzisiaj, w tym tygodniu, w tym miesiącu).
    # Dzięki temu statystyki pokazują tylko aktualne dane,
    # a nie całą historię od początku używania aplikacji.
    start = period_range_start(period_label)
    # Oblicza datę początku wybranego okresu (np. dzisiaj o 00:00).

    out = []
    # Pusta lista na sesje z wybranego okresu.

    for s in sessions:
        ended = _parse_ended(s)
        # Wyciąga datę zakończenia sesji.

        if ended is not None and ended >= start:
            out.append(s)
            # Jeśli sesja zakończyła się po starcie okresu – dodajemy do listy.

    return out
    # Zwraca sesje tylko z wybranego okresu.


def _merge_project_meta(row):
    # Sprawdza czy w danych projektu (przygotowanych do statystyk) są wszystkie
    # potrzebne informacje: emoji i kolor. Jeśli brakuje – uzupełnia je
    # z pliku projects.json. To zabezpieczenie na wypadek gdyby projekt
    # został zmieniony po zapisaniu sesji (np. zmiana emoji).
    meta = find_project_meta(row["title"])
    # Szuka aktualnych danych projektu w pliku projects.json.

    if meta:
        if meta.get("icon"):
            row["emoji_source"] = meta["icon"]
            # Jeśli projekt ma ikonę – używamy jej.
        if meta.get("color"):
            row["color"] = meta["color"]
            # Jeśli projekt ma kolor – używamy go.

    row["emoji_source"] = resolve_emoji_source(
        row.get("emoji_source") or "folder-outline"
    )
    # Zamienia nazwę ikony na ścieżkę do pliku emoji (lub domyślna ikona).

    return row
    # Zwraca wiersz z uzupełnionymi danymi.


def aggregate_by_project(sessions, period_label):
    # Grupuje sesje po projektach i sumuje czas dla każdego projektu.
    # Dodaje też czas z celów czasowych (goal_seconds_by_project).
    # Zwraca posortowaną listę (najwięcej czasu na początku).
    totals = {}
    # Pusty słownik: klucz = nazwa projektu, wartość = dane projektu + suma czasu.

    for s in sessions:
        # Przechodzi przez każdą sesję w wybranym okresie.

        title = (s.get("project_title") or "").strip() or "?"
        # Pobiera nazwę projektu, usuwa spacje. Jeśli pusta – "?".

        sec = int(s.get("duration_seconds", 0))
        # Pobiera czas trwania sesji w sekundach (minimum 0).

        if title not in totals:
            totals[title] = {
                "title": title,
                "emoji_source": resolve_emoji_source(
                    s.get("emoji_source", "folder-outline")
                ),
                "color": s.get("color", [0.6, 0.4, 0.8, 1]),
                "total_seconds": 0,
            }
            # Jeśli to pierwsza sesja dla tego projektu – tworzymy nowy wpis
            # z emoji, kolorem i licznikiem czasu.

        totals[title]["total_seconds"] += sec
        # Dodaje czas tej sesji do sumy projektu.

    # Dodaj czas z celów czasowych
    for title, sec in goal_seconds_by_project(period_label).items():
        # Przechodzi przez czas z celów czasowych dla każdego projektu.

        if title not in totals:
            meta = find_project_meta(title)
            totals[title] = {
                "title": title,
                "emoji_source": resolve_emoji_source(
                    meta.get("icon", "folder-outline")
                ),
                "color": meta.get("color", [0.6, 0.4, 0.8, 1]),
                "total_seconds": 0,
            }
            # Jeśli projektu nie ma jeszcze w wynikach – tworzymy nowy wpis.

        totals[title]["total_seconds"] += sec
        # Dodaje czas z celów do sumy projektu.

    rows = [_merge_project_meta(totals[t]) for t in totals]
    # Dla każdego projektu – uzupełnia dane (emoji, kolor) z pliku projects.json.

    rows = sorted(rows, key=lambda x: -x["total_seconds"])
    # Sortuje projekty: od największej liczby sekund do najmniejszej.

    return rows
    # Zwraca posortowaną listę projektów z czasami.


def statistics_from_sessions(period_label):
    # Główna funkcja dla ekranu statystyk.
    # Przygotowuje trzy rzeczy:
    #   1. "pie" – lista kolorów i procentów dla wykresu kołowego
    #   2. "detail" – lista szczegółów (nazwa, ikona, czas) dla tabeli
    #   3. "total" – łączny czas we wszystkich projektach
    sessions = sessions_in_period(load_sessions(), period_label)
    # Wczytuje sesje i filtruje je do wybranego okresu.

    rows = aggregate_by_project(sessions, period_label)
    # Grupuje sesje po projektach i sumuje czas.

    total = sum(r["total_seconds"] for r in rows)
    # Oblicza łączny czas wszystkich projektów w sekundach.

    if total <= 0:
        return [], [], 0
        # Jeśli nie ma żadnego czasu – zwracamy puste listy i zero.

    pie = []
    detail = []
    # Listy na dane wykresu kołowego i tabeli.

    percents = [100.0 * r["total_seconds"] / total for r in rows]
    # Oblicza procent każdego projektu: (jego sekundy / wszystkie sekundy) * 100%.
    # Np. projekt z 3600s z łącznego 7200s = 50%.

    rounded = [int(p) for p in percents]
    # Zaokrągla procenty do liczb całkowitych (np. 49.7 → 49).

    drift = 100 - sum(rounded)
    # Oblicza "błąd zaokrąglenia". Np. 49.5 + 50.5 = 100, ale po zaokrągleniu
    # 49 + 51 = 100. Czasem jednak 49.3 + 50.7 → 49 + 50 = 99 (brakuje 1%).

    if rounded and drift:
        rounded[0] += drift
        # Dodaje brakujący procent do pierwszego projektu (tego z największym
        # czasem), żeby suma zawsze wynosiła dokładnie 100%.

    for r, pct in zip(rows, rounded):
        # Przechodzi przez każdy projekt i jego procent.

        color = r["color"]
        # Pobiera kolor projektu.

        if len(color) == 3:
            color = (*color, 1.0)
            # Jeśli kolor ma tylko 3 składniki (R, G, B) – dodaje przezroczystość.

        pie.append({"color": tuple(color), "percent": pct})
        # Dodaje kolor i procent do listy dla wykresu kołowego.

        time_txt = format_statistics_duration(r["total_seconds"])
        # Formatuje czas projektu (np. 3661 sekund → "1:01:01").

        icon = r["emoji_source"]
        # Pobiera ścieżkę do ikony/emoji projektu.

        icon_color = (1, 1, 1, 1)
        # Domyślny kolor ikony: biały.

        if icon.endswith(".png"):
            icon_color = tuple(color[:3]) + (1.0,)
            # Jeśli ikona to plik PNG – używamy koloru projektu jako koloru ikony.

        detail.append(
            {
                "name": r["title"],
                "icon": icon,
                "segment_color": tuple(color),
                "time": time_txt,
                "icon_color": icon_color,
            }
        )
        # Dodaje szczegóły projektu do listy dla tabeli statystyk.

    return pie, detail, total
    # Zwraca: dane wykresu, dane tabeli, łączny czas.