"""Tables for the student's academic workspace: syllabus, materials, planning, study and revision.

Imported at the bottom of models.py so everything registers on the same metadata.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime
from .models import Course, utc_now


def _fk(table: str, nullable: bool = False, ondelete: str = "CASCADE"):
    return mapped_column(ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable, index=True)


class Profile(Base):
    """Per-student settings, availability and the learner model the tutor adapts to."""

    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    university: Mapped[str | None] = mapped_column(String(160), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(60), nullable=True)
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Kolkata")
    day_start: Mapped[str] = mapped_column(String(5), default="08:00")
    day_end: Mapped[str] = mapped_column(String(5), default="23:00")
    daily_study_minutes: Mapped[int] = mapped_column(Integer, default=240)
    pace: Mapped[str] = mapped_column(String(12), default="steady")  # slow | steady | fast
    explain_style: Mapped[str] = mapped_column(String(20), default="examples")  # examples | concise | step_by_step | analogies
    background: Mapped[str | None] = mapped_column(Text, nullable=True)  # in the student's own words
    attendance_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)  # the student's university rule
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    ingest_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class CourseworkSource(Base):
    """Every place an item was seen. One assignment can be found in Teams *and* a Moodle feed."""

    __tablename__ = "coursework_sources"
    __table_args__ = (UniqueConstraint("owner_id", "provider", "external_id", name="uq_cw_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    coursework_id: Mapped[int] = _fk("coursework")
    owner_id: Mapped[int] = _fk("users")
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    coursework_id: Mapped[int] = _fk("coursework")
    user_id: Mapped[int] = _fk("users")
    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[str] = mapped_column(String(10), default="manual")  # manual | ai


exam_topics = Table(
    "exam_topics",
    Base.metadata,
    Column("exam_id", ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
)


class Topic(Base):
    """A syllabus node: a module (parent_id null) or a topic inside one."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    course_id: Mapped[int] = _fk("courses")
    parent_id: Mapped[int | None] = _fk("topics", nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="not_started")  # not_started | in_progress | revised | practised
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    origin: Mapped[str] = mapped_column(String(10), default="manual")  # manual | extracted
    est_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_studied_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    course: Mapped[Course] = relationship()


