# Zarządzanie aktywnym timerem (stoperem) projektu.
# Ten plik przechowuje informacje o tym, który projekt jest aktualnie mierzony oraz które cele czasowe są włączone.
# Dane są zapisywane w plikach JSON w prywatnym folderze aplikacji, więc przetrwają zamknięcie i ponowne otwarcie aplikacji.

import datetime
# "datetime" – wbudowany moduł do obsługi dat i czasu. Używamy go do
# zapisywania kiedy stoper został uruchomiony i zatrzymany.

import json
# "json" – wbudowany moduł do odczytu/zapisu plików w formacie JSON.
# Dane stopera, celów i sesji są przechowywane jako JSON.

import os
# "os" – funkcje systemowe: sprawdzanie czy plik istnieje, łączenie ścieżek,
# usuwanie plików.

import tempfile
# "tempfile" – tworzy tymczasowe pliki. Używamy go do bezpiecznego zapisu
# danych: najpierw zapisujemy do pliku tymczasowego, potem podmieniamy oryginał.
# To chroni przed utratą danych, gdyby zapis się nie powiódł.

import uuid
# "uuid" – generuje unikalne identyfikatory (UID). Każdy projekt dostaje
# swój własny numer, żeby nie mieszać danych między projektami
# o takich samych nazwach.


# Nazwy plików, w których przechowujemy dane

ACTIVE_TIMER_FILE = "active_timer.json"
# Plik przechowujący stan aktualnie działającego stopera (nazwa projektu,
# czas rozpoczęcia, dotychczasowy czas).

ACTIVE_GOALS_FILE = "active_goals.json"
# Plik przechowujący listę aktywnych celów czasowych.

PROJECT_DETAILS_FILE = "project_details.json"
# Plik przechowujący szczegóły projektów: notatki, cele czasowe,
# listy zadań (checklisty) i etapy.

PROJECTS_FILE = "projects.json"
# Plik przechowujący listę wszystkich projektów (nazwy, kolory, emoji, zdjęcia).

SESSIONS_FILE = "sessions.json"
# Plik przechowujący historię zakończonych pomiarów czasu (sesji).

CARD_POSITIONS_FILE = "card_positions.json"
# Plik przechowujący pozycje kart na ekranie głównym (gdy użytkownik
# przeciągnął karty w swobodnym układzie).


_BASE_DIR_OVERRIDE = None
# Zmienna globalna – jeśli nie jest None, zastępuje domyślną ścieżkę
# do folderu z danymi. Używana przez usługę Androida, która ma inny
# dostęp do plików niż główna aplikacja.


def set_base_dir(path):
    # Ustawia folder do zapisu danych (używane przez usługę na Androidzie).
    global _BASE_DIR_OVERRIDE
    # Mówi Pythonowi: "użyj globalnej zmiennej, nie twórz nowej lokalnej".

    _BASE_DIR_OVERRIDE = path or None
    # Zapisuje ścieżkę. Jeśli path jest puste/None – ustawia None (użyj domyślnej).


def _android_files_dir():
    # Próbuje znaleźć prywatny folder aplikacji na Androidzie.
    try:
        from jnius import autoclass
        # Próbuje zaimportować jnius (biblioteka do łączenia Pythona z Javą).
    except Exception:
        return None
        # Jeśli jnius nie jest dostępny (np. na komputerze) – zwraca None.

    for cls_name, attr in (
        ("org.kivy.android.PythonService", "mService"),
        ("org.kivy.android.PythonActivity", "mActivity"),
    ):
        # Sprawdza dwie możliwości: usługa Kivy lub aktywność Kivy.

        try:
            ctx = getattr(autoclass(cls_name), attr, None)
            # Próbuje pobrać obiekt usługi/aktywności Androida.

            if ctx is None:
                continue
                # Jeśli nie udało się pobrać – spróbuj następnej opcji.

            return ctx.getFilesDir().getAbsolutePath()
            # Pobiera ścieżkę do prywatnego folderu aplikacji.
        except Exception:
            continue

    return None
    # Jeśli nie udało się znaleźć folderu – zwraca None.


