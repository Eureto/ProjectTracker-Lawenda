"""Persist tracked time sessions and expose last-session / statistics aggregates."""

import datetime
import json
import os

from kivy.clock import Clock
from kivymd.app import MDApp
from screens.emoji_assets import resolve_emoji_source


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


def record_session(
    project_title,
    duration_seconds,
    started_at=None,
    ended_at=None,
    project_uid="",
):
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
    schedule_home_last_session_refresh()
    schedule_statistics_refresh()
    return entry


def _project_details_path():
    return os.path.join(MDApp.get_running_app().user_data_dir, "project_details.json")


def load_project_details():
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


def period_range_start(period_label):
    """Inclusive start datetime for Dzień / Tydzień / Miesiąc (local time)."""
    now = datetime.datetime.now()
    if period_label == "Dzień":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period_label == "Tydzień":
        start = now - datetime.timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _goal_period_key(reset_mode):
    """Match project_info goal period keys for day / week / all-time."""
    now = datetime.datetime.now()
    if reset_mode == "daily":
        return now.date().isoformat()
    if reset_mode == "weekly":
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return "all"


def _parse_goal_reset_mode(value):
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
    """
    Goal car time for the selected statistics window.
    Nested like sessions: day ⊆ week ⊆ month.
    """
    logged = int(float(goal.get("logged_seconds", 0)))
    if logged <= 0:
        return 0
    rm = _parse_goal_reset_mode(goal.get("reset_mode", ""))
    pk = (goal.get("period_key") or "").strip()
    day_key = _goal_period_key("daily")
    week_key = _goal_period_key("weekly")

    if rm == "never":
        # All-time goal counter — only attribute to the widest window (month).
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
    """Sum car-goal logged time per project for the active calendar period."""
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
    """Show seconds when under a minute; otherwise M:SS or H:MM:SS (matches project timer)."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} s"
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def format_statistics_total(seconds):
    return f"suma: {format_statistics_duration(seconds)}"


def schedule_statistics_refresh():
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
    start = period_range_start(period_label)
    out = []
    for s in sessions:
        ended = _parse_ended(s)
        if ended is not None and ended >= start:
            out.append(s)
    return out


def _merge_project_meta(row):
    """Fill icon/color from projects.json when missing on stored sessions.

    Always rewrites the icon through resolve_emoji_source so that PNG entries
    stored as legacy in-repo paths (e.g. assets/Emoji_PNG/foo.png) point at the
    runtime-extracted location after the emoji-zip packaging refactor.
    """
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


def aggregate_by_project(sessions, period_label):
    """Return list of dicts: title, emoji_source, color, total_seconds (all projects)."""
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


def statistics_from_sessions(period_label):
    """Build pie chart data, detail rows, and total seconds for StatisticsScreen."""
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
