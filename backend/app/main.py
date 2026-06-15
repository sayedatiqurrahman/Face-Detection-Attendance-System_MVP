from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from .db import connection, cursor
from .routes import enroll, recognize, attendance

app = FastAPI(title="Face Detection Attendance API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def init_db():
    try:
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


app.include_router(enroll.router)
app.include_router(recognize.router)
app.include_router(attendance.router)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
