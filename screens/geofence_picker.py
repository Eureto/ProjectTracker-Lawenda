"""Full-screen map picker for selecting a time-goal geofence (center + radius).

The map center is always the geofence center; the user pans the map to place
the circle and zooms to size it. The visual circle is a fixed fraction of the
map viewport, so the radius (in meters) is determined entirely by the current
zoom level. Hard-capped at 1000 m.

When `kivy_garden.mapview` is not installed (desktop dev without the optional
dep), the screen renders a fallback message so the rest of the app still works.

Caller protocol:
    picker = MDApp.get_running_app().root.get_screen("geofence_picker")
    picker.configure(
        initial_lat=lat, initial_lon=lon, initial_radius_m=100.0,
        return_screen="project_info",
        on_done=lambda result: ...
    )
    MDApp.get_running_app().root.current = "geofence_picker"

`on_done(result)` is called exactly once when the user leaves the picker.
``result`` is a dict with an `action` field:
    {"action": "save",   "geofence": {"lat": ..., "lon": ..., "radius_m": ..., "zoom": ...}}
    {"action": "clear"}    # user wants no geofence
    {"action": "cancel"}   # user backed out, leave existing value untouched
"""

import math

from kivy.clock import Clock
from kivy.logger import Logger
from kivy.metrics import dp, sp


def _log(message):
    """Single-line tagged logcat/Kivy log emitter for the geofence picker."""
    try:
        Logger.info("GeofencePicker: %s", message)
    except Exception:
        pass
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex, platform
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, Ellipse, Line
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.screen import MDScreen

# Shared rounded action button used across all bottom sheets and dialogs so
# this picker matches the rest of the app visually.
from screens.project_info import RoundedSheetButton


class _TapAnchor(ButtonBehavior, AnchorLayout):
    """Tappable AnchorLayout — Python-side equivalent of the
    ``ClickableAnchorLayout`` factory class defined in ``addProject.kv``,
    so we don't have to depend on KV loading order from a Python-built
    screen."""

    pass

try:
    from kivy_garden.mapview import MapView
    _MAPVIEW_AVAILABLE = True
    _MAPVIEW_IMPORT_ERROR = None
except Exception as _exc:  # noqa: BLE001 - we surface the message in the UI
    MapView = None  # type: ignore[assignment]
    _MAPVIEW_AVAILABLE = False
    _MAPVIEW_IMPORT_ERROR = repr(_exc)


if _MAPVIEW_AVAILABLE:

    class _SmoothMapView(MapView):
        """MapView with truly continuous (non-snapping) pinch zoom.

        Upstream ``kivy_garden.mapview.MapView`` animates back to the nearest
        integer zoom level when the user lifts the last finger after a pinch
        (see ``on_touch_up`` in ``view.py``), regardless of ``snap_to_zoom``.
        That makes it impossible to stop the pinch at an intermediate zoom
        level — which is exactly what the user wants.

        We override ``on_touch_up`` to perform mapview's bookkeeping (ungrab
        + decrement ``_touch_count`` + clear ``_pause``) but *not* trigger
        the snap-back animation. The result: pinch zoom rests at exactly the
        scale/zoom the user released at, and pan/scroll/double-tap all keep
        working normally.
        """

        def on_touch_up(self, touch):
            if touch.grab_current == self:
                touch.ungrab(self)
                self._touch_count = max(0, self._touch_count - 1)
                if self._touch_count == 0:
                    self._pause = False
                return True
            # Not grabbed by us — fall through to default dispatch so
            # children (e.g. internal scatter) still see the event.
            return Widget.on_touch_up(self, touch)

    # Keep the previous name working so the rest of the module needs no
    # changes.
    _StableMapView = _SmoothMapView

else:
    _StableMapView = None  # type: ignore[assignment]


