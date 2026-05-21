"""Shared active timer state for the UI process and Android foreground service.

State files are keyed by a stable per-project ``uid`` (a UUID4 string) rather
than by the user-visible title. This lets two projects share the same display
name without sharing timers, goals, or recorded sessions. Legacy installs
(pre-uid) are migrated transparently the first time the new code runs via
``migrate_legacy_state_to_uids``.
"""

import datetime
import json
import os
import tempfile
import uuid


ACTIVE_TIMER_FILE = "active_timer.json"
ACTIVE_GOALS_FILE = "active_goals.json"
PROJECT_DETAILS_FILE = "project_details.json"
PROJECTS_FILE = "projects.json"
SESSIONS_FILE = "sessions.json"
CARD_POSITIONS_FILE = "card_positions.json"


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
    if not isinstance(data, dict):
        return {}
    # Legacy active_timer.json entries only carry ``project_title``; resolve a
    # uid lazily so callers comparing by uid still match the running project.
    if data.get("project_title") and not data.get("project_uid"):
        meta = _project_meta_by_title(data.get("project_title"), base_dir)
        if meta.get("uid"):
            data["project_uid"] = meta["uid"]
    return data if data.get("project_title") or data.get("project_uid") else {}


def start_project_timer(
    project_title,
    base_elapsed_seconds=0,
    started_at=None,
    base_dir=None,
    project_uid="",
):
    state = {
        "project_uid": project_uid or "",
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
    if not isinstance(data, list):
        return []
    # Same legacy backfill as read_project_timer: older goal rows only stored
    # the project title.
    changed = False
    for goal in data:
        if isinstance(goal, dict) and goal.get("project_title") and not goal.get("project_uid"):
            meta = _project_meta_by_title(goal.get("project_title"), base_dir)
            if meta.get("uid"):
                goal["project_uid"] = meta["uid"]
                changed = True
    if changed:
        try:
            _write_json(ACTIVE_GOALS_FILE, data, base_dir)
        except OSError:
            pass
    return data


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
    project_uid="",
):
    state = {
        "uid": uid,
        "project_uid": project_uid or "",
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


def _project_meta_by_uid(project_uid, base_dir=None):
    if not project_uid:
        return {}
    for project in _read_projects(base_dir):
        if project.get("uid") == project_uid:
            return project
    return {}


def _project_meta_by_title(project_title, base_dir=None):
    if not project_title:
        return {}
    for project in _read_projects(base_dir):
        if project.get("title") == project_title:
            return project
    return {}


def _project_meta(project_uid=None, project_title=None, base_dir=None):
    meta = _project_meta_by_uid(project_uid, base_dir) if project_uid else {}
    if not meta and project_title:
        meta = _project_meta_by_title(project_title, base_dir)
    return meta


def _details_key(state_or_meta):
    """Pick the per-project storage key — uid wins over title (legacy data)."""
    if not isinstance(state_or_meta, dict):
        return "_"
    return (
        state_or_meta.get("project_uid")
        or state_or_meta.get("uid")
        or state_or_meta.get("project_title")
        or "_"
    )


def record_session(
    project_title,
    duration_seconds,
    started_at=None,
    ended_at=None,
    base_dir=None,
    project_uid="",
):
    if not project_title or int(duration_seconds) < 1:
        return None
    ended = _to_datetime(ended_at) or _now()
    started = _to_datetime(started_at) or (ended - datetime.timedelta(seconds=int(duration_seconds)))
    meta = _project_meta(project_uid=project_uid, project_title=project_title, base_dir=base_dir)
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
    project_uid = state.get("project_uid", "")
    if duration >= 1:
        record_session(
            project_title,
            duration,
            started_at=started,
            ended_at=now,
            base_dir=base_dir,
            project_uid=project_uid,
        )

    details = _read_project_details(base_dir)
    blob = details.setdefault(_details_key(state), {})
    blob["timer_elapsed"] = max(int(blob.get("timer_elapsed", 0) or 0), int(total_elapsed))
    _write_project_details(details, base_dir)
    clear_project_timer(base_dir)
    return {
        "project_uid": project_uid,
        "project_title": project_title,
        "duration_seconds": duration,
        "timer_elapsed": total_elapsed,
    }


def finalize_goal(uid, base_dir=None, now=None):
    goal = read_goal(uid, base_dir)
    if not goal:
        return None
    now = now or _now()
    total_logged = float(goal.get("base_logged_seconds", 0.0)) + float(running_seconds(goal, now))
    project_title = goal.get("project_title", "")
    project_uid = goal.get("project_uid", "")
    details = _read_project_details(base_dir)
    blob = details.setdefault(_details_key(goal), {})
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
    return {
        "uid": uid,
        "project_uid": project_uid,
        "project_title": project_title,
        "logged_seconds": total_logged,
    }


def has_active_items(base_dir=None):
    return bool(read_project_timer(base_dir) or read_goals(base_dir))


# ---------------------------------------------------------------------------
# Project UID migration
# ---------------------------------------------------------------------------


def _new_uid():
    return f"proj-{uuid.uuid4().hex}"


def ensure_project_uids(base_dir=None):
    """Backfill ``uid`` on every project in projects.json.

    Returns the updated list. Idempotent: a no-op once every project already
    has a uid. The list is written back to disk only if at least one entry
    needed a new uid, to avoid spurious file rewrites on every launch.
    """
    projects = _read_projects(base_dir)
    if not isinstance(projects, list):
        return []
    changed = False
    for project in projects:
        if not isinstance(project, dict):
            continue
        if not project.get("uid"):
            project["uid"] = _new_uid()
            changed = True
    if changed:
        _write_json(PROJECTS_FILE, projects, base_dir)
    return projects


def migrate_legacy_state_to_uids(base_dir=None):
    """Re-key title-keyed state files to uid keys.

    When multiple projects share a title the first occurrence in projects.json
    wins ownership of the legacy blob; duplicates start with fresh state. This
    is the best we can do because pre-uid data simply didn't distinguish
    them — which is exactly what made the duplicates share timers in the
    first place.
    """
    projects = ensure_project_uids(base_dir)
    title_to_uid = {}
    for project in projects:
        if not isinstance(project, dict):
            continue
        title = project.get("title")
        uid = project.get("uid")
        if not title or not uid:
            continue
        title_to_uid.setdefault(title, uid)

    valid_uids = {
        project.get("uid")
        for project in projects
        if isinstance(project, dict) and project.get("uid")
    }

    _migrate_project_details(base_dir, title_to_uid, valid_uids)
    _migrate_active_timer(base_dir, title_to_uid)
    _migrate_active_goals(base_dir, title_to_uid)
    _migrate_card_positions(base_dir, title_to_uid, valid_uids)
    _migrate_sessions(base_dir, title_to_uid)


def _migrate_project_details(base_dir, title_to_uid, valid_uids):
    path = _path(PROJECT_DETAILS_FILE, base_dir)
    if not os.path.exists(path):
        return
    data = _read_json(PROJECT_DETAILS_FILE, {}, base_dir)
    if not isinstance(data, dict) or not data:
        return
    migrated = {}
    changed = False
    for key, blob in data.items():
        if key in valid_uids or key == "_":
            migrated[key] = blob
            continue
        uid = title_to_uid.get(key)
        if uid:
            migrated[uid] = blob
            changed = True
        else:
            # Orphan title with no matching project — keep the entry on the
            # off chance the project comes back, but stash under its title.
            migrated[key] = blob
    if changed:
        _write_json(PROJECT_DETAILS_FILE, migrated, base_dir)


def _migrate_active_timer(base_dir, title_to_uid):
    path = _path(ACTIVE_TIMER_FILE, base_dir)
    if not os.path.exists(path):
        return
    data = _read_json(ACTIVE_TIMER_FILE, {}, base_dir)
    if not isinstance(data, dict) or data.get("project_uid"):
        return
    title = data.get("project_title")
    uid = title_to_uid.get(title) if title else None
    if not uid:
        return
    data["project_uid"] = uid
    _write_json(ACTIVE_TIMER_FILE, data, base_dir)


def _migrate_active_goals(base_dir, title_to_uid):
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
        uid = title_to_uid.get(goal.get("project_title"))
        if uid:
            goal["project_uid"] = uid
            changed = True
    if changed:
        _write_json(ACTIVE_GOALS_FILE, data, base_dir)


def _migrate_card_positions(base_dir, title_to_uid, valid_uids):
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
        uid = title_to_uid.get(key)
        if uid:
            migrated[uid] = pos
            changed = True
        else:
            migrated[key] = pos
    if changed:
        _write_json(CARD_POSITIONS_FILE, migrated, base_dir)


def _migrate_sessions(base_dir, title_to_uid):
    """Backfill ``project_uid`` on legacy sessions.

    Sessions stay title-keyed for statistics aggregation — adding a uid is just
    a hint for future per-project filtering.
    """
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
        uid = title_to_uid.get(session.get("project_title"))
        if uid:
            session["project_uid"] = uid
            changed = True
    if changed:
        _write_json(SESSIONS_FILE, data, base_dir)
