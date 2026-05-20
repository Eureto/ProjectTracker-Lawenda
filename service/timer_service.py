"""Android foreground service that owns persistent running-timer notifications."""

import os
import sys
import time
import traceback
import zlib


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from screens import active_timer


PACKAGE = "org.stokrotka.stokrotka"
CHANNEL_ID = "running_timers"
ACTION_STOP_TIMER = f"{PACKAGE}.STOP_TIMER"
ACTION_STOP_GOAL = f"{PACKAGE}.STOP_GOAL"
TIMER_NOTIFICATION_ID = 1001
GOAL_NOTIFICATION_BASE_ID = 1100
PLACEHOLDER_NOTIFICATION_ID = 999
TAG = "ProjectTrackerSvc"
IDLE_GRACE_SECONDS = 6


def _argb(a, r, g, b):
    val = (a << 24) | (r << 16) | (g << 8) | b
    if val >= 0x80000000:
        val -= 0x100000000
    return val


ACCENT_COLOR = _argb(0xFF, 0x8A, 0x2B, 0xE2)


def _logcat(message):
    print(f"{TAG}: {message}", flush=True)
    try:
        from jnius import autoclass

        autoclass("android.util.Log").i(TAG, str(message))
    except Exception:
        pass


def _format_seconds(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _goal_notification_id(uid):
    return GOAL_NOTIFICATION_BASE_ID + (zlib.crc32(uid.encode("utf-8")) % 8000)


def _goal_progress(goal):
    logged = float(goal.get("base_logged_seconds", 0.0)) + active_timer.running_seconds(goal)
    target = max(1.0, float(goal.get("target_seconds", 1.0)))
    pct = int(round(100.0 * logged / target))
    label = goal.get("goal_text") or goal.get("title") or "Cel"
    return label, pct, int(logged), int(target)


def _goal_text(goal):
    label, pct, logged, _ = _goal_progress(goal)
    return f"{label} - {pct}% ({_format_seconds(logged)})"


class TimerNotificationService:
    def __init__(self):
        from jnius import autoclass

        self.autoclass = autoclass
        self.Context = autoclass("android.content.Context")
        self.Intent = autoclass("android.content.Intent")
        self.PendingIntent = autoclass("android.app.PendingIntent")
        self.JavaString = autoclass("java.lang.String")
        self.BuildVersion = autoclass("android.os.Build$VERSION")
        self.sdk_int = int(self.BuildVersion.SDK_INT)
        self.NotificationBuilder = autoclass("android.app.Notification$Builder")
        self.NotificationChannel = autoclass("android.app.NotificationChannel")
        self.NotificationManagerClass = autoclass("android.app.NotificationManager")
        self.BigTextStyle = autoclass("android.app.Notification$BigTextStyle")
        try:
            self.BitmapFactory = autoclass("android.graphics.BitmapFactory")
        except Exception:
            self.BitmapFactory = None
        try:
            self.ServiceInfo = autoclass("android.content.pm.ServiceInfo")
        except Exception:
            self.ServiceInfo = None
        self.PythonActivity = autoclass("org.kivy.android.PythonActivity")
        self.PythonService = autoclass("org.kivy.android.PythonService")
        self.service = self.PythonService.mService
        self.context = self.service.getApplicationContext()
        self.package_name = self.context.getPackageName()
        self.manager = self.service.getSystemService(self.Context.NOTIFICATION_SERVICE)
        self.icon = self.context.getApplicationInfo().icon
        self._receiver = None
        self._foreground_id = None
        self._last_goal_ids = set()
        self._idle_since = None
        self._seen_active = False
        self._large_icon = self._load_large_icon()

        try:
            base_dir = self.service.getFilesDir().getAbsolutePath()
            active_timer.set_base_dir(base_dir)
            _logcat(f"using base_dir={base_dir}")
        except Exception as exc:
            _logcat(f"set_base_dir failed: {exc!r}")

        self._create_channel()
        self._start_foreground(PLACEHOLDER_NOTIFICATION_ID, self._placeholder_notification())
        self._register_stop_receiver()

    def _jstr(self, value):
        return self.JavaString(str(value or ""))

    def _load_large_icon(self):
        if self.BitmapFactory is None:
            return None
        try:
            return self.BitmapFactory.decodeResource(
                self.context.getResources(), self.icon
            )
        except Exception as exc:
            _logcat(f"large icon load failed: {exc!r}")
            return None

    def _create_channel(self):
        if self.sdk_int < 26:
            return
        channel = self.NotificationChannel(
            CHANNEL_ID,
            self._jstr("Aktywne stopery"),
            self.NotificationManagerClass.IMPORTANCE_LOW,
        )
        channel.setDescription(self._jstr("Trwa odliczanie czasu projektu."))
        try:
            channel.setShowBadge(False)
        except Exception:
            pass
        self.manager.createNotificationChannel(channel)

    def _pending_flags(self):
        flags = self.PendingIntent.FLAG_UPDATE_CURRENT
        if self.sdk_int >= 23:
            flags |= self.PendingIntent.FLAG_IMMUTABLE
        return flags

    def _activity_intent(self, project_title):
        intent = self.Intent(self.context, self.PythonActivity)
        intent.setFlags(
            self.Intent.FLAG_ACTIVITY_CLEAR_TOP | self.Intent.FLAG_ACTIVITY_SINGLE_TOP
        )
        intent.putExtra("project", project_title or "")
        return intent

    def _stop_intent(self, action, uid=""):
        intent = self.Intent(self._jstr(action))
        intent.setPackage(self._jstr(self.package_name))
        if uid:
            intent.putExtra(self._jstr("uid"), self._jstr(uid))
        return intent

    def _builder(self):
        if self.sdk_int >= 26:
            return self.NotificationBuilder(self.context, CHANNEL_ID)
        return self.NotificationBuilder(self.context)

    def _apply_style(self, builder, title, expanded_text):
        try:
            style = self.BigTextStyle()
            style.setBigContentTitle(self._jstr(title))
            style.bigText(self._jstr(expanded_text))
            builder.setStyle(style)
        except Exception as exc:
            _logcat(f"BigTextStyle failed: {exc!r}")

    def _notification_builder(
        self,
        title,
        text,
        project_title,
        stop_intent,
        request_code,
        expanded_text=None,
        sub_text=None,
    ):
        builder = self._builder()
        tap = self.PendingIntent.getActivity(
            self.context,
            request_code,
            self._activity_intent(project_title),
            self._pending_flags(),
        )
        stop = self.PendingIntent.getBroadcast(
            self.context,
            request_code + 50000,
            stop_intent,
            self._pending_flags(),
        )
        builder.setSmallIcon(self.icon)
        if self._large_icon is not None:
            try:
                builder.setLargeIcon(self._large_icon)
            except Exception:
                pass
        try:
            builder.setColor(ACCENT_COLOR)
        except Exception:
            pass
        try:
            builder.setColorized(True)
        except Exception:
            pass
        if self.sdk_int >= 21:
            try:
                builder.setVisibility(1)
            except Exception:
                pass
        builder.setContentTitle(self._jstr(title))
        builder.setContentText(self._jstr(text))
        if sub_text:
            try:
                builder.setSubText(self._jstr(sub_text))
            except Exception:
                pass
        builder.setContentIntent(tap)
        builder.setOngoing(True)
        builder.setOnlyAlertOnce(True)
        builder.setShowWhen(False)
        builder.addAction(self.icon, self._jstr("Zatrzymaj"), stop)
        if expanded_text:
            self._apply_style(builder, title, expanded_text)
        return builder

    def _placeholder_notification(self):
        builder = self._builder()
        builder.setSmallIcon(self.icon)
        if self._large_icon is not None:
            try:
                builder.setLargeIcon(self._large_icon)
            except Exception:
                pass
        try:
            builder.setColor(ACCENT_COLOR)
        except Exception:
            pass
        builder.setContentTitle(self._jstr("Lawenda"))
        builder.setContentText(self._jstr("Trwa uruchamianie stopera..."))
        builder.setOngoing(True)
        builder.setOnlyAlertOnce(True)
        builder.setShowWhen(False)
        return builder.build()

    def _timer_notification(self, state):
        project = state.get("project_title", "") or "Projekt"
        elapsed = active_timer.elapsed_from_state(state)
        elapsed_text = _format_seconds(elapsed)
        expanded = (
            f"Projekt: {project}\n"
            f"Stoper: {elapsed_text}"
        )
        return self._notification_builder(
            f"Stoper - {project}",
            elapsed_text,
            project,
            self._stop_intent(ACTION_STOP_TIMER),
            TIMER_NOTIFICATION_ID,
            expanded_text=expanded,
            sub_text="Lawenda",
        ).build()

    def _goal_notification(self, goal):
        uid = str(goal.get("uid", "") or "")
        project = goal.get("project_title", "") or "Projekt"
        goal_name = (goal.get("title") or "").strip()
        label, pct, logged, _ = _goal_progress(goal)
        collapsed = f"{label} - {pct}% ({_format_seconds(logged)})"

        title_parts = ["Cel", project]
        if goal_name and goal_name.lower() != "cel":
            title_parts.append(goal_name)
        title = " - ".join(title_parts)

        header = project
        if goal_name and goal_name.lower() != "cel":
            header = f"{project} - {goal_name}"
        expanded = f"{header}\n{label} - {pct}% - {_format_seconds(logged)}"

        return self._notification_builder(
            title,
            collapsed,
            project,
            self._stop_intent(ACTION_STOP_GOAL, uid),
            _goal_notification_id(uid),
            expanded_text=expanded,
            sub_text="Lawenda",
        ).build()

    def _start_foreground(self, notification_id, notification):
        if self._foreground_id == notification_id:
            try:
                self.manager.notify(notification_id, notification)
            except Exception:
                pass
            return
        try:
            self.service.startForeground(notification_id, notification)
        except Exception as exc:
            _logcat(f"startForeground failed: {exc!r}")
            return
        if self._foreground_id is not None and self._foreground_id != notification_id:
            try:
                self.manager.cancel(self._foreground_id)
            except Exception:
                pass
        self._foreground_id = notification_id

    def _stop_foreground(self):
        try:
            if self.sdk_int >= 24:
                self.service.stopForeground(1)
            else:
                self.service.stopForeground(True)
        except Exception:
            pass
        if self._foreground_id is not None:
            try:
                self.manager.cancel(self._foreground_id)
            except Exception:
                pass
            self._foreground_id = None

    def _register_stop_receiver(self):
        try:
            from android.broadcast import BroadcastReceiver
        except Exception as exc:
            _logcat(f"BroadcastReceiver unavailable: {exc!r}")
            return

        def _on_receive(context, intent):
            action = str(intent.getAction() or "")
            _logcat(f"received {action}")
            try:
                if action == ACTION_STOP_TIMER:
                    active_timer.finalize_project_timer()
                    self.manager.cancel(TIMER_NOTIFICATION_ID)
                elif action == ACTION_STOP_GOAL:
                    raw_uid = intent.getStringExtra(self._jstr("uid"))
                    uid = str(raw_uid) if raw_uid is not None else ""
                    _logcat(f"STOP_GOAL uid={uid!r}")
                    if uid:
                        result = active_timer.finalize_goal(uid)
                        _logcat(f"finalize_goal({uid!r}) -> {result!r}")
                        self.manager.cancel(_goal_notification_id(uid))
                    else:
                        _logcat("STOP_GOAL received without uid extra")
            except Exception:
                _logcat(traceback.format_exc())

        self._receiver = BroadcastReceiver(
            _on_receive, actions=[ACTION_STOP_TIMER, ACTION_STOP_GOAL]
        )
        try:
            self._receiver.start()
        except Exception as exc:
            _logcat(f"BroadcastReceiver.start failed: {exc!r}")
            self._receiver = None

    def _unregister_stop_receiver(self):
        if self._receiver is None:
            return
        try:
            self._receiver.stop()
        except Exception:
            pass
        self._receiver = None

    def _tick_once(self):
        timer_state = active_timer.read_project_timer()
        goals = active_timer.read_goals()
        active_ids = []

        if timer_state:
            notification = self._timer_notification(timer_state)
            self._start_foreground(TIMER_NOTIFICATION_ID, notification)
            self.manager.notify(TIMER_NOTIFICATION_ID, notification)
            active_ids.append(TIMER_NOTIFICATION_ID)
        else:
            self.manager.cancel(TIMER_NOTIFICATION_ID)

        for goal in goals:
            uid = goal.get("uid", "")
            if not uid:
                continue
            notification_id = _goal_notification_id(uid)
            notification = self._goal_notification(goal)
            if not active_ids:
                self._start_foreground(notification_id, notification)
            self.manager.notify(notification_id, notification)
            active_ids.append(notification_id)

        for old_id in self._last_goal_ids - set(active_ids):
            self.manager.cancel(old_id)
        self._last_goal_ids = {nid for nid in active_ids if nid != TIMER_NOTIFICATION_ID}

        return bool(active_ids)

    def run(self):
        _logcat("service started")
        try:
            while True:
                try:
                    has_active = self._tick_once()
                except Exception:
                    _logcat(traceback.format_exc())
                    has_active = True

                if has_active:
                    self._seen_active = True
                    self._idle_since = None
                else:
                    if self._seen_active:
                        _logcat("no active timers - stopping service")
                        self._stop_foreground()
                        try:
                            self.service.stopSelf()
                        except Exception:
                            pass
                        return
                    if self._idle_since is None:
                        self._idle_since = time.monotonic()
                    elif time.monotonic() - self._idle_since >= IDLE_GRACE_SECONDS:
                        _logcat("idle - stopping service")
                        self._stop_foreground()
                        try:
                            self.service.stopSelf()
                        except Exception:
                            pass
                        return

                time.sleep(1)
        finally:
            self._unregister_stop_receiver()


def main():
    try:
        TimerNotificationService().run()
    except Exception:
        _logcat(traceback.format_exc())


if __name__ == "__main__":
    main()
