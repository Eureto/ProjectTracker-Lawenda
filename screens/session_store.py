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
import json
import os

from kivy.clock import Clock
from kivymd.app import MDApp
from screens.emoji_assets import resolve_emoji_source


# Zwraca ścieżkę do pliku sessions.json, który przechowuje historię
# wszystkich zakończonych pomiarów czasu (sesji).
def _sessions_path():
    return os.path.join(MDApp.get_running_app().user_data_dir, "sessions.json")


# Zwraca ścieżkę do pliku projects.json, który przechowuje listę
# wszystkich zapisanych projektów (nazwy, kolory, emoji, zdjęcia).
def _projects_path():
    return os.path.join(MDApp.get_running_app().user_data_dir, "projects.json")


# Wczytuje wszystkie zapisane sesje z pliku sessions.json.
# Jeśli plik nie istnieje lub jest uszkodzony – zwraca pustą listę.
def load_sessions():
    path = _sessions_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


# Zapisuje listę sesji do pliku sessions.json.
# "os.makedirs(exist_ok=True)" – utwórz folder do zapisu jeśli nie istnieje.
# Parametr "exist_ok=True" oznacza: nie wyrzucaj błędu, jeśli folder już istnieje.
def save_sessions(sessions):
    path = _sessions_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)


def find_project_meta(project_title):
    # Szuka projektu po nazwie w pliku projects.json i zwraca jego dane.
    # Zwraca: emoji, kolor tła, zdjęcie itp. – wszystko co jest potrzebne
    # do wyświetlenia karty projektu. Jeśli nie znajdzie – zwraca pusty słownik.
    # Używane np. przy tworzeniu statystyk, żeby pokazać kolor projektu.
    path = _projects_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            projects = json.load(f)
        for p in projects:
            if p.get("title") == project_title:
                return p
    except (OSError, json.JSONDecodeError):
        pass
    return {}


# Dodaje nową sesję na początek listy (najnowsze pierwsze).
# Parametry:
#   project_title – nazwa projektu
#   duration_seconds – czas trwania w sekundach
#   started_at / ended_at – opcjonalne daty rozpoczęcia i zakończenia
#   project_uid – identyfikator projektu (jeśli znany)
# Funkcja odświeża też ekran główny i statystyki po dodaniu.
def record_session(project_title, duration_seconds, started_at=None, ended_at=None, project_uid=""):
    if not project_title or duration_seconds < 1:
        return None

    ended = ended_at or datetime.datetime.now()
    if isinstance(ended, str):
        ended = datetime.datetime.fromisoformat(ended)
    started = started_at or (ended - datetime.timedelta(seconds=int(duration_seconds)))
    if isinstance(started, str):
        started = datetime.datetime.fromisoformat(started)

    meta = find_project_meta(project_title)
    entry = {
        "project_uid": project_uid or meta.get("uid", ""),
        "project_title": project_title,
        "emoji_source": resolve_emoji_source(meta.get("icon", "emoticon-happy-outline")),
        "image": meta.get("image", ""),
        "color": meta.get("color", [0.7, 0.5, 1, 1]),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": int(duration_seconds),
    }
    sessions = load_sessions()
    sessions.insert(0, entry)
    save_sessions(sessions)
    # Odśwież ekran główny i statystyki (mogą być widoczne)
    schedule_home_last_session_refresh()
    schedule_statistics_refresh()
    return entry


# Zwraca ścieżkę do pliku project_details.json, który przechowuje
# szczegółowe dane projektów (notatki, cele, listy zadań, etapy).
def _project_details_path():
    return os.path.join(MDApp.get_running_app().user_data_dir, "project_details.json")


def load_project_details():
    # Wczytuje z pliku project_details.json wszystkie szczegóły projektów:
    # notatki, cele czasowe, listę celów (checklistę) i etapy.
    # Zwraca słownik gdzie kluczem jest nazwa (lub UID) projektu.
    # Jeśli plik nie istnieje lub jest uszkodzony – zwraca pusty słownik.
    path = _project_details_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


