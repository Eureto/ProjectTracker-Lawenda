import datetime
import json
import os
import re
import uuid
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex, platform
from kivy.uix.scrollview import ScrollView
from kivymd.app import MDApp
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen

from screens.keyboard_inset import keyboard_inset
from screens import active_timer
from screens.emoji_assets import emoji_path
from screens.session_store import record_session, schedule_home_last_session_refresh

# Główny folder projektu = nadrzędny dla `screens/` (działa zarówno na telefonie, jak i komputerze).
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Zwraca pelna sciezke do pliku z obrazkiem samochodzika w folderze assets.
def _car_asset_path(filename):
    return os.path.join(_PKG_ROOT, "assets", "Progress_Car", filename)


# Zwraca pelna sciezke do pliku z obrazkiem emoji w folderze assets.
def _emoji_asset_path(filename):
    return emoji_path(filename)


RESET_NEVER = "never"
RESET_DAILY = "daily"
RESET_WEEKLY = "weekly"

# Wyrównanie do szerokości MDIconButton, żeby ikony +, strzałka "Zrobione" i kółka statusu były w jednej linii.
_RIGHT_ACTION_WIDTH = dp(48)

_SHEET_FIELD_RADIUS = dp(12)
_SHEET_BTN_RADIUS = dp(12)

_PURPLE = get_color_from_hex("#7e57c2")
_GREY_NODE = get_color_from_hex("#9e9e9e")
_CHIP_INACTIVE = get_color_from_hex("#5e35b1")
_CHIP_ACTIVE = get_color_from_hex("#b388ff")
_CROWN_GOLD = get_color_from_hex("#ffc107")
_GOAL_CARD_PURPLE = list(get_color_from_hex("#7e57c2"))
_GOAL_CARD_GREEN = list(get_color_from_hex("#43a047"))
_CROWN_EMOJI_PATH = _emoji_asset_path("u1F451.png")
_ANDROID_PACKAGE = "org.stokrotka.stokrotka"
_ANDROID_SERVICE_CLASS = f"{_ANDROID_PACKAGE}.ServiceTimerservice"

ETAPY_ADD_GROUP = "Grupa etapów"


# Zapisuje wiadomość w logach Kivy oraz w logcat Androida (tag: ProjectTrackerSvc).
def _android_log(message):
    try:
        from kivy.logger import Logger

        Logger.info("ProjectTrackerSvc: %s", message)
    except Exception:
        pass
    if platform != "android":
        return
    try:
        from jnius import autoclass

        autoclass("android.util.Log").i("ProjectTrackerSvc", str(message))
    except Exception:
        pass


# Zwraca wszystkie klasy usług zadeklarowane w AndroidManifest naszej aplikacji.
def _manifest_service_class_names(activity):
    try:
        from jnius import autoclass

        PackageManager = autoclass("android.content.pm.PackageManager")
        package_name = activity.getPackageName()
        info = activity.getPackageManager().getPackageInfo(
            package_name, PackageManager.GET_SERVICES
        )
        services = info.services
        if services is None:
            return []
        out = []
        for i in range(len(services)):
            name = services[i].name
            if name:
                out.append(name)
        return out
    except Exception as exc:
        _android_log(f"manifest service enumeration failed: {exc!r}")
        return []


# Uruchamia usluge w tle na Androidzie, ktora moze dzialac nawet gdy aplikacja jest zamknieta.
def _start_service_via_intent(autoclass, activity, class_name):
    Intent = autoclass("android.content.Intent")
    VERSION = autoclass("android.os.Build$VERSION")
    context = activity.getApplicationContext()
    intent = Intent()
    intent.setClassName(context.getPackageName(), class_name)
    if VERSION.SDK_INT >= 26:
        context.startForegroundService(intent)
    else:
        context.startService(intent)


# Uruchamia usługę na pierwszym planie, która wyświetla powiadomienia o aktywnym stoperze.
def ensure_android_timer_service():
    if platform != "android":
        return
    try:
        from jnius import autoclass
    except Exception as exc:
        _android_log(f"pyjnius unavailable: {exc!r}")
        return

    try:
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
    except Exception as exc:
        _android_log(f"PythonActivity lookup failed: {exc!r}")
        return

    candidates = []
    for name in _manifest_service_class_names(activity):
        _android_log(f"manifest service available: {name}")
        if name not in candidates:
            candidates.append(name)
    if _ANDROID_SERVICE_CLASS not in candidates:
        candidates.append(_ANDROID_SERVICE_CLASS)

    last_error = None
    for class_name in candidates:
        try:
            service_cls = autoclass(class_name)
            service_cls.start(activity, "")
            _android_log(f"started service via {class_name}.start()")
            return
        except Exception as exc:
            last_error = (class_name, exc)

        try:
            _start_service_via_intent(autoclass, activity, class_name)
            _android_log(f"started service via Intent to {class_name}")
            return
        except Exception as exc:
            last_error = (class_name, exc)

    if last_error:
        _android_log(
            f"failed to start any service. Tried {candidates}. "
            f"Last error on {last_error[0]}: {last_error[1]!r}"
        )
    else:
        _android_log("no service classes found in manifest")


# Rysuje zaokrąglone tło pod polami tekstowymi (TextInput / Spinner) w arkuszach.
class _RoundedSheetBackground:

    fill_color = ListProperty([0.97, 0.97, 0.97, 1])
    corner_radius = NumericProperty(_SHEET_FIELD_RADIUS)

    # Podlacza odswiezanie tla przy kazdej zmianie polozenia, rozmiaru lub koloru.
    def _init_rounded_bg(self):
        self.bind(pos=self._redraw_rounded_bg, size=self._redraw_rounded_bg)
        self.bind(fill_color=lambda *_: self._redraw_rounded_bg())
        self.bind(corner_radius=lambda *_: self._redraw_rounded_bg())
        Clock.schedule_once(lambda _dt: self._redraw_rounded_bg(), 0)

    def _redraw_rounded_bg(self, *_args):
        # Usuwamy tylko naszą własną grupę tła — czyszczenie całego canvas.before
        # usunęłoby regułę koloru Kivy i tekst stałby się biały.
        self.canvas.before.remove_group("sheet_field_bg")
        r = float(self.corner_radius)
        with self.canvas.before:
            Color(*self.fill_color, group="sheet_field_bg")
            RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[r, r, r, r],
                group="sheet_field_bg",
            )


# Pole tekstowe w arkuszu z zaokrąglonym tłem i wbudowanym kolorem tekstu.
class RoundedSheetTextInput(_RoundedSheetBackground, TextInput):

    # Przygotowuje pole tekstowe: przezroczyste tlo, fioletowy kursor i kolor tekstu, a takze zaokraglone tlo w arkuszu.
    def __init__(self, **kwargs):
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_active", "")
        kwargs.setdefault("foreground_color", get_color_from_hex("#222222"))
        kwargs.setdefault("cursor_color", get_color_from_hex("#7e57c2"))
        kwargs.setdefault("hint_text_color", (0.55, 0.55, 0.55, 1))
        super().__init__(**kwargs)
        self._init_rounded_bg()
        self.bind(
            foreground_color=self._on_sheet_text_color_changed,
            hint_text_color=self._on_sheet_text_color_changed,
            disabled_foreground_color=self._on_sheet_text_color_changed,
            disabled=self._on_sheet_text_color_changed,
        )

    # Odswieza wyglad linii tekstu po zmianie koloru tekstu.
    def _on_sheet_text_color_changed(self, *_args):
        self._trigger_refresh_line_options()

    # Zwraca kolor linii tekstu: podpowiedzi, nieaktywny lub normalny.
    def _line_color(self, hint=False):
        if hint:
            return list(self.hint_text_color)
        if self.disabled:
            return list(self.disabled_foreground_color)
        return list(self.foreground_color)

    # Przygotowuje ustawienia dla etykiety linii tekstu, dodajac odpowiedni kolor.
    def _kwargs_for_line_label(self, base_opts, hint=False):
        keys = (
            "font_size",
            "font_name",
            "font_context",
            "font_family",
            "text_language",
            "base_direction",
            "padding_x",
            "padding_y",
            "padding",
        )
        kw = {k: base_opts[k] for k in keys if k in base_opts}
        kw["color"] = self._line_color(hint=hint)
        return kw

    # Pobiera ustawienia linii tekstu i upewnia sie, ze kolor jest aktualny.
    def _get_line_options(self):
        opts = super()._get_line_options()
        color = self._line_color(hint=False)
        if opts.get("color") != color:
            opts = dict(opts)
            opts["color"] = color
            self._line_options = opts
        return self._line_options

    # Tworzy etykiete dla pojedynczej linii tekstu z uwzglednieniem koloru dla podpowiedzi lub zwyklego tekstu.
    def _create_line_label(self, text, hint=False):
        saved = self._line_options
        base = dict(super()._get_line_options())
        merged = dict(base)
        merged.update(self._kwargs_for_line_label(base, hint=hint))
        self._line_options = merged
        try:
            return super()._create_line_label(text, hint=hint)
        finally:
            self._line_options = saved


class RoundedSheetSpinner(_RoundedSheetBackground, Spinner):
    # Przygotowuje liste wyboru z zaokraglonym tlem i przezroczystym standardowym tlem.
    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        super().__init__(**kwargs)
        self._init_rounded_bg()


# Zaokrąglony przycisk wyboru okresu resetowania dla celu czasowego.
class ResetPeriodChip(Button):

    selected = BooleanProperty(False)

    # Przygotowuje przycisk wyboru okresu: przezroczyste tlo, stala wysokosc i szerokosc na caly dostepny obszar.
    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(40))
        kwargs.setdefault("size_hint_x", 1)
        kwargs.setdefault("font_size", sp(13))
        super().__init__(**kwargs)
        self.bind(
            selected=self._apply_visual,
            pos=self._apply_visual,
            size=self._apply_visual,
            state=self._apply_visual,
        )
        Clock.schedule_once(lambda _dt: self._apply_visual(), 0)

    # Odswieza wyglad przycisku: zmienia kolor tla w zaleznosci od tego, czy jest wybrany.
    def _apply_visual(self, *_args):
        r = float(_SHEET_BTN_RADIUS)
        if self.selected:
            fill = list(_PURPLE)
            self.color = 1, 1, 1, 1
        else:
            fill = [0.93, 0.90, 0.98, 1]
            self.color = list(_PURPLE[:3]) + [1]
        if self.state == "down":
            fill = [c * 0.92 for c in fill[:3]] + [fill[3]]
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*fill)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[r, r, r, r])


# Zaokrąglony przycisk akcji w arkuszach (zastępuje płaskie przyciski MD w arkuszach).
class RoundedSheetButton(Button):

    bg_color = ListProperty([0.7, 0.5, 1, 1])
    text_rgb = ListProperty([1, 1, 1, 1])
    corner_radius = NumericProperty(_SHEET_BTN_RADIUS)

    # Przygotowuje zaokraglony przycisk: przezroczyste tlo, pogrubiona czcionka, odswiezanie wygladu przy zmianie.
    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("bold", True)
        super().__init__(**kwargs)
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            state=self._redraw,
            bg_color=lambda *_: self._redraw(),
            text_rgb=lambda *_: self._redraw(),
        )
        Clock.schedule_once(lambda _dt: self._redraw(), 0)

    # Rysuje zaokraglone tlo przycisku z odpowiednim kolorem i przyciemnieniem po nacisnieciu.
    def _redraw(self, *_args):
        bg = list(self.bg_color)
        if self.state == "down":
            bg = [c * 0.9 for c in bg[:3]] + [bg[3]]
        r = float(self.corner_radius)
        self.color = self.text_rgb
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[r, r, r, r])


# Klucz (dzień kalendarzowy / tydzień ISO) używany do resetowania postępów po zakończeniu okresu.
def current_period_key(reset_mode):
    if reset_mode == RESET_NEVER:
        return "all"
    if reset_mode == RESET_DAILY:
        return datetime.date.today().isoformat()
    if reset_mode == RESET_WEEKLY:
        d = datetime.date.today()
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return "all"


# Zamienia liczbe sekund na krotki tekst, np. "2h" dla 7200 sekund, "30min" dla 1800 sekund.
def format_quota_short(seconds):
    s = int(max(1, round(float(seconds))))
    if s >= 3600 and s % 3600 == 0:
        return f"{s // 3600}h"
    if s >= 60 and s % 60 == 0:
        return f"{s // 60}min"
    return f"{s}s"


# Tworzy podsumowanie celu czasowego, np. "2h / dzien" lub "30min / tydzien".
def format_goal_summary(quota_seconds, reset_mode):
    amt = format_quota_short(quota_seconds)
    if reset_mode == RESET_DAILY:
        return f"{amt} / dzień"
    if reset_mode == RESET_WEEKLY:
        return f"{amt} / tydzień"
    return amt


# Odczytuje okres resetowania z tekstu i zwraca odpowiadajaca mu stala (never, daily lub weekly).
def parse_reset_mode(value):
    if not value:
        return RESET_WEEKLY
    v = str(value).lower()
    if v in (RESET_NEVER, "none"):
        return RESET_NEVER
    if v in (RESET_DAILY, "daily", "day", "dzien", "dziennie"):
        return RESET_DAILY
    if v in (RESET_WEEKLY, "weekly", "week", "tydzien", "tygodniowo"):
        return RESET_WEEKLY
    return RESET_WEEKLY


# Próbuje odczytać czas z tekstu wpisanego przez użytkownika, np. '1h' = 1 godzina, '30min' = 30 minut, '2h/1d' = 2 godziny dziennie. Domyślnie 1 godzina.
def parse_goal_target_seconds(goal_str):
    s = (goal_str or "").lower().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*h", s)
    if m:
        return max(60.0, float(m.group(1)) * 3600.0)
    m = re.search(r"(\d+(?:\.\d+)?)\s*min", s)
    if m:
        return max(60.0, float(m.group(1)) * 60.0)
    m = re.search(r"(\d+)\s*s(?:ec)?", s)
    if m:
        return max(10.0, float(m.group(1)))
    return 3600.0


# Tworzy docelowy czas z osobnych pól godzin i minut.
def parse_goal_hours_minutes(hours_text, minutes_text):
    try:
        hours = max(0, int((hours_text or "0").strip()))
    except ValueError:
        hours = 0
    try:
        minutes = max(0, int((minutes_text or "0").strip()))
    except ValueError:
        minutes = 0
    total = hours * 3600 + minutes * 60
    return float(max(60, total))


# Zamienia liczbe sekund na zwiezly tekst do wyswietlenia, np. "45s", "30m", "2h" lub "2h30m".
def format_goal_elapsed(seconds):
    s = int(max(0, round(float(seconds))))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    h, r = divmod(s, 3600)
    m = r // 60
    # Pokazuje czas w zwartej formie, np. "2h30m" zamiast "2 godziny 30 minut".
    return f"{h}h{m}m" if m else f"{h}h"


# Biała etykieta z poziomą linią pod spodem (lista projektów / linie etapów).
class UnderlineTextBlock(BoxLayout):

    text = StringProperty("")
    text_color = ListProperty([1, 1, 1, 1])
    font_size = NumericProperty(sp(14))
    compact_rule = BooleanProperty(False)
    line_box_height = NumericProperty(0)
    show_rule = BooleanProperty(True)

    # Przygotowuje blok tekstu: dodaje etykiete, pozioma linie pod spodem i odstep.
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", 0)
        super().__init__(**kwargs)
        self._top_pad = Widget(size_hint_y=None, height=0)
        self._lbl = Label(
            color=self.text_color,
            font_size=self.font_size,
            halign="left",
            valign="bottom",
            size_hint_y=None,
        )
        self._rule = Widget(size_hint_x=1, size_hint_y=None, height=dp(4))
        self.add_widget(self._top_pad)
        self.add_widget(self._lbl)
        self.add_widget(self._rule)
        self._rule.bind(pos=self._draw_rule, size=self._draw_rule)
        self.bind(
            text=self._relayout,
            width=self._relayout,
            size=self._relayout,
            text_color=self._relayout,
            compact_rule=self._relayout,
            line_box_height=self._relayout,
            show_rule=self._draw_rule,
        )
        Clock.schedule_once(lambda _dt: self._relayout(), 0)

    # Rysuje pozioma biala linie pod tekstem, jesli opcja show_rule jest wlaczona.
    def _draw_rule(self, *_args):
        self._rule.canvas.clear()
        if not self.show_rule:
            return
        w, h = self._rule.size
        if w < 1 or h < 1:
            return
        stroke = dp(1.2)
        with self._rule.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=(0, (h - stroke) * 0.5), size=(w, stroke))

    # Oblicza wysokosc bloku tekstu razem z odstepem i linia pod spodem.
    def _compact_content_height(self, text_h):
        gap = dp(3) if self.compact_rule else dp(4)
        return text_h + gap + dp(4)

    # Przelicza i ustawia rozmiar etykiety, odstepy i wysokosc calego bloku. Odswieza tez rysowanie linii.
    def _relayout(self, *_args):
        self._lbl.text = self.text or ""
        self._lbl.color = tuple(self.text_color)
        self._lbl.font_size = float(self.font_size)
        if self.width < 1:
            return
        self._lbl.text_size = (self.width, None)
        self._lbl.texture_update()
        th = max(sp(16), self._lbl.texture_size[1])
        self._lbl.height = th
        gap = dp(3) if self.compact_rule else dp(4)
        self.spacing = gap
        self._rule.opacity = 1
        self._rule.height = dp(4)
        natural_h = th + gap + self._rule.height
        extra_top = 0
        if self.line_box_height > natural_h:
            extra_top = self.line_box_height - natural_h
        self._top_pad.height = extra_top
        self.height = natural_h + extra_top
        Clock.schedule_once(lambda _dt: self._draw_rule(), 0)