def default_base_dir():
    # Zwraca domyślny folder do zapisu danych aplikacji.
    if _BASE_DIR_OVERRIDE:
        return _BASE_DIR_OVERRIDE
        # Jeśli usługa ustawiła własną ścieżkę – użyj jej.

    try:
        from kivymd.app import MDApp
        app = MDApp.get_running_app()
        # Próbuje pobrać aktualnie uruchomioną aplikację KivyMD.

        if app is not None and getattr(app, "user_data_dir", ""):
            return app.user_data_dir
            # Jeśli aplikacja istnieje – użyj jej prywatnego folderu.
    except Exception:
        pass

    android_dir = _android_files_dir()
    # Próbuje znaleźć folder po stronie Androida.

    if android_dir:
        return android_dir

    return os.environ.get("PROJECTTRACKER_USER_DATA_DIR") or os.getcwd()
    # Ostateczność: zmienna środowiskowa lub bieżący folder.


# ---------------------------------------------------------------------------
# FUNKCJE POMOCNICZE DO ODCZYTU / ZAPISU PLIKÓW
# ---------------------------------------------------------------------------

def _path(filename, base_dir=None):
    # Zwraca pełną ścieżkę do pliku: folder (base_dir lub domyślny) + nazwa pliku.
    return os.path.join(base_dir or default_base_dir(), filename)


def _read_json(filename, default, base_dir=None):
    # Wczytuje plik JSON w bezpieczny sposób. Jeśli plik nie istnieje lub jest
    # uszkodzony, zwraca domyślną wartość, taką jak pusta lista lub słownik.
    path = _path(filename, base_dir)
    # Oblicza pełną ścieżkę do pliku.

    if not os.path.exists(path):
        return default
        # Jeśli plik nie istnieje – zwraca wartość domyślną.

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Otwiera plik i odczytuje JSON.

        return data if data is not None else default
        # Jeśli dane nie są None – zwraca je. W przeciwnym razie – domyślne.

    except (OSError, json.JSONDecodeError):
        return default
        # Jeśli plik jest uszkodzony lub nie dało się go przeczytać –
        # zwraca domyślną wartość.


def _write_json(filename, data, base_dir=None):
    # Zapisuje dane do pliku JSON w bezpieczny sposób. Najpierw zapisuje je
    # do tymczasowego pliku, a potem podmienia oryginał – to chroni przed
    # utratą danych, gdyby zapis się nie powiódł.
    path = _path(filename, base_dir)
    # Oblicza pełną ścieżkę do pliku.

    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Tworzy foldery na ścieżce jeśli nie istnieją.

    fd, tmp = tempfile.mkstemp(prefix=f".{filename}.", dir=os.path.dirname(path))
    # Tworzy tymczasowy plik w tym samym folderze.
    # fd = deskryptor pliku (numer), tmp = ścieżka do pliku tymczasowego.

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            # Zapisuje dane do pliku tymczasowego.

        os.replace(tmp, path)
        # Podmienia oryginalny plik tymczasowym (atomowa operacja).
        # Dzięki temu oryginał nie zostanie uszkodzony, nawet jeśli
        # w trakcie zapisu wystąpi błąd.
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
                # Sprząta plik tymczasowy (jeśli nadal istnieje).
            except OSError:
                pass


def _remove(filename, base_dir=None):
    # Usuwa plik, jeśli istnieje.
    try:
        os.remove(_path(filename, base_dir))
        # Próbuje usunąć plik.
    except FileNotFoundError:
        pass
        # Jeśli plik nie istnieje – nic nie rób (to nie jest błąd).
    except OSError:
        pass
        # Inne błędy systemowe – też ignorujemy.


def _now():
    # Zwraca aktualną datę i godzinę z systemu.
    return datetime.datetime.now()


def _to_datetime(value):
    # Konwertuje podaną wartość (tekst lub wewnętrzny format daty) na
    # wewnętrzny format datetime, którym program może łatwo manipulować.
    # Jeśli podano już datetime, zwraca je bez zmian.
    if isinstance(value, datetime.datetime):
        return value
        # Jeśli to już obiekt datetime – zwróć bez zmian.

    if not value:
        return None
        # Jeśli wartość jest pusta (None, "") – zwróć None.

    try:
        return datetime.datetime.fromisoformat(str(value))
        # Próbuje zamienić tekst (np. "2026-06-07T12:00:00") na obiekt daty.
    except ValueError:
        return None
        # Jeśli format jest nieprawidłowy – zwraca None.


# ---------------------------------------------------------------------------
# OBLICZANIE CZASU
# ---------------------------------------------------------------------------

