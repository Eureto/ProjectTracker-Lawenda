"""Persist tracked time sessions and expose last-session / statistics aggregates."""

import datetime
import json
import os

from kivy.clock import Clock
from kivymd.app import MDApp


def _sessions_path():
    return os.path.join(MDApp.get_running_app().user_data_dir, "sessions.json")


def _projects_path():
    return os.path.join(MDApp.get_running_app().user_data_dir, "projects.json")


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


def save_sessions(sessions):
    path = _sessions_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)


def find_project_meta(project_title):
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


def record_session(project_title, duration_seconds, started_at=None, ended_at=None):
    """Append a completed tracking session (newest first)."""
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
        "project_title": project_title,
        "emoji_source": meta.get("icon", "emoticon-happy-outline"),
        "image": meta.get("image", ""),
        "color": meta.get("color", [0.7, 0.5, 1, 1]),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": int(duration_seconds),
    }
    sessions = load_sessions()
    sessions.insert(0, entry)
    save_sessions(sessions)
    schedule_home_last_session_refresh()
    return entry


def schedule_home_last_session_refresh():
    """Refresh home session card after navigation / screen transitions."""
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


def get_last_session():
    sessions = load_sessions()
    return sessions[0] if sessions else None


def format_duration_hms(seconds):
    s = max(0, int(seconds))
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def format_when_label(iso_dt):
    """Polish relative label for session end time."""
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
    raw = session.get("ended_at") or session.get("started_at")
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def sessions_in_period(sessions, period_label):
    """Filter sessions by statistics period: Dzień / Tydzień / Miesiąc."""
    now = datetime.datetime.now()
    if period_label == "Dzień":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period_label == "Tydzień":
        start = now - datetime.timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    out = []
    for s in sessions:
        ended = _parse_ended(s)
        if ended is not None and ended >= start:
            out.append(s)
    return out


def aggregate_by_project(sessions):
    """Return list of dicts: title, emoji_source, color, total_seconds."""
    totals = {}
    for s in sessions:
        title = s.get("project_title") or "?"
        sec = int(s.get("duration_seconds", 0))
        if title not in totals:
            totals[title] = {
                "title": title,
                "emoji_source": s.get("emoji_source", "folder-outline"),
                "color": s.get("color", [0.6, 0.4, 0.8, 1]),
                "total_seconds": 0,
            }
        totals[title]["total_seconds"] += sec
    rows = sorted(totals.values(), key=lambda x: -x["total_seconds"])
    return rows


def statistics_from_sessions(period_label):
    """Build pie chart data and detail rows for StatisticsScreen."""
    sessions = sessions_in_period(load_sessions(), period_label)
    rows = aggregate_by_project(sessions)
    total = sum(r["total_seconds"] for r in rows)
    if total <= 0:
        return [], []

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
        h = r["total_seconds"] // 3600
        m = (r["total_seconds"] % 3600) // 60
        time_txt = f"{h:02d}:{m:02d}" if h else f"{m} min"
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
    return pie, detail