# Przycisk z kółkiem po prawej — biały pierścień dla listy celów, fioletowy/koronka dla etapów.
class StatusCircleButton(Button):

    done = BooleanProperty(False)
    show_crown = BooleanProperty(True)
    white_style = BooleanProperty(False)

    # Przygotowuje przycisk statusu: przezroczyste tlo, staly rozmiar 26x26 pikseli i odswiezanie wygladu przy kazdej zmianie.
    def __init__(self, **kwargs):
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(26), dp(26)))
        super().__init__(**kwargs)
        self.bind(
            done=self._redraw,
            show_crown=self._redraw,
            white_style=self._redraw,
            pos=self._redraw,
            size=self._redraw,
        )
        Clock.schedule_once(lambda _dt: self._redraw(), 0)

    # Rysuje kolko (wypelnione lub pusty pierscien) w zaleznosci od stanu "done". Gdy zrobione i pokaz koronke, wyswietla symbol korony.
    def _redraw(self, *_args):
        self.canvas.before.clear()
        if self.width < 1 or self.height < 1:
            return
        cx = self.center_x
        cy = self.center_y
        r = min(self.width, self.height) * 0.36
        ring_w = dp(2.5)
        with self.canvas.before:
            if self.white_style:
                if self.done:
                    Color(1, 1, 1, 1)
                    Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
                else:
                    Color(1, 1, 1, 1)
                    Line(circle=(cx, cy, r), width=ring_w)
            elif self.done and self.show_crown:
                Color(*_PURPLE)
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            elif self.done:
                Color(*_PURPLE)
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            else:
                Color(*_PURPLE)
                Line(circle=(cx, cy, r), width=dp(2))
        if self.done and self.show_crown:
            self.text = "\u2655"
            self.font_size = sp(12)
            self.color = _CROWN_GOLD
        else:
            self.text = ""


class ChecklistGoalRow(MDBoxLayout):
    index_label = StringProperty("1.")
    display_text = StringProperty("")
    done = BooleanProperty(False)
    parent_screen = ObjectProperty(None, allownone=True)

    # Przygotowuje wiersz celu z listy: ustawia odstepy, poczatkowa wysokosc i laczy zmiany tekstu z przeliczaniem wysokosci.
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(10))
        kwargs.setdefault("padding", [0, dp(2)])
        kwargs.setdefault("size_hint_x", 1)
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(32)
        self._underline = None
        self._status_btn = None
        self.bind(
            display_text=self._schedule_sync_height,
            index_label=self._schedule_sync_height,
            size=self._schedule_sync_height,
        )
        self._sync_clock = None

    # Planuje dopasowanie wysokosci wiersza do zawartosci.
    def _schedule_sync_height(self, *_args):
        if self._sync_clock is not None:
            self._sync_clock.cancel()
        self._sync_clock = Clock.schedule_once(self._sync_height, 0)

    # Reaguje na zmiane rodzica - gdy wiersz jest usuwany, czysci zaplanowane zadania.
    def on_parent(self, _instance, parent):
        if parent is not None:
            self._schedule_sync_height()

    # Wywolywane po utworzeniu widoku - podlacza przeliczanie wysokosci i wyswietla poczatkowy tekst.
    def on_kv_post(self, base_widget):
        self._underline = self.ids.underline_block
        self._status_btn = self.ids.status_btn
        self._status_btn.show_crown = False
        self._status_btn.bind(on_release=self._toggle_done)
        self.ids.index_lbl.text = self.index_label
        self._underline.text = self.display_text
        self._apply_done_to_ui()
        Clock.schedule_once(self._sync_height, 0)

    # Aktualizuje wyglad wiersza po zmianie stanu "zrobione": przekresla tekst i zmienia kolor.
    def _apply_done_to_ui(self):
        btn = self._status_btn or self.ids.get("status_btn")
        if btn is not None:
            btn.done = self.done

    # Przelacza stan "zrobione" celu z listy.
    def _toggle_done(self, *_args):
        self.done = not self.done
        self._apply_done_to_ui()
        if self.parent_screen:
            self.parent_screen.relocate_checklist_goal(self)

    # Dopasowuje wysokosc wiersza do dlugosci tekstu.
    def _sync_height(self, *_args):
        underline = self._underline or self.ids.get("underline_block")
        btn = self._status_btn or self.ids.get("status_btn")
        if underline is None:
            return
        self._underline = underline
        self._status_btn = btn
        idx_w = dp(22) if self.index_label else 0
        btn_w = _RIGHT_ACTION_WIDTH
        btn_h = dp(26)

        underline.text = self.display_text
        if self.width > 1:
            underline.width = max(sp(40), self.width - idx_w - btn_w - self.spacing)
        underline.line_box_height = 0
        underline._relayout()
        text_h = max(sp(16), underline._lbl.texture_size[1])
        content_h = underline._compact_content_height(text_h)
        line_h = max(content_h, btn_h, dp(32))
        underline.line_box_height = line_h
        underline._relayout()

        self.height = line_h
        underline.height = line_h

        if "index_anchor" in self.ids:
            anchor = self.ids.index_anchor
            anchor.size_hint_y = None
            anchor.height = line_h
            if "index_lbl" in self.ids:
                idx = self.ids.index_lbl
                idx.text = self.index_label
                idx.text_size = (None, None)
                idx.texture_update()
                idx.size = idx.texture_size

        status_anchor = btn.parent if btn is not None else self.ids.get("status_anchor")
        if status_anchor is not None:
            status_anchor.size_hint_y = None
            status_anchor.height = line_h
            status_anchor.width = btn_w
        if btn is not None:
            btn.size = (btn_h, btn_h)

        self._apply_done_to_ui()
        parent = self.parent
        if parent is not None and hasattr(parent, "minimum_height"):
            parent.height = parent.minimum_height

    # Sprawdza, czy uzytkownik kliknal w przycisk usuwania lub w tekst - otwiera edytor celu.
    def on_touch_up(self, touch):
        if super().on_touch_up(touch):
            return True
        if not self.collide_point(*touch.pos):
            return False
        if "status_btn" in self.ids and self.ids.status_btn.collide_point(*touch.pos):
            return False
        self.open_edit()
        return True

    # Otwiera arkusz do edycji tego celu.
    def open_edit(self):
        if self.parent_screen:
            self.parent_screen.open_edit_checklist_goal_sheet(self)


# Wiersz do kliknięcia: nagłówek "Zrobione" + strzałka. Kliknięcie rozwija lub zwija listę ukończonych celów.
class ZrobioneHeaderBar(MDBoxLayout):

    section = ObjectProperty(None, allownone=True)

    # Przygotowuje naglowek sekcji "Zrobione" z przyciskiem rozwijania.
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(28))
        kwargs.setdefault("padding", [0, 0, 0, 0])
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)

    # Reaguje na dotkniecie naglowka - przelacza rozwiniecie sekcji.
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    # Konczy obsluge dotkniecia naglowka.
    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if self.collide_point(*touch.pos) and self.section is not None:
                self.section._toggle_expanded()
            return True
        return super().on_touch_up(touch)


# Rozwijana sekcja 'Zrobione' dla ukończonych celów z listy.
class ZrobioneSection(MDBoxLayout):

    expanded = BooleanProperty(True)
    done_count = NumericProperty(0)

    # Przygotowuje sekcje "Zrobione", ktora pokazuje ukonczone cele.
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("spacing", dp(8))
        kwargs.setdefault("size_hint_y", None)
        super().__init__(**kwargs)
        self.bind(
            expanded=self._apply_expanded,
            done_count=self._apply_visibility,
        )
        self.bind(expanded=lambda *_: Clock.schedule_once(self._sync_section_height, 0))
        self._setup_attempts = 0
        self._detached_done_rows = []

    # Wywolywane po utworzeniu - podlacza odswiezanie po zmianie wlasciwosci.
    def on_kv_post(self, base_widget):
        Clock.schedule_once(self._setup_after_kv, 0)

    # Podlacza funkcje odswiezania do zmiany wlasciwosci sekcji.
    def _setup_after_kv(self, _dt):
        if "zrobione_header" not in self.ids:
            self._setup_attempts += 1
            if self._setup_attempts < 20:
                Clock.schedule_once(self._setup_after_kv, 0.05)
            return
        header = self.ids.zrobione_header
        header.section = self
        self.bind(done_count=self._refresh_header, expanded=self._refresh_header)
        self.ids.checklist_done_list.bind(
            minimum_height=lambda *_: Clock.schedule_once(self._sync_section_height, 0)
        )
        self._refresh_all()

    # Przelacza rozwiniecie sekcji - pokazuje lub ukrywa liste zrobionych celow.
    def _toggle_expanded(self, *_args):
        self.expanded = not self.expanded

    # Odswieza tekst naglowka z liczba zrobionych celow.
    def _refresh_header(self, *_args):
        if "zrobione_header" not in self.ids:
            return
        header = self.ids.zrobione_header
        n = int(self.done_count)
        title = f"Zrobione ({n})" if n else "Zrobione"
        if "zrobione_title" in header.ids:
            header.ids.zrobione_title.text = title
        if "zrobione_chevron" in header.ids:
            header.ids.zrobione_chevron.icon = (
                "chevron-down" if self.expanded else "chevron-right"
            )

    # Pokazuje lub ukrywa cala sekcje w zaleznosci od tego, czy sa jakies zrobione cele.
    def _apply_visibility(self, *_args):
        visible = self.done_count > 0
        self.opacity = 1 if visible else 0
        self.disabled = False
        self.size_hint_y = None
        if not visible:
            self.height = 0
            self.collide_disabled = True
            self._detached_done_rows = []
        else:
            self.collide_disabled = False
            Clock.schedule_once(self._apply_expanded, 0)
            Clock.schedule_once(self._sync_section_height, 0)

    # Rozwija lub zwija sekcje z animacja.
    def _apply_expanded(self, *_args):
        if self.done_count <= 0 or "checklist_done_list" not in self.ids:
            return
        lst = self.ids.checklist_done_list
        self._refresh_header()
        if self.expanded:
            if self._detached_done_rows:
                for row in reversed(self._detached_done_rows):
                    lst.add_widget(row)
                self._detached_done_rows = []
            for child in list(lst.children):
                if not isinstance(child, ChecklistGoalRow):
                    continue
                child.collide_disabled = False
                child.disabled = False
                child.opacity = getattr(child, "_zrobione_saved_opacity", 0.72)
                child._sync_height()
            lst.collide_disabled = False
            lst.disabled = False
            lst.height = lst.minimum_height
        else:
            self._detached_done_rows = []
            for child in list(lst.children):
                if not isinstance(child, ChecklistGoalRow):
                    continue
                child._zrobione_saved_opacity = child.opacity
                self._detached_done_rows.append(child)
                lst.remove_widget(child)
            lst.collide_disabled = True
            lst.height = 0
        Clock.schedule_once(self._sync_section_height, 0)

    # Dopasowuje wysokosc sekcji do zawartosci.
    def _sync_section_height(self, *_args):
        if self.done_count <= 0:
            self.height = 0
            self.collide_disabled = True
            self._refresh_lista_celow_box()
            return
        self.collide_disabled = False
        if "zrobione_header" not in self.ids or "checklist_done_list" not in self.ids:
            return
        header_h = self.ids.zrobione_header.height
        body_h = self.ids.checklist_done_list.height if self.expanded else 0
        self.height = header_h + body_h + float(self.spacing)
        self._refresh_lista_celow_box()

    # Odswieza widocznosc i wysokosc listy zrobionych celow.
    def _refresh_lista_celow_box(self, *_args):
        parent = self.parent
        if parent is not None and hasattr(parent, "minimum_height"):
            parent.height = parent.minimum_height

    # Odswieza wszystkie elementy sekcji: naglowek, widocznosc i wysokosc.
    def _refresh_all(self, *_args):
        self._apply_visibility()
        self._apply_expanded()


# Wiersz na osi czasu: linia + podkreślony tekst + status (koronka gdy zrobione).
class StageItemRow(MDBoxLayout):

    display_text = StringProperty("")
    done = BooleanProperty(False)
    is_sub = BooleanProperty(False)
    is_first = BooleanProperty(False)
    is_last = BooleanProperty(False)
    parent_screen = ObjectProperty(None, allownone=True)
    group_index = NumericProperty(0)
    item_index = NumericProperty(0)
    child_index = NumericProperty(-1)

    # Przygotowuje wiersz kroku lub podkroku na osi czasu.
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)
        self.size_hint_y = None
        self._spine = None
        self.bind(display_text=self._sync_height, width=self._sync_height)

    # Wywolywane po utworzeniu - podlacza aktualizacje wygladu po zmianie stanu.
    def on_kv_post(self, base_widget):
        self._spine = self.ids.spine
        self._underline = self.ids.underline_block
        self._status_btn = self.ids.status_btn
        self._status_btn.bind(on_release=self._toggle_done)
        # `sub_arrow` to teraz tylko poziomy odstęp dla Podkroków — strzałkę
        # rysuje sama oś (spine), więc ten element jest niewidoczny i służy
        # tylko do wcięcia tekstu.
        self.ids.sub_arrow.opacity = 0
        self.ids.sub_arrow.width = dp(16) if self.is_sub else 0
        self._spine.is_sub = self.is_sub
        self._spine.is_first = self.is_first
        self._spine.is_last = self.is_last
        # UWAGA: celowo NIE przesuwamy lewego marginesu wiersza dla
        # Podkroków. Przesunięcie całego wiersza przesunęłoby też oś pionową,
        # co przerwałoby ciągłość linii z nadrzędnym Krokiem. Zamiast tego
        # odstęp dp(16) powyżej robi wcięcie tylko dla tekstu.
        self._apply_done_to_ui()
        Clock.schedule_once(self._sync_height, 0)

    # Aktualizuje wyglad wiersza po zmianie stanu "zrobione" dla kroku.
    def _apply_done_to_ui(self):
        if self._spine is not None:
            self._spine.done = self.done
        btn = self._status_btn or self.ids.get("status_btn")
        if btn is not None:
            btn.done = self.done

    # Przelacza stan "zrobione" kroku.
    def _toggle_done(self, *_args):
        self.done = not self.done
        self._apply_done_to_ui()
        if self.parent_screen:
            self.parent_screen._set_etapy_item_done(
                self.group_index, self.item_index, self.child_index, self.done
            )

    # Otwiera edytor kroku w celu edycji nadrzędnego Kroku.
    # Kliknięcie Podkroku otwiera edytor nadrzędnego Kroku, żeby użytkownik
    # mógł zmienić nazwę, dodać lub usunąć Podkroki w jednym miejscu.
    def _open_editor(self, *_args):
        screen = self.parent_screen
        if screen is None:
            return
        screen.open_edit_etapy_krok_sheet(int(self.group_index), int(self.item_index))

    # Dopasowuje wysokosc wiersza do dlugosci opisu kroku.
    def _sync_height(self, *_args):
        underline = self._underline or self.ids.get("underline_block")
        if underline is None:
            return
        self._underline = underline
        underline.text = self.display_text
        if self.width > 1:
            # Approximate width consumed by the fixed-width siblings:
            #   spine(22) + sub_arrow_spacer(16 or 0) + status_btn(26)
            #   + 3 spacings(8 each)
            pad = dp(88) if self.is_sub else dp(72)
            underline.width = max(sp(40), self.width - pad)
        underline._relayout()
        self.height = max(dp(40), underline.height + dp(4))
        self._apply_done_to_ui()


class TimelineSpine(Widget):
    is_sub = BooleanProperty(False)
    is_first = BooleanProperty(False)
    is_last = BooleanProperty(False)
    done = BooleanProperty(False)

    # Przygotowuje element wizualny pionowej linii laczacej kroki na osi czasu.
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", dp(22))
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, is_sub=self._redraw)
        self.bind(is_first=self._redraw, is_last=self._redraw, done=self._redraw)

    # Rysuje pionowa linie osi czasu z wezlami i laczeniami miedzy krokami.
    def _redraw(self, *_args):
        self.canvas.clear()
        if self.height < 1:
            return
        cx = self.center_x
        node_cy = self.center_y
        with self.canvas:
            # Always draw the connecting line so the timeline spine reads as
            # one continuous chain — even through Podkroki and behind the
            # arrow head.
            Color(*_GREY_NODE)
            Line(points=[cx, self.top, cx, self.y], width=dp(1.5))
            Color(*(_PURPLE if self.done else _GREY_NODE))
            if self.is_sub:
                # Right-pointing arrow head ( > ) drawn to the RIGHT of the
                # spine line so the line itself stays uninterrupted. The
                # arrow's left tip starts ~dp(4) past the line so there's a
                # clear visual gap between line and arrow.
                gap = dp(4)
                tip_x = cx + gap
                a = dp(5)
                Line(
                    points=[
                        tip_x, node_cy + a,
                        tip_x + a, node_cy,
                        tip_x, node_cy - a,
                    ],
                    width=dp(1.8),
                )
            else:
                node_r = dp(6)
                Ellipse(
                    pos=(cx - node_r, node_cy - node_r),
                    size=(2 * node_r, 2 * node_r),
                )