def elapsed_from_state(state, now=None):
    # Oblicza łączny czas w sekundach, który upłynął od uruchomienia stopera
    # do teraz. Sumuje czas z poprzednich uruchomień (base_elapsed_seconds)
    # z czasem bieżącego uruchomienia.
    started = _to_datetime((state or {}).get("started_at"))
    # Pobiera datę rozpoczęcia bieżącego pomiaru.

    if started is None:
        return float((state or {}).get("base_elapsed_seconds", 0))
        # Jeśli nie ma daty startu (stoper nie był uruchomiony) –
        # zwróć tylko poprzedni czas.

    now = now or _now()
    # Jeśli nie podano "teraz" – użyj aktualnego czasu.

    base = float((state or {}).get("base_elapsed_seconds", 0))
    # Pobiera czas z poprzednich uruchomień (w sekundach).

    return max(0.0, base + (now - started).total_seconds())
    # Zwraca: poprzedni czas + czas od ostatniego startu do teraz.
    # max(0.0) – zabezpieczenie przed ujemną wartością.


def running_seconds(state, now=None):
    # Oblicza liczbę sekund, które upłynęły od ostatniego uruchomienia stopera.
    started = _to_datetime((state or {}).get("started_at"))
    # Pobiera datę rozpoczęcia bieżącego pomiaru.

    if started is None:
        return 0.0
        # Jeśli nie ma daty startu – stoper nie jest uruchomiony, zwróć 0.

    now = now or _now()
    # Jeśli nie podano "teraz" – użyj aktualnego czasu.

    return max(0.0, (now - started).total_seconds())
    # Zwraca: czas od startu do teraz (w sekundach).


# ---------------------------------------------------------------------------
# TIMER (STOPER) GŁÓWNEGO PROJEKTU
# ---------------------------------------------------------------------------

def read_project_timer(base_dir=None):
    # Odczytuje aktualny stan stopera projektu.
    data = _read_json(ACTIVE_TIMER_FILE, {}, base_dir)
    # Wczytuje dane z pliku active_timer.json.

    if not isinstance(data, dict):
        return {}
        # Jeśli dane to nie słownik – zwraca pusty słownik.

    if data.get("project_title") and not data.get("project_uid"):
        meta = _project_meta_by_title(data.get("project_title"), base_dir)
        if meta.get("uid"):
            data["project_uid"] = meta["uid"]
            # Jeśli stoper ma nazwę projektu ale nie ma UID – uzupełnia UID
            # z metadanych projektu (migracja ze starej wersji).

    return data if data.get("project_title") or data.get("project_uid") else {}
    # Zwraca dane tylko jeśli jest nazwa projektu lub UID (w przeciwnym razie
    # stoper nie istnieje – zwraca pusty słownik).


def start_project_timer(
    project_title,
    base_elapsed_seconds=0,
    started_at=None,
    base_dir=None,
    project_uid="",
):
    # Uruchamia stoper (licznik czasu) dla wybranego projektu. Zapisuje w pliku
    # nazwę projektu, dotychczasowy czas oraz moment startu.
    state = {
        "project_uid": project_uid or "",
        # UID projektu (jeśli znany).

        "project_title": project_title,
        # Nazwa projektu.

        "base_elapsed_seconds": int(max(0, float(base_elapsed_seconds or 0))),
        # Czas z poprzednich pomiarów (w sekundach). Minimum 0.

        "started_at": (started_at or _now()).isoformat(),
        # Data i czas rozpoczęcia pomiaru (w formacie ISO).
    }

    _write_json(ACTIVE_TIMER_FILE, state, base_dir)
    # Zapisuje stan stopera do pliku.

    return state
    # Zwraca zapisany stan.


def clear_project_timer(base_dir=None):
    # Zatrzymuje i usuwa plik przechowujący stan stopera projektu.
    _remove(ACTIVE_TIMER_FILE, base_dir)
    # Usuwa plik active_timer.json – stoper przestaje istnieć.


# ---------------------------------------------------------------------------
# CELE CZASOWE (z samochodzikiem)
# ---------------------------------------------------------------------------

