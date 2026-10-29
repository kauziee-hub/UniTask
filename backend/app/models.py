from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(10))  # "student" | "teacher"
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Set when the account lives in Amazon Cognito instead of the local table.
    cognito_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Course(Base):
    """A class. Teacher-owned classes have members; Teams-mirrored classes belong to one student."""

    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("owner_id", "source", "external_id", name="uq_course_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(30), default="")
    color: Mapped[str] = mapped_column(String(7), default="#2f5d50")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    join_code: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="unitask")  # "unitask" | "teams"
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    owner: Mapped[User] = relationship()
    members: Mapped[list["CourseMember"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    coursework: Mapped[list["Coursework"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class CourseMember(Base):
    __tablename__ = "course_members"
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_course_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # "teacher" | "student"
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    course: Mapped[Course] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Coursework(Base):
    """Anything with a deadline: a teacher's assignment, a synced Teams assignment, or a personal task."""

    __tablename__ = "coursework"
    __table_args__ = (UniqueConstraint("owner_id", "source", "external_id", name="uq_coursework_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=True)
    # Teams and personal items are private to owner_id; UniTask class work is visible to course members.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="unitask")  # "unitask" | "teams" | "personal"
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True, nullable=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_late: Mapped[bool] = mapped_column(Boolean, default=True)
    attachment_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attachment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    removed_at_source: Mapped[bool] = mapped_column(Boolean, default=False)
    # assignment | quiz | lab | assessment | task
    kind: Mapped[str] = mapped_column(String(20), default="assignment", server_default="assignment")
    # verified (from the source system) | manual (typed by the student) | inferred (extracted, needs confirming)
    due_confidence: Mapped[str] = mapped_column(String(10), default="manual", server_default="manual")
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    course: Mapped[Course | None] = relationship(back_populates="coursework")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="coursework", cascade="all, delete-orphan")
    changes: Mapped[list["CourseworkChange"]] = relationship(
        back_populates="coursework", cascade="all, delete-orphan", order_by="CourseworkChange.detected_at.desc()"
    )


class Submission(Base):
    """One student's progress on one piece of coursework."""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("coursework_id", "student_id", name="uq_submission"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    coursework_id: Mapped[int] = mapped_column(ForeignKey("coursework.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # "assigned" -> "working" -> "turned_in" -> "returned"
    status: Mapped[str] = mapped_column(String(12), default="assigned")
    effort_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # The student's own tracking, kept separate from what the source system reports.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_done_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    snooze_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    coursework: Mapped[Coursework] = relationship(back_populates="submissions")
    student: Mapped[User] = relationship()


class CourseworkChange(Base):
    """Something that changed at the source after we first saw it — e.g. Teams moved a due date."""

    __tablename__ = "coursework_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    coursework_id: Mapped[int] = mapped_column(ForeignKey("coursework.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # "created" | "due_changed" | "title_changed" | "removed"
    old_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    seen: Mapped[bool] = mapped_column(Boolean, default=False)

    coursework: Mapped[Coursework] = relationship(back_populates="changes")


class Connection(Base):
    """A student's link to an external source such as Microsoft Teams."""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_connection"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="connected")  # connected | needs_consent | error
    account_label: Mapped[str | None] = mapped_column(String(254), nullable=True)
    token_cache: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted MSAL cache
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted provider settings, e.g. a Moodle feed URL
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    flow: Mapped[str] = mapped_column(Text)  # encrypted MSAL auth-code flow
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class TimetableUpload(Base):
    __tablename__ = "timetable_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Null for uploads made before accounts existed; claimable through the legacy import.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    storage_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


from .academic_models import *  # noqa: E402,F401,F403 — register the academic tables
