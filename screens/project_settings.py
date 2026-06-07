# ---------------------------------------------------------------------------
# EKRAN USTAWIEŃ PROJEKTU – edycja i usuwanie
# ---------------------------------------------------------------------------
# Ten ekran pozwala edytować istniejący projekt: zmienić nazwę, zdjęcie,
# kolor, emoji, lub usunąć projekt całkowicie (wymaga potwierdzenia).
# Wszystkie zmiany są zapisywane dopiero po kliknięciu przycisku zapisu.
# ---------------------------------------------------------------------------

import json
# "json" – wbudowany moduł do odczytu/zapisu plików w formacie JSON
# (dane projektu, sesje, szczegóły itd. są przechowywane jako JSON).

import os
# "os" – funkcje systemowe: sprawdzanie czy plik istnieje, tworzenie folderów,
# łączenie ścieżek (np. folder_a/podfolder_b/plik.json).

from kivy.clock import Clock
# "Clock" – narzędzie Kivy do planowania zadań na później
# (np. odświeżenie ekranu po zmianie zdjęcia).

from kivy.properties import ColorProperty, StringProperty
# "ColorProperty" – właściwość przechowująca kolor (R, G, B, A).
# "StringProperty" – właściwość przechowująca tekst.
# Gdy zmieniają wartość – Kivy automatycznie odświeża ekran.

from kivy.uix.screenmanager import Screen
# "Screen" – pojedynczy ekran w ScreenManager (przełączniku ekranów).
# Każda "strona" aplikacji to osobna klasa dziedzicząca po Screen.

from kivy.utils import platform
# "platform" – mówi na jakim systemie działa aplikacja
# ("android", "ios", "linux", "win"). Używamy do warunkowego
# proszenia o pozwolenia na Androidzie.

from kivymd.app import MDApp
# "MDApp" – główna klasa aplikacji KivyMD. Przez nią uzyskujemy
# dostęp do wszystkich ekranów, ustawień itp.

from kivymd.uix.button import MDFlatButton
# "MDFlatButton" – płaski przycisk bez tła (tylko tekst) z KivyMD.

from kivymd.uix.dialog import MDDialog
# "MDDialog" – okno dialogowe (wyskakujące z pytaniem lub informacją).

from plyer import filechooser
# "filechooser" – okno wyboru plików z systemu (np. galeria zdjęć).
# Plyer to biblioteka ułatwiająca dostęp do funkcji systemowych.

from screens.color_palette import open_palette_picker
# Importujemy funkcję otwierającą paletę kolorów (wybór koloru tła).

from screens.emoji_assets import resolve_emoji_source
# Importujemy funkcję, która zamienia nazwę ikony na ścieżkę do pliku.

from screens.image_utils import prepare_project_image
# Importujemy funkcję przygotowującą zdjęcie: zmniejsza je i zapisuje
# w prywatnym folderze aplikacji (żeby było szybciej).


# Zwraca ścieżkę do pliku lub folderu w prywatnym katalogu aplikacji.
# *parts to lista fragmentów ścieżki, które są łączone ze sobą.
def _user_path(*parts):
    # Zwraca ścieżkę do pliku lub folderu w prywatnym katalogu aplikacji.
    # *parts to lista fragmentów ścieżki, które są łączone ze sobą.
    app = MDApp.get_running_app()
    # Pobiera aktualnie uruchomioną aplikację (KivyMD).

    return os.path.join(app.user_data_dir, *parts)
    # Łączy prywatny folder aplikacji z podanymi fragmentami ścieżki.
    # Np. _user_path("projects.json") → "/data/data/app/projects.json".