def read_goals(base_dir=None):
    # Odczytuje listę aktualnie aktywnych celów czasowych.
    data = _read_json(ACTIVE_GOALS_FILE, [], base_dir)
    # Wczytuje dane z pliku active_goals.json.

    if not isinstance(data, list):
        return []
        # Jeśli dane to nie lista – zwraca pustą listę.

    changed = False
    for goal in data:
        if isinstance(goal, dict) and goal.get("project_title") and not goal.get("project_uid"):
            meta = _project_meta_by_title(goal.get("project_title"), base_dir)
            if meta.get("uid"):
                goal["project_uid"] = meta["uid"]
                changed = True
                # Jeśli cel ma nazwę projektu ale nie ma UID – uzupełnia UID
                # z metadanych projektu (migracja ze starej wersji).

    if changed:
        try:
            _write_json(ACTIVE_GOALS_FILE, data, base_dir)
            # Jeśli zmieniono jakieś cele – zapisuje zaktualizowane dane.
        except OSError:
            pass

    return data


def read_goal(uid, base_dir=None):
    # Zwraca pojedynczy cel czasowy na podstawie jego unikalnego identyfikatora.
    for goal in read_goals(base_dir):
        if goal.get("uid") == uid:
            return goal
            # Przechodzi przez wszystkie aktywne cele i szuka tego z podanym UID.
    return {}
    # Jeśli nie znaleziono – zwraca pusty słownik.


def upsert_goal(goal_state, base_dir=None):
    # Dodaje nowy cel czasowy lub aktualizuje istniejący.
    uid = goal_state.get("uid")
    # Pobiera UID celu.

    if not uid:
        return goal_state
        # Jeśli cel nie ma UID – nie da się go zapisać.

    goals = [g for g in read_goals(base_dir) if g.get("uid") != uid]
    # Bierze wszystkie aktywne cele OPRÓCZ tego z podanym UID.

    goals.append(goal_state)
    # Dodaje nowy/aktualizowany cel na koniec listy.

    _write_json(ACTIVE_GOALS_FILE, goals, base_dir)
    # Zapisuje zaktualizowaną listę.

    return goal_state


def start_goal(
    uid,
    project_title,
    title,
    goal_text,
    target_seconds,
    base_logged_seconds=0,
    reset_mode="weekly",
    period_key="",
    started_at=None,
    base_dir=None,
    project_uid="",
):
    # Uruchamia nowy cel czasowy. Zapisuje w pliku wszystkie ustawienia celu,
    # takie jak nazwa, limit czasu i moment rozpoczęcia.
    state = {
        "uid": uid,
        # Unikalny identyfikator celu.

        "project_uid": project_uid or "",
        # UID projektu (jeśli znany).

        "project_title": project_title,
        # Nazwa projektu.

        "title": title or "Cel",
        # Tytuł celu (np. "Nauka hiszpańskiego").

        "goal_text": goal_text or "",
        # Dodatkowy opis celu (opcjonalny).

        "target_seconds": float(max(1.0, float(target_seconds or 1))),
        # Docelowy czas w sekundach. Minimum 1 sekunda.

        "base_logged_seconds": float(max(0.0, float(base_logged_seconds or 0))),
        # Czas już zalogowany przed uruchomieniem (w sekundach). Minimum 0.

        "reset_mode": reset_mode or "weekly",
        # Tryb resetowania: "daily" (codziennie), "weekly" (co tydzień),
        # "never" (nigdy).

        "period_key": period_key or "",
        # Klucz okresu (np. "2026-W23" dla bieżącego tygodnia).

        "started_at": (started_at or _now()).isoformat(),
        # Data i czas rozpoczęcia pomiaru.
    }

    return upsert_goal(state, base_dir)
    # Zapisuje cel i zwraca jego stan.


def remove_goal(uid, base_dir=None):
    # Usuwa określony cel czasowy.
    goals = [g for g in read_goals(base_dir) if g.get("uid") != uid]
    # Bierze wszystkie aktywne cele OPRÓCZ tego z podanym UID.

    if goals:
        _write_json(ACTIVE_GOALS_FILE, goals, base_dir)
        # Jeśli zostały jakieś cele – zapisuje listę bez usuniętego.
    else:
        _remove(ACTIVE_GOALS_FILE, base_dir)
        # Jeśli nie ma już żadnych celów – usuwa cały plik.


# ---------------------------------------------------------------------------
# SZCZEGÓŁY PROJEKTU (notatki, cele, etapy)
# ---------------------------------------------------------------------------

def _read_project_details(base_dir=None):
    # Odczytuje z pliku szczegóły projektów (notatki, cele, postępy).
    data = _read_json(PROJECT_DETAILS_FILE, {}, base_dir)
    return data if isinstance(data, dict) else {}
    # Zwraca dane tylko jeśli to słownik – w przeciwnym razie pusty słownik.