# Otoczka wokół tekstu StageItemRow, która reaguje na kliknięcie: dotknięcie = edycja kroku.
class StageTextTap(ButtonBehavior, BoxLayout):

    pass


# Kolumna osi dla wiersza EtapyPlusRow: linia od góry do środka,
# a potem wypełnione fioletowe kółko z białym plusem pośrodku.
#
# Szerokość odpowiada TimelineSpine (dp(22)), żeby węzeł z plusem
# był idealnie w jednej linii z kropkami powyżej na osi czasu.
#
# ``connect_top`` kontroluje, czy rysować górną linię — ustaw na False,
# gdy to jedyny wpis na osi, żeby przycisk '+' nie wyglądał,
# jakby był połączony z niczym.
class EtapyPlusSpine(Widget):

    connect_top = BooleanProperty(True)

    # Przygotowuje element wizualny lacznika miedzy etapami na osi czasu.
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", dp(22))
        super().__init__(**kwargs)
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            connect_top=self._redraw,
        )
        Clock.schedule_once(lambda _dt: self._redraw(), 0)

    # Rysuje wezel na osi czasu: fioletowe kolko z bialym krzyzykiem i opcjonalnie pionowa linia do dolu.
    def _redraw(self, *_args):
        self.canvas.clear()
        if self.height < 1 or self.width < 1:
            return
        cx = self.center_x
        cy = self.center_y
        node_r = dp(10)
        with self.canvas:
            if self.connect_top:
                Color(*_GREY_NODE)
                Line(points=[cx, self.top, cx, cy], width=dp(1.5))
            Color(*_PURPLE)
            Ellipse(pos=(cx - node_r, cy - node_r), size=(2 * node_r, 2 * node_r))
            Color(1, 1, 1, 1)
            arm = node_r * 0.55
            Line(points=[cx - arm, cy, cx + arm, cy], width=dp(2.2))
            Line(points=[cx, cy - arm, cx, cy + arm], width=dp(2.2))


# Stały wiersz 'dodaj krok' na dole osi czasu etapów.
#
# Wizualnie kontynuuje linię osi czasu i kończy się fioletowym węzłem z '+'.
# Cały wiersz można kliknąć — otwiera edytor EditEtapyKrokBottomSheet
# w trybie dodawania nowego kroku do wybranej grupy.
#
# ``connect_top`` kontroluje, czy rysować górną linię na osi.
# Gdy to jedyny wpis na osi czasu, powinno być False, żeby przycisk '+'
# nie był połączony pionową linią z niczym.
class EtapyPlusRow(ButtonBehavior, MDBoxLayout):

    parent_screen = ObjectProperty(None, allownone=True)
    connect_top = BooleanProperty(True)

    # Przygotowuje przycisk "+" do dodawania nowego kroku na osi czasu.
    def __init__(self, parent_screen=None, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(48))
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)
        self.parent_screen = parent_screen
        self.bind(on_release=self._on_release)

    # Otwiera edytor nowego kroku po kliknieciu przycisku "+".
    def _on_release(self, *_args):
        screen = self.parent_screen
        if screen is not None:
            screen.open_new_etapy_krok_sheet()


