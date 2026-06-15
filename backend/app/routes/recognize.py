from fastapi import APIRouter
import numpy as np
import cv2
import base64
from datetime import date, datetime

from ..schemas import RecognizeRequest
from ..face_engine import get_all_embeddings
from ..db import connection, cursor
from ..state import session_active, is_within_session_window

router = APIRouter()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@router.post("/recognize")
async def recognize(req: RecognizeRequest):
    sess_active = session_active()

    try:
        raw = base64.b64decode(req.image)
        np_arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception:
        return {"status": "error", "detail": "Invalid Base64 image data.", "session_active": sess_active}

    if img is None:
        return {"status": "error", "detail": "Could not decode image.", "session_active": sess_active}

    faces = get_all_embeddings(img)
    if not faces:
        return {"status": "no_face", "results": [], "session_active": sess_active}

    cursor.execute("SELECT id, name, embedding FROM students")
    students = cursor.fetchall()
    if not students:
        return {"status": "no_students", "results": [], "session_active": sess_active}

    today = date.today()
    results = []

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

        if best_score > 0.5 and best_match:
            student_id = best_match["id"]
            student_name = best_match["name"]

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

    return {"status": "success", "results": results, "session_active": sess_active}