def _write_project_details(data, base_dir=None):
    # Zapisuje do pliku szczegóły projektów (notatki, cele, postępy).
    _write_json(PROJECT_DETAILS_FILE, data, base_dir)

def _read_projects(base_dir=None):
    # Odczytuje z pliku listę wszystkich projektów.
    data = _read_json(PROJECTS_FILE, [], base_dir)
    return data if isinstance(data, list) else []
    # Zwraca dane tylko jeśli to lista – w przeciwnym razie pusta lista.


def _project_meta_by_uid(project_uid, base_dir=None):
    # Znajduje metadane projektu na podstawie jego unikalnego identyfikatora (UID).
    if not project_uid:
        return {}
        # Jeśli nie ma UID – zwraca pusty słownik.

    for project in _read_projects(base_dir):
        if project.get("uid") == project_uid:
            return project
            # Przechodzi przez wszystkie projekty i szuka tego z podanym UID.

    return {}
    # Jeśli nie znaleziono – zwraca pusty słownik.


def _project_meta_by_title(project_title, base_dir=None):
    # Znajduje metadane projektu na podstawie jego nazwy (tytułu).
    if not project_title:
        return {}
        # Jeśli nie ma nazwy – zwraca pusty słownik.

    for project in _read_projects(base_dir):
        if project.get("title") == project_title:
            return project
            # Przechodzi przez wszystkie projekty i szuka tego z podaną nazwą.

    return {}
    # Jeśli nie znaleziono – zwraca pusty słownik.


def _project_meta(project_uid=None, project_title=None, base_dir=None):
    # Szuka metadanych projektu – najpierw po UID, a jeśli go nie ma, po tytule.
    meta = _project_meta_by_uid(project_uid, base_dir) if project_uid else {}
    # Próbuje znaleźć po UID.

    if not meta and project_title:
        meta = _project_meta_by_title(project_title, base_dir)
        # Jeśli nie znaleziono po UID – szuka po nazwie.

    return meta


def _details_key(state_or_meta):
    # Określa unikalny identyfikator (UID lub tytuł) używany do przechowywania
    # danych projektu. Dzięki temu każdy projekt ma swoje własne miejsce
    # w pamięci – nawet jeśli dwa projekty mają tę samą nazwę.
    if not isinstance(state_or_meta, dict):
        return "_"
        # Jeśli to nie słownik – zwraca podkreślnik (klucz wewnętrzny).

    return (
        state_or_meta.get("project_uid")
        or state_or_meta.get("uid")
        or state_or_meta.get("project_title")
        or "_"
    )
    # Zwraca: po pierwsze UID projektu, po drugie UID ogólny,
    # po trzecie nazwę projektu, a jeśli nic nie pasuje – "_".


# ---------------------------------------------------------------------------
# ZAPISYWANIE SESJI (zakończonego pomiaru czasu)
# ---------------------------------------------------------------------------

def record_session(project_title, duration_seconds, started_at=None, ended_at=None, base_dir=None, project_uid=""):
    # Zapisuje zakończoną sesję pomiaru czasu, czyli jeden odcinek czasu.
    if not project_title or int(duration_seconds) < 1:
        return None
        # Jeśli nie ma nazwy projektu lub czas < 1 sekundy – nie zapisuj.

    ended = _to_datetime(ended_at) or _now()
    # Ustala datę zakończenia: podana lub "teraz".

    started = _to_datetime(started_at) or (ended - datetime.timedelta(seconds=int(duration_seconds)))
    # Ustala datę rozpoczęcia: podana lub (zakończenie - czas trwania).

    meta = _project_meta(project_uid=project_uid, project_title=project_title, base_dir=base_dir)
    # Pobiera dane projektu (emoji, kolor, zdjęcie).

    entry = {
        "project_uid": project_uid or meta.get("uid", ""),
        "project_title": project_title,
        "emoji_source": meta.get("icon", "emoticon-happy-outline"),
        "image": meta.get("image", ""),
        "color": meta.get("color", [0.7, 0.5, 1, 1]),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": int(duration_seconds),
    }
    # Tworzy wpis sesji: UID projektu, nazwa, emoji, zdjęcie, kolor, daty, czas.

    sessions = _read_json(SESSIONS_FILE, [], base_dir)
    # Wczytuje istniejące sesje.

    if not isinstance(sessions, list):
        sessions = []
        # Jeśli dane to nie lista – zaczyna od pustej listy.

    sessions.insert(0, entry)
    # Wstawia nową sesję na początek listy (najnowsza pierwsza).

    _write_json(SESSIONS_FILE, sessions, base_dir)
    # Zapisuje zaktualizowaną listę.

    return entry
    # Zwraca zapisaną sesję.


