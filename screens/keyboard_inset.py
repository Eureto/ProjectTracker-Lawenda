"""Keyboard overlap height for bottom sheets (Android needs extra help beyond Window.keyboard_height)."""

from kivy.core.window import Window
from kivy.metrics import Metrics, dp
from kivy.utils import platform


def keyboard_inset(baseline_window_height=0):
    """
    Return how much space the soft keyboard occupies from the bottom, in Kivy coordinates.
    Uses the largest reliable measurement available (Window, shrink delta, Android JNI).
    """
    values = []

    kh = float(Window.keyboard_height or 0)
    if kh > 0:
        values.append(kh)

    win_h = float(Window.height or 0)
    baseline = float(baseline_window_height or 0)
    if baseline > 0 and win_h > 0:
        shrunk = baseline - win_h
        if shrunk > 0:
            values.append(shrunk)

    if platform == "android":
        android_kh = _android_keyboard_inset()
        if android_kh > 0:
            values.append(android_kh)

    if not values:
        return 0.0
    return max(values)


def _android_keyboard_inset():
    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        m_activity = PythonActivity.mActivity
        if m_activity is None:
            return 0.0

        decor_view = m_activity.getWindow().getDecorView()
        if decor_view is None:
            return 0.0

        Rect = autoclass("android.graphics.Rect")
        visible = Rect()
        decor_view.getWindowVisibleDisplayFrame(visible)

        root_view = decor_view.getRootView()
        if root_view is None:
            return 0.0

        screen_px = float(root_view.getHeight())
        inset_px = screen_px - float(visible.bottom)
        if inset_px < dp(20):
            return 0.0

        density = float(Metrics.density or 1.0)
        return inset_px / density
    except Exception:
        return 0.0