# Panel szczegółów projektu: notatki i cele, stoper, dolne menu nawigacyjne jak na głównym.
class ProjectInfoScreen(MDScreen):

    # ``project_uid`` to główny klucz identyfikacyjny we wszystkich plikach
    # projektu (project_details, active_timer, active_goals). ``project_title``
    # to tylko nazwa wyświetlana — dwa projekty mogą mieć tę samą nazwę.
    # Gdy uid jest puste (stara wersja / nowa instalacja bez migracji),
    # używamy tytułu jako klucza zapasowego, żeby nadal znaleźć dane.
    project_uid = StringProperty("")
    project_title = StringProperty("")
    timer_display = StringProperty("00:00:00")
    timer_running = BooleanProperty(False)
    timer_button_caption = StringProperty("start")

    _timer_ev = None
    _timer_elapsed_seconds = 0
    _run_base_elapsed = 0
    _run_started_at = None
    _etapy_groups = []
    _etapy_selected_index = 0
    _goal_period_ev = None

    # Przygotowuje ekran projektu: wczytuje dane, ustawia zmienne i przygotowuje interfejs.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._checklist_sheet = None
        self._etapy_sheet = None
        self._add_note_sheet = None
        self._goal_sheet = None
        self._goal_period_ev = None
        self._loading_project_content = False
        # Gdy zmienia się project_uid, trzeba przeładować całą zawartość;
        # gdy zmienia się tylko nazwa projektu (zmiana nazwy w miejscu),
        # wystarczy odświeżyć metadane.
        self.bind(project_uid=self._on_project_identity_changed)
        self.bind(project_title=self._on_project_identity_changed)

    # Klucz do danych tego projektu w plikach stanu.
    def _state_key(self):
        return self.project_uid or self.project_title or "_"

    # Reaguje na zmiane nazwy lub koloru projektu.
    def _on_project_identity_changed(self, *_args):
        mgr = self.manager
        if mgr is not None and mgr.current == self.name:
            self.load_project_content()
            self._restore_active_runtime()

    def on_pre_enter(self):
        # Wyświetl zawartość nowego projektu PRZED zakończeniem animacji
        # przejścia, żeby użytkownik nie zobaczył przebłysków poprzedniego
        # projektu. Funkcja on_enter i tak uruchomi ponownie przywracanie
        # stanu, gdy ekran będzie już widoczny.
        self.load_project_content()
        self._restore_active_runtime()

    # Wywolywane po wejsciu na ekran projektu - wczytuje dane i przywraca stan.
    def on_enter(self):
        Window.bind(on_keyboard=self._on_keyboard)
        # on_pre_enter już wypełnił interfejs; tutaj potrzebujemy tylko
        # ponownej synchronizacji stanu (np. opóźnienia stopera podczas
        # animacji) i harmonogramu odświeżania okresów.
        self._restore_active_runtime()
        self._refresh_time_goal_periods()
        if self._goal_period_ev is not None:
            self._goal_period_ev.cancel()
        self._goal_period_ev = Clock.schedule_interval(self._refresh_time_goal_periods, 60)

    # Wywolywane przed opuszczeniem ekranu - czysci dynamiczne elementy.
    def on_leave(self):
        Window.unbind(on_keyboard=self._on_keyboard)
        if self._goal_period_ev is not None:
            self._goal_period_ev.cancel()
            self._goal_period_ev = None
        self._sync_active_timer_elapsed()
        self._stop_timer_event()
        self._stop_all_goal_trackers(update_active=False)
        self.save_project_content()

    # Resetuje postęp samochodzika, gdy skończy się dzień lub tydzień.
    def _refresh_time_goal_periods(self, *_args):
        goals = self.ids.get("goals_list")
        if goals is None:
            return
        changed = False
        for row in list(goals.children):
            if not isinstance(row, TimeGoalTrackRow):
                continue
            before_pk, before_log = row.period_key, row.logged_seconds
            row._ensure_period()
            if row.period_key != before_pk or row.logged_seconds != before_log:
                row.apply_logged_to_ui()
                changed = True
        if changed:
            self.save_project_content()

    # Zatrzymuje pomiar czasu dla wszystkich aktywnych celow.
    def _stop_all_goal_trackers(self, update_active=True):
        for row in list(self.ids.goals_list.children):
            if isinstance(row, TimeGoalTrackRow):
                row.stop_tracking(update_active=update_active)

    # Obsluguje nacisniecie klawisza - klawisz ESC zamyka arkusz.
    def _on_keyboard(self, window, key, scancode, codepoint, modifier):
        if key == 27:
            self._finalize_and_go_home()
            return True
        return False

    # --- Storage ---

    def _state_path(self):
        return os.path.join(MDApp.get_running_app().user_data_dir, "project_details.json")

    # Odczytuje zapisany stan stopera i celow z plikow.
    def _read_all_states(self):
        path = self._state_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    # Zapisuje biezacy stan stopera i celow do plikow.
    def _write_all_states(self, data):
        path = self._state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # Zapisuje wszystkie dane projektu (notatki, cele, etapy) do pliku.
    def save_project_content(self):
        if not (self.project_uid or self.project_title):
            return
        key = self._state_key()
        data = self._read_all_states()
        data[key] = {
            "timer_elapsed": self._timer_elapsed_seconds,
            "notes": self._serialize_notes(),
            "goals": self._serialize_goals(),
            "checklist_goals": self._serialize_checklist_goals(),
            "etapy": self._serialize_etapy(),
        }
        self._write_all_states(data)

    # Wczytuje wszystkie dane projektu z pliku i odtwarza interfejs.
    def load_project_content(self):
        if self.timer_running:
            self.timer_running = False
            self.timer_button_caption = "start"
            self._stop_timer_event()
        self._run_started_at = None
        self._loading_project_content = True
        try:
            self._clear_dynamic_widgets()
            key = self._state_key()
            blob = self._read_all_states().get(key)
            if blob:
                self._timer_elapsed_seconds = int(blob.get("timer_elapsed", 0))
                self._refresh_timer_label()
                for n in blob.get("notes") or []:
                    t = (n.get("text") or "").strip()
                    if not t:
                        continue
                    self.add_note(text=n.get("text", ""), tall=bool(n.get("tall", False)))
                for g in blob.get("goals") or []:
                    goal = g.get("goal", "1h/tydzień")
                    tgt = g.get("goal_target_seconds")
                    if tgt is None:
                        tgt = parse_goal_target_seconds(goal)
                    logged = float(g.get("logged_seconds", 0))
                    if logged <= 0 and "percent" in g:
                        try:
                            p = float(g.get("percent", 0))
                            logged = max(0.0, (p / 100.0) * float(tgt))
                        except (TypeError, ValueError):
                            logged = 0.0
                    rm = parse_reset_mode(g.get("reset_mode", ""))
                    saved_pk = g.get("period_key")
                    cur = current_period_key(rm)
                    if rm != RESET_NEVER and saved_pk is not None and saved_pk != cur:
                        logged = 0.0
                        pk = cur
                    elif saved_pk is None:
                        pk = cur
                    else:
                        pk = saved_pk
                    self.add_time_goal(
                        title=g.get("title", ""),
                        goal=goal,
                        goal_target_seconds=float(tgt),
                        logged_seconds=logged,
                        reset_mode=rm,
                        period_key=pk,
                        uid=g.get("uid") or "",
                        geofence=g.get("geofence") or None,
                    )
                for cg in blob.get("checklist_goals") or []:
                    t = (cg.get("text") or "").strip()
                    if t:
                        self.add_checklist_goal(text=t, done=bool(cg.get("done", False)))
                et = blob.get("etapy") or {}
                self._etapy_groups = et.get("groups") or []
                self._etapy_selected_index = int(et.get("selected_index", 0))
            else:
                self._timer_elapsed_seconds = 0
                self._refresh_timer_label()
                self._etapy_groups = []
                self._etapy_selected_index = 0
            self._run_base_elapsed = self._timer_elapsed_seconds
            self._clamp_etapy_selection()
            self._rebuild_etapy_chips()
            self._rebuild_etapy_timeline()
        finally:
            self._loading_project_content = False

    # Usuwa wszystkie dynamicznie dodane elementy z ekranu: notatki, cele, liste zadan i sekcje "Zrobione".
    def _clear_dynamic_widgets(self):
        for c in list(self.ids.notes_list.children):
            self.ids.notes_list.remove_widget(c)
        for c in list(self.ids.goals_list.children):
            self.ids.goals_list.remove_widget(c)
        cl = self.ids.get("checklist_goals_list")
        if cl is not None:
            for c in list(cl.children):
                cl.remove_widget(c)
        dl = self._checklist_done_list()
        if dl is not None:
            for c in list(dl.children):
                dl.remove_widget(c)
        zr = self.ids.get("zrobione_section")
        if zr is not None:
            zr.done_count = 0
        self._etapy_groups = []
        self._etapy_selected_index = 0

    # Przygotowuje liste notatek do zapisania.
    def _serialize_notes(self):
        out = []
        for row in self.ids.notes_list.children:
            if isinstance(row, ProjectNoteRow):
                out.append(
                    {
                        "text": row.display_text or "",
                        "tall": bool(row.tall),
                    }
                )
        return out

    # Przygotowuje liste celow czasowych do zapisania.
    def _serialize_goals(self):
        out = []
        for row in self.ids.goals_list.children:
            if isinstance(row, TimeGoalTrackRow):
                entry = {
                    "title": row.title_text,
                    "goal": row.goal_text,
                    "goal_target_seconds": row.goal_target_seconds,
                    "logged_seconds": row.logged_seconds,
                    "reset_mode": row.reset_mode,
                    "period_key": row.period_key,
                    "uid": row.active_uid,
                }
                geofence = dict(row.geofence or {})
                if geofence:
                    entry["geofence"] = geofence
                out.append(entry)
        return out

    # Zwraca wszystkie wiersze celow oznaczone jako zrobione.
    def _all_done_checklist_rows(self, zr=None):
        zr = zr or self.ids.get("zrobione_section")
        if zr is None:
            return []
        rows = []
        done_list = self._checklist_done_list()
        if done_list is not None:
            rows.extend(c for c in done_list.children if isinstance(c, ChecklistGoalRow))
        rows.extend(getattr(zr, "_detached_done_rows", []))
        return rows

    # Przechodzi przez wszystkie wiersze celow na liscie.
    def _iter_checklist_rows(self):
        active = self.ids.get("checklist_goals_list")
        if active is not None:
            for c in reversed(active.children):
                if isinstance(c, ChecklistGoalRow):
                    yield c
        for row in self._all_done_checklist_rows():
            yield row

    # Przygotowuje liste celow z listy zadan do zapisania.
    def _serialize_checklist_goals(self):
        out = []
        for row in self._iter_checklist_rows():
            t = (row.display_text or "").strip()
            if t:
                out.append({"text": t, "done": bool(row.done)})
        return out

    # Przygotowuje dane etapow do zapisania: wybrana grupe i liste wszystkich grup z krokami.
    def _serialize_etapy(self):
        return {
            "selected_index": int(self._etapy_selected_index),
            "groups": self._etapy_groups,
        }

    # --- Lista celów (checklist) ---

    def _checklist_done_list(self):
        zr = self.ids.get("zrobione_section")
        if zr is None:
            return None
        return zr.ids.get("checklist_done_list")

    # Czyści nieaktualne okno edycji celu z listy, jesli zostalo zamkniete.
    def _clear_stale_checklist_sheet(self):
        sheet = getattr(self, "_checklist_sheet", None)
        if sheet is None:
            return
        if getattr(sheet, "parent", None) is None:
            self._checklist_sheet = None

    # Otwiera okno do dodawania nowego celu na liscie zadan.
    def open_add_checklist_goal_sheet(self, *_args):
        self._clear_stale_checklist_sheet()
        if self._checklist_sheet is not None:
            return
        sheet = AddChecklistGoalBottomSheet(self, goal_row=None)

        def _cleared(*_a):
            self._checklist_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._checklist_sheet = sheet
        try:
            sheet.open()
        except Exception:
            self._checklist_sheet = None
            raise

    # Otwiera okno do edycji istniejacego celu z listy zadan.
    def open_edit_checklist_goal_sheet(self, row):
        self._clear_stale_checklist_sheet()
        if self._checklist_sheet is not None:
            return
        sheet = AddChecklistGoalBottomSheet(self, goal_row=row)

        def _cleared(*_a):
            self._checklist_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._checklist_sheet = sheet
        try:
            sheet.open()
        except Exception:
            self._checklist_sheet = None
            raise

    # Dodaje nowy cel do listy zadan: tworzy wiersz, umieszcza go na liscie aktywnej lub zrobionej, przelicza wysokosci i zapisuje stan.
    def add_checklist_goal(self, text="", done=False):
        row = ChecklistGoalRow(
            display_text=text,
            done=done,
            parent_screen=self,
        )
        target = self._checklist_done_list() if done else self.ids.checklist_goals_list
        if target is None:
            return
        target.add_widget(row)
        row._sync_height()
        self._refresh_checklist_goals_list_height()
        self._renumber_checklist_goals()
        self._refresh_zrobione_section()
        self.save_project_content()

    # Odswieza wysokosc listy celow, dopasowujac ja do zawartosci.
    def _refresh_checklist_goals_list_height(self, *_args):
        cl = self.ids.get("checklist_goals_list")
        if cl is not None:
            cl.height = cl.minimum_height

    # Usuwa wybrany wiersz celu z listy i zapisuje zmiany.
    def remove_checklist_goal_row(self, row):
        parent = row.parent
        if parent is not None:
            parent.remove_widget(row)
        zr = self.ids.get("zrobione_section")
        if zr is not None and row in getattr(zr, "_detached_done_rows", []):
            zr._detached_done_rows.remove(row)
        self._renumber_checklist_goals()
        self._refresh_checklist_goals_list_height()
        self._refresh_zrobione_section()
        self.save_project_content()

    # Przenosi cel miedzy sekcja aktywna a zrobiona, w zaleznosci od jego stanu.
    def relocate_checklist_goal(self, row):
        active = self.ids.checklist_goals_list
        done_box = self._checklist_done_list()
        if done_box is None:
            return
        if row.parent is not None:
            row.parent.remove_widget(row)
        if row.done:
            done_box.add_widget(row)
            row.index_label = ""
            row.opacity = 0.72
        else:
            active.add_widget(row)
            row.opacity = 1.0
        self._renumber_checklist_goals()
        self._refresh_zrobione_section()
        zr = self.ids.get("zrobione_section")
        if zr is not None and row.done:
            zr.expanded = True
        self.save_project_content()

    # Odswieza sekcje "zrobione" - pokazuje, ile celow jest oznaczonych jako wykonane.
    def _refresh_zrobione_section(self):
        zr = self.ids.get("zrobione_section")
        if zr is None:
            return
        rows = self._all_done_checklist_rows(zr)
        zr.done_count = len(rows)
        for row in rows:
            row.index_label = ""
            row.opacity = 0.72
        zr._apply_expanded()

    # Przenumerowuje wszystkie aktywne cele na liscie od 1 w gore.
    def _renumber_checklist_goals(self):
        cl = self.ids.get("checklist_goals_list")
        if cl is None:
            return
        rows = [c for c in reversed(cl.children) if isinstance(c, ChecklistGoalRow)]
        for i, row in enumerate(rows, start=1):
            row.index_label = f"{i}."
            row.opacity = 1.0
            row._sync_height()
        self._refresh_checklist_goals_list_height()

    # --- Etapy ---

    _etapy_sheet = None
    _etapy_krok_sheet = None

    # Przycisk '+' w nagłówku → tworzy nową Grupę etapów (tylko to).
    def open_add_etapy_group_sheet(self):
        if self._etapy_sheet is not None:
            return
        sheet = AddEtapyGroupBottomSheet(self)

        def _cleared(*_a):
            self._etapy_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._etapy_sheet = sheet
        sheet.open()

    # Otwiera arkusz do edycji/deletu istniejącej grupy etapów (wywoływane po dwukliku na chip).
    def open_edit_etapy_group_sheet(self, group_index):
        if self._etapy_sheet is not None:
            return
        sheet = EditEtapyGroupBottomSheet(self, int(group_index))

        def _cleared(*_a):
            self._etapy_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._etapy_sheet = sheet
        sheet.open()
    # Wewnętrzne: otwiera pełny edytor Kroku (nowy lub edycja).
    def _open_etapy_krok_sheet(self, group_index, item_index):
        if self._etapy_krok_sheet is not None:
            return
        sheet = EditEtapyKrokBottomSheet(self, group_index, item_index)

        def _cleared(*_a):
            self._etapy_krok_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._etapy_krok_sheet = sheet
        sheet.open()

    # Przycisk '+' na osi czasu → tworzy nowy Krok w wybranej grupie.
    def open_new_etapy_krok_sheet(self):
        if not self._etapy_groups:
            return
        self._clamp_etapy_selection()
        self._open_etapy_krok_sheet(self._etapy_selected_index, None)

    # Dotknięcie wiersza Kroku/Podkroku → edycja nadrzędnego Kroku.
    def open_edit_etapy_krok_sheet(self, group_index, item_index):
        try:
            _ = self._etapy_groups[int(group_index)]["items"][int(item_index)]
        except (IndexError, KeyError, TypeError):
            return
        self._open_etapy_krok_sheet(int(group_index), int(item_index))

    # Zabezpiecza wybrany indeks grupy etapow, zebys nie wyszedl poza zakres.
    def _clamp_etapy_selection(self):
        if not self._etapy_groups:
            self._etapy_selected_index = 0
            return
        self._etapy_selected_index = max(
            0, min(self._etapy_selected_index, len(self._etapy_groups) - 1)
        )

    # Zwraca aktualnie wybrana grupe etapow.
    def _selected_etapy_group(self):
        self._clamp_etapy_selection()
        if not self._etapy_groups:
            return None
        return self._etapy_groups[self._etapy_selected_index]

    # Wyswietla wybrana grupe etapow i odswieza os czasu.
    def select_etapy_group(self, index):
        old_index = self._etapy_selected_index
        self._etapy_selected_index = int(index)
        self._clamp_etapy_selection()
        # Update existing chips in-place instead of rebuilding, so that
        # double-click timing (_last_click_time) is preserved.
        # Note: Kivy children are in reverse visual order (last added = first).
        box = self.ids.get("etapy_chips_box")
        if box is not None:
            n = len(box.children)
            for i, child in enumerate(box.children):
                if hasattr(child, '_chip_active'):
                    # Reversed index: child at box.children[0] is the last chip visually
                    child._chip_active = (n - 1 - i == self._etapy_selected_index)
                    if hasattr(child, '_refresh_chip'):
                        child._refresh_chip(child)
        self._rebuild_etapy_timeline()
        self.save_project_content()

    # Oznacza krok lub podkrok jako wykonany / niewykonany.
    def _set_etapy_item_done(self, group_index, item_index, child_index, done):
        try:
            group = self._etapy_groups[group_index]
            if child_index >= 0:
                group["items"][item_index]["children"][child_index]["done"] = done
            else:
                group["items"][item_index]["done"] = done
        except (IndexError, KeyError, TypeError):
            return
        self.save_project_content()

    # Dodaje nowa grupe etapow o podanej nazwie.
    def add_etapy_group(self, name):
        name = (name or "").strip() or "Etap"
        self._etapy_groups.append({"name": name, "items": []})
        self._etapy_selected_index = len(self._etapy_groups) - 1
        self._rebuild_etapy_chips()
        self._rebuild_etapy_timeline()
        self.save_project_content()

    # Zastępuje nazwę istniejącej grupy etapów.
    def update_etapy_group_name(self, group_index, name):
        name = (name or "").strip()
        if not name:
            return
        try:
            self._etapy_groups[int(group_index)]["name"] = name
        except (IndexError, KeyError, TypeError):
            return
        self._rebuild_etapy_chips()
        self.save_project_content()

    # Usuwa grupę etapów (wraz ze wszystkimi jej krokami).
    def delete_etapy_group(self, group_index):
        try:
            del self._etapy_groups[int(group_index)]
        except (IndexError, TypeError):
            return
        self._clamp_etapy_selection()
        self._rebuild_etapy_chips()
        self._rebuild_etapy_timeline()
        self.save_project_content()
    # Dodaje nowy Krok z jego Podkrokami (wywoływane przez edytor kroku).
    def create_etapy_step(self, group_index, text, children=None):
        text = (text or "").strip()
        if not text:
            return
        try:
            group = self._etapy_groups[int(group_index)]
        except (IndexError, TypeError):
            return
        normalized_children = [
            {"text": (c.get("text") or "").strip(), "done": bool(c.get("done", False))}
            for c in (children or [])
            if (c.get("text") or "").strip()
        ]
        group.setdefault("items", []).append(
            {"text": text, "done": False, "children": normalized_children}
        )
        self._rebuild_etapy_timeline()
        self.save_project_content()

    # Zastępuje nazwę Kroku i listę jego Podkroków w jednym zapisie (edytor kroku).
    def update_etapy_step(self, group_index, item_index, text, children=None):
        text = (text or "").strip() or "Krok"
        try:
            item = self._etapy_groups[int(group_index)]["items"][int(item_index)]
        except (IndexError, KeyError, TypeError):
            return
        item["text"] = text
        item["children"] = [
            {"text": (c.get("text") or "").strip(), "done": bool(c.get("done", False))}
            for c in (children or [])
            if (c.get("text") or "").strip()
        ]
        self._rebuild_etapy_timeline()
        self.save_project_content()

    # Usuwa Krok (i wszystkie jego Podkroki) z wybranej grupy.
    def delete_etapy_step(self, group_index, item_index):
        try:
            items = self._etapy_groups[int(group_index)]["items"]
            del items[int(item_index)]
        except (IndexError, KeyError, TypeError):
            return
        self._rebuild_etapy_timeline()
        self.save_project_content()

    # Odtwarza przyciski wyboru grup etapow na gorze osi czasu.
    def _rebuild_etapy_chips(self):
        box = self.ids.get("etapy_chips_box")
        if box is None:
            return
        box.clear_widgets()
        if not self._etapy_groups:
            return
        for idx, group in enumerate(self._etapy_groups):
            active = idx == self._etapy_selected_index
            chip = Button(
                text=group.get("name", "Etap"),
                size_hint=(None, None),
                height=dp(32),
                padding=(dp(14), dp(6)),
                background_normal="",
                background_color=(0, 0, 0, 0),
                color=(0.12, 0.12, 0.12, 1) if active else (1, 1, 1, 1),
                font_size=sp(13),
            )
            chip.texture_update()
            chip.width = chip.texture_size[0] + dp(28)

            chip._chip_active = bool(active)

            def _paint_chip(btn, *_a):
                is_active = getattr(btn, '_chip_active', False)
                btn.canvas.before.clear()
                bg = _CHIP_ACTIVE if is_active else _CHIP_INACTIVE
                btn.color = (0.12, 0.12, 0.12, 1) if is_active else (1, 1, 1, 1)
                with btn.canvas.before:
                    Color(*bg)
                    RoundedRectangle(
                        pos=btn.pos,
                        size=btn.size,
                        radius=[dp(16), dp(16), dp(16), dp(16)],
                    )

            chip._refresh_chip = _paint_chip
            _paint_chip(chip)
            chip.bind(pos=_paint_chip, size=_paint_chip)
            gi = idx
            # Single click: select group. Double-click: open edit/delete sheet.
            chip._last_click_time = 0
            def _on_chip_release(*_a, i=gi, c=chip):
                now = Clock.get_time()
                if now - c._last_click_time < 0.4:
                    # Double-click detected
                    self.open_edit_etapy_group_sheet(i)
                    c._last_click_time = 0
                else:
                    c._last_click_time = now
                    self.select_etapy_group(i)
            chip.bind(on_release=_on_chip_release)
            box.add_widget(chip)
    # Odtwarza pelna os czasu dla wybranej grupy etapow.
    def _rebuild_etapy_timeline(self):
        timeline = self.ids.get("etapy_timeline_list")
        if timeline is None:
            return
        timeline.clear_widgets()
        group = self._selected_etapy_group()
        if group is None:
            # No group → no in-timeline '+'. The header '+' is the only path
            # for creating the first group.
            return
        items = group.get("items") or []
        gi = self._etapy_selected_index
        # Pre-compute (item_index, child_index) of the visually last row so
        # we can mark it `is_last` and suppress its trailing underline.
        last_ii = -1
        last_ci = -1
        if items:
            last_ii = len(items) - 1
            last_children = items[last_ii].get("children") or []
            last_ci = len(last_children) - 1 if last_children else -1
        seq = 0
        for ii, item in enumerate(items):
            seq += 1
            is_last_row = (ii == last_ii and last_ci == -1)
            timeline.add_widget(
                StageItemRow(
                    display_text=item.get("text", ""),
                    done=bool(item.get("done", False)),
                    is_sub=False,
                    is_first=(seq == 1),
                    is_last=is_last_row,
                    parent_screen=self,
                    group_index=gi,
                    item_index=ii,
                    child_index=-1,
                )
            )
            children = item.get("children") or []
            for ci, child in enumerate(children):
                seq += 1
                is_last_row = (ii == last_ii and ci == last_ci)
                timeline.add_widget(
                    StageItemRow(
                        display_text=child.get("text", ""),
                        done=bool(child.get("done", False)),
                        is_sub=True,
                        is_first=False,
                        is_last=is_last_row,
                        parent_screen=self,
                        group_index=gi,
                        item_index=ii,
                        child_index=ci,
                    )
                )
        # Persistent in-timeline '+' node — only when a group is selected.
        # The spine's upward line is only drawn when there's at least one
        # Krok above, so an empty group doesn't show an orphan vertical line
        # trailing from the top of the screen down to the '+' button.
        timeline.add_widget(
            EtapyPlusRow(parent_screen=self, connect_top=bool(items))
        )

    # --- Notes ---

    _add_note_sheet = None

    # Otwiera arkusz do dodawania nowej notatki.
    def open_add_note_sheet(self):
        if self._add_note_sheet is not None:
            return
        sheet = AddNoteBottomSheet(self, note_row=None)

        def _cleared(*_a):
            self._add_note_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._add_note_sheet = sheet
        sheet.open()

    # Otwiera arkusz do edycji istniejacej notatki.
    def open_edit_note_sheet(self, row):
        if self._add_note_sheet is not None:
            return
        sheet = AddNoteBottomSheet(self, note_row=row)

        def _cleared(*_a):
            self._add_note_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._add_note_sheet = sheet
        sheet.open()

    # Dodaje nowa notatke do listy na ekranie.
    def add_note(self, text="", tall=False):
        row = ProjectNoteRow(tall=tall, display_text=text or "", parent_screen=self)
        self.ids.notes_list.add_widget(row)

    # Usuwa wybrany wiersz notatki z listy.
    def remove_note_row(self, row):
        notes = self.ids.get("notes_list")
        if notes is None:
            return
        if row.parent is notes:
            notes.remove_widget(row)
        elif row.parent is not None:
            row.parent.remove_widget(row)
        self.save_project_content()

    # --- Time goals ---

    _goal_sheet = None

    # Reaguje na klikniecie przycisku dodawania celu czasowego.
    def on_goals_add_clicked(self):
        self.open_add_goal_sheet()

    # Otwiera arkusz do dodania nowego celu czasowego.
    def open_add_goal_sheet(self, draft=None):
        if self._goal_sheet is not None:
            return
        sheet = AddTimeGoalBottomSheet(self, draft=draft)

        def _cleared(*_a):
            self._goal_sheet = None

        sheet.bind(on_dismiss=_cleared)
        self._goal_sheet = sheet
        sheet.open()

    # Otwiera wybór lokalizacji na mapie, zachowując roboczą wersję celu.
    #
    # ``draft`` to modyfikowalny słownik z bieżącymi wartościami formularza;
    # funkcja uzupełnia w nim pole ``geofence`` i po powrocie otwiera
    # ponownie arkusz celu.
    def open_geofence_picker_for_goal_draft(self, draft):
        if not isinstance(draft, dict):
            draft = {}
        existing = draft.get("geofence") or {}

        def _on_done(result):
            action = (result or {}).get("action", "cancel")
            if action == "save":
                draft["geofence"] = result.get("geofence") or {}
            elif action == "clear":
                draft["geofence"] = {}
            Clock.schedule_once(
                lambda _dt: self.open_add_goal_sheet(draft=draft), 0
            )

        app = MDApp.get_running_app()
        if app is None or app.root is None:
            return
        try:
            picker = app.root.get_screen("geofence_picker")
        except Exception:
            picker = None
        if picker is None:
            self.open_add_goal_sheet(draft=draft)
            return
        picker.configure(
            initial_lat=existing.get("lat"),
            initial_lon=existing.get("lon"),
            initial_radius_m=existing.get("radius_m"),
            initial_zoom=existing.get("zoom"),
            return_screen="project_info",
            on_done=_on_done,
        )
        app.root.current = "geofence_picker"

    # Tworzy nowy cel czasowy z podanymi ustawieniami i dodaje go do listy celow.
    def add_time_goal(
        self,
        title="",
        goal="",
        goal_target_seconds=None,
        logged_seconds=0.0,
        reset_mode=RESET_WEEKLY,
        period_key=None,
        uid="",
        geofence=None,
    ):
        tgt = float(goal_target_seconds) if goal_target_seconds is not None else parse_goal_target_seconds(goal)
        tgt = max(10.0, tgt)
        if period_key is None:
            period_key = current_period_key(reset_mode) if reset_mode != RESET_NEVER else "all"
        disp = (goal or "").strip() or format_goal_summary(tgt, reset_mode)
        row = TimeGoalTrackRow(
            title_text=title.strip() or "Cel",
            goal_text=disp,
            goal_target_seconds=tgt,
            logged_seconds=max(0.0, float(logged_seconds)),
            reset_mode=reset_mode,
            period_key=period_key,
            active_uid=uid or f"goal-{uuid.uuid4().hex}",
            parent_screen=self,
            geofence=dict(geofence) if isinstance(geofence, dict) else {},
        )
        row.apply_logged_to_ui()
        self.ids.goals_list.add_widget(row)

    # Usuwa wybrany cel czasowy z listy, zatrzymujac jego sledzenie.
    def remove_time_goal_row(self, row):
        if isinstance(row, TimeGoalTrackRow):
            row.stop_tracking()
            if row.active_uid:
                active_timer.remove_goal(row.active_uid)
        goals = self.ids.get("goals_list")
        if goals is None:
            return
        if row.parent is goals:
            goals.remove_widget(row)
        elif row.parent is not None:
            row.parent.remove_widget(row)
        self.save_project_content()

    # Tworzy slownik wszystkich aktywnych celow, gdzie kluczem jest ich unikalny identyfikator.
    def _active_goal_rows_by_uid(self):
        rows = {}
        goals = self.ids.get("goals_list")
        if goals is None:
            return rows
        for row in goals.children:
            if isinstance(row, TimeGoalTrackRow) and row.active_uid:
                rows[row.active_uid] = row
        return rows

    # Zwraca True, gdy ``state`` (stoper / cel) należy do bieżącego projektu.
    #
    # Najpierw porównuje unikalne identyfikatory (uid); gdy żadna strona
    # nie ma uid (np. częściowo skonwertowane dane), porównuje nazwy.
    def _state_matches_project(self, state):
        if not isinstance(state, dict):
            return False
        state_uid = state.get("project_uid")
        if self.project_uid and state_uid:
            return state_uid == self.project_uid
        if state_uid or self.project_uid:
            # One side has a uid and the other doesn't → assume mismatch to
            # avoid falsely binding a renamed-but-shared-name project.
            return False
        return state.get("project_title") == self.project_title

    # Przywraca stan timera i sledzonych celow po wejsciu na ekran projektu.
    def _restore_active_runtime(self):
        timer_state = active_timer.read_project_timer()
        if self._state_matches_project(timer_state):
            started = timer_state.get("started_at")
            try:
                self._run_started_at = datetime.datetime.fromisoformat(started)
            except (TypeError, ValueError):
                self._run_started_at = datetime.datetime.now()
            self._run_base_elapsed = int(timer_state.get("base_elapsed_seconds", 0) or 0)
            self._timer_elapsed_seconds = active_timer.elapsed_from_state(timer_state)
            self._refresh_timer_label()
            self._stop_timer_event()
            self._timer_ev = Clock.schedule_interval(self._on_timer_tick, 1.0)
            self.timer_running = True
            self.timer_button_caption = "stop"

        rows_by_uid = self._active_goal_rows_by_uid()
        for goal_state in active_timer.read_goals():
            if not self._state_matches_project(goal_state):
                continue
            row = rows_by_uid.get(goal_state.get("uid"))
            if row is not None:
                row.restore_tracking_from_state(goal_state)

    # --- Timer ---

    def _sync_active_timer_elapsed(self):
        state = active_timer.read_project_timer()
        if self._state_matches_project(state):
            self._timer_elapsed_seconds = active_timer.elapsed_from_state(state)
            self._refresh_timer_label()

    # Odswieza wyswietlany napis timera w formacie gg:mm:ss.
    def _refresh_timer_label(self):
        s = self._timer_elapsed_seconds
        h, r = divmod(s, 3600)
        m, sec = divmod(r, 60)
        self.timer_display = f"{h:02d}:{m:02d}:{sec:02d}"

    # Zapisuje zakonczona sesje czasowa i zeruje dane biezacego pomiaru.
    def _finish_timer_run(self):
        if self._run_started_at is None:
            return
        duration = self._timer_elapsed_seconds - int(self._run_base_elapsed)
        if duration >= 1:
            record_session(
                self.project_title,
                duration,
                started_at=self._run_started_at,
                project_uid=self.project_uid,
            )
        self._run_started_at = None
        self._run_base_elapsed = self._timer_elapsed_seconds

    # Wlacza lub wylacza stoper projektu - zapisuje lub konczy biezacy pomiar czasu.
    def toggle_timer(self):
        if self.timer_running:
            self._stop_timer_event()
            self._finish_timer_run()
            self.timer_running = False
            self.timer_button_caption = "start"
            active_timer.clear_project_timer()
            self.save_project_content()
            schedule_home_last_session_refresh()
        else:
            self._stop_timer_event()
            self._run_base_elapsed = self._timer_elapsed_seconds
            self._run_started_at = datetime.datetime.now()
            active_timer.start_project_timer(
                self.project_title,
                base_elapsed_seconds=self._run_base_elapsed,
                started_at=self._run_started_at,
                project_uid=self.project_uid,
            )
            self.save_project_content()
            ensure_android_timer_service()
            self._timer_ev = Clock.schedule_interval(self._on_timer_tick, 1.0)
            self.timer_running = True
            self.timer_button_caption = "stop"

    # Zatrzymuje cykliczne odswiezanie timera (konczy tykanie co sekunde).
    def _stop_timer_event(self):
        if self._timer_ev is not None:
            self._timer_ev.cancel()
            self._timer_ev = None

    # Wywolywane co sekunde - aktualizuje wyswietlany czas timera.
    def _on_timer_tick(self, _dt):
        state = active_timer.read_project_timer()
        if self._state_matches_project(state):
            self._timer_elapsed_seconds = active_timer.elapsed_from_state(state)
        elif self.timer_running:
            self._stop_timer_event()
            self.timer_running = False
            self.timer_button_caption = "start"
            self.load_project_content()
            self._restore_active_runtime()
            return
        else:
            self._timer_elapsed_seconds += 1
        self._refresh_timer_label()

    # --- Bottom bar / settings ---

    def _finalize_and_go_home(self):
        self._stop_timer_event()
        self._stop_all_goal_trackers(update_active=False)
        self.save_project_content()
        MDApp.get_running_app().root.current = "home"
        schedule_home_last_session_refresh()

    # Przechodzi do ekranu glownego, zapisujac stan projektu.
    def go_home(self):
        self._finalize_and_go_home()

    # Przechodzi do ekranu statystyk.
    def go_statistics(self):
        MDApp.get_running_app().root.current = "statistics"

    # Zapisuje bieżący stan, a potem przechodzi do ekranu ustawień projektu.
    def open_project_settings(self):
        if not (self.project_uid or self.project_title):
            return
        self._stop_all_goal_trackers(update_active=False)
        self.save_project_content()
        app = MDApp.get_running_app()
        if not app or not getattr(app, "root", None):
            return
        settings = app.root.get_screen("project_settings")
        settings.project_uid = self.project_uid
        settings.project_title = self.project_title
        app.root.current = "project_settings"


