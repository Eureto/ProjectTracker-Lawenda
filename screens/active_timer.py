"""Shared active timer state for the UI process and Android foreground service."""

import datetime
import json
import os
import tempfile


ACTIVE_TIMER_FILE = "active_timer.json"
ACTIVE_GOALS_FILE = "active_goals.json"
PROJECT_DETAILS_FILE = "project_details.json"
PROJECTS_FILE = "projects.json"
SESSIONS_FILE = "sessions.json"


_BASE_DIR_OVERRIDE = None


def set_base_dir(path):
    """Force a specific storage directory (used by the Android service process)."""
    global _BASE_DIR_OVERRIDE
    _BASE_DIR_OVERRIDE = path or None


def _android_files_dir():
    """Resolve getFilesDir() from either PythonActivity (UI) or PythonService (service)."""
    try:
        from jnius import autoclass
    except Exception:
        return None
    for cls_name, attr in (
        ("org.kivy.android.PythonService", "mService"),
        ("org.kivy.android.PythonActivity", "mActivity"),
    ):
        try:
            ctx = getattr(autoclass(cls_name), attr, None)
            if ctx is None:
                continue
            return ctx.getFilesDir().getAbsolutePath()
        except Exception:
            continue
    return None


def default_base_dir():
    """Return the app-private storage directory in both UI and Android service processes."""
    if _BASE_DIR_OVERRIDE:
        return _BASE_DIR_OVERRIDE

    try:
        from kivymd.app import MDApp

        app = MDApp.get_running_app()
        if app is not None and getattr(app, "user_data_dir", ""):
            return app.user_data_dir
    except Exception:
        pass

    android_dir = _android_files_dir()
    if android_dir:
        return android_dir

    return os.environ.get("PROJECTTRACKER_USER_DATA_DIR") or os.getcwd()


def _path(filename, base_dir=None):
    return os.path.join(base_dir or default_base_dir(), filename)


def _read_json(filename, default, base_dir=None):
    path = _path(filename, base_dir)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else default
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(filename, data, base_dir=None):
    path = _path(filename, base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{filename}.", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _remove(filename, base_dir=None):
    try:
        os.remove(_path(filename, base_dir))
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _now():
    return datetime.datetime.now()


def _to_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return None


def elapsed_from_state(state, now=None):
    started = _to_datetime((state or {}).get("started_at"))
    if started is None:
        return int(float((state or {}).get("base_elapsed_seconds", 0)))
    now = now or _now()
    base = int(float((state or {}).get("base_elapsed_seconds", 0)))
    return max(0, base + int((now - started).total_seconds()))


def running_seconds(state, now=None):
    started = _to_datetime((state or {}).get("started_at"))
    if started is None:
        return 0
    now = now or _now()
    return max(0, int((now - started).total_seconds()))


def read_project_timer(base_dir=None):
    data = _read_json(ACTIVE_TIMER_FILE, {}, base_dir)
    return data if isinstance(data, dict) and data.get("project_title") else {}


def start_project_timer(project_title, base_elapsed_seconds=0, started_at=None, base_dir=None):
    state = {
        "project_title": project_title,
        "base_elapsed_seconds": int(max(0, float(base_elapsed_seconds or 0))),
        "started_at": (started_at or _now()).isoformat(),
    }
    _write_json(ACTIVE_TIMER_FILE, state, base_dir)
    return state


def clear_project_timer(base_dir=None):
    _remove(ACTIVE_TIMER_FILE, base_dir)


def read_goals(base_dir=None):
    data = _read_json(ACTIVE_GOALS_FILE, [], base_dir)
    return data if isinstance(data, list) else []


def read_goal(uid, base_dir=None):
    for goal in read_goals(base_dir):
        if goal.get("uid") == uid:
            return goal
    return {}


def upsert_goal(goal_state, base_dir=None):
    uid = goal_state.get("uid")
    if not uid:
        return goal_state
    goals = [g for g in read_goals(base_dir) if g.get("uid") != uid]
    goals.append(goal_state)
    _write_json(ACTIVE_GOALS_FILE, goals, base_dir)
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
):
    state = {
        "uid": uid,
        "project_title": project_title,
        "title": title or "Cel",
        "goal_text": goal_text or "",
        "target_seconds": float(max(1.0, float(target_seconds or 1))),
        "base_logged_seconds": float(max(0.0, float(base_logged_seconds or 0))),
        "reset_mode": reset_mode or "weekly",
        "period_key": period_key or "",
        "started_at": (started_at or _now()).isoformat(),
    }
    return upsert_goal(state, base_dir)


