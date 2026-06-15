from fastapi import APIRouter, HTTPException
from datetime import datetime, date

from ..schemas import AttendanceTimeWindow
from ..state import active_session, is_within_session_window
from ..db import connection, cursor

router = APIRouter()


@router.post("/attendance/start")
def start_attendance(window: AttendanceTimeWindow):
    try:
        datetime.strptime(window.start_time, "%H:%M")
        datetime.strptime(window.end_time, "%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Times must be in HH:MM format.")

    active_session["active"] = True
    active_session["start_time"] = window.start_time
    active_session["end_time"] = window.end_time
    active_session["started_at"] = datetime.now().isoformat()

    return {
        "status": "started",
        "start_time": window.start_time,
        "end_time": window.end_time,
    }


@router.post("/attendance/stop")
def stop_attendance():
    active_session["active"] = False
    return {"status": "stopped"}


@router.get("/attendance/session")
def get_attendance_session():
    return {
        "active": active_session["active"],
        "start_time": active_session["start_time"],
        "end_time": active_session["end_time"],
        "started_at": active_session["started_at"],
        "within_window": is_within_session_window(),
    }


@router.get("/attendance/summary")
def get_attendance_summary():
    today = date.today()

    cursor.execute("SELECT id, name FROM students ORDER BY name")
    all_students = cursor.fetchall()

    cursor.execute(
        """SELECT student_id, timestamp FROM attendance
           WHERE DATE(timestamp) = %s ORDER BY timestamp""",
        (today,),
    )
    present_rows = cursor.fetchall()
    present_ids = {r["student_id"] for r in present_rows}
    first_seen = {}
    for r in present_rows:
        sid = r["student_id"]
        if sid not in first_seen:
            first_seen[sid] = r["timestamp"].strftime("%H:%M:%S")

    students_info = []
    for s in all_students:
        sid = s["id"]
        students_info.append({
            "id": sid,
            "name": s["name"],
            "present": sid in present_ids,
            "time": first_seen.get(sid, None),
        })

    total = len(students_info)
    present_count = len(present_ids)
    percentage = round((present_count / total * 100) if total > 0 else 0, 1)
    return {
        "total": total,
        "present": present_count,
        "absent": total - present_count,
        "percentage": percentage,
        "students": students_info,
    }