# Utrzymuje panele arkuszowe nad klawiaturą ekranową, zostawiając miejsce na pola i przyciski.
class _BottomSheetKeyboardMixin:

    _KB_RELAYOUT_DELAYS = (0.0, 0.2, 0.35, 0.5, 0.7, 0.9, 1.15)

    # Uruchamia nasluchiwanie klawiatury i zmiany rozmiaru okna, by dopasowac panel.
    def _sheet_bind_keyboard(self):
        if getattr(self, "_sheet_kb_bound", False):
            return
        self._win_h_baseline = float(Window.height or 0)
        self._kb_lift_peak = 0.0
        self._kb_relayout_ev = []
        Window.bind(keyboard_height=self._on_sheet_keyboard)
        Window.bind(size=self._on_sheet_window_resize)
        self._sheet_kb_bound = True
        self._kb_poll_ev = Clock.schedule_interval(self._poll_keyboard_layout, 0.2)
        self._sync_modal_height()

    # Zatrzymuje nasluchiwanie klawiatury i przywraca normalne dzialanie okna.
    def _sheet_unbind_keyboard(self):
        poll = getattr(self, "_kb_poll_ev", None)
        if poll is not None:
            poll.cancel()
            self._kb_poll_ev = None
        for ev in getattr(self, "_kb_relayout_ev", []):
            ev.cancel()
        self._kb_relayout_ev = []
        if getattr(self, "_sheet_kb_bound", False):
            Window.unbind(keyboard_height=self._on_sheet_keyboard)
            Window.unbind(size=self._on_sheet_window_resize)
            self._sheet_kb_bound = False

    #
    # O ile dolna krawędź okna Kivy znajduje się nad rzeczywistą górą klawiatury.
    # Odjęcie tej wartości od okna modalnego usuwa widoczną przerwę na urządzeniach z trybem adjustResize.
    def _keyboard_unreserved_gap(self):
        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        win_h = float(Window.height or 0)
        shrink = max(0.0, baseline - win_h) if baseline > win_h + dp(8) else 0.0
        inset = keyboard_inset(baseline) if baseline > 0 else 0.0
        kh = float(Window.keyboard_height or 0)

        gap = max(0.0, inset - shrink)
        if kh > shrink + dp(4):
            gap = max(gap, kh - shrink)

        if self._sheet_input_focused() and gap < dp(16):
            gap = dp(20)

        return min(gap + dp(5), dp(27))

    # Ustawia wysokosc okna modalnego tak, by nie zachodzilo na klawiature.
    def _sync_modal_height(self):
        h = float(Window.height or 0)
        if h <= 0:
            return
        gap = 0.0
        if (
            self._sheet_input_focused()
            or self._window_shrunk_for_keyboard()
            or float(Window.keyboard_height or 0) > dp(48)
        ):
            gap = self._keyboard_unreserved_gap()

        self.size_hint = (1, None)
        self.size_hint_y = None
        self.height = max(dp(160), h - gap)
        self.pos_hint = {"x": 0, "y": 0}
        self.x = 0
        self.y = 0

    # Planuje kilkukrotne przeliczenie ukladu panelu po pojawieniu sie klawiatury.
    def _schedule_keyboard_relayout(self, animate=True):
        if getattr(self, "_closing", False):
            return
        for ev in getattr(self, "_kb_relayout_ev", []):
            ev.cancel()
        self._kb_relayout_ev = []
        for delay in self._KB_RELAYOUT_DELAYS:
            ev = Clock.schedule_once(
                lambda _dt, anim=animate: self._relayout_for_keyboard(anim),
                delay,
            )
            self._kb_relayout_ev.append(ev)

    # Reaguje na pojawienie sie lub znikniecie klawiatury ekranowej.
    def _on_sheet_keyboard(self, *_args):
        if getattr(self, "_closing", False):
            return
        self._schedule_keyboard_relayout(True)

    # Reaguje na zmiane rozmiaru okna, np. po obroceniu ekranu.
    def _on_sheet_window_resize(self, *_args):
        if getattr(self, "_closing", False):
            return
        self._sync_modal_height()
        self._schedule_keyboard_relayout(True)

    # Cyklicznie sprawdza uklad klawiatury i dostosowuje panel (dla bezpieczenstwa).
    def _poll_keyboard_layout(self, _dt):
        if getattr(self, "_closing", False):
            return False
        self._relayout_for_keyboard(True)
        return True

    # Wlacza tryb, w ktorym okno zmniejsza sie, by zrobic miejsce dla klawiatury.
    def _enable_resize_softinput(self):
        try:
            Window.softinput_mode = "resize"
        except Exception:
            pass

    # Sprawdza, czy ktorejs z pol tekstowych w arkuszu jest aktualnie edytowane.
    def _sheet_input_focused(self):
        for name in ("field", "title_field", "hours_field", "minutes_field", "goal_field"):
            w = getattr(self, name, None)
            if w is not None and getattr(w, "focus", False):
                return True
        return False

    # Sprawdza, czy okno zostalo zmniejszone, by zrobic miejsce na klawiature.
    def _window_shrunk_for_keyboard(self):
        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        win_h = float(Window.height or 0)
        return baseline > win_h + dp(40)

    # Dodatkowy odstęp na dole tylko wtedy, gdy okno się NIE zmniejszyło (klawiatura nakłada się na pełny ekran).
    def _keyboard_lift(self):
        if self._window_shrunk_for_keyboard():
            return 0.0

        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        kh = keyboard_inset(baseline)
        peak = float(getattr(self, "_kb_lift_peak", 0) or 0)
        if kh > peak:
            self._kb_lift_peak = kh
        lift = max(kh, peak)

        if self._sheet_input_focused() and lift < dp(200):
            win_h = float(Window.height or 640)
            lift = max(lift, win_h * 0.36)
        return lift

    # Zlicza stałe elementy (marginesy, tytuł, przyciski), żeby pole tekstowe nie zakrywało paska akcji.
    def _measure_panel_chrome(self, panel, exclude=()):
        chrome = float(panel.padding[1]) + float(panel.padding[3])
        excluded = set(exclude)
        for child in panel.children:
            if child in excluded:
                continue
            chrome += float(child.height)
        n = len(panel.children)
        if n > 1:
            chrome += float(panel.spacing) * (n - 1)
        return chrome + dp(4)

    # Określa położenie dolnej krawędzi panelu — kotwiczy do dołu okna (przyciętego do klawiatury).
    def _sheet_bottom_y(self, win_h):
        baseline = float(getattr(self, "_win_h_baseline", 0) or 0)
        shrink = max(0.0, baseline - win_h) if baseline > 0 else 0.0
        inset = keyboard_inset(baseline) if baseline > 0 else float(Window.keyboard_height or 0)

        if not (
            self._sheet_input_focused()
            or shrink > dp(40)
            or inset > dp(48)
        ):
            return 0.0

        if shrink > dp(40):
            return 0.0

        lift = max(inset, float(Window.keyboard_height or 0), self._keyboard_lift())
        gap = self._keyboard_unreserved_gap()
        return max(0.0, lift - gap)

    # Zwraca (panel_height, target_y, inner_height) — wysokość, pozycję i wnętrze arkusza.
    def _sheet_panel_geometry(
        self, max_panel_dp, chrome_dp, field_max_dp=None, fill_available=False
    ):
        win_h = float(self.height or Window.height or 640)
        chrome = float(chrome_dp)
        target_y = self._sheet_bottom_y(win_h)
        keyboard_up = target_y > 0 or self._sheet_input_focused()

        if keyboard_up:
            available = max(dp(160), win_h - target_y - dp(4))
        else:
            available = min(float(max_panel_dp), win_h * 0.85)
            target_y = dp(8)

        panel_h = min(float(max_panel_dp), available)
        inner_h = max(dp(44), panel_h - chrome)

        if keyboard_up and fill_available:
            panel_h = available
            inner_h = max(dp(44), panel_h - chrome)
        elif keyboard_up and field_max_dp is not None:
            inner_h = min(inner_h, float(field_max_dp))
            panel_h = chrome + inner_h
        else:
            panel_h = max(dp(180), panel_h)
            inner_h = max(dp(44), panel_h - chrome)

        if panel_h > available:
            inner_h = max(dp(44), available - chrome)
            panel_h = chrome + inner_h

        return panel_h, target_y, inner_h

    # Wysokość panelu = marginesy + stałe elementy + zawartość (bez dodatkowego luzu).
    def _panel_height_for_content(self, panel, body_height, body_scroll=None):
        pad = float(panel.padding[1]) + float(panel.padding[3])
        spacing = float(panel.spacing)
        n = len(panel.children)
        chrome = pad + (spacing * (n - 1) if n > 1 else 0.0)
        for child in panel.children:
            if child is body_scroll:
                chrome += float(body_height)
            else:
                chrome += float(child.height)
        return chrome


# Wysuwa się od dołu z polem tekstowym i przyciskiem dodawania; automatycznie pokazuje klawiaturę.
class AddNoteBottomSheet(ModalView, _BottomSheetKeyboardMixin):

    _NOTE_FIELD_LINES = 4

    # Oblicza wysokosc pola tekstowego notatki na podstawie liczby wierszy.
    def _note_field_height(self):
        line_h = sp(16) * 1.35
        return dp(24) + line_h * self._NOTE_FIELD_LINES

    # Ustawia rozmiar i polozenie panelu notatki, opcjonalnie z animacja.
    def _apply_note_layout(self, animate=False):
        self._sync_modal_height()
        field_h = self._note_field_height()
        self.field.height = field_h
        self.panel.height = self._panel_height_for_content(self.panel, field_h)
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    # Przygotowuje okno do dodania lub edycji notatki z polem tekstowym i przyciskami.
    def __init__(self, project_screen, note_row=None, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self.note_row = note_row
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        self._fl = root

        dim = Button(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            background_normal="",
            background_color=(0, 0, 0, 0.45),
        )
        dim.bind(on_release=lambda *a: self.dismiss())
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(400),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        title = "Edytuj notatkę" if note_row else "Nowa notatka"
        self.panel.add_widget(
            MDLabel(
                text=title,
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
                valign="middle",
            )
        )

        self.field = RoundedSheetTextInput(
            hint_text="Treść notatki…",
            text=note_row.display_text if note_row else "",
            multiline=True,
            size_hint_y=None,
            height=self._note_field_height(),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
            hint_text_color=(0.55, 0.55, 0.55, 1),
        )
        self.panel.add_widget(self.field)

        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(12),
        )
        if note_row is not None:
            btn_delete = RoundedSheetButton(
                text="Usuń",
                size_hint_x=None,
                width=dp(88),
                bg_color=list(get_color_from_hex("#e53935")),
            )
            btn_delete.bind(on_release=lambda *a: self._delete_note_and_close())
            bar.add_widget(btn_delete)
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        add_label = "Zapisz" if note_row else "Dodaj"
        btn_add = RoundedSheetButton(
            text=add_label,
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)

        self.add_widget(root)

    # Przelicza uklad panelu po zmianie klawiatury (woluje wlasciwe ustawienie).
    def _relayout_for_keyboard(self, animate=False):
        self._apply_note_layout(animate)

    # Wywolywane gdy arkusz notatki zostaje otwarty - przygotowuje klawiature i chowa panel poza ekranem.
    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(500)
        Clock.schedule_once(self._open_start, 0)

    # Wyswietla panel od dolu z plyna animacja, a potem ustawia focus na polu tekstowym.
    def _open_start(self, _dt):
        self._apply_note_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_keyboard_focus, 0.35)

    # Przy zmianie rozmiaru okna aktualizuje szerokosc panelu i wysokosc modala.
    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    # Ustawia kursor w polu tekstowym i przelicza uklad po pojawieniu sie klawiatury.
    def _request_keyboard_focus(self, _dt):
        self.field.focus = True
        self._schedule_keyboard_relayout(True)
        if self.field.text:
            self.field.cursor = (len(self.field.text), 0)

    # Usuwa notatke i zamyka arkusz.
    def _delete_note_and_close(self):
        if self.note_row is not None and self.project_screen is not None:
            self.project_screen.remove_note_row(self.note_row)
        self.dismiss()

    # Zapisuje nowa lub zmodyfikowana notatke i zamyka arkusz.
    def _commit_and_close(self):
        raw = self.field.text or ""
        text = raw.strip()
        tall = bool(text) and (("\n" in raw) or len(text) > 100)
        if self.note_row is not None:
            self.note_row.display_text = text
            self.note_row.tall = tall
            self.project_screen.save_project_content()
            self.dismiss()
            return
        if not text:
            self.dismiss()
            return
        self.project_screen.add_note(text=text, tall=tall)
        self.field.text = ""
        self.dismiss()

    # Zamyka arkusz z animacja zsuwania panelu w dol.
    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddNoteBottomSheet, self).dismiss())
        anim.start(self.panel)