class TopicLink(Base):
    """from_topic is a prerequisite of to_topic. AI suggestions stay flagged until the student accepts."""

    __tablename__ = "topic_links"
    __table_args__ = (UniqueConstraint("from_topic_id", "to_topic_id", name="uq_topic_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    from_topic_id: Mapped[int] = _fk("topics")
    to_topic_id: Mapped[int] = _fk("topics")
    suggested: Mapped[bool] = mapped_column(Boolean, default=False)


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    course_id: Mapped[int | None] = _fk("courses", nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    course: Mapped[Course | None] = relationship()
    topics: Mapped[list[Topic]] = relationship(secondary=exam_topics)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    course_id: Mapped[int | None] = _fk("courses", nullable=True)
    kind: Mapped[str] = mapped_column(String(12), default="notes")  # notes | slides | syllabus | pyq | lab_manual | textbook | other
    title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued | processing | ready | needs_ocr | failed
    extractor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    course: Mapped[Course | None] = relationship()
    pages: Mapped[list["MaterialPage"]] = relationship(cascade="all, delete-orphan", order_by="MaterialPage.page_no")


class MaterialPage(Base):
    __tablename__ = "material_pages"
    __table_args__ = (UniqueConstraint("material_id", "page_no", name="uq_material_page"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = _fk("materials")
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")


class MaterialTopic(Base):
    __tablename__ = "material_topics"
    __table_args__ = (UniqueConstraint("material_id", "topic_id", "page_no", name="uq_material_topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = _fk("materials")
    topic_id: Mapped[int] = _fk("topics")
    page_no: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, default=0)


class Question(Base):
    """A previous-year question, kept verbatim with its year and page."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    material_id: Mapped[int] = _fk("materials")
    course_id: Mapped[int | None] = _fk("courses", nullable=True)
    topic_id: Mapped[int | None] = _fk("topics", nullable=True, ondelete="SET NULL")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pattern_key: Mapped[str] = mapped_column(String(64), index=True)


class PlanBlock(Base):
    __tablename__ = "plan_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    coursework_id: Mapped[int | None] = _fk("coursework", nullable=True)
    topic_id: Mapped[int | None] = _fk("topics", nullable=True)
    exam_id: Mapped[int | None] = _fk("exams", nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(12), default="work")  # work | study | revision | rescue
    state: Mapped[str] = mapped_column(String(10), default="planned")  # planned | done | missed | skipped
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    plan: Mapped[str] = mapped_column(String(20), default="week")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    coursework_id: Mapped[int | None] = _fk("coursework", nullable=True, ondelete="SET NULL")
    topic_id: Mapped[int | None] = _fk("topics", nullable=True, ondelete="SET NULL")
    exam_id: Mapped[int | None] = _fk("exams", nullable=True, ondelete="SET NULL")
    plan_block_id: Mapped[int | None] = _fk("plan_blocks", nullable=True, ondelete="SET NULL")
    kind: Mapped[str] = mapped_column(String(12), default="topic")  # assignment | topic | revision | rescue
    title: Mapped[str] = mapped_column(String(200))
    planned_minutes: Mapped[int] = mapped_column(Integer, default=25)
    state: Mapped[str] = mapped_column(String(10), default="active")  # active | paused | completed | abandoned
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    resumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    scratch: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    resume: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    course_id: Mapped[int | None] = _fk("courses", nullable=True, ondelete="SET NULL")
    title: Mapped[str] = mapped_column(String(160))
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    start: Mapped[str] = mapped_column(String(5))  # "09:00", local time
    end: Mapped[str] = mapped_column(String(5))
    kind: Mapped[str] = mapped_column(String(10), default="class")  # class | lab | tutorial
    location: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | image | ics
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)


class AttendanceMark(Base):
    __tablename__ = "attendance_marks"
    __table_args__ = (UniqueConstraint("user_id", "course_id", "date", name="uq_attendance"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    course_id: Mapped[int] = _fk("courses")
    date: Mapped[str] = mapped_column(String(10))
    present: Mapped[bool] = mapped_column(Boolean)


class RevisionCard(Base):
    __tablename__ = "revision_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    topic_id: Mapped[int | None] = _fk("topics", nullable=True, ondelete="SET NULL")
    course_id: Mapped[int | None] = _fk("courses", nullable=True, ondelete="SET NULL")
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    material_id: Mapped[int | None] = _fk("materials", nullable=True, ondelete="SET NULL")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[str] = mapped_column(String(10), default="manual")  # manual | ai | mistake
    due_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Attempt(Base):
    """Evidence: one answer to a card, a practice question or a tutor check question."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    topic_id: Mapped[int | None] = _fk("topics", nullable=True, ondelete="SET NULL")
    card_id: Mapped[int | None] = _fk("revision_cards", nullable=True, ondelete="SET NULL")
    question_id: Mapped[int | None] = _fk("questions", nullable=True, ondelete="SET NULL")
    kind: Mapped[str] = mapped_column(String(10), default="card")  # card | question | check | explain
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_inbox_dedupe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    # new_work | due_changed | removed | material_ready | announcement | graded | sync_error | reminder
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="unitask")
    dedupe_key: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    emailed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    provider: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | ok | failed
    counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    course_id: Mapped[int | None] = _fk("courses", nullable=True, ondelete="SET NULL")
    topic_id: Mapped[int | None] = _fk("topics", nullable=True, ondelete="SET NULL")
    mode: Mapped[str] = mapped_column(String(12), default="tutor")  # tutor | ask | explain_back
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    messages: Mapped[list["Message"]] = relationship(cascade="all, delete-orphan", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = _fk("conversations")
    role: Mapped[str] = mapped_column(String(10))  # user | tutor
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    check: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class TutorMemory(Base):
    """What the tutor has learned about this student: misconceptions, what clicked, preferences."""

    __tablename__ = "tutor_memory"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = _fk("users")
    topic_id: Mapped[int | None] = _fk("topics", nullable=True, ondelete="SET NULL")
    kind: Mapped[str] = mapped_column(String(14))  # misconception | understood | preference | struggle
    text: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = _fk("users", nullable=True, ondelete="SET NULL")
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