def remove_goal(uid, base_dir=None):
    goals = [g for g in read_goals(base_dir) if g.get("uid") != uid]
    if goals:
        _write_json(ACTIVE_GOALS_FILE, goals, base_dir)
    else:
        _remove(ACTIVE_GOALS_FILE, base_dir)


def _read_project_details(base_dir=None):
    data = _read_json(PROJECT_DETAILS_FILE, {}, base_dir)
    return data if isinstance(data, dict) else {}


def _write_project_details(data, base_dir=None):
    _write_json(PROJECT_DETAILS_FILE, data, base_dir)


def _read_projects(base_dir=None):
    data = _read_json(PROJECTS_FILE, [], base_dir)
    return data if isinstance(data, list) else []


def _project_meta(project_title, base_dir=None):
    for project in _read_projects(base_dir):
        if project.get("title") == project_title:
            return project
    return {}


def record_session(project_title, duration_seconds, started_at=None, ended_at=None, base_dir=None):
    if not project_title or int(duration_seconds) < 1:
        return None
    ended = _to_datetime(ended_at) or _now()
    started = _to_datetime(started_at) or (ended - datetime.timedelta(seconds=int(duration_seconds)))
    meta = _project_meta(project_title, base_dir)
    entry = {
        "project_title": project_title,
        "emoji_source": meta.get("icon", "emoticon-happy-outline"),
        "image": meta.get("image", ""),
        "color": meta.get("color", [0.7, 0.5, 1, 1]),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": int(duration_seconds),
    }
    sessions = _read_json(SESSIONS_FILE, [], base_dir)
    if not isinstance(sessions, list):
        sessions = []
    sessions.insert(0, entry)
    _write_json(SESSIONS_FILE, sessions, base_dir)
    return entry


def finalize_project_timer(base_dir=None, now=None):
    state = read_project_timer(base_dir)
    if not state:
        return None
    now = now or _now()
    started = _to_datetime(state.get("started_at"))
    duration = running_seconds(state, now)
    total_elapsed = elapsed_from_state(state, now)
    project_title = state.get("project_title", "")
    if duration >= 1:
        record_session(project_title, duration, started_at=started, ended_at=now, base_dir=base_dir)

    details = _read_project_details(base_dir)
    blob = details.setdefault(project_title or "_", {})
    blob["timer_elapsed"] = max(int(blob.get("timer_elapsed", 0) or 0), int(total_elapsed))
    _write_project_details(details, base_dir)
    clear_project_timer(base_dir)
    return {"project_title": project_title, "duration_seconds": duration, "timer_elapsed": total_elapsed}


def finalize_goal(uid, base_dir=None, now=None):
    goal = read_goal(uid, base_dir)
    if not goal:
        return None
    now = now or _now()
    total_logged = float(goal.get("base_logged_seconds", 0.0)) + float(running_seconds(goal, now))
    project_title = goal.get("project_title", "")
    details = _read_project_details(base_dir)
    blob = details.setdefault(project_title or "_", {})
    goals = blob.setdefault("goals", [])
    for saved in goals:
        if saved.get("uid") == uid:
            period_key = goal.get("period_key", saved.get("period_key", ""))
            if saved.get("period_key") == period_key:
                saved["logged_seconds"] = max(float(saved.get("logged_seconds", 0) or 0), total_logged)
            else:
                saved["logged_seconds"] = total_logged
            saved["period_key"] = period_key
            break
    _write_project_details(details, base_dir)
    remove_goal(uid, base_dir)
    return {"uid": uid, "project_title": project_title, "logged_seconds": total_logged}


def has_active_items(base_dir=None):
    return bool(read_project_timer(base_dir) or read_goals(base_dir))