# Arkusz: tytuł + opis celu (np. 1h/1d); docelowy czas jest odczytywany dla postępu samochodzika.
class AddTimeGoalBottomSheet(ModalView, _BottomSheetKeyboardMixin):

    # Przygotowuje okno do dodania nowego celu czasowego z polami na nazwe, godziny, minuty i reset.
    def __init__(self, project_screen, draft=None, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self._closing = False
        self._draft = dict(draft) if isinstance(draft, dict) else {}
        self._geofence = dict(self._draft.get("geofence") or {})
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        dim = Button(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            background_normal="",
            background_color=(0, 0, 0, 0.45),
        )
        dim.bind(on_release=lambda *a: self.dismiss())
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(12), dp(8), dp(12), 0],
            spacing=dp(6),
            size_hint=(1, None),
            height=dp(360),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        self.panel.add_widget(
            MDLabel(
                text="Nowy cel czasowy",
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(22),
                valign="middle",
            )
        )

        self._body_scroll = ScrollView(
            size_hint_y=None,
            height=dp(220),
            do_scroll_x=False,
            bar_width=dp(4),
        )
        self._body = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(210),
        )

        self.title_field = RoundedSheetTextInput(
            hint_text="Nazwa celu",
            text=str(self._draft.get("title", "")),
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            font_size=sp(16),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            foreground_color=get_color_from_hex("#222222"),
        )
        self._body.add_widget(self.title_field)

        time_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            height=dp(62),
        )
        for label_text, default_val, attr in (
            ("Godziny", str(self._draft.get("hours", "1")), "hours_field"),
            ("Minuty", str(self._draft.get("minutes", "0")), "minutes_field"),
        ):
            col = MDBoxLayout(
                orientation="vertical",
                spacing=dp(4),
                size_hint_x=0.5,
                size_hint_y=None,
                height=dp(62),
            )
            col.add_widget(
                MDLabel(
                    text=label_text,
                    font_style="Caption",
                    theme_text_color="Custom",
                    text_color=(0.25, 0.25, 0.28, 1),
                    size_hint_y=None,
                    height=dp(16),
                    valign="middle",
                )
            )
            field = RoundedSheetTextInput(
                text=default_val,
                hint_text="0",
                multiline=False,
                input_filter="int",
                size_hint_y=None,
                height=dp(44),
                font_size=sp(16),
                padding=[dp(12), dp(10), dp(12), dp(10)],
                foreground_color=get_color_from_hex("#222222"),
                halign="center",
            )
            setattr(self, attr, field)
            col.add_widget(field)
            time_row.add_widget(col)
        self._body.add_widget(time_row)

        self._body.add_widget(
            MDLabel(
                text="Reset postępu",
                font_style="Caption",
                theme_text_color="Custom",
                text_color=(0.25, 0.25, 0.28, 1),
                size_hint_y=None,
                height=dp(18),
            )
        )

        self._selected_reset_mode = RESET_WEEKLY
        self._reset_chips = {}
        chip_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(40),
        )
        for label, mode in (
            ("Codziennie", RESET_DAILY),
            ("Tygodniowo", RESET_WEEKLY),
            ("Bez resetu", RESET_NEVER),
        ):
            chip = ResetPeriodChip(text=label)
            chip.bind(on_release=lambda _inst, m=mode: self._select_reset_mode(m))
            self._reset_chips[mode] = chip
            chip_row.add_widget(chip)
        self._body.add_widget(chip_row)
        self._select_reset_mode(
            parse_reset_mode(self._draft.get("reset_mode")) if self._draft.get("reset_mode") else RESET_WEEKLY
        )

        self._body.add_widget(
            MDLabel(
                text="Krótszy cel = szybszy przejazd auta na osi czasu.",
                font_style="Caption",
                theme_text_color="Custom",
                text_color=(0.35, 0.35, 0.38, 1),
                size_hint_x=1,
                size_hint_y=None,
                height=dp(24),
                shorten=True,
                shorten_from="right",
            )
        )

        self._body.add_widget(self._build_geofence_section())

        self._body_scroll.add_widget(self._body)
        self.panel.add_widget(self._body_scroll)
        self._sync_goal_body_height()

        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8),
        )
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_add = RoundedSheetButton(
            text="Dodaj cel",
            size_hint_x=None,
            width=dp(112),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)

        self.add_widget(root)

    # Zaznacza wybrany tryb resetowania celu (np. co tydzien, co miesiac).
    def _select_reset_mode(self, mode):
        self._selected_reset_mode = mode
        for m, chip in self._reset_chips.items():
            chip.selected = m == mode

    # Zwraca krotki tekst opisujacy wybrana lokalizacje (geofence) - np. wspolrzedne i promien.
    def _geofence_summary_text(self):
        gf = self._geofence or {}
        if not gf:
            return "Nie wybrano lokalizacji."
        try:
            lat = float(gf.get("lat"))
            lon = float(gf.get("lon"))
            radius = float(gf.get("radius_m"))
        except (TypeError, ValueError):
            return "Nie wybrano lokalizacji."
        return f"Wybrano: {lat:.4f}, {lon:.4f}  |  {int(radius)} m"

    # Tworzy i zwraca pionowy panel z przyciskami "Mapa" i "Usun" oraz opisem wybranej lokalizacji.
    def _build_geofence_section(self):
        container = MDBoxLayout(
            orientation="vertical",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(96),
        )

        app = MDApp.get_running_app()
        button_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(40),
        )
        btn_map = RoundedSheetButton(
            text="Mapa",
            size_hint_x=None,
            width=dp(112),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_map.bind(on_release=lambda *_a: self._open_geofence_picker())
        button_row.add_widget(btn_map)

        if self._geofence:
            btn_clear = RoundedSheetButton(
                text="Usuń",
                size_hint_x=None,
                width=dp(80),
                bg_color=[0.94, 0.94, 0.96, 1],
                text_rgb=list(get_color_from_hex("#444444")),
            )
            btn_clear.bind(on_release=lambda *_a: self._clear_geofence())
            button_row.add_widget(btn_clear)

        button_row.add_widget(Widget(size_hint_x=1))
        container.add_widget(button_row)

        container.add_widget(
            MDLabel(
                text="Zaznacz miejsce gdzie chcesz mierzyć czas automatycznie po wejściu",
                font_style="Caption",
                theme_text_color="Custom",
                text_color=(0.35, 0.35, 0.38, 1),
                size_hint_y=None,
                height=dp(28),
                text_size=(None, None),
                shorten=False,
                halign="left",
                valign="top",
            )
        )

        self._geofence_summary_lbl = MDLabel(
            text=self._geofence_summary_text(),
            font_style="Caption",
            theme_text_color="Custom",
            text_color=(0.20, 0.20, 0.22, 1) if self._geofence else (0.45, 0.45, 0.48, 1),
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
        )
        container.add_widget(self._geofence_summary_lbl)

        # The descriptive label needs proper text wrapping. Bind text_size to
        # its own width so it can wrap when the panel is narrow.
        def _bind_wrap(lbl):
            def _sync(*_a):
                lbl.text_size = (lbl.width, None)
                lbl.texture_update()
                lbl.height = max(dp(20), lbl.texture_size[1])

            lbl.bind(width=_sync)
            Clock.schedule_once(lambda _dt: _sync(), 0)

        _bind_wrap(container.children[1])  # the descriptive MDLabel
        return container

    # Zapamietuje aktualne wartosci z pol formularza (tytul, godziny, minuty, reset, geofence) do tymczasowego szkicu.
    def _capture_form_into_draft(self):
        self._draft.update(
            {
                "title": (self.title_field.text or "").strip(),
                "hours": (self.hours_field.text or "").strip() or "0",
                "minutes": (self.minutes_field.text or "").strip() or "0",
                "reset_mode": self._selected_reset_mode,
                "geofence": dict(self._geofence) if self._geofence else {},
            }
        )

    # Otwiera ekran wyboru lokalizacji na mapie. Najpierw zapisuje formularz do szkicu.
    def _open_geofence_picker(self):
        self._capture_form_into_draft()
        screen = self.project_screen
        draft = self._draft
        # Szybko zamyka arkusz (bez animacji), żeby nie nakładał się na ekran
        # mapy, do którego za chwilę przejdziemy.
        self._sheet_unbind_keyboard()
        self.title_field.focus = False
        self.hours_field.focus = False
        self.minutes_field.focus = False
        self._closing = True
        super(AddTimeGoalBottomSheet, self).dismiss()
        Clock.schedule_once(
            lambda _dt: screen.open_geofence_picker_for_goal_draft(draft), 0
        )

    # Usuwa wybrana lokalizacje (geofence) i aktualizuje podglad na ekranie.
    def _clear_geofence(self):
        self._geofence = {}
        if getattr(self, "_geofence_summary_lbl", None) is not None:
            self._geofence_summary_lbl.text = self._geofence_summary_text()
            self._geofence_summary_lbl.text_color = (0.45, 0.45, 0.48, 1)

    # Przelicza i ustawia wysokosc kontenera z elementami formularza.
    def _sync_goal_body_height(self):
        spacing = float(self._body.spacing)
        n = len(self._body.children)
        body_h = sum(float(c.height) for c in self._body.children)
        if n > 1:
            body_h += spacing * (n - 1)
        self._body.height = body_h

    # Ustawia pozycje i rozmiar panelu arkusza na ekranie, uwzgledniajac wysokosc zawartosci.
    def _apply_goal_layout(self, animate=False):
        self._sync_modal_height()
        self._sync_goal_body_height()
        body_h = float(self._body.height)
        self._body_scroll.height = body_h
        self.panel.height = self._panel_height_for_content(
            self.panel, body_h, body_scroll=self._body_scroll
        )
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        max_h = win_h - target_y
        if self.panel.height > max_h:
            chrome = self._measure_panel_chrome(
                self.panel, exclude=(self._body_scroll,)
            )
            self._body_scroll.height = max(dp(80), max_h - chrome)
            self.panel.height = self._panel_height_for_content(
                self.panel, self._body_scroll.height, body_scroll=self._body_scroll
            )
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    # Przelicza uklad arkusza, gdy pojawia sie lub znika klawiatura.
    def _relayout_for_keyboard(self, animate=False):
        self._apply_goal_layout(animate)

    # Wywolywane automatycznie po otwarciu arkusza - podlacza obsluge klawiatury i rozpoczyna animacje wysuwania.
    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(600)
        Clock.schedule_once(self._open_start, 0)

    # Animuje wysuniecie panelu z dolu ekranu, a po zakonczeniu ustawia focus na polu tytulu.
    def _open_start(self, _dt):
        self._apply_goal_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_goal_focus, 0.35)

    # Przenosi focus (kursor) do pola tytulu, zeby uzytkownik mogl od razu pisac.
    def _request_goal_focus(self, _dt):
        self.title_field.focus = True
        self._schedule_keyboard_relayout(True)

    # Wywolywane przy zmianie rozmiaru ekranu - dopasowuje szerokosc panelu i przelicza uklad.
    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    # Zapisuje nowy cel czasowy do projektu i zamyka arkusz.
    def _commit(self):
        title = (self.title_field.text or "").strip()
        if not title:
            self.dismiss()
            return
        quota = parse_goal_hours_minutes(
            self.hours_field.text,
            self.minutes_field.text,
        )
        mode = self._selected_reset_mode
        summary = format_goal_summary(quota, mode)
        self.project_screen.add_time_goal(
            title=title,
            goal=summary,
            goal_target_seconds=quota,
            logged_seconds=0.0,
            reset_mode=mode,
            geofence=dict(self._geofence) if self._geofence else None,
        )
        self.project_screen.save_project_content()
        self.dismiss()

    # Zamyka arkusz z animacja zsuwania w dol. Wylacza klawiature i czysci focus z pol.
    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.title_field.focus = False
        self.hours_field.focus = False
        self.minutes_field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddTimeGoalBottomSheet, self).dismiss())
        anim.start(self.panel)


# Dodaje lub edytuje prosty cel z listy (Lista celów).
class AddChecklistGoalBottomSheet(ModalView, _BottomSheetKeyboardMixin):

    # Przygotowuje okno do dodania lub edycji prostego celu z listy.
    def __init__(self, project_screen, goal_row=None, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self.goal_row = goal_row
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        dim = Button(
            size_hint=(1, 1),
            background_normal="",
            background_color=(0, 0, 0, 0.45),
            on_release=lambda *a: self.dismiss(),
        )
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(220),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        title = "Edytuj cel" if goal_row else "Nowy cel"
        self.panel.add_widget(
            MDLabel(
                text=title,
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
            )
        )
        self.field = RoundedSheetTextInput(
            hint_text="Opis celu…",
            text=goal_row.display_text if goal_row else "",
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
        )
        self.panel.add_widget(self.field)

        bar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(12))
        if goal_row is not None:
            btn_delete = RoundedSheetButton(
                text="Usuń",
                size_hint_x=None,
                width=dp(88),
                bg_color=list(get_color_from_hex("#e53935")),
            )
            btn_delete.bind(on_release=lambda *a: self._delete_and_close())
            bar.add_widget(btn_delete)
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_add = RoundedSheetButton(
            text="Zapisz" if goal_row else "Dodaj",
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)
        self.add_widget(root)

    # Ustawia pozycje i rozmiar panelu na ekranie. Jesli animate=True, przesuwa go plytko.
    def _apply_sheet_layout(self, animate=False):
        self._sync_modal_height()
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        self.panel.height = self._panel_height_for_content(self.panel, 0)
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    # Przelicza uklad arkusza, gdy pojawia sie klawiatura.
    def _relayout_for_keyboard(self, animate=False):
        self._apply_sheet_layout(animate)

    # Wywolywane po otwarciu - podlacza klawiature i rozpoczyna animacje wysuwania.
    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(300)
        Clock.schedule_once(self._open_anim, 0)

    # Wysuwa panel z dolu ekranu, ustawia jego wysokosc i po chwili przenosi focus na pole tekstowe.
    def _open_anim(self, _dt):
        self.panel.height = max(
            dp(220),
            self._panel_height_for_content(self.panel, 0),
        )
        self._apply_sheet_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_focus, 0.3)

    # Ustawia kursor w polu tekstowym, zeby uzytkownik mogl od razu pisac.
    def _request_focus(self, _dt):
        self.field.focus = True
        self._schedule_keyboard_relayout(True)

    # Dopasowuje szerokosc panelu przy zmianie rozmiaru okna.
    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    # Usuwa cel z listy i zamyka arkusz.
    def _delete_and_close(self):
        if self.goal_row is not None:
            self.project_screen.remove_checklist_goal_row(self.goal_row)
        self.dismiss()

    # Zapisuje nowy lub zmodyfikowany cel do projektu i zamyka arkusz.
    def _commit_and_close(self):
        text = (self.field.text or "").strip()
        if self.goal_row is not None:
            self.goal_row.display_text = text
            self.goal_row._sync_height()
            self.project_screen._renumber_checklist_goals()
            self.project_screen.save_project_content()
            self.dismiss()
            return
        if text:
            self.project_screen.add_checklist_goal(text=text)
            self.project_screen.save_project_content()
        self.dismiss()

    # Zamyka arkusz z animacja - zsuwa panel w dol i wylacza klawiature.
    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddChecklistGoalBottomSheet, self).dismiss())
        anim.start(self.panel)


