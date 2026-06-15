from pydantic import BaseModel


class RecognizeRequest(BaseModel):
    image: str


class AttendanceTimeWindow(BaseModel):
    start_time: str
    end_time: str