def finalize_project_timer(base_dir=None, now=None):
    # Zatrzymuje stoper, zapisuje sesję i czyści przechowywany stan.
    state = read_project_timer(base_dir)
    # Odczytuje stan stopera.

    if not state:
        return None
        # Jeśli stoper nie jest aktywny – zwróć None.

    now = now or _now()
    # Ustala "teraz".

    started = _to_datetime(state.get("started_at"))
    # Pobiera datę rozpoczęcia.

    duration = running_seconds(state, now)
    # Oblicza czas bieżącego pomiaru (sekundy od startu do teraz).

    total_elapsed = elapsed_from_state(state, now)
    # Oblicza łączny czas (poprzedni + bieżący).

    project_title = state.get("project_title", "")
    project_uid = state.get("project_uid", "")
    # Pobiera nazwę i UID projektu.

    if duration >= 1:
        record_session(
            project_title,
            duration,
            started_at=started,
            ended_at=now,
            base_dir=base_dir,
            project_uid=project_uid,
        )
        # Jeśli czas >= 1 sekunda – zapisuje sesję.

    details = _read_project_details(base_dir)
    # Wczytuje szczegóły projektu.

    blob = details.setdefault(_details_key(state), {})
    # Pobiera lub tworzy wpis dla tego projektu w szczegółach.

    blob["timer_elapsed"] = max(
        int(blob.get("timer_elapsed", 0) or 0), int(total_elapsed)
    )
    # Zapisuje maksymalny czas stopera (nie zmniejsza się).

    _write_project_details(details, base_dir)
    # Zapisuje zaktualizowane szczegóły.

    clear_project_timer(base_dir)
    # Usuwa plik stopera (stoper przestaje być aktywny).

    return {
        "project_uid": project_uid,
        "project_title": project_title,
        "duration_seconds": duration,
        "timer_elapsed": total_elapsed,
    }
    # Zwraca podsumowanie zatrzymanego stopera.


def finalize_goal(uid, base_dir=None, now=None):
    # Zatrzymuje cel czasowy i zapisuje jego aktualny stan.
    goal = read_goal(uid, base_dir)
    # Odczytuje cel po UID.

    if not goal:
        return None
        # Jeśli cel nie istnieje – zwróć None.

    now = now or _now()

    total_logged = (
        float(goal.get("base_logged_seconds", 0.0))
        + float(running_seconds(goal, now))
    )
    # Oblicza łączny czas: poprzednio zalogowany + czas bieżącego pomiaru.

    project_title = goal.get("project_title", "")
    project_uid = goal.get("project_uid", "")

    details = _read_project_details(base_dir)
    # Wczytuje szczegóły projektu.

    blob = details.setdefault(_details_key(goal), {})
    # Pobiera lub tworzy wpis dla tego projektu.

    goals = blob.setdefault("goals", [])
    # Pobiera lub tworzy listę celów w szczegółach.

    for saved in goals:
        if saved.get("uid") == uid:
            # Szuka zapisanego celu o tym samym UID.

            period_key = goal.get("period_key", saved.get("period_key", ""))
            # Pobiera klucz okresu (np. "2026-W23").

            if saved.get("period_key") == period_key:
                saved["logged_seconds"] = max(
                    float(saved.get("logged_seconds", 0) or 0), total_logged
                )
                # Jeśli ten sam okres – zachowuje większą wartość.
            else:
                saved["logged_seconds"] = total_logged
                # Jeśli inny okres – zapisuje nowy czas.

            saved["period_key"] = period_key
            break

    _write_project_details(details, base_dir)
    # Zapisuje zaktualizowane szczegóły.

    remove_goal(uid, base_dir)
    # Usuwa cel z aktywnych (cel został zrealizowany/zatrzymany).

    return {
        "uid": uid,
        "project_uid": project_uid,
        "project_title": project_title,
        "logged_seconds": total_logged,
    }
    # Zwraca podsumowanie zatrzymanego celu.


