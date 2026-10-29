"""Request bodies for the student workspace API. Responses are built in workspace.py."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
HEX = r"^#[0-9a-fA-F]{6}$"


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    university: str | None = Field(default=None, max_length=160)
    semester: str | None = Field(default=None, max_length=60)
    timezone: str | None = Field(default=None, max_length=60)
    day_start: str | None = Field(default=None, pattern=HHMM)
    day_end: str | None = Field(default=None, pattern=HHMM)
    daily_study_minutes: int | None = Field(default=None, ge=30, le=16 * 60)
    pace: Literal["slow", "steady", "fast"] | None = None
    explain_style: Literal["examples", "concise", "step_by_step", "analogies"] | None = None
    background: str | None = Field(default=None, max_length=2000)
    attendance_threshold: int | None = Field(default=None, ge=1, le=100)
    onboarded: bool | None = None


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(default="", max_length=30)
    color: str = Field(default="#2f5d50", pattern=HEX)


class SubjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=30)
    color: str | None = Field(default=None, pattern=HEX)


class TopicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    parent_id: int | None = None
    est_minutes: int | None = Field(default=None, ge=5, le=600)


class TopicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: Literal["not_started", "in_progress", "revised", "practised"] | None = None
    est_minutes: int | None = Field(default=None, ge=5, le=600)
    position: int | None = None
    confirmed: bool | None = None


class SyllabusExtract(BaseModel):
    material_id: int | None = None
    text: str | None = Field(default=None, max_length=60000)


class SyllabusConfirm(BaseModel):
    accept: bool = True


class LinkCreate(BaseModel):
    prerequisite_id: int


class MaterialUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    kind: Literal["notes", "slides", "syllabus", "pyq", "lab_manual", "textbook", "other"] | None = None
    course_id: int | None = None
    year: int | None = Field(default=None, ge=1990, le=2100)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    course_id: int | None = None
    topic_id: int | None = None


class ExamCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    course_id: int | None = None
    starts_at: datetime
    duration_minutes: int = Field(default=90, ge=10, le=600)
    location: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    topic_ids: list[int] | None = None


class ExamUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    course_id: int | None = None
    starts_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=10, le=600)
    location: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class ExamTopics(BaseModel):
    topic_ids: list[int]


class RescueRequest(BaseModel):
    mode: Literal["tomorrow", "three_day", "week", "zero", "weak", "pyq"] = "tomorrow"
    hours: float | None = Field(default=None, gt=0, le=24 * 14)


class ReplanRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=14)


class BlockUpdate(BaseModel):
    state: Literal["planned", "done", "missed", "skipped"] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class SessionStart(BaseModel):
    kind: Literal["assignment", "topic", "revision", "rescue"] = "topic"
    coursework_id: int | None = None
    topic_id: int | None = None
    exam_id: int | None = None
    plan_block_id: int | None = None
    planned_minutes: int = Field(default=25, ge=5, le=240)
    title: str | None = Field(default=None, max_length=200)


class SessionUpdate(BaseModel):
    scratch: str | None = Field(default=None, max_length=50000)
    checklist: list[dict] | None = None
    resume: dict | None = None
    planned_minutes: int | None = Field(default=None, ge=5, le=240)


class SessionEnd(BaseModel):
    outcome: str | None = Field(default=None, max_length=2000)
    topic_status: Literal["in_progress", "revised", "practised"] | None = None


class CardCreate(BaseModel):
    front: str = Field(min_length=1, max_length=2000)
    back: str = Field(min_length=1, max_length=4000)
    topic_id: int | None = None
    course_id: int | None = None


class CardUpdate(BaseModel):
    front: str | None = Field(default=None, min_length=1, max_length=2000)
    back: str | None = Field(default=None, min_length=1, max_length=4000)


class CardReview(BaseModel):
    grade: Literal["again", "hard", "good", "easy"]
    confidence: int | None = Field(default=None, ge=1, le=5)


class PracticeAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=6000)
    confidence: int | None = Field(default=None, ge=1, le=5)
    self_correct: bool | None = None


class ConversationCreate(BaseModel):
    mode: Literal["tutor", "ask", "explain_back"] = "tutor"
    course_id: int | None = None
    topic_id: int | None = None


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class CheckAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    confidence: int | None = Field(default=None, ge=1, le=5)


class TimetableEntryIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    course_id: int | None = None
    weekday: int = Field(ge=0, le=6)
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    kind: Literal["class", "lab", "tutorial"] = "class"
    location: str | None = Field(default=None, max_length=80)


class TimetableEntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    course_id: int | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    start: str | None = Field(default=None, pattern=HHMM)
    end: str | None = Field(default=None, pattern=HHMM)
    kind: Literal["class", "lab", "tutorial"] | None = None
    location: str | None = Field(default=None, max_length=80)
    confirmed: bool | None = None


class AttendanceIn(BaseModel):
    course_id: int
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    present: bool


class FeedConnect(BaseModel):
    url: str = Field(min_length=10, max_length=2000)


class CaptureRequest(BaseModel):
    text: str = Field(min_length=3, max_length=6000)


class ConfirmDue(BaseModel):
    due_at: datetime | None = None


class LegacyImport(BaseModel):
    subjects: list[dict] = Field(default_factory=list, max_length=200)
    assignments: list[dict] = Field(default_factory=list, max_length=2000)


class ExtensionItem(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime | None = None
    subject: str | None = Field(default=None, max_length=160)
    kind: str = Field(default="assignment", max_length=20)
    url: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=8000)


class ExtensionIngest(BaseModel):
    items: list[ExtensionItem] = Field(max_length=500)
    snapshot: bool = False
    source: Literal["vtop"] = "vtop"


class Snooze(BaseModel):
    until: datetime
    reason: str | None = Field(default=None, max_length=200)


class NotesUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=20000)


class LocalDone(BaseModel):
    done: bool


class SubtaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    minutes: int | None = Field(default=None, ge=5, le=600)


class SubtaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    done: bool | None = None
    minutes: int | None = Field(default=None, ge=5, le=600)
    position: int | None = None
