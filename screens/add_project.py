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
import unicodedata
import uuid
from kivy.properties import StringProperty, ColorProperty, NumericProperty, ObjectProperty, ListProperty
from kivy.uix.screenmanager import Screen
from kivymd.uix.dialog import MDDialog
from screens.color_palette import open_palette_picker
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivymd.uix.label import MDIcon
from kivymd.uix.fitimage import FitImage
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import platform
from kivy.clock import Clock
from plyer import filechooser

from screens.image_utils import prepare_project_image
from screens.emoji_assets import ensure_emoji_assets, resolve_emoji_source
from kivymd.app import MDApp
from kivymd.uix.behaviors import RectangularRippleBehavior
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import AsyncImage, Image
from kivy.cache import Cache
from kivy.factory import Factory
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget


# ---------------------------------------------------------------------------
# PRZYCISK EMOJI – mały kwadracik z obrazkiem emoji
# ---------------------------------------------------------------------------
class EmojiButton(RectangularRippleBehavior, ButtonBehavior, Image):
    # Klikalny kwadracik z obrazkiem emoji – pojawia się w oknie wyboru emoji,
    # gdy użytkownik chce ustawić ikonę projektu. Każdy przycisk zawiera
    # jeden znak emoji i po kliknięciu informuje ekran, które emoji wybrano.
    
    screen = ObjectProperty(None)  # Przechowuje odniesienie do ekranu głównego – potrzebne do odświeżania po dodaniu projektu
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nocache = True  # Nie przechowuj w pamięci podręcznej (oszczędność RAM)
        self.size_hint = (None, None)
        self.size = (dp(60), dp(60))
        self.allow_stretch = True
        self.keep_ratio = True
        self.mipmap = False

    # Po kliknięciu przycisku emoji – przekazuje wybrane emoji do ekranu.
    # "screen" to referencja do AddProjectScreen, która obsługuje wybór.
    def on_release(self):
        if self.screen:
            self.screen._on_emoji_selected(self.source)

Factory.register('EmojiButton', cls=EmojiButton)


# ---------------------------------------------------------------------------
# METADANE EMOJI – wyszukiwanie emoji po nazwie lub kodzie
# ---------------------------------------------------------------------------
class EmojiMetadata:
    # Pomaga wyszukiwać emoji po nazwie (np. "uśmiech") lub kodzie szesnastkowym.
    
    # Odczytuje z nazwy pliku kod znaku Unicode.
    # Np. z pliku "u1F600.png" odczytuje kod "1F600" (znak 😀).
    #
    # CO TO JEST UNICODE?
    # To standard który przypisuje każdemu znakowi (literze, emoji) 
    # niepowtarzalny numer. Np. "A" to U+0041, a 😀 to U+1F600.
    # "kod szesnastkowy" (hex) – system liczbowy używający cyfr 0-9 i liter A-F.
    # Np. 1F600 w systemie szesnastkowym = 128512 w dziesiętnym.
    @staticmethod
    def extract_unicode_codepoint(filename):
        base = os.path.splitext(filename)[0]
        
        hex_value = None
        if base.startswith('uni') and len(base) > 3:
            hex_value = base[3:]
        elif base.startswith('u') and len(base) > 1:
            hex_value = base[1:]
        
        if not hex_value:
            return None, None, None
        
        try:
            codepoint = int(hex_value, 16)
            char = chr(codepoint)
            try:
                name = unicodedata.name(char).lower()
            except ValueError:
                category = unicodedata.category(char)
                name = f"category_{category}".lower()
            return hex_value.lower(), char, name
        except (ValueError, OverflowError):
            return None, None, None
    
    # Buduje listę wszystkich dostępnych emoji z podanego folderu.
    # Każdy wpis zawiera: ścieżkę do pliku, kod szesnastkowy, znak, nazwę i słowa kluczowe.
    # Słowa kluczowe umożliwiają wyszukiwanie (np. "uśmiech" znajdzie 😀).
    @staticmethod
    def build_emoji_index(emoji_dir):
        if not os.path.exists(emoji_dir):
            return []
        emoji_index = []
        for filename in sorted([f for f in os.listdir(emoji_dir) if f.lower().endswith(".png")]):
            hex_val, char, name = EmojiMetadata.extract_unicode_codepoint(filename)
            if hex_val:
                keywords = [hex_val] + (name.split('_') if name else [])
                emoji_index.append({
                    'source': os.path.join(emoji_dir, filename),
                    'hex': hex_val,
                    'char': char,
                    'name': name or '',
                    'keywords': keywords,
                    'screen': None
                })
        return emoji_index
    
    # Filtruje emoji po wyszukiwanej frazie (np. po nazwie lub kodzie szesnastkowym).
    # Jeśli nie ma frazy – zwraca pierwsze 200 emoji (żeby nie pokazywać tysięcy).
    @staticmethod
    def filter_emojis(emoji_index, search_term):
        if not search_term or not search_term.strip():
            return emoji_index[:200]
        search_term = search_term.lower().strip()
        filtered = []
        for emoji in emoji_index:
            if search_term in emoji['hex']:
                filtered.append(emoji)
            elif any(search_term in keyword for keyword in emoji['keywords']):
                filtered.append(emoji)
        return filtered