# Zwraca datę początku okresu dla statystyk.
# "Dzień" – początek dzisiejszego dnia (00:00:00).
# "Tydzień" – początek bieżącego tygodnia (poniedziałek 00:00:00).
# "Miesiąc" – pierwszy dzień miesiąca (00:00:00).
def period_range_start(period_label):
    now = datetime.datetime.now()
    if period_label == "Dzień":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period_label == "Tydzień":
        start = now - datetime.timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _goal_period_key(reset_mode):
    # Tworzy "identyfikator okresu" dla celu czasowego na podstawie trybu resetowania.
    # Np. dla trybu "codziennie" zwróci datę typu "2026-06-04",
    # dla "co tydzień" zwróci "2026-W23" (rok i numer tygodnia).
    # Dzięki temu wiemy, w którym okresie cel został zalogowany
    # i czy trzeba go zresetować (gdy okres się zmienił).
    now = datetime.datetime.now()
    if reset_mode == "daily":
        return now.date().isoformat()
    if reset_mode == "weekly":
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return "all"


def _parse_goal_reset_mode(value):
    # Zamienia tekstowy opis trybu resetowania celu na wewnętrzny kod, który program rozumie.
    # Przykłady: "daily", "dziennie", "day" → "daily" (codziennie)
    #            "weekly", "tygodniowo" → "weekly" (co tydzień)
    #            "never", "none" → "never" (nigdy nie resetuj)
    # Jeśli nie rozpozna wartości – domyślnie ustawia "weekly".
    if not value:
        return "weekly"
    v = str(value).lower()
    if v in ("never", "none"):
        return "never"
    if v in ("daily", "day", "dzien", "dziennie"):
        return "daily"
    if v in ("weekly", "week", "tydzien", "tygodniowo"):
        return "weekly"
    return "weekly"


def _goal_logged_for_period(period_label, goal):
    # Sprawdza ile czasu z danego celu czasowego należy do wybranego okresu
    # statystyk (Dzień/Tydzień/Miesiąc). Cel może być resetowany codziennie,
    # co tydzień lub nigdy – to wpływa na to, w których statystykach się pojawi.
    # Np. cel tygodniowy pokaże się tylko w statystykach "Tydzień" i "Miesiąc",
    # ale nie w "Dzień".
    logged = int(float(goal.get("logged_seconds", 0)))
    if logged <= 0:
        return 0
    rm = _parse_goal_reset_mode(goal.get("reset_mode", ""))
    pk = (goal.get("period_key") or "").strip()
    day_key = _goal_period_key("daily")
    week_key = _goal_period_key("weekly")

    if rm == "never":
        return logged if period_label == "Miesiąc" else 0
    if rm == "daily":
        if pk != day_key:
            return 0
        if period_label == "Dzień":
            return logged
        if period_label == "Tydzień":
            return logged
        return logged
    if rm == "weekly":
        if pk != week_key:
            return 0
        if period_label == "Dzień":
            return 0
        return logged
    return 0


def goal_seconds_by_project(period_label):
    # Przechodzi przez wszystkie projekty i sumuje czas spędzony na celach czasowych
    # w wybranym okresie (Dzień/Tydzień/Miesiąc). Wynik to słownik, gdzie kluczem
    # jest nazwa projektu, a wartością łączna liczba sekund z celów czasowych.
    # Te dane są dodawane do zwykłych sesji w statystykach.
    totals = {}
    for project_title, blob in load_project_details().items():
        if not project_title or project_title == "_":
            continue
        sec = 0
        for g in blob.get("goals") or []:
            sec += _goal_logged_for_period(period_label, g)
        if sec > 0:
            totals[project_title] = totals.get(project_title, 0) + sec
    return totals


