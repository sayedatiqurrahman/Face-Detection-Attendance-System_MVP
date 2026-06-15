from fastapi import APIRouter, HTTPException, UploadFile, File, Form
import numpy as np
import cv2

from ..face_engine import get_embedding
from ..db import connection, cursor

router = APIRouter()


@router.post("/enroll")
async def enroll(name: str = Form(...), file: UploadFile = File(...)):
    img_bytes = await file.read()
    np_img = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    embedding = get_embedding(img)
    if embedding is None:
        return {"status": "no face detected", "detail": "No face found in the image."}

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
