# ---------------------------------------------------------------------------
# EKRAN DODAWANIA NOWEGO PROJEKTU
# ---------------------------------------------------------------------------
# Ten plik zawiera logikę ekranu, na którym użytkownik tworzy nowy projekt.
# Użytkownik może: wpisać nazwę, wybrać zdjęcie, kolor tła i emoji.
# Po naciśnięciu przycisku zapisu, projekt jest zapisywany do pliku
# projects.json i pojawia się na ekranie głównym.
# ---------------------------------------------------------------------------

import os
import json
import math
import uuid
from kivy.properties import StringProperty, ColorProperty, ObjectProperty, NumericProperty
from kivymd.uix.screen import MDScreen
from kivymd.uix.dialog import MDDialog
from screens.color_palette import open_palette_picker
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRaisedButton
from kivy.uix.recycleview import RecycleView
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivymd.uix.fitimage import FitImage
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import platform
from kivy.clock import Clock
from plyer import filechooser

from screens.image_utils import prepare_project_image
from screens.emoji_assets import resolve_emoji_source
from screens import emoji_index
from kivymd.app import MDApp
from kivymd.uix.behaviors import RectangularRippleBehavior
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.cache import Cache
from kivy.factory import Factory
from kivy.uix.scrollview import ScrollView


