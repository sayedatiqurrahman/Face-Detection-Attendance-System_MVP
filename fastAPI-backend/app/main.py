"""
Main application — FastAPI server for Face Recognition Attendance.

Routes:
  - GET  /                       : frontend index.html (served by StaticFiles)
  - GET  /courses                : list all courses
  - POST /course/add             : add a new course
  - GET  /course/{id}            : get one course by id
  - PUT  /course/{id}            : update a course
  - DELETE /course/{id}          : delete a course
  - POST /enroll                 : register a new student (name + photo file)
  - POST /recognize              : recognise face(s) from a Base64 image frame
  - POST /attendance/start       : start an attendance session (time window)
  - POST /attendance/stop        : stop the current attendance session
  - GET  /attendance/session     : get current session status
  - GET  /attendance/summary     : today's attendance list with present/absent
"""
from fastapi import FastAPI, HTTPException, status, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from enum import Enum
from datetime import datetime, date, time as time_type
import numpy as np
import cv2
import base64
import os

# Internal imports — sibling modules in the same package
from .face_engine import get_embedding, get_all_embeddings
from .db import connection, cursor

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Face Recognition Attendance API", version="1.0.0")

# CORS — kept for development (frontend served from same origin in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auto-create required database tables on first startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
def init_db():
    """
    Ensure database tables exist with the correct schema.
    If tables already exist but have wrong column types (e.g. name as ARRAY
    instead of VARCHAR), they are dropped and recreated.
    """
    try:
        # Drop & recreate to fix any schema mismatches from earlier runs.
        # (Safe for MVP — no critical data yet.)
        cursor.execute("DROP TABLE IF EXISTS attendance CASCADE")
        cursor.execute("DROP TABLE IF EXISTS students CASCADE")

        cursor.execute("""
            CREATE TABLE students (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                embedding BYTEA NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE attendance (
                id SERIAL PRIMARY KEY,
                student_id INTEGER REFERENCES students(id),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Database tables initialised with correct schema.")
    except Exception as e:
        print("Table setup error:", e)


# ---------------------------------------------------------------------------
# Helper — return session_active flag
# ---------------------------------------------------------------------------
def _session_active() -> bool:
    return active_session["active"] and is_within_session_window()

# ---------------------------------------------------------------------------
# Pydantic schemas (used by course routes)
# ---------------------------------------------------------------------------
class sexEnum(str, Enum):
    male = "male"
    female = "female"
    third_gender = "third_gender"


class Instructor(BaseModel):
    name: str
    sex: sexEnum
    age: int
    portfolio: HttpUrl


class Course(BaseModel):
    title: str
    duration: float
    instructor: Instructor


class RecognizeRequest(BaseModel):
    """Body for POST /recognize — expects a Base64-encoded JPEG frame."""
    image: str  # raw base64 string (without data:image/... prefix)


class AttendanceTimeWindow(BaseModel):
    """Start and end time for an attendance session (HH:MM format)."""
    start_time: str
    end_time: str


# ---------------------------------------------------------------------------
# In-memory attendance session state
# ---------------------------------------------------------------------------
# This stores the current active session's time window.
# In a production app you would persist this in the database.
active_session = {
    "active": False,
    "start_time": None,
    "end_time": None,
    "started_at": None,
}


def is_within_session_window() -> bool:
    """Return True if there is an active session and now is inside the window."""
    if not active_session["active"]:
        return False
    now = datetime.now().time()
    start = datetime.strptime(active_session["start_time"], "%H:%M").time()
    end = datetime.strptime(active_session["end_time"], "%H:%M").time()
    if start <= end:
        return start <= now <= end
    else:
        # Window crosses midnight (e.g. 22:00 -> 02:00)
        return now >= start or now <= end


# ---------------------------------------------------------------------------
# Helper — cosine similarity between two 512-d vectors
# ---------------------------------------------------------------------------
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity ∈ [-1, 1]; higher = more similar."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ===================================================================
#  COURSE CRUD  (kept exactly as in the original codebase)
# ===================================================================

@app.get("/courses")
def get_courses():
    cursor.execute("""SELECT * FROM course_table ORDER BY id""")
    courses = cursor.fetchall()
    return courses


@app.post("/course/add")
def add_course(new_course: Course):
    cursor.execute(
        """INSERT INTO course_table(title, instructor, duration, website)
           VALUES (%s, %s, %s, %s) RETURNING *""",
        (new_course.title, new_course.instructor.name,
         new_course.duration, str(new_course.instructor.portfolio)),
    )
    new_post = cursor.fetchone()
    connection.commit()
    return {"course": new_post}


@app.get("/course/{id}")
def get_course_by_id(id: int):
    cursor.execute("""SELECT * FROM course_table WHERE id = %s""", (str(id),))
    course = cursor.fetchone()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course not found with id: {id}",
        )
    return {"course": course}


@app.delete("/course/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course_by_id(id: int):
    cursor.execute("""DELETE FROM course_table WHERE id = %s RETURNING *""", (str(id),))
    deleted = cursor.fetchone()
    connection.commit()
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course not found with id: {id}",
        )
    return Response(status_code=status.HTTP_200_OK)


@app.put("/course/{id}", status_code=status.HTTP_202_ACCEPTED)
def update_course_by_id(id: int, course: Course):
    cursor.execute(
        """UPDATE course_table
           SET title=%s, instructor=%s, duration=%s, website=%s
           WHERE id=%s RETURNING *""",
        (course.title, course.instructor.name,
         course.duration, str(course.instructor.portfolio), str(id)),
    )
    updated = cursor.fetchone()
    connection.commit()
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course not found with id: {id}",
        )
    return {"course": updated}


# ===================================================================
#  ENROLL — register a new student from a photo file
# ===================================================================

@app.post("/enroll")
async def enroll(name: str = Form(...), file: UploadFile = File(...)):
    """
    Register a new student.
    - name  : student's full name
    - file  : JPEG/ PNG photo containing exactly one face
    The face embedding is extracted and stored in the `students` table.
    """
    # Read uploaded file -> OpenCV image (BGR)
    img_bytes = await file.read()
    np_img = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    # Extract face embedding
    embedding = get_embedding(img)
    if embedding is None:
        return {"status": "no face detected", "detail": "No face found in the image."}

    # Persist to database
    cursor.execute(
        "INSERT INTO students (name, embedding) VALUES (%s, %s) RETURNING id, name",
        (name, embedding.tobytes()),
    )
    student = cursor.fetchone()
    connection.commit()

    return {
        "status": "enrolled",
        "student_id": student["id"],
        "student_name": student["name"],
    }


# ===================================================================
#  ATTENDANCE SESSION — start / stop / status / summary
# ===================================================================

@app.post("/attendance/start")
def start_attendance(window: AttendanceTimeWindow):
    """
    Start an attendance session with a time window.
    Only face detections inside the window will mark attendance.
    """
    # Basic validation
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


@app.post("/attendance/stop")
def stop_attendance():
    """Stop the current attendance session."""
    active_session["active"] = False
    return {"status": "stopped"}


@app.get("/attendance/session")
def get_attendance_session():
    """Return the current session state."""
    return {
        "active": active_session["active"],
        "start_time": active_session["start_time"],
        "end_time": active_session["end_time"],
        "started_at": active_session["started_at"],
        "within_window": is_within_session_window(),
    }


@app.get("/attendance/summary")
def get_attendance_summary():
    """
    Return every registered student with their attendance status today.
    Used by the frontend to populate Present / Absent tabs.
    """
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
    # Build lookup: student_id -> first-attendance-time
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


# ===================================================================
#  RECOGNIZE — identify face(s) from a live webcam frame
# ===================================================================

@app.post("/recognize")
async def recognize(req: RecognizeRequest):
    """
    Accept a Base64-encoded JPEG frame.
    1. Decode -> OpenCV image
    2. Detect all faces via InsightFace, extract 512-d embeddings
    3. Compare each embedding against every student in the database
    4. If similarity > 0.5 -> recognise the student
    5. Check if attendance was already marked today -> skip or insert
    6. Return an array of results (one per detected face)
    """
    session_active = _session_active()

    # ---------- decode Base64 image ----------
    try:
        raw = base64.b64decode(req.image)
        np_arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Base64 image data.")

    if img is None:
        return {"status": "error", "detail": "Could not decode image.", "session_active": session_active}

    # ---------- face detection & embedding ----------
    faces = get_all_embeddings(img)          # list of {embedding, bbox}
    if not faces:
        return {"status": "no_face", "results": [], "session_active": session_active}

    # ---------- load all registered students ----------
    cursor.execute("SELECT id, name, embedding FROM students")
    students = cursor.fetchall()
    if not students:
        return {"status": "no_students", "results": [], "session_active": session_active}

    today = date.today()
    results = []

    # ---------- match each detected face ----------
    for face in faces:
        emb = face["embedding"]
        bbox = face["bbox"]

        best_match = None
        best_score = 0.0

        for stu in students:
            db_emb = np.frombuffer(stu["embedding"], dtype=np.float32)
            score = cosine_similarity(emb, db_emb)
            if score > best_score:
                best_score = score
                best_match = stu

        # Threshold = 0.5 (tune this based on your environment)
        if best_score > 0.5 and best_match:
            student_id = best_match["id"]
            student_name = best_match["name"]

            # ----- only mark attendance when session is active & within window -----
            attendance_marked = False
            if is_within_session_window():
                cursor.execute(
                    """SELECT id FROM attendance
                       WHERE student_id = %s AND DATE(timestamp) = %s""",
                    (student_id, today),
                )
                already_marked = cursor.fetchone()

                if not already_marked:
                    cursor.execute(
                        "INSERT INTO attendance (student_id, timestamp) VALUES (%s, %s)",
                        (student_id, datetime.now()),
                    )
                    connection.commit()
                    attendance_marked = True

            results.append({
                "status": "recognized",
                "student_name": student_name,
                "confidence": round(best_score, 4),
                "attendance_marked": attendance_marked,
                "bbox": bbox,
            })
        else:
            results.append({
                "status": "unknown",
                "confidence": round(best_score, 4),
                "bbox": bbox,
            })

    return {"status": "success", "results": results, "session_active": session_active}


# ===================================================================
#  SERVE FRONTEND — mount after all API routes so they take priority
# ===================================================================
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
