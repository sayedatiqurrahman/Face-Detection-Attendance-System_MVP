# Face-Detection-Attendance-System (MVP)

A real-time face recognition attendance system using InsightFace and FastAPI. The device's built-in camera or an external webcam is accessed directly from the browser via `getUserMedia`, and face embeddings are matched against a PostgreSQL database to automatically mark attendance.

## Project Structure

```
Face-Detection-Attendance-System/
├── fastAPI-backend/          # FastAPI backend
│   ├── app/
│   │   ├── main.py           # Entry point — app, CORS, router includes
│   │   ├── db.py             # PostgreSQL connection
│   │   ├── face_engine.py    # InsightFace face detection & embedding
│   │   ├── schemas.py        # Pydantic request/response models
│   │   ├── state.py          # In-memory attendance session state
│   │   ├── routes/
│   │   │   ├── enroll.py     # POST /enroll — register new student
│   │   │   ├── recognize.py  # POST /recognize — detect & match faces
│   │   │   └── attendance.py # Attendance session CRUD + summary
│   │   └── __init__.py
│   ├── requirements.txt
│   └── env/                  # Python virtual environment
└── frontend/                 # Vanilla HTML/CSS/JS frontend
    ├── index.html
    ├── style.css
    └── app.js
```

The frontend is **served directly by the backend** at `http://localhost:8080/` — no separate dev server needed.

## Prerequisites

- Python 3.10+
- PostgreSQL (running on `localhost:5432`)
- A device with a built-in camera or an external webcam

## Setup & Installation

### 1. Clone

```bash
git clone https://github.com/sayedatiqurrahman/Face-Detection-Attendance-System.git
cd Face-Detection-Attendance-System
```

### 2. Create virtual environment

```bash
cd fastAPI-backend
python -m venv env
```

Activate it:
- **Windows (cmd):** `env\Scripts\activate`
- **Windows (PowerShell):** `env\Scripts\Activate.ps1`
- **Linux / macOS:** `source env/bin/activate`

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the database

Ensure PostgreSQL is running, then create a database named `face-detection-db`:

```bash
psql -U postgres -c "CREATE DATABASE face-detection-db"
```

Update credentials in `app/db.py` if needed (default: user `postgres`, password `1234`, db `face-detection-db`).

## Running

```bash
# From the fastAPI-backend directory (with venv activated)
python -m app.main
```

The server starts on **`http://0.0.0.0:8080`**.

- Open `http://localhost:8080` in a browser
- Click **Start Camera** to enable the camera (the browser will prompt for camera permission)
- Click **Start Attendance** to set a time window and begin marking attendance
- Enrolled students whose faces are recognised during the window are marked **Present**

## API Endpoints

| Method | Path                    | Description                        |
|--------|-------------------------|------------------------------------|
| GET    | `/`                     | Frontend (index.html)              |
| POST   | `/recognize`            | Recognise face(s) from Base64 frame|
| POST   | `/enroll`               | Enroll a new student               |
| POST   | `/attendance/start`     | Start an attendance session        |
| POST   | `/attendance/stop`      | Stop the current session           |
| GET    | `/attendance/session`   | Get current session status         |
| GET    | `/attendance/summary`   | Today's attendance summary         |


## Notes

- Face recognition uses the **buffalo_l** InsightFace model (GPU-accelerated if available, otherwise runs on CPU).
- The attendance time window supports crossing midnight (e.g. 22:00 → 02:00).
- All attendance data resets daily — the database is for MVP use and tables are recreated on startup.