# Minimalny arkusz dla przycisku '+' w nagłówku Etapów: pyta tylko o nazwę Grupy etapów.
#
# Po przeprojektowaniu to jedyne miejsce do tworzenia nowej grupy.
# Kroki i Podkroki są edytowane w EditEtapyKrokBottomSheet (otwieranym z osi czasu).
class AddEtapyGroupBottomSheet(ModalView, _BottomSheetKeyboardMixin):

    # Przygotowuje okno do wpisania nazwy nowej grupy etapow.
    def __init__(self, project_screen, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        root = FloatLayout()
        dim = Button(
            size_hint=(1, 1),
            background_normal="",
            background_color=(0, 0, 0, 0.45),
            on_release=lambda *a: self.dismiss(),
        )
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(300),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        self.panel.add_widget(
            MDLabel(
                text="Nowa grupa etapów",
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
            )
        )

        self.field = RoundedSheetTextInput(
            hint_text="Nazwa grupy (np. Salto)…",
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
        )
        self.panel.add_widget(self.field)

        bar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(12))
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_add = RoundedSheetButton(
            text="Dodaj",
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_add.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_add)
        self.panel.add_widget(bar)
        self.add_widget(root)

    # Ustawia pozycje i rozmiar panelu, uwzgledniajac wysokosc ekranu i klawiature.
    def _apply_sheet_layout(self, animate=False):
        self._sync_modal_height()
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        self.panel.height = self._panel_height_for_content(self.panel, 0)
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        max_h = win_h - target_y
        if self.panel.height > max_h:
            self.panel.height = max(dp(180), max_h)
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    # Przelicza uklad przy pojawieniu sie klawiatury.
    def _relayout_for_keyboard(self, animate=False):
        self._apply_sheet_layout(animate)

    # Podlacza obsluge klawiatury i rozpoczyna animacje otwarcia.
    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(400)
        Clock.schedule_once(self._open_anim, 0)

    # Wysuwa panel z dolu i po chwili ustawia focus na polu tekstowym.
    def _open_anim(self, _dt):
        self._apply_sheet_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_focus, 0.3)

    # Ustawia kursor w polu tekstowym, zeby uzytkownik mogl od razu wpisac nazwe.
    def _request_focus(self, _dt):
        self.field.focus = True
        self._schedule_keyboard_relayout(True)

    # Dopasowuje szerokosc panelu po zmianie rozmiaru ekranu.
    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    # Dodaje nowa grupe etapow do projektu i zamyka arkusz.
    def _commit_and_close(self):
        text = (self.field.text or "").strip()
        if not text:
            self.dismiss()
            return
        self.project_screen.add_etapy_group(text)
        self.dismiss()

    # Zamyka arkusz z animacja - zsuwa panel w dol i wylacza klawiature.
    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(AddEtapyGroupBottomSheet, self).dismiss())
        anim.start(self.panel)


# Arkusz do edycji/deletu istniejącej grupy etapów — wywoływany po dwukliku na chipie.
class EditEtapyGroupBottomSheet(ModalView, _BottomSheetKeyboardMixin):

    # Przygotowuje okno do edycji nazwy grupy etapów z przyciskiem usuwania.
    def __init__(self, project_screen, group_index, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self.group_index = int(group_index)
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        # Odczytuje aktualną nazwę grupy.
        try:
            group = project_screen._etapy_groups[self.group_index]
            self._initial_name = group.get("name", "")
        except (IndexError, KeyError, TypeError):
            self._initial_name = ""

        root = FloatLayout()
        dim = Button(
            size_hint=(1, 1),
            background_normal="",
            background_color=(0, 0, 0, 0.45),
            on_release=lambda *a: self.dismiss(),
        )
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(300),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        self.panel.add_widget(
            MDLabel(
                text="Edytuj grupę etapów",
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
            )
        )

        self.field = RoundedSheetTextInput(
            hint_text="Nazwa grupy (np. Salto)…",
            text=self._initial_name,
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
        )
        self.panel.add_widget(self.field)

        bar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(12))
        btn_delete = RoundedSheetButton(
            text="Usuń",
            size_hint_x=None,
            width=dp(88),
            bg_color=list(get_color_from_hex("#e53935")),
        )
        btn_delete.bind(on_release=lambda *a: self._delete_and_close())
        bar.add_widget(btn_delete)
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        app = MDApp.get_running_app()
        btn_save = RoundedSheetButton(
            text="Zapisz",
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_save.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_save)
        self.panel.add_widget(bar)
        self.add_widget(root)

    # Ustawia pozycje i rozmiar panelu, uwzgledniajac wysokosc ekranu i klawiature.
    def _apply_sheet_layout(self, animate=False):
        self._sync_modal_height()
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        self.panel.height = self._panel_height_for_content(self.panel, 0)
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        max_h = win_h - target_y
        if self.panel.height > max_h:
            self.panel.height = max(dp(180), max_h)
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    # Przelicza uklad przy pojawieniu sie klawiatury.
    def _relayout_for_keyboard(self, animate=False):
        self._apply_sheet_layout(animate)

    # Podlacza obsluge klawiatury i rozpoczyna animacje otwarcia.
    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(400)
        Clock.schedule_once(self._open_anim, 0)

    # Wysuwa panel z dolu i po chwili ustawia focus na polu tekstowym.
    def _open_anim(self, _dt):
        self._apply_sheet_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_focus, 0.3)

    # Ustawia kursor w polu tekstowym, zeby uzytkownik mogl od razu edytowac nazwe.
    def _request_focus(self, _dt):
        self.field.focus = True
        self._schedule_keyboard_relayout(True)
        if self.field.text:
            self.field.cursor = (len(self.field.text), 0)

    # Dopasowuje szerokosc panelu po zmianie rozmiaru ekranu.
    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    # Usuwa grupe etapow i zamyka arkusz.
    def _delete_and_close(self):
        self.project_screen.delete_etapy_group(self.group_index)
        self.dismiss()

    # Zapisuje zmieniona nazwe grupy i zamyka arkusz.
    def _commit_and_close(self):
        text = (self.field.text or "").strip()
        if not text:
            self.dismiss()
            return
        self.project_screen.update_etapy_group_name(self.group_index, text)
        self.dismiss()

    # Zamyka arkusz z animacja - zsuwa panel w dol i wylacza klawiature.
    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(EditEtapyGroupBottomSheet, self).dismiss())
        anim.start(self.panel)


# Pojedynczy wiersz edytora wewnątrz listy Podkroków w EditEtapyKrokBottomSheet.
#
# Zawiera punktor, pole tekstowe do edycji i czerwony przycisk × do usuwania.
# Zachowuje oryginalny stan ``done``, żeby zmiana kolejności/edycja nie kasowała informacji o ukończeniu.
class _PodkrokEditorRow(MDBoxLayout):

    # Tworzy pojedynczy wiersz edytora podkroku z punktorem, polem tekstowym i przyciskiem usuwania.
    def __init__(self, sheet, text="", done=False, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(44))
        super().__init__(**kwargs)
        self.sheet = sheet
        self.done_state = bool(done)

        self.add_widget(
            MDLabel(
                text="•",
                size_hint_x=None,
                width=dp(14),
                font_size=sp(22),
                theme_text_color="Custom",
                text_color=get_color_from_hex("#7e57c2"),
                halign="center",
                valign="middle",
                bold=True,
            )
        )

        self.field = RoundedSheetTextInput(
            hint_text="Nazwa podkroku…",
            text=text or "",
            multiline=False,
            size_hint_y=None,
            height=dp(40),
            font_size=sp(15),
            padding=[dp(10), dp(10), dp(10), dp(10)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
        )
        self.add_widget(self.field)

        del_btn = Button(
            text="×",
            size_hint=(None, None),
            size=(dp(36), dp(36)),
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            color=get_color_from_hex("#e53935"),
            font_size=sp(22),
            bold=True,
        )
        del_btn.bind(on_release=lambda *_: self.sheet._remove_podkrok_row(self))
        self.add_widget(del_btn)


# Edytor wysuwany od dołu dla jednego Kroku i jego Podkroków.
#
# Tryby:
#   * item_index=None → nowy Krok w ``group_index`` (bez przycisku usuwania).
#   * item_index=int  → edycja istniejącego Kroku; przycisk 'Usuń' w lewym dolnym rogu go usuwa.
#
# Podkroki można w pełni zarządzać: zmieniać nazwę w miejscu, usuwać × w każdym wierszu,
# 'Dodaj podkrok' dodaje pusty wiersz. Wszystkie zmiany są zapisywane przyciskiem 'Zapisz'.
class EditEtapyKrokBottomSheet(ModalView, _BottomSheetKeyboardMixin):

    # Przygotowuje okno edytora dla jednego kroku i jego podkrokow.
    def __init__(self, project_screen, group_index, item_index=None, **kwargs):
        super().__init__(**kwargs)
        self.project_screen = project_screen
        self.group_index = int(group_index)
        self.item_index = item_index
        self._closing = False
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background_color = (0, 0, 0, 0)
        self.background = ""

        # Zapisuje początkowy stan, żeby anulowanie faktycznie odrzucało zmiany.
        self._initial_text = ""
        self._initial_children = []
        if item_index is not None:
            try:
                src = project_screen._etapy_groups[self.group_index]["items"][item_index]
                self._initial_text = src.get("text", "")
                self._initial_children = [
                    {
                        "text": c.get("text", ""),
                        "done": bool(c.get("done", False)),
                    }
                    for c in (src.get("children") or [])
                ]
            except (IndexError, KeyError, TypeError):
                pass

        root = FloatLayout()
        self._fl = root
        dim = Button(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            background_normal="",
            background_color=(0, 0, 0, 0.45),
        )
        dim.bind(on_release=lambda *a: self.dismiss())
        root.add_widget(dim)

        self.panel = MDCard(
            orientation="vertical",
            padding=[dp(14), dp(10), dp(14), 0],
            spacing=dp(8),
            size_hint=(1, None),
            height=dp(420),
            radius=[dp(22), dp(22), 0, 0],
            md_bg_color=(1, 1, 1, 1),
            elevation=16,
        )
        root.add_widget(self.panel)

        title = "Edytuj krok" if item_index is not None else "Nowy krok"
        self.panel.add_widget(
            MDLabel(
                text=title,
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#222222"),
                size_hint_y=None,
                height=dp(24),
                valign="middle",
            )
        )

        self.name_field = RoundedSheetTextInput(
            hint_text="Nazwa kroku…",
            text=self._initial_text,
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=sp(16),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            foreground_color=get_color_from_hex("#222222"),
            cursor_color=get_color_from_hex("#7e57c2"),
        )
        self.panel.add_widget(self.name_field)

        self.panel.add_widget(
            MDLabel(
                text="Podkroki",
                font_size=sp(13),
                bold=True,
                theme_text_color="Custom",
                text_color=get_color_from_hex("#666666"),
                size_hint_y=None,
                height=dp(20),
                valign="middle",
            )
        )

        self._podkrok_scroll = ScrollView(
            size_hint_y=None,
            height=dp(150),
            do_scroll_x=False,
            bar_width=dp(4),
        )
        self._podkrok_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(0),
        )
        self._podkrok_box.bind(minimum_height=self._sync_podkrok_box_height)
        self._podkrok_scroll.add_widget(self._podkrok_box)
        self.panel.add_widget(self._podkrok_scroll)

        app = MDApp.get_running_app()
        add_pod_btn = RoundedSheetButton(
            text="+ Dodaj podkrok",
            size_hint_y=None,
            height=dp(40),
            bg_color=[0.94, 0.92, 1.0, 1],
            text_rgb=list(get_color_from_hex("#5e35b1")),
        )
        add_pod_btn.bind(on_release=lambda *_: self._add_podkrok_row())
        self.panel.add_widget(add_pod_btn)

        for child in self._initial_children:
            self._add_podkrok_row(child.get("text", ""), child.get("done", False))

        bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(12),
        )
        if item_index is not None:
            btn_delete = RoundedSheetButton(
                text="Usuń",
                size_hint_x=None,
                width=dp(96),
                bg_color=list(get_color_from_hex("#e53935")),
            )
            btn_delete.bind(on_release=lambda *a: self._delete_and_close())
            bar.add_widget(btn_delete)
        bar.add_widget(Widget(size_hint_x=1))
        btn_cancel = RoundedSheetButton(
            text="Anuluj",
            size_hint_x=None,
            width=dp(96),
            bg_color=[0.94, 0.94, 0.96, 1],
            text_rgb=list(get_color_from_hex("#444444")),
        )
        btn_cancel.bind(on_release=lambda *a: self.dismiss())
        save_label = "Zapisz" if item_index is not None else "Dodaj"
        btn_save = RoundedSheetButton(
            text=save_label,
            size_hint_x=None,
            width=dp(104),
            bg_color=list(get_color_from_hex(app.theme_card_bg)),
        )
        btn_save.bind(on_release=lambda *a: self._commit_and_close())
        bar.add_widget(btn_cancel)
        bar.add_widget(btn_save)
        self.panel.add_widget(bar)
        self.add_widget(root)

    # --- Podkrok list management ---

    def _add_podkrok_row(self, text="", done=False):
        row = _PodkrokEditorRow(self, text=text, done=done)
        self._podkrok_box.add_widget(row)
        Clock.schedule_once(lambda _dt: self._apply_sheet_layout(True), 0)

    # Usuwa wybrany wiersz podkroku z listy i przelicza uklad arkusza.
    def _remove_podkrok_row(self, row):
        if row.parent is self._podkrok_box:
            self._podkrok_box.remove_widget(row)
        Clock.schedule_once(lambda _dt: self._apply_sheet_layout(True), 0)

    # Dopasowuje wysokosc kontenera podkrokow do ich rzeczywistej zawartosci.
    def _sync_podkrok_box_height(self, *_):
        self._podkrok_box.height = self._podkrok_box.minimum_height
        Clock.schedule_once(lambda _dt: self._apply_sheet_layout(False), 0)

    # --- Layout (mirrors AddTimeGoalBottomSheet pattern) ---

    def _apply_sheet_layout(self, animate=False):
        self._sync_modal_height()
        body_h = float(self._podkrok_box.minimum_height)
        self._podkrok_scroll.height = max(dp(60), min(body_h, dp(220)))
        self.panel.height = self._panel_height_for_content(
            self.panel, self._podkrok_scroll.height, body_scroll=self._podkrok_scroll
        )
        self.panel.width = self.width or Window.width
        self.panel.x = 0
        self.panel.pos_hint = {}
        win_h = float(self.height or Window.height or 640)
        target_y = self._sheet_bottom_y(win_h)
        max_h = win_h - target_y
        if self.panel.height > max_h:
            chrome = self._measure_panel_chrome(
                self.panel, exclude=(self._podkrok_scroll,)
            )
            self._podkrok_scroll.height = max(dp(60), max_h - chrome)
            self.panel.height = self._panel_height_for_content(
                self.panel,
                self._podkrok_scroll.height,
                body_scroll=self._podkrok_scroll,
            )
        if animate:
            Animation(y=target_y, d=0.12, t="out_cubic").start(self.panel)
        else:
            self.panel.y = target_y

    # Przelicza uklad przy pojawieniu sie klawiatury.
    def _relayout_for_keyboard(self, animate=False):
        self._apply_sheet_layout(animate)

    # Podlacza obsluge klawiatury i rozpoczyna otwieranie arkusza.
    def on_open(self):
        self._sheet_kb_bound = False
        self._sheet_bind_keyboard()
        self._enable_resize_softinput()
        self.panel.y = -dp(500)
        Clock.schedule_once(self._open_start, 0)

    # Wysuwa panel z dolu ekranu i po chwili ustawia focus na polu nazwy kroku.
    def _open_start(self, _dt):
        self._apply_sheet_layout(False)
        target_y = self.panel.y
        self.panel.y = -self.panel.height
        Animation(y=target_y, d=0.28, t="out_cubic").start(self.panel)
        Clock.schedule_once(self._request_focus, 0.35)

    # Dopasowuje szerokosc panelu po zmianie rozmiaru okna.
    def on_size(self, *_):
        if self.panel is not None and self.parent is not None:
            self.panel.width = self.width
            self._sync_modal_height()
            self._schedule_keyboard_relayout(False)

    # Ustawia kursor w polu nazwy kroku, zeby uzytkownik mogl od razu pisac.
    def _request_focus(self, _dt):
        self.name_field.focus = True
        self._schedule_keyboard_relayout(True)
        if self.name_field.text:
            self.name_field.cursor = (len(self.name_field.text), 0)

    # Nadpisuje metodę z domieszki: oryginalna klasa sprawdza tylko kilka ustalonych nazw.
    #
    # My mamy dodatkowo name_field oraz dynamiczną listę _PodkrokEditorRow,
    # z których każdy ma własne pole .field. Jeśli któreś z nich jest
    # aktywne, arkusz powinien unieść się nad klawiaturę.
    def _sheet_input_focused(self):
        if getattr(self, "name_field", None) is not None and self.name_field.focus:
            return True
        box = getattr(self, "_podkrok_box", None)
        if box is not None:
            for row in box.children:
                field = getattr(row, "field", None)
                if field is not None and getattr(field, "focus", False):
                    return True
        return False

    # --- Commit / delete ---

    def _collect_children(self):
        out = []
        rows = [
            w for w in reversed(self._podkrok_box.children)
            if isinstance(w, _PodkrokEditorRow)
        ]
        for row in rows:
            text = (row.field.text or "").strip()
            if not text:
                continue
            out.append({"text": text, "done": bool(row.done_state)})
        return out

    # Zapisuje krok (z nazwa i lista podkrokow) do projektu i zamyka arkusz.
    def _commit_and_close(self):
        name = (self.name_field.text or "").strip()
        children = self._collect_children()
        if not name:
            if self.item_index is None:
                self.dismiss()
                return
            name = "Krok"
        if self.item_index is None:
            self.project_screen.create_etapy_step(
                self.group_index, name, children
            )
        else:
            self.project_screen.update_etapy_step(
                self.group_index, self.item_index, name, children
            )
        self.dismiss()

    # Usuwa krok z projektu i zamyka arkusz.
    def _delete_and_close(self):
        if self.item_index is not None:
            self.project_screen.delete_etapy_step(self.group_index, self.item_index)
        self.dismiss()

    # Zamyka arkusz z animacja - zsuwa panel w dol, czysci focus i wylacza klawiature.
    def dismiss(self, *largs):
        if self._closing:
            return
        self._closing = True
        self._sheet_unbind_keyboard()
        self.name_field.focus = False
        for row in list(self._podkrok_box.children):
            if isinstance(row, _PodkrokEditorRow):
                row.field.focus = False
        h = max(self.panel.height, dp(1))
        anim = Animation(y=-h, d=0.22, t="in_cubic")
        anim.bind(on_complete=lambda *a: super(EditEtapyKrokBottomSheet, self).dismiss())
        anim.start(self.panel)