def has_active_items(base_dir=None):
    # Sprawdza, czy istnieje aktywny stoper lub aktywny cel czasowy.
    return bool(read_project_timer(base_dir) or read_goals(base_dir))
    # True = jest stoper LUB są cele czasowe. False = nic nie jest aktywne.


# ---------------------------------------------------------------------------
# MIGRACJA DANYCH – nadawanie UID starym projektom
# ---------------------------------------------------------------------------
# Kiedyś projekty były identyfikowane tylko po nazwie (tytule). To powodowało
# problemy gdy dwa projekty miały tę samą nazwę – ich dane się mieszały.
# Dlatego teraz każdy projekt ma swój unikalny numer (UID). Poniższe funkcje
# nadają UID istniejącym projektom i przenoszą ich dane z kluczy nazwowych
# na klucze UID.

def _new_uid():
    # Tworzy nowy unikalny identyfikator. Zawsze zaczyna się od "proj-".
    return f"proj-{uuid.uuid4().hex}"
    # uuid4() generuje losowy identyfikator, .hex zwraca go bez myślników.
    # Przykład: "proj-a1b2c3d4e5f6..."

def ensure_project_uids(base_dir=None):
    # Dodaje brakujące UID do wszystkich projektów. Wywoływane automatycznie
    # przy starcie, aby projekty bez UID (z wcześniejszych wersji) dostały
    # swój własny unikalny numer.
    projects = _read_projects(base_dir)
    # Wczytuje listę wszystkich projektów.

    if not isinstance(projects, list):
        return []
        # Jeśli dane to nie lista – zwraca pustą listę.

    changed = False
    for project in projects:
        if not isinstance(project, dict):
            continue
        if not project.get("uid"):
            project["uid"] = _new_uid()
            # Jeśli projekt nie ma UID – nadaje mu nowy.
            changed = True

    if changed:
        _write_json(PROJECTS_FILE, projects, base_dir)
        # Jeśli zmieniono jakieś projekty – zapisuje zaktualizowaną listę.

    return projects


def migrate_legacy_state_to_uids(base_dir=None):
    # Przenosi dane z kluczy opartych na tytule na klucze oparte na UID.
    projects = ensure_project_uids(base_dir)
    # Nadaje UID wszystkim projektom, które jeszcze ich nie mają.

    title_to_uid = {}
    # Słownik: nazwa projektu → UID. Potrzebny do znalezienia UID po nazwie.

    for project in projects:
        if not isinstance(project, dict):
            continue
        title = project.get("title")
        uid = project.get("uid")
        if not title or not uid:
            continue
        title_to_uid.setdefault(title, uid)
        # Jeśli nazwa nie ma jeszcze UID w słowniku – przypisuje jej.

    valid_uids = {
        project.get("uid")
        for project in projects
        if isinstance(project, dict) and project.get("uid")
    }
    # Zbiór wszystkich istniejących UID. Używane do sprawdzenia, czy klucz
    # już jest UID (a nie starą nazwą).

    _migrate_project_details(base_dir, title_to_uid, valid_uids)
    _migrate_active_timer(base_dir, title_to_uid)
    _migrate_active_goals(base_dir, title_to_uid)
    _migrate_card_positions(base_dir, title_to_uid, valid_uids)
    _migrate_sessions(base_dir, title_to_uid)
    # Uruchamia migrację wszystkich plików danych (szczegóły, stoper,
    # cele, pozycje kart, sesje).


def _migrate_project_details(base_dir, title_to_uid, valid_uids):
    # Przenosi szczegóły projektów ze starych kluczy (nazwa projektu) na nowe
    # (unikalny numer UID). Dzięki temu dane się nie mieszają, gdy dwa projekty
    # mają tę samą nazwę.
    path = _path(PROJECT_DETAILS_FILE, base_dir)
    if not os.path.exists(path):
        return
        # Jeśli plik nie istnieje – nie ma co migrować.

    data = _read_json(PROJECT_DETAILS_FILE, {}, base_dir)
    if not isinstance(data, dict) or not data:
        return
        # Jeśli dane to nie słownik lub są puste – nic do roboty.

    migrated = {}
    changed = False
    for key, blob in data.items():
        if key in valid_uids or key == "_":
            migrated[key] = blob
            continue
            # Jeśli klucz to już UID albo wewnętrzny "_" – zostaw bez zmian.

        uid = title_to_uid.get(key)
        if uid:
            migrated[uid] = blob
            # Jeśli znajdziemy UID dla tej nazwy – przenieś dane pod nowy klucz.
            changed = True
        else:
            migrated[key] = blob
            # Jeśli nie ma UID dla tej nazwy – zostaw stary klucz.

    if changed:
        _write_json(PROJECT_DETAILS_FILE, migrated, base_dir)
        # Jeśli cokolwiek się zmieniło – zapisz zaktualizowany plik.