def format_statistics_duration(seconds):
    # Zamienia liczbę sekund na tekst zrozumiały dla człowieka.
    # Np. 3661 → "1:01:01" (1 godzina, 1 minuta, 1 sekunda).
    # Jeśli czas jest krótszy niż minuta – pokazuje tylko sekundy ("45 s").
    # Jeśli krótszy niż godzina – pokazuje minuty i sekundy ("30:15").
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} s"
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


# Zwraca tekst "suma: X" gdzie X to sformatowany czas całkowity
# (np. "suma: 1:30:00" dla 5400 sekund). Używane na ekranie statystyk.
def format_statistics_total(seconds):
    return f"suma: {format_statistics_duration(seconds)}"


# ---------------------------------------------------------------------------
# FUNKCJE DO ODŚWIEŻANIA EKRANÓW
# ---------------------------------------------------------------------------

def schedule_statistics_refresh():
    # Odświeża ekran statystyk, ale z małym opóźnieniem.
    # To ważne, bo gdy dopiero co zapisaliśmy nową sesję, plik może być
    # jeszcze niegotowy do odczytu. Wywołujemy odświeżenie kilka razy
    # (po 0, 0.05 i 0.15 sekundy) żeby na pewno dane się załadowały.
    app = MDApp.get_running_app()
    if not app or not getattr(app, "root", None):
        return
    try:
        stats = app.root.get_screen("statistics")
    except Exception:
        return
    if stats is None:
        return
    for delay in (0, 0.05, 0.15):
        Clock.schedule_once(lambda _dt, s=stats: s.refresh_statistics(), delay)


def schedule_home_last_session_refresh():
    # Odświeża kartę "ostatnia sesja" na ekranie głównym.
    # Robi to z opóźnieniem, żeby plik z sesjami zdążył się zapisać
    # zanim spróbujemy go odczytać. Podobnie jak w przypadku statystyk. 
    app = MDApp.get_running_app()
    if not app or not getattr(app, "root", None):
        return
    try:
        home = app.root.get_screen("home")
    except Exception:
        return
    if home is None:
        return
    for delay in (0, 0.05, 0.2):
        Clock.schedule_once(lambda _dt, h=home: h.refresh_last_session(), delay)


# Zwraca ostatnią (najnowszą) sesję z pliku, lub None jeśli nie ma żadnej.
# Uzupełnia dane o emoji i kolorze z metadanych projektu.
def get_last_session():
    sessions = load_sessions()
    if not sessions:
        return None
    session = dict(sessions[0])
    meta = find_project_meta(session.get("project_title", ""))
    if meta.get("icon"):
        session["emoji_source"] = meta["icon"]
    session["emoji_source"] = resolve_emoji_source(
        session.get("emoji_source") or "folder-outline"
    )
    return session


# Formatuje liczbę sekund w formacie HH:MM:SS (np. "01:30:00" = 1 godzina 30 minut).
def format_duration_hms(seconds):
    s = max(0, int(seconds))
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


# Tworzy polską etykietę opisującą kiedy sesja się zakończyła.
# Jeśli dzisiaj – "Dzisiaj". Jeśli wczoraj – "Wczoraj".
# W przeciwnym razie – dzień i miesiąc (np. "3 cze").
def format_when_label(iso_dt):
    if not iso_dt:
        return ""
    if isinstance(iso_dt, str):
        try:
            dt = datetime.datetime.fromisoformat(iso_dt)
        except ValueError:
            return iso_dt
    else:
        dt = iso_dt

    now = datetime.datetime.now()
    day = dt.date()
    today = now.date()
    if day == today:
        return "Dzisiaj"
    if day == today - datetime.timedelta(days=1):
        return "Wczoraj"
    months = (
        "sty", "lut", "mar", "kwi", "maj", "cze",
        "lip", "sie", "wrz", "paź", "lis", "gru",
    )
    return f"{dt.day} {months[dt.month - 1]}"