# ---------------------------------------------------------------------------
# KOMÓRKA EMOJI – pojedynczy obrazek emoji w siatce pickera
# ---------------------------------------------------------------------------
# To widżet używany przez RecycleView. RecycleView tworzy tylko tyle komórek,
# ile mieści się na ekranie, i podmienia w nich obrazek podczas przewijania.
# Dzięki temu picker otwiera się natychmiast nawet przy tysiącach emoji –
# nie tworzymy już tysięcy widżetów naraz (to powodowało wielosekundowe
# zawieszenie).
class EmojiCell(RecycleDataViewBehavior, RectangularRippleBehavior, ButtonBehavior, Image):
    screen = ObjectProperty(None, allownone=True)
    index = NumericProperty(0, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.allow_stretch = True
        self.keep_ratio = True
        self.mipmap = False

    # RecycleView woła tę metodę przy podmianie danych w komórce (przewijanie).
    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.source = data.get("source", "")
        self.screen = data.get("screen")

    # Po kliknięciu komórki – przekazuje wybrane emoji do ekranu.
    def on_release(self):
        if self.screen and self.source:
            self.screen._on_emoji_selected(self.source)

Factory.register('EmojiCell', cls=EmojiCell)


# ---------------------------------------------------------------------------
# GŁÓWNY EKRAN DODAWANIA PROJEKTU
# ---------------------------------------------------------------------------
class AddProjectScreen(MDScreen):
    selected_color = ColorProperty([0.7, 0.5, 1, 1])  # Domyślny fiolet
    selected_icon = StringProperty("emoticon-happy-outline")
    selected_image_path = StringProperty("")
    _emoji_index = []
    _filtered_emojis = []
    _search_input = None
    _recycle_view = None
    _emoji_layout = None
    _category_tabs = None
    _category_order = []
    _current_active_category = ""
    _cell_size = 0
    _cell_spacing = 0
    _grid_padding = 0
    _grid_cols = 1

    def on_enter(self):
        # Gdy użytkownik wchodzi na ekran dodawania projektu – prosimy
        # o pozwolenia dostępu do plików (Android wymaga tego do galerii)
        # i resetujemy podgląd karty projektu do stanu początkowego.
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        self._search_timer = None
        self._reset_preview_card()

    def _compute_grid_cols(self, viewport_width):
        # Ile kolumn faktycznie mieści się w szerokości widoku, uwzględniając
        # padding siatki i pasek przewijania – żeby ostatnia kolumna nie była obcięta.
        cell = self._cell_size
        spacing = self._cell_spacing
        pad = self._grid_padding
        scrollbar = dp(8)
        inner = viewport_width - 2 * pad - scrollbar
        if inner <= 0:
            return 4
        cols = max(4, int((inner + spacing) // (cell + spacing)))
        while cols > 4 and cols * cell + (cols - 1) * spacing > inner:
            cols -= 1
        return cols

    def _grid_content_width(self, cols):
        return cols * self._cell_size + (cols - 1) * self._cell_spacing

    def _fit_emoji_grid_columns(self, _dt=None):
        if not self._recycle_view or not self._emoji_layout:
            return
        width = self._recycle_view.width
        if width <= 0:
            Clock.schedule_once(self._fit_emoji_grid_columns, 0.05)
            return

        cols = self._compute_grid_cols(width)
        self._grid_cols = cols
        self._emoji_layout.cols = cols

        # Wyśrodkuj siatkę w pozostałej szerokości okna.
        content_w = self._grid_content_width(cols)
        scrollbar = dp(8)
        side_pad = max(self._grid_padding, (width - scrollbar - content_w) / 2.0)
        self._emoji_layout.padding = [
            side_pad,
            self._grid_padding,
            side_pad,
            self._grid_padding,
        ]

    # -----------------------------------------------------------------------
    # WYBÓR EMOJI – otwiera okno z siatką emoji i wyszukiwarką
    # -----------------------------------------------------------------------
    # Otwiera okno wyboru emoji z paskiem wyszukiwania i siatką obrazków.
    # Najpierw czyści pamięć podręczną obrazków (Cache), żeby zwolnić miejsce w pamięci RAM.
    # Cache to tymczasowe przechowywanie obrazków – czyścimy go przed otwarciem okna emoji.
    def select_emoji(self):
        # Buduje indeks emoji (raz – wynik jest zapamiętany) i otwiera okno
        # wyboru. Indeks zawiera tylko metadane (ścieżki, kategorie, nazwy),
        # a nie widżety, więc okno otwiera się natychmiast. Same obrazki
        # tworzy leniwie RecycleView, w miarę przewijania.
        Cache.remove('kv.image')
        Cache.remove('kv.texture')

        if not self._emoji_index:
            self._emoji_index = emoji_index.build_index()
            print(f"[EmojiPicker] Built index with {len(self._emoji_index)} emojis")

        self._filtered_emojis = self._emoji_index
        self._category_tabs = {}
        self._category_order = emoji_index.category_order(self._emoji_index)
        self._current_active_category = self._category_order[0] if self._category_order else ""

        # Wymiary komórek siatki (potrzebne też do obliczeń przewijania).
        self._cell_size = dp(56)
        self._cell_spacing = dp(6)
        self._grid_padding = dp(6)
        # Wstępna liczba kolumn (doprecyzowana po ułożeniu okna dialogowego).
        estimate_width = Window.width * 0.95 - dp(56)
        self._grid_cols = self._compute_grid_cols(estimate_width)

        container = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=dp(6),
            size_hint_y=None,
            height=dp(620),
        )

        # Pole wyszukiwania
        self._search_input = MDTextField(
            hint_text="Szukaj emoji (nazwa, np. 'heart', albo kod hex)...",
            mode="rectangle",
            size_hint_y=None,
            height=dp(50),
        )
        self._search_input.bind(text=self._on_search_text)
        container.add_widget(self._search_input)

        # Pasek zakładek z kategoriami (poziomo przewijany)
        categories_container = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=None,
            size_hint_y=None,
            height=dp(40),
            spacing=dp(6),
            padding=(dp(2), 0),
        )
        categories_container.bind(minimum_width=categories_container.setter('width'))

        for category in self._category_order:
            btn = MDRaisedButton(
                text=category,
                size_hint=(None, None),
                height=dp(36),
                md_bg_color=(
                    [0.7, 0.5, 1, 1] if category == self._current_active_category
                    else [0.2, 0.2, 0.2, 1]
                ),
            )
            btn.bind(on_release=lambda _btn, cat=category: self._on_category_selected(cat))
            self._category_tabs[category] = btn
            categories_container.add_widget(btn)

        cat_scroll = ScrollView(size_hint_y=None, height=dp(44), do_scroll_y=False, bar_width=0)
        cat_scroll.add_widget(categories_container)
        container.add_widget(cat_scroll)

        # Wirtualizowana siatka emoji (RecycleView) – tworzy widżety tylko
        # dla widocznych komórek.
        rv = RecycleView(size_hint=(1, 1), bar_width=dp(4))
        rv.bind(scroll_y=self._on_emoji_scroll)
        layout = RecycleGridLayout(
            cols=self._grid_cols,
            default_size=(self._cell_size, self._cell_size),
            default_size_hint=(None, None),
            size_hint=(1, None),
            spacing=self._cell_spacing,
            padding=self._grid_padding,
        )
        layout.bind(minimum_height=layout.setter('height'))
        rv.add_widget(layout)
        rv.viewclass = 'EmojiCell'
        self._recycle_view = rv
        self._emoji_layout = layout
        self._set_emoji_data(self._filtered_emojis)
        container.add_widget(rv)

        self.emoji_dialog = MDDialog(
            title="Wybierz ikonę projektu",
            type="custom",
            content_cls=container,
            size_hint_x=0.95,
            size_hint_y=None,
            height=dp(700),
        )
        self.emoji_dialog.open()

        # Po ułożeniu okna przelicz kolumny według rzeczywistej szerokości.
        Clock.schedule_once(self._fit_emoji_grid_columns, 0)
        Clock.schedule_once(self._fit_emoji_grid_columns, 0.1)

        # Ustaw kursor w polu wyszukiwania zaraz po otwarciu.
        def focus_search(_dt):
            self._search_input.focus = True
        Clock.schedule_once(focus_search, 0.1)

    # Przekazuje listę emoji do RecycleView. To tanie – budujemy tylko listę
    # słowników; widżety powstają leniwie.
    def _set_emoji_data(self, emoji_list):
        if not self._recycle_view:
            return
        self._filtered_emojis = emoji_list
        self._recycle_view.data = [
            {"source": e["source"], "screen": self} for e in emoji_list
        ]
        self._recycle_view.scroll_y = 1

    def _on_search_text(self, instance, value):
        # Filtrujemy z opóźnieniem 0.3 s po ostatnim znaku, żeby nie filtrować
        # przy każdym wciśnięciu klawisza.
        Clock.unschedule(self._delayed_filter)
        Clock.schedule_once(self._delayed_filter, 0.3)

    def _delayed_filter(self, _dt=None):
        if not self._search_input:
            return
        search_term = self._search_input.text
        filtered = emoji_index.filter_index(self._emoji_index, search_term)
        self._set_emoji_data(filtered)

    def _on_category_selected(self, category):
        # Klik w zakładkę kategorii – przewiń do pierwszego emoji tej kategorii.
        self._current_active_category = category
        self._scroll_to_category(category)
        self._update_category_button_styles()

    def _row_height(self):
        return self._cell_size + self._cell_spacing

    def _content_height(self):
        # Pełna wysokość siatki (również tej poza ekranem).
        count = len(self._filtered_emojis)
        rows = math.ceil(count / self._grid_cols) if count else 0
        return rows * self._row_height() + 2 * self._grid_padding

    def _scroll_to_category(self, category):
        if not self._filtered_emojis or not self._recycle_view:
            return

        target_index = next(
            (i for i, e in enumerate(self._filtered_emojis) if e.get("category") == category),
            None,
        )
        if target_index is None:
            return

        row = target_index // self._grid_cols
        y_offset = row * self._row_height()
        viewport = self._recycle_view.height
        scrollable = self._content_height() - viewport
        if scrollable <= 0:
            self._recycle_view.scroll_y = 1
            return
        scroll_y = 1.0 - (y_offset / scrollable)
        self._recycle_view.scroll_y = max(0, min(1, scroll_y))

    def _on_emoji_scroll(self, instance, value):
        # Podczas przewijania podświetlamy zakładkę kategorii, która jest
        # aktualnie u góry widoku.
        if not self._filtered_emojis or not self._recycle_view:
            return
        if self._search_input and self._search_input.text.strip():
            return

        viewport = self._recycle_view.height
        scrollable = self._content_height() - viewport
        if scrollable <= 0:
            return
        y_px = (1.0 - value) * scrollable
        top_index = int(y_px / self._row_height()) * self._grid_cols
        top_index = max(0, min(top_index, len(self._filtered_emojis) - 1))

        new_category = self._filtered_emojis[top_index].get("category", "")
        if new_category and new_category != self._current_active_category:
            self._current_active_category = new_category
            self._update_category_button_styles()

    def _update_category_button_styles(self):
        if not self._category_tabs:
            return
        for category, btn in self._category_tabs.items():
            btn.md_bg_color = (
                [0.7, 0.5, 1, 1] if category == self._current_active_category
                else [0.2, 0.2, 0.2, 1]
            )

    def _on_emoji_selected(self, emoji_val):
        # Po kliknięciu emoji: zapisz wybór, zamknij okno i wyczyść wyszukiwarkę.
        self.selected_icon = resolve_emoji_source(emoji_val)
        if hasattr(self, 'emoji_dialog'):
            self.emoji_dialog.dismiss()
        if self._search_input:
            self._search_input.text = ""

    # -----------------------------------------------------------------------
    # WYBÓR ZDJĘCIA
    # -----------------------------------------------------------------------
    def select_photo(self):
        # Otwiera systemowy wybór plików/galerię, żeby użytkownik mógł
        # wybrać zdjęcie z telefonu. Pokazuje tylko obrazy (png, jpg, jpeg).
        # Po wybraniu zdjęcia wywołuje _on_image_selected.
        filechooser.open_file(
            title="Select Project Image",
            filters=[("Images", "*.png", "*.jpg", "*.jpeg")],
            on_selection=self._on_image_selected
        )

    # Wywoływane po wybraniu zdjęcia przez użytkownika – przekazuje ścieżkę do dalszego przetworzenia.
    def _on_image_selected(self, selection):
        if selection:
            Clock.schedule_once(lambda _dt: self._apply_selected_photo(selection[0]), 0)

    def _apply_selected_photo(self, path):
        # Przetwarza wybrane przez użytkownika zdjęcie: zmniejsza je do
        # rozmiaru odpowiedniego dla karty projektu (żeby nie zajmowało
        # za dużo miejsca) i zapisuje w prywatnym folderze aplikacji.
        # Jeśli przetworzenie się nie uda – używa oryginalnego pliku.
        app = MDApp.get_running_app()
        cache_dir = os.path.join(app.user_data_dir, "project_images")
        try:
            path = prepare_project_image(path, cache_dir)
        except Exception as exc:
            print(f"[AddProject] Image normalize failed, using original: {exc}")
        self._update_image_preview(path)

    def _update_image_preview(self, path):
        # Aktualizuje podgląd wybranego zdjęcia na karcie projektu.
        # Najpierw czyści starą ścieżkę (żeby odświeżyć obrazek),
        # a po chwili ustawia nową – to wymusza przeładowanie obrazka
        # na ekranie.
        self.selected_image_path = ""
        # Po krótkim opóźnieniu ustawia ścieżkę do zdjęcia w podglądzie,
        # co powoduje załadowanie i wyświetlenie obrazka na karcie projektu.
        def reapply_path(dt):
            self.selected_image_path = path
            print(f"Image updated in preview: {path}")
        Clock.schedule_once(reapply_path, 0.1)

    def _reset_preview_card(self):
        # Przywraca kartę podglądu projektu do stanu wyjściowego.
        # Zatrzymuje ewentualne animacje (drżenie karty z trybu
        # przeciągania), ustawia domyślny rozmiar i pozycję na środku.
        # To ważne, żeby przy ponownym otwarciu formularza karta
        # wyglądała jak nowa.
        card = self.ids.preview_card
        card.interactive = False
        if card._long_press_ev:
            Clock.unschedule(card._long_press_ev)
            card._long_press_ev = None
        if card._shake_anim:
            card._shake_anim.cancel(card)
            card._shake_anim = None
        card.angle = 0
        card.size_hint = None, None
        card.width = dp(200)
        card.height = dp(220)
        card.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        if card.parent:
            card.parent.do_layout()

    def _clear_image_preview(self):
        # Usuwa wybrane zdjęcie z podglądu i czyści pamięć podręczną
        # (żeby nie zajmowała miejsca w RAM). Przechodzi przez wszystkie
        # elementy karty i usuwa z nich obrazek.
        path = self.selected_image_path
        if path:
            Cache.remove("kv.image", path)
            Cache.remove("kv.texture", path)
        self.selected_image_path = ""
        card = self.ids.preview_card
        card.image_source = ""
        for widget in card.walk(restrict=True):
            if isinstance(widget, FitImage):
                widget.source = ""
                if hasattr(widget, "reload"):
                    widget.reload()

    def _clear_form(self):
        # Czyści cały formularz dodawania projektu: nazwę, emoji, kolor
        # i zdjęcie. Przywraca wszystko do domyślnych wartości,
        # gotowe do wpisania kolejnego nowego projektu.
        self.ids.project_name_input.text = ""
        self.selected_icon = "emoticon-happy-outline"
        self.selected_color = [0.7, 0.5, 1, 1]
        self._clear_image_preview()
        self._reset_preview_card()

    # -----------------------------------------------------------------------
    # ZAPISYWANIE PROJEKTU
    # -----------------------------------------------------------------------
    # Zapisuje dane nowego projektu do pliku projects.json i dodaje
    # jego kartę na ekranie głównym. Po zapisie wraca do ekranu głównego.
    def save_project(self):
        app = MDApp.get_running_app()
        project_name = self.ids.project_name_input.text.strip()

        if not project_name:
            return

        project_data = {
            "uid": f"proj-{uuid.uuid4().hex}",
            "title": project_name,
            "color": list(self.selected_color),
            "icon": self.selected_icon,
            "image": self.selected_image_path
        }

        # Odczytaj istniejące projekty, dodaj nowy, zapisz
        storage_path = os.path.join(app.user_data_dir, 'projects.json')
        projects = []
        if os.path.exists(storage_path):
            try:
                with open(storage_path, 'r', encoding='utf-8') as f:
                    projects = json.load(f)
            except (IOError, json.JSONDecodeError):
                pass

        projects.append(project_data)
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(projects, f)

        # Dodaj kartę projektu na ekranie głównym
        home_screen = app.root.get_screen('home')
        home_screen.add_project_card(
            project_name, self.selected_image_path, self.selected_icon,
            self.selected_color, 0.1, 0.9,
            uid=project_data["uid"],
        )

        self._clear_form()
        app.root.current = "home"

    def select_color(self):
        # Otwiera okno z paletą kolorów, gdzie użytkownik może wybrać
        # kolor tła dla swojego projektu. Przekazuje aktualnie wybrany
        # kolor (żeby go podświetlić w palecie) i funkcję, która
        # zostanie wywołana po kliknięciu nowego koloru.
        open_palette_picker(
            default_color=tuple(self.selected_color),
            on_pick=self._apply_picked_color,
        )

    # Zapamiętuje kolor wybrany przez użytkownika w palecie kolorów.
    def _apply_picked_color(self, color):
        self.selected_color = color