# Dotknięcie treści notatki = edycja; × po prawej = usuwanie.
class ProjectNoteRow(MDBoxLayout):

    tall = BooleanProperty(False)
    display_text = StringProperty("")
    parent_screen = ObjectProperty(None, allownone=True)

    NOTE_SCROLL_MAX = dp(280)

    # Przygotowuje wiersz notatki - ustawia odstepy i podlacza automatyczne przeliczanie ukladu.
    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(10))
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.bind(display_text=self._schedule_layout)
        self.bind(tall=self._schedule_layout)
        self.bind(width=self._schedule_layout)

    # Zwraca unikalny klucz do rozpoznawania dotkniec na tym wierszu.
    def _touch_key(self):
        return "_pnr_%d" % id(self)

    # Sprawdza, czy uzytkownik dotknal tego wiersza - zapamietuje miejsce dotkniecia.
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if "delete_btn" in self.ids and self.ids.delete_btn.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if super().on_touch_down(touch):
            return True
        if "note_scroll" in self.ids and self.ids.note_scroll.collide_point(*touch.pos):
            touch.ud[self._touch_key()] = touch.pos
        return False

    # Sprawdza, czy uzytkownik puscil dotkniecie w tym samym miejscu (krotkie klikniecie). Jesli tak, otwiera edytor notatki.
    def on_touch_up(self, touch):
        if super().on_touch_up(touch):
            return True
        key = self._touch_key()
        start = touch.ud.pop(key, None)
        if start and self.collide_point(*touch.pos):
            if "delete_btn" in self.ids and self.ids.delete_btn.collide_point(*touch.pos):
                return False
            dx = touch.pos[0] - start[0]
            dy = touch.pos[1] - start[1]
            if dx * dx + dy * dy < dp(14) ** 2:
                self.open_edit_from_row()
                return True
        return False

    # Usuwa te notatke z projektu.
    def request_delete(self, *_args):
        scr = self.parent_screen
        if scr is None:
            w = self.parent
            while w is not None:
                if isinstance(w, ProjectInfoScreen):
                    scr = w
                    break
                w = w.parent
        if scr is not None:
            scr.remove_note_row(self)

    # Wywolywane po utworzeniu widoku - podlacza przeliczanie ukladu i obsluge przycisku usuwania.
    def on_kv_post(self, base_widget):
        self.ids.note_scroll.bind(width=self._schedule_layout)
        self.ids.note_label.bind(texture_size=self._schedule_layout)
        self.ids.delete_btn.bind(on_press=lambda *_a: self.request_delete())
        Clock.schedule_once(self._sync_note_layout, 0)

    # Planuje przeliczenie ukladu notatki przy najblizszej okazji.
    def _schedule_layout(self, *args):
        Clock.schedule_once(self._sync_note_layout, 0)

    # Przelicza wysokosc wiersza notatki na podstawie dlugosci tekstu i szerokosci ekranu.
    def _sync_note_layout(self, *args):
        sc = self.ids.note_scroll
        lbl = self.ids.note_label
        aw = max(self.width - dp(74), sc.width - dp(16), sp(20))
        if aw <= sp(20) or self.width <= 1:
            Clock.schedule_once(self._sync_note_layout, 0.05)
            return
        lbl.text_size = (aw, None)
        lbl.texture_update()
        content_h = lbl.texture_size[1] + dp(24)
        cap = self.NOTE_SCROLL_MAX + dp(24)
        self.height = max(dp(52), min(cap, max(dp(48), content_h)))

    # Otwiera edytor notatki (arkusz edycyjny) dla tego wiersza.
    def open_edit_from_row(self):
        scr = self.parent_screen
        if scr:
            scr.open_edit_note_sheet(self)


# Klikalny samochodzik. Zwykły Image, żeby RelativeLayout na pasku mógł go przesuwać przez pos_hint center_x.
class CarProgressButton(ButtonBehavior, Image):

    # Przygotowuje klikalny obrazek samochodzika - ustawia jego rozmiar i dopasowanie.
    def __init__(self, **kwargs):
        kwargs.setdefault("nocache", True)
        kwargs.setdefault("allow_stretch", True)
        kwargs.setdefault("keep_ratio", True)
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        if hasattr(self, "fit_mode"):
            self.fit_mode = "contain"


# Pasek celu czasowego: dotknięcie samochodzika = start/pauza; × po prawej = usuwanie.
class TimeGoalTrackRow(MDBoxLayout):

    title_text = StringProperty("")
    goal_text = StringProperty("")
    goal_target_seconds = NumericProperty(3600.0)
    logged_seconds = NumericProperty(0.0)
    tracking_active = BooleanProperty(False)
    car_hint_x = NumericProperty(0.08)
    car_scale_x = NumericProperty(1.0)
    percent_text = StringProperty("0%")
    is_goal_complete = BooleanProperty(False)
    percent_card_color = ListProperty(_GOAL_CARD_PURPLE)
    crown_source = StringProperty(_CROWN_EMOJI_PATH)
    elapsed_text = StringProperty("")
    reset_mode = StringProperty(RESET_WEEKLY)
    period_key = StringProperty("")
    active_uid = StringProperty("")
    car_source_idle = StringProperty(_car_asset_path("ZZzz 1.png"))
    car_source_active = StringProperty(_car_asset_path("CCcc 1.png"))
    parent_screen = ObjectProperty(None, allownone=True)
    geofence = ObjectProperty({})

    _tick_ev = None
    _caption_scheduled = False
    _has_reached_goal = False
    _overflow_cx = None
    _overflow_dir = -1

    # Wywolywane po utworzeniu widoku - podlacza aktualizacje wygladu i obsluge przycisku usuwania.
    def on_kv_post(self, base_widget):
        self.fbind("title_text", self._schedule_goal_caption_refresh)
        self.fbind("goal_text", self._schedule_goal_caption_refresh)
        self.fbind("width", self._schedule_goal_caption_refresh)
        self.fbind("width", lambda *a: self.apply_logged_to_ui())
        track = self.ids.get("goal_track")
        if track is not None:
            track.fbind("width", lambda *a: self.apply_logged_to_ui())
        if "delete_btn" in self.ids:
            self.ids.delete_btn.bind(on_press=lambda *_a: self.request_delete())
        Clock.schedule_once(self._bind_caption_box_width, 0)
        Clock.schedule_once(self._refresh_goal_caption_layout, 0)

    # Zatrzymuje pomiar czasu i usuwa ten cel czasowy z projektu.
    def request_delete(self, *_args):
        self.stop_tracking()
        scr = self.parent_screen
        if scr is None:
            w = self.parent
            while w is not None:
                if isinstance(w, ProjectInfoScreen):
                    scr = w
                    break
                w = w.parent
        if scr is not None:
            scr.remove_time_goal_row(self)

    # Podlacza funkcje przeliczania ukladu do zmiany szerokosci kontenera z tytulem.
    def _bind_caption_box_width(self, *args):
        box = self.ids.get("goal_caption_box")
        if box is not None:
            box.fbind("width", self._schedule_goal_caption_refresh)

    # Planuje odswiezenie ukladu tytulu i okresu celu przy najblizszej okazji.
    def _schedule_goal_caption_refresh(self, *args):
        if self._caption_scheduled:
            return
        self._caption_scheduled = True
        Clock.schedule_once(self._refresh_goal_caption_layout, 0)

    # Przelicza uklad tytulu i okresu celu, zeby oba teksty ladnie miescily sie obok siebie.
    def _refresh_goal_caption_layout(self, *args):
        self._caption_scheduled = False
        if "goal_title_lbl" not in self.ids or "goal_period_lbl" not in self.ids:
            return
        title_lbl = self.ids.goal_title_lbl
        period_lbl = self.ids.goal_period_lbl
        box = self.ids.goal_caption_box
        inner_w = box.width - box.padding[0] - box.padding[2] - box.spacing
        if inner_w <= 1:
            Clock.schedule_once(self._refresh_goal_caption_layout, 0.08)
            return
        period_lbl.text_size = (None, None)
        period_lbl.texture_update()
        pw = max(dp(44), min(inner_w * 0.42, period_lbl.texture_size[0] + dp(10)))
        period_lbl.width = pw
        period_lbl.text_size = (pw, None)
        tw = max(sp(16), inner_w - pw)
        title_lbl.text_size = (tw, None)

    # Sprawdza, czy okres (tydzien/miesiac) sie zmienil - jesli tak, zeruje licznik i zaczyna od nowa.
    def _ensure_period(self):
        if self.reset_mode == RESET_NEVER:
            if not self.period_key:
                self.period_key = "all"
            return
        cur = current_period_key(self.reset_mode)
        if not self.period_key:
            self.period_key = cur
            return
        if self.period_key != cur:
            self.logged_seconds = 0.0
            self.period_key = cur
            self._has_reached_goal = False
            self._overflow_cx = None
            self._overflow_dir = -1
            if self.tracking_active and self.active_uid:
                project_title = self.parent_screen.project_title if self.parent_screen else ""
                project_uid = self.parent_screen.project_uid if self.parent_screen else ""
                active_timer.start_goal(
                    self.active_uid,
                    project_title,
                    self.title_text,
                    self.goal_text,
                    self.goal_target_seconds,
                    base_logged_seconds=0.0,
                    reset_mode=self.reset_mode,
                    period_key=self.period_key,
                    project_uid=project_uid,
                )

    # Aktualizuje wyglad paska na podstawie zapisanego czasu - przelicza procent i pozycje samochodzika.
    def apply_logged_to_ui(self):
        t = max(10.0, float(self.goal_target_seconds))
        if float(self.logged_seconds) >= t:
            self._has_reached_goal = True
        self._update_progress_from_time(0)

    # Zwraca szerokosc paska postepu w pikselach.
    def _track_width(self):
        track = self.ids.get("goal_track")
        if track is not None and track.width > 1:
            return float(track.width)
        return max(dp(160), float(self.width or 300) - dp(58))

    # Oblicza granice "drogi" dla samochodzika - gdzie moze sie przesuwac w lewo i prawo.
    def _road_bounds(self):
        tw = self._track_width()
        road_start = float(dp(8))
        road_end = max(road_start + dp(96), tw - float(dp(8)))
        car_w = float(dp(96))
        half = car_w * 0.5
        min_cx = road_start + half
        max_cx = max(min_cx, road_end - half)
        return tw, min_cx, max_cx

    # Taka sama liczba px/s jak przy postępie 0→100%: pełna długość paska na docelowy czas.
    def _car_travel_speed(self, min_cx, max_cx):
        span = max(1.0, max_cx - min_cx)
        duration = max(10.0, float(self.goal_target_seconds))
        return span / duration

    # Po osiągnięciu 100%: samochodzik jeździ w lewo i prawo; odwraca się na każdym końcu.
    def _advance_overflow_car(self, min_cx, max_cx, dt):
        if self._overflow_cx is None:
            self._overflow_cx = max_cx
            self._overflow_dir = -1
        speed = self._car_travel_speed(min_cx, max_cx)
        self._overflow_cx += self._overflow_dir * speed * max(float(dt), 0.0)
        if self._overflow_cx >= max_cx:
            self._overflow_cx = max_cx
            self._overflow_dir = -1
        elif self._overflow_cx <= min_cx:
            self._overflow_cx = min_cx
            self._overflow_dir = 1
        self.car_scale_x = -1.0 if self._overflow_dir < 0 else 1.0
        return self._overflow_cx

    # Przelicza postep celu na procenty, aktualizuje tekst i przesuwa samochodzik na pasku.
    def _update_progress_from_time(self, dt=0):
        self._ensure_period()
        t = max(10.0, float(self.goal_target_seconds))
        p_raw = 100.0 * float(self.logged_seconds) / t
        pct_int = int(round(p_raw))
        self.percent_text = f"{pct_int}%"

        if pct_int >= 100:
            self._has_reached_goal = True
        self.is_goal_complete = self._has_reached_goal
        self.percent_card_color = _GOAL_CARD_GREEN if self._has_reached_goal else _GOAL_CARD_PURPLE

        tw, min_cx, max_cx = self._road_bounds()

        if self.tracking_active and self._has_reached_goal:
            cx = self._advance_overflow_car(min_cx, max_cx, dt)
        elif self._overflow_cx is not None:
            cx = self._overflow_cx
            self.car_scale_x = -1.0 if self._overflow_dir < 0 else 1.0
        else:
            self.car_scale_x = 1.0
            p_track = min(100.0, p_raw)
            cx = min_cx + (p_track / 100.0) * (max_cx - min_cx)

        self.car_hint_x = cx / tw if tw > 0 else 0.5
        self.elapsed_text = format_goal_elapsed(self.logged_seconds) if self.logged_seconds >= 1 else ""

    # Wywolywane po kliknieciu samochodzika - przelacza miedzy startem a zatrzymaniem pomiaru czasu.
    def on_car_button_release(self, *args):
        if self.tracking_active:
            self.stop_tracking()
        else:
            self.start_tracking()

    # Rozpoczyna pomiar czasu dla tego celu. Uruchamia licznik w tle.
    def start_tracking(self):
        if self._tick_ev is not None:
            return
        if not self.active_uid:
            self.active_uid = f"goal-{uuid.uuid4().hex}"
        self._ensure_period()
        project_title = self.parent_screen.project_title if self.parent_screen else ""
        project_uid = self.parent_screen.project_uid if self.parent_screen else ""
        active_timer.start_goal(
            self.active_uid,
            project_title,
            self.title_text,
            self.goal_text,
            self.goal_target_seconds,
            base_logged_seconds=self.logged_seconds,
            reset_mode=self.reset_mode,
            period_key=self.period_key,
            project_uid=project_uid,
        )
        if self.parent_screen:
            self.parent_screen.save_project_content()
        ensure_android_timer_service()
        self.tracking_active = True
        self._tick_ev = Clock.schedule_interval(self._on_track_tick, 0.05)

    # Zatrzymuje pomiar czasu dla tego celu. Odczytuje koncowy wynik z licznika.
    def stop_tracking(self, update_active=True):
        state = active_timer.read_goal(self.active_uid) if self.active_uid else {}
        if state:
            self.logged_seconds = float(state.get("base_logged_seconds", 0.0)) + float(
                active_timer.running_seconds(state)
            )
        if self._tick_ev is not None:
            self._tick_ev.cancel()
            self._tick_ev = None
        self.tracking_active = False
        self._update_progress_from_time(0)
        if update_active and self.active_uid:
            active_timer.remove_goal(self.active_uid)
            if self.parent_screen:
                self.parent_screen.save_project_content()

    # Przywraca pomiar czasu po ponownym uruchomieniu aplikacji.
    def restore_tracking_from_state(self, goal_state):
        if not goal_state:
            return
        self.active_uid = goal_state.get("uid", self.active_uid)
        self.logged_seconds = float(goal_state.get("base_logged_seconds", 0.0)) + float(
            active_timer.running_seconds(goal_state)
        )
        self._ensure_period()
        self.tracking_active = True
        if self._tick_ev is not None:
            self._tick_ev.cancel()
        self._tick_ev = Clock.schedule_interval(self._on_track_tick, 0.05)
        self._update_progress_from_time(0)

    # Wywolywane co 0.05 sekundy podczas pomiaru - odczytuje aktualny czas z licznika.
    def _on_track_tick(self, dt):
        state = active_timer.read_goal(self.active_uid) if self.active_uid else {}
        if state:
            self.logged_seconds = float(state.get("base_logged_seconds", 0.0)) + float(
                active_timer.running_seconds(state)
            )
        elif self.tracking_active:
            self.tracking_active = False
            if self._tick_ev is not None:
                self._tick_ev.cancel()
                self._tick_ev = None
            if self.parent_screen:
                self.parent_screen.load_project_content()
                self.parent_screen._restore_active_runtime()
            return
        else:
            self.logged_seconds += float(dt)
        self._ensure_period()
        self._update_progress_from_time(dt)

    # Gdy wiersz celu zostaje usuniety z ekranu (parent = None), zatrzymuje pomiar czasu.
    def on_parent(self, *_args):
        if self.parent is None:
            loading = bool(self.parent_screen and getattr(self.parent_screen, "_loading_project_content", False))
            self.stop_tracking(update_active=not loading)