def _load_json(path, default):
    # Odczytuje plik JSON i zwraca jego zawartość. Jeśli plik nie istnieje
    # lub jest uszkodzony – zwraca wartość domyślną podaną w "default".
    if not os.path.exists(path):
        return default
        # Jeśli ścieżka nie istnieje – zwracamy wartość domyślną (np. [] lub {}).

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
            # Otwiera plik i odczytuje jego zawartość jako JSON (lista/słownik).
    except (OSError, json.JSONDecodeError):
        return default
        # Jeśli plik jest uszkodzony lub nie dało się go przeczytać –
        # zwracamy wartość domyślną zamiast wywalać błąd.


def _save_json(path, data):
    # Zapisuje dane do pliku w formacie JSON. Tworzy foldery jeśli trzeba.
    # "data" to dowolna wartość którą można zapisać w JSON (lista, słownik itp.).
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Tworzy wszystkie foldery na ścieżce jeśli nie istnieją.
    # "exist_ok=True" = nie wywołuj błędu jeśli już istnieją.

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        # Zapisuje dane do pliku w formacie JSON.
        # indent=2 = ładne wcięcia (łatwiej czytać).
        # ensure_ascii=False = polskie znaki (ą, ć, ę) zapisane normalnie.


# Ekran do edycji/usuwania projektu. project_uid to unikalny numer identyfikacyjny (UID),
# który odróżnia ten projekt od innych – nawet jeśli mają taką samą nazwę.
class ProjectSettingsScreen(Screen):
    # "ProjectSettingsScreen" – ekran do edycji/usuwania projektu.
    # Użytkownik może zmienić: nazwę, kolor, emoji, zdjęcie.
    # Może też usunąć projekt (po potwierdzeniu w oknie dialogowym).

    project_uid = StringProperty("")
    # Unikalny numer identyfikacyjny (UID) projektu. Przekazywany z ekranu
    # project_info, żeby wiedzieć który projekt edytujemy.

    project_title = StringProperty("")
    # Tytuł (nazwa) projektu. Wyświetlany w polu tekstowym do edycji.

    selected_color = ColorProperty([0.7, 0.5, 1, 1])
    # Wybrany kolor tła projektu (R, G, B, A). Domyślnie fioletowy.

    selected_icon = StringProperty("emoticon-happy-outline")
    # Wybrana ikona (emoji) projektu. Domyślnie uśmiechnięta buźka.

    selected_image_path = StringProperty("")
    # Ścieżka do zdjęcia projektu (jeśli użytkownik wybrał zdjęcie z galerii).
    # Pusta = brak zdjęcia (użyj koloru tła).

    name_text = StringProperty("")
    # Tekst wpisany przez użytkownika w polu edycji nazwy projektu.

    _original_title = ""
    # Zapamiętuje ORYGINALNĄ nazwę projektu (przed zmianami).
    # Używane do znajdowania projektu w plikach.

    _original_uid = ""
    # Zapamiętuje ORYGINALNY UID projektu (przed zmianami).
    # Używane do znajdowania projektu w plikach.

    # Przed wejściem na ekran – wczytaj dane projektu z pliku.
    def on_pre_enter(self, *_args):
        self._load_project_meta()
        # Wywołuje funkcję ładującą dane projektu (nazwa, kolor, emoji,
        # zdjęcie) z pliku projects.json.

    # Po wejściu na ekran – poproś o pozwolenia na pliki (Android).
    # Potrzebujemy dostępu do zdjęć w galerii użytkownika.
    def on_enter(self, *_args):
        if platform == "android":
            from android.permissions import Permission, request_permissions
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        # Jeśli aplikacja działa na Androidzie – prosimy użytkownika
        # o pozwolenie na czytanie i zapis plików (potrzebne do
        # wybrania zdjęcia z galerii).

    # Znajduje projekt w liście projektów.
    # Najpierw szuka po UID (unikalny numer identyfikacyjny).
    # Jeśli nie znajdzie – szuka po nazwie projektu (rozwiązanie awaryjne).
    def _find_project(self, projects):
        if self._original_uid:
            for p in projects:
                if p.get("uid") == self._original_uid:
                    return p
            # Jeśli mamy UID – szukamy projektu po tym identyfikatorze.
        for p in projects:
            if p.get("title") == self._original_title:
                return p
            # Jeśli nie ma UID lub nie znaleźliśmy – szukamy po nazwie.
        return None
        # Jeśli nie znaleziono projektu – zwracamy None.

    # Wczytuje aktualne dane projektu (nazwa, kolor, emoji, zdjęcie) z pliku.
    def _load_project_meta(self):
        self._original_uid = self.project_uid or ""
        # Zapamiętuje oryginalny UID (może być pusty, jeśli stary projekt).

        self._original_title = self.project_title or ""
        # Zapamiętuje oryginalną nazwę projektu.

        self.name_text = self._original_title
        # Ustawia tekst w polu edycji na oryginalną nazwę.

        name_input = self.ids.get("name_input")
        # Próbuje znaleźć pole tekstowe (MDTextField) po ID "name_input".

        if name_input is not None:
            name_input.text = self._original_title
            # Jeśli pole istnieje – wpisuje w nim oryginalną nazwę.

        projects = _load_json(_user_path("projects.json"), [])
        # Wczytuje listę wszystkich projektów z pliku. Jeśli plik nie
        # istnieje – zwraca pustą listę.

        proj = self._find_project(projects)
        # Szuka naszego projektu w liście (po UID lub po nazwie).

        if proj is None:
            self.selected_color = [0.7, 0.5, 1, 1]
            self.selected_icon = resolve_emoji_source("emoticon-happy-outline")
            self.selected_image_path = ""
            return
            # Jeśli projektu nie znaleziono – ustawiamy domyślne wartości
            # (fioletowy kolor, uśmiechnięta buźka, brak zdjęcia).

        self.selected_color = list(proj.get("color") or [0.7, 0.5, 1, 1])
        # Pobiera kolor projektu z danych (lub domyślny fioletowy).

        self.selected_icon = resolve_emoji_source(
            proj.get("icon") or "emoticon-happy-outline"
        )
        # Pobiera ikonę projektu – resolve_emoji_source zamienia nazwę
        # ikony na ścieżkę do pliku z emoji.

        self.selected_image_path = proj.get("image") or ""
        # Pobiera ścieżkę do zdjęcia projektu (lub puste = brak zdjęcia).

    # Otwiera wybór zdjęcia z galerii systemowej.
    def select_photo(self):
        filechooser.open_file(
            on_selection=self._on_image_selected,
        )
        # Otwiera systemowe okno wyboru plików, ograniczone do obrazków
        # (PNG, JPG). Po wybraniu pliku wywołuje _on_image_selected.

    # Po wybraniu zdjęcia z galerii – przekazuje je do funkcji, która
    # przetworzy i wyświetli obrazek. Jeśli nic nie wybrano – nic nie robi.
    def _on_image_selected(self, selection):
        if not selection:
            return
        # Jeśli użytkownik nic nie wybrał (anulował) – nic nie robimy.

        Clock.schedule_once(
            lambda _dt: self._apply_selected_photo(selection[0]), 0
        )
        # Planuje przetworzenie wybranego zdjęcia na "za chwilę"
        # (0 sekund = przy najbliższej okazji). Przekazuje ścieżkę
        # do pierwszego wybranego pliku.

    # Przygotowuje wybrane zdjęcie do użycia: zmniejsza je i zapisuje
    # w prywatnym folderze aplikacji. Jeśli się nie uda – używa oryginału.
    def _apply_selected_photo(self, path):
        cache_dir = _user_path("project_images")
        # Tworzy ścieżkę do prywatnego folderu "project_images".

        try:
            path = prepare_project_image(path, cache_dir)
            # Próbuje zmniejszyć zdjęcie i zapisać w folderze aplikacji.
            # Zwraca nową ścieżkę do przetworzonego obrazka.
        except Exception as exc:
            print(f"[ProjectSettings] image normalize failed, using original: {exc}")
            # Jeśli się nie udało (np. plik jest uszkodzony) – wypisuje
            # ostrzeżenie i używa oryginalnej ścieżki.

        self.selected_image_path = ""
        # Czyści starą ścieżkę (żeby nie pokazywać starego zdjęcia).

        Clock.schedule_once(lambda _dt: self._set_image_path(path), 0.05)
        # Planuje wyświetlenie nowego zdjęcia za 0.05 sekundy (krótkie
        # opóźnienie, żeby Kivy zdążył odświeżyć ekran).

    # Ustawia ścieżkę do wybranego zdjęcia w podglądzie, co powoduje
    # wyświetlenie nowego obrazka na karcie projektu.
    def _set_image_path(self, path):
        self.selected_image_path = path
        # Ustawia właściwość selected_image_path – Kivy automatycznie
        # odświeży podgląd zdjęcia na ekranie. Gdy puste = brak zdjęcia.

    # Usuwa zdjęcie projektu (przywraca do domyślnego tła kolorowego).
    def clear_photo(self):
        self.selected_image_path = ""
        # Czyści ścieżkę do zdjęcia. Kivy automatycznie usunie obrazek
        # z podglądu i pokaże kolor tła.

    # Otwiera okno wyboru koloru tła projektu (paleta barw).
    def select_color(self):
        open_palette_picker(
            default_color=tuple(self.selected_color),
            on_pick=self._apply_picked_color,
        )
        # Wywołuje funkcję z color_palette.py, która pokazuje siatkę
        # kolorów. Gdy użytkownik wybierze kolor – wywołuje
        # _apply_picked_color z wybranym kolorem.

    # Zapisuje wybrany przez użytkownika kolor jako aktualny kolor projektu.
    def _apply_picked_color(self, color):
        self.selected_color = list(color)
        # Zamienia wybrany kolor (krotka) na listę i zapisuje.
        # Kivy automatycznie odświeży podgląd koloru na ekranie.

    # Anuluj – wróć do ekranu projektu bez zapisywania zmian.
    def cancel(self):
        self._return_to_project(self._original_title)
        # Wraca do ekranu szczegółów projektu z ORYGINALNĄ nazwą
        # (bez zapisywania jakichkolwiek zmian).

    # Zapisz zmiany – nadpisz dane projektu w plikach.
    # Zapisuje zmienione dane projektu do plików: aktualizuje nazwę,
    # kolor, emoji i zdjęcie. Odświeża ekran główny i wraca do projektu.
    def save(self):
        new_name = (self.name_text or "").strip()
        # Pobiera nową nazwę z pola tekstowego, usuwa zbędne spacje.

        if not new_name:
            new_name = self._original_title
            # Jeśli pole jest puste – używamy oryginalnej nazwy (nie
            # pozwalamy na pustą nazwę).

        original = self._original_title
        original_uid = self._original_uid
        # Zapamiętuje oryginalną nazwę i UID przed zmianami.

        # Po zmianie nazwy nie trzeba już przestawiać kluczy w danych —
        # każdy plik stanu jest powiązany z unikalnym identyfikatorem (uid),
        # więc projekty o takich samych nazwach nie stanowią problemu.
        self._write_projects_json(new_name)
        # Zapisuje zmienione dane projektu do pliku projects.json.

        self._rename_sessions_by_uid(new_name)
        # Aktualizuje nazwę projektu we wszystkich zapisanych sesjach.

        self._refresh_home_cards()
        # Odświeża karty na ekranie głównym (nowa nazwa, kolor itp.).

        self._return_to_project(new_name, original_uid)
        # Wraca do ekranu szczegółów projektu z nową nazwą.

    # Pokaż okno z prośbą o potwierdzenie usunięcia projektu.
    # Operacja jest nieodwracalna – dlatego wymaga potwierdzenia.
    def delete_project(self):
        cancel_btn = MDFlatButton(text="ANULUJ")
        # Przycisk "ANULUJ" – zamyka okno bez usuwania.

        confirm_btn = MDFlatButton(
            text="USUŃ NA ZAWSZE",
            theme_text_color="Custom",
            text_color=(0.85, 0.18, 0.18, 1),
        )
        # Przycisk "USUŃ NA ZAWSZE" – czerwony tekst, żeby przyciągnąć
        # uwagę. Po kliknięciu wykonuje faktyczne usunięcie.

        dlg = MDDialog(
            title="Usunąć projekt?",
            text=(
                f"Tej operacji nie da się cofnąć. Cała historia czasu, "
                f"notatki i etapy projektu „{self._original_title}” "
                f"zostaną trwale usunięte."
            ),
            buttons=[cancel_btn, confirm_btn],
        )
        # Tworzy okno dialogowe z tytułem, ostrzeżeniem i dwoma
        # przyciskami: anuluj i usuń. MDDialog to wyskakujące okno.

        cancel_btn.bind(on_release=lambda *_a: dlg.dismiss())
        # Gdy użytkownik kliknie "ANULUJ" – zamyka okno dialogowe.

        confirm_btn.bind(on_release=lambda *_a: self._confirm_delete(dlg))
        # Gdy użytkownik kliknie "USUŃ" – wykonuje faktyczne usunięcie.

        dlg.open()
        # Pokazuje okno dialogowe użytkownikowi.

    def _confirm_delete(self, dlg):
        # Usuwa projekt ze wszystkich plików po potwierdzeniu przez użytkownika.
        # Czyści: listę projektów, szczegóły (notatki, cele), historię sesji
        # oraz zapisane pozycje kart na ekranie głównym.
        # Na koniec odświeża ekran główny i wraca do niego.
        dlg.dismiss()
        # Zamyka okno dialogowe (użytkownik już potwierdził).

        uid = self._original_uid
        title = self._original_title
        # Pobiera UID i nazwę projektu do usunięcia.

        if not uid and not title:
            return
            # Jeśli nie ma ani UID ani nazwy – nie ma co usuwać.

        projects = _load_json(_user_path("projects.json"), [])
        # Wczytuje listę wszystkich projektów.

        if uid:
            projects = [p for p in projects if p.get("uid") != uid]
            # Jeśli mamy UID – filtrujemy projekty: zostawiamy wszystkie
            # OPRÓCZ tego z pasującym UID.
        else:
            projects = [p for p in projects if p.get("title") != title]
            # Jeśli nie mamy UID – filtrujemy po nazwie.

        _save_json(_user_path("projects.json"), projects)
        # Zapisuje zaktualizowaną listę (bez usuniętego projektu).

        details = _load_json(_user_path("project_details.json"), {})
        # Wczytuje szczegóły projektów (notatki, cele czasowe, etapy).

        for key in (uid, title):
            if key and key in details:
                details.pop(key)
            # Usuwa szczegóły projektu – zarówno po UID jak i po nazwie
            # (dla bezpieczeństwa, żeby nie zostawić śmieci).

        _save_json(_user_path("project_details.json"), details)
        # Zapisuje zaktualizowane szczegóły.

        sessions = _load_json(_user_path("sessions.json"), [])
        # Wczytuje historię wszystkich sesji (timerów).

        if uid:
            sessions = [s for s in sessions if s.get("project_uid") != uid]
        else:
            sessions = [s for s in sessions if s.get("project_title") != title]
            # Filtruje sesje – usuwa wszystkie związane z tym projektem.

        _save_json(_user_path("sessions.json"), sessions)
        # Zapisuje zaktualizowaną historię sesji.

        positions = _load_json(_user_path("card_positions.json"), {})
        # Wczytuje zapisane pozycje kart na ekranie głównym.

        for key in (uid, title):
            if key and key in positions:
                positions.pop(key)
            # Usuwa zapisaną pozycję karty tego projektu.

        _save_json(_user_path("card_positions.json"), positions)
        # Zapisuje zaktualizowane pozycje.

        self._refresh_home_cards()
        # Odświeża karty na ekranie głównym (projekt zniknie z listy).

        self._go_home_after_delete()
        # Wraca do ekranu głównego (bo projekt już nie istnieje).

    # Zapisuje zmienione dane projektu do pliku projects.json.
    # Tworzy nowy UID jeśli projekt go nie miał (migracja ze starej wersji).
    def _write_projects_json(self, new_name):
        import uuid as _uuid
        # Importuje moduł do generowania unikalnych identyfikatorów (UUID).
        # Używamy go tylko w tej funkcji, dlatego import jest tutaj.

        path = _user_path("projects.json")
        # Ścieżka do pliku z listą projektów.

        projects = _load_json(path, [])
        # Wczytuje aktualną listę projektów z pliku.

        updated = False
        # Flaga: czy zaktualizowaliśmy istniejący projekt?

        for p in projects:
            # Przechodzi przez wszystkie projekty w poszukiwaniu naszego.

            match = (
                (self._original_uid and p.get("uid") == self._original_uid)
                or (not self._original_uid and p.get("title") == self._original_title)
            )
            # Warunek dopasowania: jeśli mamy UID – szukaj po UID.
            # Jeśli nie mamy UID – szukaj po nazwie.

            if match:
                p["title"] = new_name
                p["color"] = list(self.selected_color)
                p["icon"] = self.selected_icon
                p["image"] = self.selected_image_path
                # Aktualizuje wszystkie dane projektu: nazwę, kolor,
                # ikonę i zdjęcie.

                if not p.get("uid"):
                    p["uid"] = self._original_uid or f"proj-{_uuid.uuid4().hex}"
                    # Jeśli projekt nie ma jeszcze UID (stara wersja)
                    # – generujemy nowy unikalny identyfikator.

                self._original_uid = p["uid"]
                self.project_uid = p["uid"]
                # Aktualizuje zapamiętany UID.

                updated = True
                break
                # Oznacza, że zaktualizowaliśmy projekt i kończy pętlę.

        if not updated:
            new_uid = self._original_uid or f"proj-{_uuid.uuid4().hex}"
            # Jeśli nie znaleźliśmy projektu do aktualizacji – tworzymy
            # nowy unikalny identyfikator.

            projects.append(
                {
                    "uid": new_uid,
                    "title": new_name,
                    "color": list(self.selected_color),
                    "icon": self.selected_icon,
                    "image": self.selected_image_path,
                }
            )
            # Dodaje nowy projekt do listy z wszystkimi danymi.

            self._original_uid = new_uid
            self.project_uid = new_uid
            # Aktualizuje zapamiętany UID.

        _save_json(path, projects)
        # Zapisuje zaktualizowaną listę projektów do pliku.

    # Po zmianie nazwy – aktualizuje nazwę we wszystkich zapisanych sesjach.
    # Dzięki temu historia sesji nadal pasuje do projektu mimo zmiany nazwy.
    def _rename_sessions_by_uid(self, new_name):
        if not self._original_uid:
            return
            # Jeśli projekt nie ma UID – nie da się zaktualizować sesji.

        path = _user_path("sessions.json")
        # Ścieżka do pliku z historią sesji.

        sessions = _load_json(path, [])
        # Wczytuje wszystkie zapisane sesje.

        changed = False
        # Flaga: czy jakakolwiek sesja została zmieniona?

        for s in sessions:
            if s.get("project_uid") == self._original_uid and s.get("project_title") != new_name:
                s["project_title"] = new_name
                changed = True
                # Dla każdej sesji należącej do tego projektu – aktualizuje
                # jej nazwę projektu na nową. Dzięki temu historia czasu
                # nadal będzie poprawna po zmianie nazwy.

        if changed:
            _save_json(path, sessions)
            # Jeśli cokolwiek się zmieniło – zapisuje zaktualizowane sesje.

    # Odświeża karty na ekranie głównym po zmianie lub usunięciu projektu.
    # Usuwa stare karty i ładuje je ponownie z pliku.
    def _refresh_home_cards(self):
        app = MDApp.get_running_app()
        # Pobiera aktualnie uruchomioną aplikację.

        if not app or not getattr(app, "root", None):
            return
            # Jeśli aplikacja nie istnieje lub nie ma głównego widoku – przerwij.

        try:
            home = app.root.get_screen("home")
            # Próbuje pobrać ekran główny ("home") z menedżera ekranów.
        except Exception:
            return
            # Jeśli ekran nie istnieje – przerwij.

        if home is None:
            return

        container = home.ids.get("projects_container")
        # Pobiera kontener z kartami projektów na ekranie głównym.

        if container is None:
            return
            # Jeśli kontener nie istnieje – przerwij.

        from screens.home import ProjectCard
        # Importuje klasę ProjectCard (opóźniony import – unikamy cykli).

        for child in list(container.children):
            if isinstance(child, ProjectCard):
                container.remove_widget(child)
                # Usuwa wszystkie stare karty projektów z kontenera.

        home.load_projects()
        # Ładuje karty od nowa (z zaktualizowanymi danymi).

        Clock.schedule_once(lambda _dt: home.restore_card_positions(), 0)
        # Przywraca zapisane pozycje kart (przeciąganie) po przeładowaniu.

        home.refresh_last_session()
        # Odświeża informację o ostatniej sesji na ekranie głównym.

    # Wraca do ekranu szczegółów projektu po zapisaniu zmian.
    def _return_to_project(self, title, uid=""):
        app = MDApp.get_running_app()
        # Pobiera aktualnie uruchomioną aplikację.

        if not app or not getattr(app, "root", None):
            return
            # Jeśli aplikacja nie istnieje – przerwij.

        info = app.root.get_screen("project_info")
        # Pobiera ekran szczegółów projektu ("project_info").

        info.project_uid = uid or self._original_uid or info.project_uid
        # Ustawia UID projektu na ekranie szczegółów (żeby wiedział
        # który projekt pokazać).

        info.project_title = title
        # Ustawia tytuł projektu na ekranie szczegółów.

        app.root.current = "project_info"
        # Przełącza aplikację na ekran szczegółów projektu.

    # Po usunięciu projektu – wraca do ekranu głównego (bo projektu już nie ma).
    def _go_home_after_delete(self):
        app = MDApp.get_running_app()
        # Pobiera aktualnie uruchomioną aplikację.

        if not app or not getattr(app, "root", None):
            return
            # Jeśli aplikacja nie istnieje – przerwij.

        app.root.current = "home"
        # Przełącza na ekran główny (lista projektów).

    # --- Misc ---

    def _warn(self, title, text):
        # Pokazuje okno z ostrzeżeniem (np. gdy coś poszło nie tak).
        ok = MDFlatButton(text="OK")
        # Tworzy przycisk "OK" do zamknięcia okna.

        dlg = MDDialog(title=title, text=text, buttons=[ok])
        # Tworzy okno dialogowe z tytułem, treścią i przyciskiem.

        ok.bind(on_release=lambda *_a: dlg.dismiss())
        # Gdy użytkownik kliknie "OK" – zamyka okno.

        dlg.open()
        # Pokazuje okno ostrzeżenia użytkownikowi.

    # Gdy użytkownik wpisuje nową nazwę projektu – zapamiętuje ją,
    # żeby można było zapisać przy kliknięciu przycisku "Zapisz".
    def on_name_input(self, value):
        self.name_text = value or ""
        # Zapisuje wpisany tekst w właściwości name_text. Jeśli tekst
        # jest pusty – zapisuje pusty string zamiast None.