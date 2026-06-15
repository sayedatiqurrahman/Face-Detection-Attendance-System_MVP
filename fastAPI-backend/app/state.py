from datetime import datetime

active_session = {
    "active": False,
    "start_time": None,
    "end_time": None,
    "started_at": None,
}


def is_within_session_window() -> bool:
    if not active_session["active"]:
        return False
    now = datetime.now().time()
    start = datetime.strptime(active_session["start_time"], "%H:%M").time()
    end = datetime.strptime(active_session["end_time"], "%H:%M").time()
    if start <= end:
        return start <= now <= end
    else:
        return now >= start or now <= end


def session_active() -> bool:
    return active_session["active"] and is_within_session_window()