def _parse_ended(session):
    # Wyciąga datę zakończenia sesji z jej danych.
    # Najpierw sprawdza pole "ended_at" (kiedy się zakończyła),
    # a jeśli go nie ma – używa "started_at" (kiedy się zaczęła).
    # To zabezpieczenie dla starszych wersji pliku, które nie miały
    # osobnego pola zakończenia. Jeśli daty są nieprawidłowe – zwraca None.
    raw = session.get("ended_at") or session.get("started_at")
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def sessions_in_period(sessions, period_label):
    # Filtruje listę sesji – zostawia tylko te, które zakończyły się
    # w wybranym okresie (dzisiaj, w tym tygodniu, w tym miesiącu).
    # Dzięki temu statystyki pokazują tylko aktualne dane,
    # a nie całą historię od początku używania aplikacji.
    start = period_range_start(period_label)
    out = []
    for s in sessions:
        ended = _parse_ended(s)
        if ended is not None and ended >= start:
            out.append(s)
    return out


def _merge_project_meta(row):
    # Sprawdza czy w danych projektu (przygotowanych do statystyk) są wszystkie
    # potrzebne informacje: emoji i kolor. Jeśli brakuje – uzupełnia je
    # z pliku projects.json. To zabezpieczenie na wypadek gdyby projekt
    # został zmieniony po zapisaniu sesji (np. zmiana emoji).
    meta = find_project_meta(row["title"])
    if meta:
        if meta.get("icon"):
            row["emoji_source"] = meta["icon"]
        if meta.get("color"):
            row["color"] = meta["color"]
    row["emoji_source"] = resolve_emoji_source(
        row.get("emoji_source") or "folder-outline"
    )
    return row


# Grupuje sesje po projektach i sumuje czas dla każdego projektu.
# Dodaje też czas z celów czasowych (goal_seconds_by_project).
# Zwraca posortowaną listę (najwięcej czasu na początku).
def aggregate_by_project(sessions, period_label):
    totals = {}
    for s in sessions:
        title = (s.get("project_title") or "").strip() or "?"
        sec = int(s.get("duration_seconds", 0))
        if title not in totals:
            totals[title] = {
                "title": title,
                "emoji_source": resolve_emoji_source(
                    s.get("emoji_source", "folder-outline")
                ),
                "color": s.get("color", [0.6, 0.4, 0.8, 1]),
                "total_seconds": 0,
            }
        totals[title]["total_seconds"] += sec

    # Dodaj czas z celów czasowych
    for title, sec in goal_seconds_by_project(period_label).items():
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
        totals[title]["total_seconds"] += sec

    rows = [_merge_project_meta(totals[t]) for t in totals]
    rows = sorted(rows, key=lambda x: -x["total_seconds"])
    return rows


# Główna funkcja dla ekranu statystyk.
# Przygotowuje trzy rzeczy:
#   1. "pie" – lista kolorów i procentów dla wykresu kołowego
#   2. "detail" – lista szczegółów (nazwa, ikona, czas) dla tabeli
#   3. "total" – łączny czas we wszystkich projektach
def statistics_from_sessions(period_label):
    sessions = sessions_in_period(load_sessions(), period_label)
    rows = aggregate_by_project(sessions, period_label)
    total = sum(r["total_seconds"] for r in rows)
    if total <= 0:
        return [], [], 0

    pie = []
    detail = []
    percents = [100.0 * r["total_seconds"] / total for r in rows]
    rounded = [int(p) for p in percents]
    drift = 100 - sum(rounded)
    if rounded and drift:
        rounded[0] += drift
    for r, pct in zip(rows, rounded):
        color = r["color"]
        if len(color) == 3:
            color = (*color, 1.0)
        pie.append({"color": tuple(color), "percent": pct})
        time_txt = format_statistics_duration(r["total_seconds"])
        icon = r["emoji_source"]
        icon_color = (1, 1, 1, 1)
        if icon.endswith(".png"):
            icon_color = tuple(color[:3]) + (1.0,)
        detail.append(
            {
                "name": r["title"],
                "icon": icon,
                "segment_color": tuple(color),
                "time": time_txt,
                "icon_color": icon_color,
            }
        )
    return pie, detail, total