class _TouchBarrierBox(MDBoxLayout):
    """MDBoxLayout that blocks touches inside its bounds from reaching widgets
    beneath it. Children still receive events normally."""

    def on_touch_down(self, touch):
        handled = super().on_touch_down(touch)
        if handled:
            return True
        if self.collide_point(*touch.pos):
            return True
        return False

    def on_touch_move(self, touch):
        handled = super().on_touch_move(touch)
        if handled:
            return True
        if self.collide_point(*touch.pos):
            return True
        return False

    def on_touch_up(self, touch):
        handled = super().on_touch_up(touch)
        if handled:
            return True
        if self.collide_point(*touch.pos):
            return True
        return False


# Warsaw fallback so the map at least shows tiles before we know the user's
# location.
_DEFAULT_LAT = 52.2297
_DEFAULT_LON = 21.0122
_DEFAULT_ZOOM = 17  # ≈100 m radius at the default viewport fraction
_DEFAULT_RADIUS_M = 100.0
_MAX_RADIUS_M = 1000.0

# Diameter of the on-screen circle as a fraction of the shorter map edge.
# 1.0 means the circle visually spans the full width of the map on portrait
# screens. Radius in meters is derived from this pixel diameter and the
# current zoom/lat, so changing the zoom is how the user picks the area
# size; the 1000 m cap clamps the radius (and shrinks the visual circle)
# at low zoom levels.
_VIEWPORT_FRACTION = 1.0

# Soft bounds; mapview's source maxes out around 19.
_MIN_ZOOM = 12.0
_MAX_ZOOM = 19.0


def _meters_per_pixel(lat_deg, zoom):
    """Web Mercator meters/pixel at the given latitude and zoom level."""
    return 156543.03392 * math.cos(lat_deg * math.pi / 180.0) / (2.0 ** float(zoom))


def _zoom_for_radius(radius_m, lat_deg, viewport_short_px):
    """Inverse of the radius-from-zoom mapping; used only when re-opening
    the picker with a previously saved radius but no zoom."""
    if radius_m <= 0 or viewport_short_px <= 0:
        return _DEFAULT_ZOOM
    visual_d = viewport_short_px * _VIEWPORT_FRACTION
    if visual_d <= 0:
        return _DEFAULT_ZOOM
    target_mpp = (2.0 * radius_m) / visual_d
    base = 156543.03392 * math.cos(lat_deg * math.pi / 180.0)
    if target_mpp <= 0 or base <= 0:
        return _DEFAULT_ZOOM
    return max(_MIN_ZOOM, min(_MAX_ZOOM, math.log2(base / target_mpp)))


def _effective_zoom(mapview):
    """Read a smooth zoom value from MapView, honoring its internal scale."""
    z = float(getattr(mapview, "zoom", _DEFAULT_ZOOM))
    scale = getattr(mapview, "scale", None)
    if scale is None or float(scale) <= 0:
        return z
    try:
        return z + math.log2(float(scale))
    except (ValueError, TypeError):
        return z


class GeofenceCircleOverlay(Widget):
    """Translucent ring centered on the parent widget; size set externally.

    Explicitly forwards all touch events so the underlying MapView still
    receives pan/zoom gestures unobstructed.
    """

    ring_color = ObjectProperty((0.55, 0.31, 0.78, 1.0))
    fill_color = ObjectProperty((0.55, 0.31, 0.78, 0.18))
    diameter_px = NumericProperty(dp(120))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, 1)
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            ring_color=self._redraw,
            fill_color=self._redraw,
            diameter_px=self._redraw,
        )

    # Never consume touches — let the map handle pan/zoom.
    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False

    def _redraw(self, *_args):
        self.canvas.clear()
        if self.width < 1 or self.height < 1 or self.diameter_px < 2:
            return
        d = min(float(self.diameter_px), min(self.width, self.height) - dp(4))
        d = max(d, dp(8))
        cx = self.center_x
        cy = self.center_y
        with self.canvas:
            Color(*self.fill_color)
            Ellipse(pos=(cx - d / 2.0, cy - d / 2.0), size=(d, d))
            Color(*self.ring_color)
            Line(circle=(cx, cy, d / 2.0), width=dp(2))
            # Center crosshair dot.
            Color(1, 1, 1, 0.95)
            Ellipse(pos=(cx - dp(4), cy - dp(4)), size=(dp(8), dp(8)))
            Color(*self.ring_color)
            Line(circle=(cx, cy, dp(4)), width=dp(1.2))