# ---------------------------------------------------------------------------
# GŁÓWNY EKRAN DODAWANIA PROJEKTU
# ---------------------------------------------------------------------------
class AddProjectScreen(Screen):
    selected_color = ColorProperty([0.7, 0.5, 1, 1])  # Domyślny fiolet
    selected_icon = StringProperty("emoticon-happy-outline")
    selected_image_path = StringProperty("")
    _emoji_index = []
    _filtered_emojis = []
    _search_input = None
    _recycle_view = None

    def on_enter(self):
        # Gdy użytkownik wchodzi na ekran dodawania projektu – prosimy
        # o pozwolenia dostępu do plików (Android wymaga tego do galerii)
        # i resetujemy podgląd karty projektu do stanu początkowego.
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        self._search_timer = None
        self._reset_preview_card()

    # -----------------------------------------------------------------------
    # WYBÓR EMOJI – otwiera okno z siatką emoji i wyszukiwarką
    # -----------------------------------------------------------------------
    # Otwiera okno wyboru emoji z paskiem wyszukiwania i siatką obrazków.
    # Najpierw czyści pamięć podręczną obrazków (Cache), żeby zwolnić miejsce w pamięci RAM.
    # Cache to tymczasowe przechowywanie obrazków – czyścimy go przed otwarciem okna emoji.
    def select_emoji(self):
        Cache.remove('kv.image')
        Cache.remove('kv.texture')

        if not self._emoji_index:
            emoji_dir = ensure_emoji_assets()
            self._emoji_index = EmojiMetadata.build_emoji_index(emoji_dir)
            print(f"[EmojiPicker] Built index with {len(self._emoji_index)} emojis")

        self._filtered_emojis = self._emoji_index[:100]

        # Create main container
        container = MDBoxLayout(
            orientation="vertical", 
            spacing=dp(5), 
            padding=dp(5),
            size_hint_y=None,
            height=dp(600)
        )
        
        # Search box
        self._search_input = MDTextField(
            hint_text="Search emoji (hex or name)...",
            mode="rectangle",
            size_hint_y=None,
            height=dp(50)
        )
        self._search_input.bind(text=self._on_search_text)
        container.add_widget(self._search_input)
        
        scroll = ScrollView(size_hint_y=1, do_scroll_x=False)
        
        # Wrapper to center the grid
        grid_wrapper = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            size_hint_x=1,
            padding=0,
            spacing=0
        )
        grid_wrapper.bind(minimum_height=grid_wrapper.setter('height'))

        emoji_size = dp(60)
        emoji_spacing = dp(5)
        available_width = Window.width * 0.9 - dp(20)
        cols = max(3, int(available_width / (emoji_size + emoji_spacing)))
        
        # GridLayout with dynamic columns
        self._emoji_grid = MDGridLayout(
            cols=cols,
            spacing=dp(5),
            padding=dp(5),
            size_hint_y=None,
            size_hint_x=None,
            width=cols * (emoji_size + emoji_spacing) + dp(10)
        )
        self._emoji_grid.bind(minimum_height=self._emoji_grid.setter('height'))
        
        self._populate_emoji_grid(self._filtered_emojis)
        
        grid_wrapper.add_widget(Widget(size_hint_x=1))
        grid_wrapper.add_widget(self._emoji_grid)
        grid_wrapper.add_widget(Widget(size_hint_x=1))
        scroll.add_widget(grid_wrapper)
        container.add_widget(scroll)
        
        # Dialog with proper size
        self.emoji_dialog = MDDialog(
            title="Wybierz ikonę projektu",
            type="custom",
            content_cls=container,
            size_hint_x=0.95,
            size_hint_y=None,
            height=dp(650)
        )
        self.emoji_dialog.open()
        
        def focus_search(dt):
            self._search_input.focus = True
        Clock.schedule_once(focus_search, 0.1)

    def _on_search_text(self, instance, value):
        # Gdy użytkownik wpisuje coś w polu wyszukiwania emoji – nie filtrujemy
        # od razu (bo to spowalniałoby przy każdym znaku). Zamiast tego
        # czekamy 0.5 sekundy po ostatnim wpisanym znaku, żeby dopiero
        # wtedy przefiltrować listę. To daje płynniejsze działanie.
        if not hasattr(self, '_search_scheduled'):
            self._search_scheduled = False
        if not self._search_scheduled:
            self._search_scheduled = True
            Clock.schedule_once(self._delayed_filter, 0.5)

    def _delayed_filter(self, dt=None):
        # Wykonuje właściwe filtrowanie emoji po upływie opóźnienia.
        # Pobiera tekst z paska wyszukiwania, przekazuje do EmojiMetadata
        # i odświeża siatkę emoji tak, żeby pokazywała tylko pasujące wyniki.
        self._search_scheduled = False
        search_term = self._search_input.text
        filtered = EmojiMetadata.filter_emojis(self._emoji_index, search_term)
        self._populate_emoji_grid(filtered)
        print(f"[EmojiPicker] Filtered to {len(filtered)} emojis")
    
    def _on_emoji_selected(self, emoji_val):
        # Gdy użytkownik kliknie na jakieś emoji: zapisujemy wybór,
        # zamykamy okno dialogowe z emoji i czyścimy pole wyszukiwania
        # (żeby przy następnym otwarciu było puste).
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
                with open(storage_path, 'r') as f:
                    projects = json.load(f)
            except (IOError, json.JSONDecodeError):
                pass

        projects.append(project_data)
        with open(storage_path, 'w') as f:
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

    def _apply_picked_color(self, color):
        self.selected_color = color

    def _populate_emoji_grid(self, emoji_list):
        # Wypełnia siatkę widoczną w oknie wyboru emoji – dla każdego emoji
        # z listy tworzy przycisk (EmojiButton). Jeśli lista się nie zmieniła
        # (ma tyle samo elementów co wcześniej) – pomija odświeżanie,
        # żeby nie migotać ekranem przy każdym wpisaniu litery.
        if len(self._emoji_grid.children) == len(emoji_list):
            return
        self._emoji_grid.clear_widgets()
        for emoji in emoji_list:
            btn = EmojiButton(
                source=emoji['source'],
                screen=self,
                size_hint=(None, None),
                size=(dp(60), dp(60))
            )
            self._emoji_grid.add_widget(btn)