def _migrate_active_timer(base_dir, title_to_uid):
    # Przenosi aktywny stoper ze starego zapisu (po nazwie projektu) na nowy
    # (z unikalnym numerem UID).
    path = _path(ACTIVE_TIMER_FILE, base_dir)
    if not os.path.exists(path):
        return
        # Jeśli plik nie istnieje – nie ma co migrować.

    data = _read_json(ACTIVE_TIMER_FILE, {}, base_dir)
    if not isinstance(data, dict) or data.get("project_uid"):
        return
        # Jeśli dane to nie słownik lub już mają UID – nic do roboty.

    title = data.get("project_title")
    uid = title_to_uid.get(title) if title else None
    if not uid:
        return
        # Jeśli nie ma UID dla tej nazwy projektu – nie da się przenieść.

    data["project_uid"] = uid
    # Dodaje UID do danych stopera.

    _write_json(ACTIVE_TIMER_FILE, data, base_dir)
    # Zapisuje zaktualizowany plik.


def _migrate_active_goals(base_dir, title_to_uid):
    # Przenosi aktywne cele czasowe ze starego zapisu (po nazwie projektu) na
    # nowy (z unikalnym numerem UID).
    path = _path(ACTIVE_GOALS_FILE, base_dir)
    if not os.path.exists(path):
        return

    data = _read_json(ACTIVE_GOALS_FILE, [], base_dir)
    if not isinstance(data, list) or not data:
        return

    changed = False
    for goal in data:
        if not isinstance(goal, dict):
            continue
        if goal.get("project_uid"):
            continue
            # Jeśli cel już ma UID – pomiń.

        uid = title_to_uid.get(goal.get("project_title"))
        if uid:
            goal["project_uid"] = uid
            # Jeśli znajdziemy UID dla nazwy projektu celu – dodaj go.
            changed = True

    if changed:
        _write_json(ACTIVE_GOALS_FILE, data, base_dir)
        # Jeśli cokolwiek się zmieniło – zapisz zaktualizowany plik.


def _migrate_card_positions(base_dir, title_to_uid, valid_uids):
    # Przenosi ułożenie kart na ekranie głównym ze starego zapisu (po nazwie
    # projektu) na nowy (z unikalnym numerem UID).
    path = _path(CARD_POSITIONS_FILE, base_dir)
    if not os.path.exists(path):
        return

    data = _read_json(CARD_POSITIONS_FILE, {}, base_dir)
    if not isinstance(data, dict) or not data:
        return

    migrated = {}
    changed = False
    for key, pos in data.items():
        if key in valid_uids:
            migrated[key] = pos
            continue
            # Jeśli klucz to już UID – zostaw bez zmian.

        uid = title_to_uid.get(key)
        if uid:
            migrated[uid] = pos
            # Jeśli znajdziemy UID dla tej nazwy – przenieś pozycję pod nowy klucz.
            changed = True
        else:
            migrated[key] = pos
            # Jeśli nie ma UID – zostaw stary klucz.

    if changed:
        _write_json(CARD_POSITIONS_FILE, migrated, base_dir)


def _migrate_sessions(base_dir, title_to_uid):
    # Przenosi zapisane sesje pomiaru czasu ze starego zapisu (po nazwie
    # projektu) na nowy (z unikalnym numerem UID).
    path = _path(SESSIONS_FILE, base_dir)
    if not os.path.exists(path):
        return

    data = _read_json(SESSIONS_FILE, [], base_dir)
    if not isinstance(data, list) or not data:
        return

    changed = False
    for session in data:
        if not isinstance(session, dict):
            continue
        if session.get("project_uid"):
            continue
            # Jeśli sesja już ma UID – pomiń.

        uid = title_to_uid.get(session.get("project_title"))
        if uid:
            session["project_uid"] = uid
            # Jeśli znajdziemy UID dla nazwy projektu sesji – dodaj go.
            changed = True

    if changed:
        _write_json(SESSIONS_FILE, data, base_dir)