class GeofencePickerScreen(MDScreen):
    """Map screen for picking a geofence center + radius for a time goal."""

    return_screen = StringProperty("home")
    radius_text = StringProperty(f"{int(_DEFAULT_RADIUS_M)} m")

    _on_done = None  # callback(result_dict)
    _initial_lat = _DEFAULT_LAT
    _initial_lon = _DEFAULT_LON
    _initial_zoom = float(_DEFAULT_ZOOM)
    _initial_radius_m = _DEFAULT_RADIUS_M
    _initial_zoom_explicit = False
    _initial_location_explicit = False
    _gps_started = False
    _location_acquired = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.md_bg_color = get_color_from_hex("#8A2BE2")
        self._mapview = None
        self._overlay = None
        self._radius_label = None
        self._build_ui()

    # --- Public API -----------------------------------------------------

    def configure(
        self,
        initial_lat=None,
        initial_lon=None,
        initial_radius_m=None,
        initial_zoom=None,
        return_screen="project_info",
        on_done=None,
    ):
        """Set the next-open state. Call BEFORE switching screens."""
        self._initial_location_explicit = (
            initial_lat is not None and initial_lon is not None
        )
        self._initial_lat = float(initial_lat) if initial_lat is not None else _DEFAULT_LAT
        self._initial_lon = float(initial_lon) if initial_lon is not None else _DEFAULT_LON
        self._initial_radius_m = (
            float(initial_radius_m)
            if initial_radius_m is not None
            else _DEFAULT_RADIUS_M
        )
        if initial_zoom is not None:
            self._initial_zoom = float(initial_zoom)
            self._initial_zoom_explicit = True
        else:
            self._initial_zoom = float(_DEFAULT_ZOOM)
            self._initial_zoom_explicit = False
        self.return_screen = return_screen or "project_info"
        self._on_done = on_done
        self._location_acquired = False

    # --- Lifecycle ------------------------------------------------------

    def on_pre_enter(self, *_args):
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            self._kickoff_location_acquisition()
            return
        # Determine the starting zoom: prefer explicit one, otherwise derive
        # from the previously saved radius once we know the viewport size.
        target_zoom = self._initial_zoom
        if not self._initial_zoom_explicit:
            short_px = min(self._mapview.width, self._mapview.height)
            if short_px > 1:
                target_zoom = _zoom_for_radius(
                    self._initial_radius_m, self._initial_lat, short_px
                )
        self._set_smooth_zoom(target_zoom)
        # Use center_on rather than assigning lat/lon directly: assigning the
        # properties does not recompute the viewport offsets, so the view
        # stays wherever it last was. center_on() sets delta_x/delta_y and
        # resets the scatter, which is what actually moves the visible map.
        self._center_map_on(self._initial_lat, self._initial_lon)
        Clock.schedule_once(lambda _dt: self._refresh_overlay(), 0)
        # If the picker was opened without an existing geofence, try to
        # auto-center on the device's current location.
        self._kickoff_location_acquisition()

    def on_leave(self, *_args):
        self._stop_gps()

    # --- Current-location acquisition ----------------------------------

    def _kickoff_location_acquisition(self):
        """If no saved geofence was provided, request the device location and
        recenter the map on the first GPS fix. No-op when a saved location
        was passed in or when plyer/GPS isn't usable on this platform."""
        if self._initial_location_explicit:
            _log("skip GPS bootstrap (geofence already saved)")
            self._set_status("")
            return
        self._set_status("Lokalizuję...")
        if platform == "android":
            _log("requesting location permissions on Android")
            self._request_location_permission_then_start()
        else:
            _log(f"non-Android platform ({platform!r}); trying plyer.gps directly")
            Clock.schedule_once(lambda _dt: self._start_gps(), 0)

    def _request_location_permission_then_start(self):
        used_callback = False
        try:
            from android.permissions import Permission, request_permissions

            def _cb(perms, results):
                _log(f"permission callback: perms={list(perms)} results={list(results)}")
                if results and any(results):
                    Clock.schedule_once(lambda _dt: self._start_gps(), 0)
                else:
                    Clock.schedule_once(
                        lambda _dt: self._set_status("Brak uprawnień GPS"),
                        0,
                    )

            request_permissions(
                [
                    Permission.ACCESS_FINE_LOCATION,
                    Permission.ACCESS_COARSE_LOCATION,
                ],
                _cb,
            )
            used_callback = True
            _log("request_permissions called with callback")
        except Exception as exc:
            _log(f"request_permissions with callback failed: {exc!r}")
        if not used_callback:
            try:
                from android.permissions import (
                    Permission,
                    request_permissions,
                )

                request_permissions(
                    [
                        Permission.ACCESS_FINE_LOCATION,
                        Permission.ACCESS_COARSE_LOCATION,
                    ]
                )
                _log("request_permissions (no callback) succeeded")
            except Exception as exc:
                _log(f"request_permissions (no callback) failed: {exc!r}")
            # Try to start GPS anyway — permissions may already be granted
            # from a previous session.
            Clock.schedule_once(lambda _dt: self._start_gps(), 0)

    def _start_gps(self):
        if self._gps_started or self._location_acquired:
            _log("skip _start_gps (already started or fix acquired)")
            return
        if self._initial_location_explicit:
            return
        try:
            from plyer import gps
        except Exception as exc:
            _log(f"plyer import failed: {exc!r}")
            self._set_status("Brak GPS (plyer)")
            return

        try:
            gps.configure(
                on_location=self._on_gps_location,
                on_status=self._on_gps_status,
            )
            gps.start(minTime=1000, minDistance=0)
            self._gps_started = True
            _log("plyer.gps started (requesting location updates)")
        except NotImplementedError as exc:
            _log(f"plyer.gps not implemented on this platform: {exc!r}")
            self._set_status("GPS niedostępny na tej platformie")
        except Exception as exc:
            _log(f"plyer.gps start failed: {exc!r}")
            self._set_status(f"Błąd GPS: {exc!r}")

    def _stop_gps(self):
        if not self._gps_started:
            return
        try:
            from plyer import gps

            gps.stop()
            _log("plyer.gps stopped")
        except Exception as exc:
            _log(f"plyer.gps stop failed: {exc!r}")
        self._gps_started = False

    def _on_gps_status(self, status_type, status_message):
        _log(f"gps status: {status_type} {status_message}")

    def _on_gps_location(self, **kwargs):
        lat = kwargs.get("lat")
        lon = kwargs.get("lon")
        _log(f"gps fix: lat={lat} lon={lon} acc={kwargs.get('accuracy')}")
        if lat is None or lon is None:
            return
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return
        Clock.schedule_once(lambda _dt: self._apply_user_location(lat_f, lon_f), 0)

    def _apply_user_location(self, lat, lon):
        if self._location_acquired or self._initial_location_explicit:
            self._stop_gps()
            return
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return
        self._location_acquired = True
        moved = self._center_map_on(lat, lon)
        if moved:
            _log(f"centered map on user location: {lat}, {lon}")
        self._refresh_overlay()
        self._set_status("")
        # One fix is enough — release the GPS hardware.
        self._stop_gps()

    def _center_map_on(self, lat, lon):
        """Move the visible map center to (lat, lon).

        Setting ``mapview.lat`` / ``mapview.lon`` directly only updates the
        properties — it does NOT recompute the viewport offsets, so the
        rendered map stays where it was. ``MapView.center_on(lat, lon)``
        does the right thing (sets delta_x/delta_y, resets scatter pos,
        then assigns lat/lon).

        The map may not be fully laid out yet on the very first enter; in
        that case ``center_on`` is a no-op for the visual, so we retry on
        the next frame.
        """
        mv = self._mapview
        if mv is None:
            return False
        try:
            mv.center_on(float(lat), float(lon))
        except Exception as exc:
            _log(f"center_on failed: {exc!r}")
            return False
        # If width/height aren't set yet, center_on math is degenerate; try
        # again once the layout completes.
        if mv.width <= 1 or mv.height <= 1:
            Clock.schedule_once(
                lambda _dt: self._retry_center_map_on(lat, lon), 0
            )
        return True

    def _retry_center_map_on(self, lat, lon):
        mv = self._mapview
        if mv is None or mv.width <= 1 or mv.height <= 1:
            # Still not laid out; try once more next frame.
            Clock.schedule_once(
                lambda _dt: self._retry_center_map_on(lat, lon), 0
            )
            return
        try:
            mv.center_on(float(lat), float(lon))
            self._refresh_overlay()
        except Exception as exc:
            _log(f"retry center_on failed: {exc!r}")

    def _set_status(self, text):
        """Update the small status line in the bottom panel (creates it
        on first call). Safe to call from the main thread only."""
        if getattr(self, "_status_lbl", None) is None:
            return
        self._status_lbl.text = text or ""
        self._status_lbl.opacity = 1.0 if text else 0.0

    # --- UI construction -----------------------------------------------

    def _build_ui(self):
        root = FloatLayout()

        if _MAPVIEW_AVAILABLE:
            self._mapview = _StableMapView(
                lat=self._initial_lat,
                lon=self._initial_lon,
                zoom=int(round(self._initial_zoom)),
                size_hint=(1, 1),
                pos_hint={"x": 0, "y": 0},
            )
            # Smooth (fractional) zoom on assignment; suppress accidental
            # tap-to-zoom; keep tile rendering live during gestures.
            self._safe_set(self._mapview, "snap_to_zoom", False)
            self._safe_set(self._mapview, "double_tap_zoom", False)
            self._safe_set(self._mapview, "pause_on_action", False)
            root.add_widget(self._mapview)
            self._overlay = GeofenceCircleOverlay()
            root.add_widget(self._overlay)
            self._mapview.bind(
                lat=lambda *_a: self._refresh_overlay(),
                lon=lambda *_a: self._refresh_overlay(),
                zoom=lambda *_a: self._refresh_overlay(),
                size=lambda *_a: self._refresh_overlay(),
            )
            # mapview.scale is a Python @property, not a Kivy property — bind
            # to the inner Scatter's bindable scale/pos so the overlay tracks
            # fractional zoom changes from diff_scale_at().
            scatter = getattr(self._mapview, "_scatter", None)
            if scatter is not None:
                try:
                    scatter.bind(
                        scale=lambda *_a: self._refresh_overlay(),
                        pos=lambda *_a: self._refresh_overlay(),
                    )
                except Exception:
                    pass
        else:
            placeholder = MDLabel(
                text=(
                    "Mapa nie jest dostępna.\n\n"
                    "Zainstaluj pakiet kivy_garden.mapview, aby wybrać "
                    "lokalizację geofence.\n\n"
                    f"(import error: {_MAPVIEW_IMPORT_ERROR})"
                ),
                halign="center",
                valign="middle",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
                pos_hint={"x": 0, "y": 0},
                size_hint=(1, 1),
                padding=(dp(24), dp(24)),
            )
            root.add_widget(placeholder)

        root.add_widget(self._build_header())
        root.add_widget(self._build_bottom_panel())

        self.add_widget(root)

    @staticmethod
    def _safe_set(obj, attr, value):
        try:
            setattr(obj, attr, value)
        except Exception:
            pass

    def _set_smooth_zoom(self, zoom):
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return
        z = max(_MIN_ZOOM, min(_MAX_ZOOM, float(zoom)))
        # MapView's `zoom` is a NumericProperty (often float when
        # snap_to_zoom=False). If the source only supports int, the cast
        # below at least keeps it valid.
        try:
            self._mapview.zoom = z
        except Exception:
            self._mapview.zoom = int(round(z))

    def _build_header(self):
        header = _TouchBarrierBox(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(60),
            pos_hint={"x": 0, "top": 1},
            padding=(0, 0, 0, 0),
            spacing=0,
        )
        header.md_bg_color = (0, 0, 0, 0.35)

        # Same back-affordance as Project Settings / Add Project headers:
        # a tappable anchor with a white chevron-left MDIcon.
        back_anchor = _TapAnchor(
            size_hint_x=None,
            width=dp(56),
            anchor_x="left",
            anchor_y="center",
        )
        back_anchor.add_widget(
            MDIcon(
                icon="chevron-left",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
                font_size=sp(50),
                adaptive_size=True,
            )
        )
        back_anchor.bind(on_release=lambda *_a: self._cancel())
        header.add_widget(back_anchor)

        title = Label(
            text="Wybierz miejsce",
            font_size=sp(20),
            bold=True,
            color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
        )
        title.bind(size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size))
        header.add_widget(title)

        # Spacer that mirrors the back-button width so the title stays
        # centered.
        spacer = Widget(size_hint_x=None, width=dp(56))
        header.add_widget(spacer)

        return header

    def _build_bottom_panel(self):
        panel = _TouchBarrierBox(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(196),
            pos_hint={"x": 0, "y": 0},
            padding=(dp(16), dp(14), dp(16), dp(18)),
            spacing=dp(8),
        )
        panel.md_bg_color = (0, 0, 0, 0.55)

        radius_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(30),
            spacing=dp(10),
        )
        radius_caption = Label(
            text="Promień:",
            font_size=sp(15),
            color=(1, 1, 1, 1),
            size_hint_x=None,
            width=dp(90),
            halign="left",
            valign="middle",
        )
        radius_caption.bind(
            size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size)
        )
        self._radius_label = Label(
            text=self.radius_text,
            font_size=sp(15),
            bold=True,
            color=(1, 1, 1, 1),
            halign="right",
            valign="middle",
        )
        self._radius_label.bind(
            size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size)
        )
        radius_row.add_widget(radius_caption)
        radius_row.add_widget(self._radius_label)
        panel.add_widget(radius_row)

        # Status line — used to surface the GPS bootstrap state so the user
        # can tell whether the app is actively trying to locate them.
        self._status_lbl = Label(
            text="",
            font_size=sp(12),
            color=(1, 1, 1, 0.85),
            size_hint=(1, None),
            height=dp(18),
            halign="left",
            valign="middle",
            opacity=0.0,
        )
        self._status_lbl.bind(
            size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size)
        )
        panel.add_widget(self._status_lbl)

        # Zoom controls — primary way to size the area. Pinch-zoom is
        # disabled on _StableMapView so this is what the user uses. The
        # buttons drive `diff_scale_at` so zoom is continuous (no integer
        # snapping); tap for a small step, press-and-hold for fast smooth
        # zoom.
        zoom_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(40),
            spacing=dp(12),
        )
        btn_zoom_out = self._make_zoom_button("−", direction=-1)
        zoom_row.add_widget(btn_zoom_out)

        hint = Label(
            text="Przybliż/oddal aby ustawić obszar (maks. 1000 m)",
            font_size=sp(12),
            color=(1, 1, 1, 0.85),
            size_hint=(1, 1),
            halign="center",
            valign="middle",
        )
        hint.bind(size=lambda lbl, *_: setattr(lbl, "text_size", lbl.size))
        zoom_row.add_widget(hint)

        btn_zoom_in = self._make_zoom_button("+", direction=1)
        zoom_row.add_widget(btn_zoom_in)
        panel.add_widget(zoom_row)

        button_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(44),
            spacing=dp(12),
        )

        # Theme color used for primary actions across the rest of the app.
        app = MDApp.get_running_app()
        primary_bg = list(
            get_color_from_hex(
                getattr(app, "theme_card_bg", "#B388FF") if app else "#B388FF"
            )
        )

        # Destructive — same red as "Usuń" elsewhere. The header chevron
        # already provides Cancel, so we only need Wyczyść + Zapisz here.
        clear_btn = RoundedSheetButton(
            text="Wyczyść",
            font_size=sp(15),
            size_hint_x=None,
            width=dp(96),
            bg_color=list(get_color_from_hex("#e53935")),
        )
        clear_btn.bind(on_release=lambda *_a: self._clear_and_return())
        button_row.add_widget(clear_btn)

        button_row.add_widget(Widget(size_hint_x=1))

        save_btn = RoundedSheetButton(
            text="Zapisz",
            font_size=sp(15),
            size_hint_x=None,
            width=dp(104),
            bg_color=primary_bg,
        )
        save_btn.bind(on_release=lambda *_a: self._save_and_return())
        button_row.add_widget(save_btn)

        panel.add_widget(button_row)
        return panel

    def _make_zoom_button(self, glyph, direction):
        app = MDApp.get_running_app()
        bg = list(
            get_color_from_hex(
                getattr(app, "theme_card_bg", "#B388FF") if app else "#B388FF"
            )
        )
        btn = RoundedSheetButton(
            text=glyph,
            font_size=sp(22),
            size_hint=(None, 1),
            width=dp(56),
            bg_color=bg,
        )
        # Press-and-hold for continuous smooth zoom; tap for a small step.
        btn.bind(
            on_press=lambda *_a, _d=direction: self._zoom_press_start(_d),
            on_release=lambda *_a: self._zoom_press_stop(),
        )
        return btn

    # Per-tick zoom amount (in "scale octaves"): scatter.scale *= 2**TICK.
    # 60 ticks/sec * 0.035 ≈ 2.1 octaves/sec ≈ 4× zoom per second when held.
    _ZOOM_TICK = 0.035
    # Initial step applied on press for snappy tap response.
    _ZOOM_TAP_STEP = 0.18

    def _zoom_press_start(self, direction):
        """Begin continuous smooth zoom in the given direction (+1 or -1)."""
        # Cancel any in-flight zoom from a previous press.
        self._zoom_press_stop()
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return
        self._zoom_direction = int(1 if direction > 0 else -1)
        # One immediate small step so a quick tap still produces visible zoom.
        self._apply_smooth_zoom_delta(self._zoom_direction * self._ZOOM_TAP_STEP)
        # Then ramp continuously at 60Hz while the button is held.
        self._zoom_clock = Clock.schedule_interval(self._zoom_tick, 1.0 / 60.0)

    def _zoom_tick(self, _dt):
        if (
            not _MAPVIEW_AVAILABLE
            or self._mapview is None
            or getattr(self, "_zoom_direction", 0) == 0
        ):
            return False
        self._apply_smooth_zoom_delta(self._zoom_direction * self._ZOOM_TICK)
        return None  # keep scheduling

    def _zoom_press_stop(self, *_):
        self._zoom_direction = 0
        clk = getattr(self, "_zoom_clock", None)
        if clk is not None:
            try:
                clk.cancel()
            except Exception:
                pass
            self._zoom_clock = None

    def _apply_smooth_zoom_delta(self, d):
        """Apply a fractional zoom delta via the inner Scatter's scale.

        ``d`` is in "octaves" — scatter.scale *= 2**d. mapview's on_transform
        callback automatically promotes/demotes the integer ``zoom`` when
        scale crosses 2.0 or 1.0, so we get truly continuous zoom across
        integer boundaries without touch-up snapping.
        """
        mv = self._mapview
        if mv is None or abs(d) < 1e-6:
            return
        # Don't push beyond our soft cap on either side.
        eff = _effective_zoom(mv)
        if d > 0 and eff >= _MAX_ZOOM:
            return
        if d < 0 and eff <= _MIN_ZOOM:
            return
        cx = mv.center_x
        cy = mv.center_y
        try:
            mv.diff_scale_at(float(d), cx, cy)
        except Exception:
            # Fall back to integer zoom step if the API isn't available.
            try:
                mv.zoom = int(round(float(mv.zoom) + (1 if d > 0 else -1)))
            except Exception:
                pass
        # diff_scale_at may not fire a Kivy property binding we listen to, so
        # refresh the overlay explicitly each step.
        self._refresh_overlay()

    # --- Overlay sizing -------------------------------------------------

    def _current_radius_m(self):
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return _DEFAULT_RADIUS_M
        short_px = min(self._mapview.width, self._mapview.height)
        if short_px <= 1:
            return _DEFAULT_RADIUS_M
        zoom = _effective_zoom(self._mapview)
        lat = float(self._mapview.lat)
        mpp = _meters_per_pixel(lat, zoom)
        if mpp <= 0:
            return _DEFAULT_RADIUS_M
        visual_d_px = short_px * _VIEWPORT_FRACTION
        radius_m = (visual_d_px / 2.0) * mpp
        return max(1.0, min(_MAX_RADIUS_M, radius_m))

    def _refresh_overlay(self):
        if not _MAPVIEW_AVAILABLE or self._mapview is None or self._overlay is None:
            return
        short_px = min(self._mapview.width, self._mapview.height)
        if short_px <= 1:
            return
        zoom = _effective_zoom(self._mapview)
        lat = float(self._mapview.lat)
        mpp = _meters_per_pixel(lat, zoom)
        if mpp <= 0:
            return
        # Target radius from the fixed viewport fraction, then clamp at the
        # 1000 m cap. When clamped, the visual circle shrinks to honor the
        # real cap (so the user sees "you've hit the maximum").
        target_radius_m = (short_px * _VIEWPORT_FRACTION / 2.0) * mpp
        actual_radius_m = max(1.0, min(_MAX_RADIUS_M, target_radius_m))
        diameter_px = max(dp(12), (2.0 * actual_radius_m) / mpp)

        self._overlay.pos = self._mapview.pos
        self._overlay.size = self._mapview.size
        self._overlay.diameter_px = diameter_px

        self.radius_text = f"{int(round(actual_radius_m))} m"
        if self._radius_label is not None:
            self._radius_label.text = self.radius_text

    # --- Save / cancel --------------------------------------------------

    def _current_result(self):
        if not _MAPVIEW_AVAILABLE or self._mapview is None:
            return None
        return {
            "lat": float(self._mapview.lat),
            "lon": float(self._mapview.lon),
            "radius_m": float(self._current_radius_m()),
            "zoom": float(_effective_zoom(self._mapview)),
        }

    def _save_and_return(self):
        gf = self._current_result()
        if gf is None:
            self._finish({"action": "cancel"})
        else:
            self._finish({"action": "save", "geofence": gf})

    def _clear_and_return(self):
        self._finish({"action": "clear"})

    def _cancel(self):
        self._finish({"action": "cancel"})

    def _finish(self, result):
        cb = self._on_done
        self._on_done = None
        try:
            if cb is not None:
                cb(result)
        finally:
            self._navigate_back()

    def _navigate_back(self):
        app = MDApp.get_running_app()
        if app is None or app.root is None:
            return
        target = self.return_screen or "home"
        try:
            app.root.current = target
        except Exception:
            app.root.current = "home"
