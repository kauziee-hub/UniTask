from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["student", "teacher"]
Source = Literal["unitask", "teams", "personal"]
SubmissionStatus = Literal["assigned", "working", "turned_in", "returned"]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: Role


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=1, max_length=12)


class AuthResponse(BaseModel):
    token: str | None = None
    user: UserRead | None = None
    needs_confirmation: bool = False
    message: str | None = None


class AuthConfig(BaseModel):
    provider: Literal["local", "cognito"]
    demo: bool = False


class DemoLogin(BaseModel):
    role: Role = "student"


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(default="", max_length=30)
    color: str = Field(default="#2f5d50", pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = Field(default=None, max_length=2000)


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=30)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = Field(default=None, max_length=2000)


class JoinRequest(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class CourseBrief(BaseModel):
    id: int
    name: str
    code: str
    color: str
    source: Source


class CourseRead(CourseBrief):
    description: str | None
    my_role: Literal["teacher", "student", "owner"]
    teacher_name: str | None
    join_code: str | None
    student_count: int
    open_count: int


class MemberRead(BaseModel):
    id: int
    name: str
    email: str
    joined_at: datetime


class ChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    old_value: str | None
    new_value: str | None
    detected_at: datetime
    seen: bool


class Priority(BaseModel):
    score: float
    tier: Literal["missed", "overdue", "now", "soon", "later", "someday"]
    reason: str
    start_by: datetime | None
    hours_left: float | None
    effort_minutes: int


class WorkItem(BaseModel):
    id: int
    title: str
    instructions: str | None
    course: CourseBrief | None
    source: Source
    external_url: str | None
    due_at: datetime | None
    points: int | None
    allow_late: bool
    attachment_name: str | None
    removed_at_source: bool
    status: SubmissionStatus
    effort_minutes: int | None
    text: str | None
    file_name: str | None
    submitted_at: datetime | None
    grade: int | None
    feedback: str | None
    submission_id: int | None
    changes: list[ChangeRead]
    priority: Priority
    kind: str = "assignment"
    due_confidence: str = "manual"
    last_verified_at: datetime | None = None
    source_status: str | None = None
    local_done_at: datetime | None = None
    snoozed_until: datetime | None = None
    snooze_reason: str | None = None
    notes: str | None = None
    providers: list[str] = []


class PlanBlock(BaseModel):
    item_id: int
    title: str
    course: CourseBrief | None
    minutes: int
    finishes_item: bool
    note: str


class TodayResponse(BaseModel):
    next: WorkItem | None
    focus: list[WorkItem]
    upcoming: list[WorkItem]
    overdue: list[WorkItem]
    changes: list[dict]
    teams: dict


class PlanResponse(BaseModel):
    minutes: int
    blocks: list[PlanBlock]
    left_over: int
    skipped: list[str]


class WorkUpdate(BaseModel):
    status: Literal["assigned", "working", "done"] | None = None
    effort_minutes: int | None = Field(default=None, ge=5, le=60 * 40)


class PersonalTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime | None = None
    course_id: int | None = None
    effort_minutes: int | None = Field(default=None, ge=5, le=60 * 40)
    notes: str | None = Field(default=None, max_length=4000)


class CourseworkUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=20000)
    due_at: datetime | None = None
    points: int | None = Field(default=None, ge=0, le=1000)
    allow_late: bool | None = None


class TeacherCourseworkRead(BaseModel):
    id: int
    course_id: int
    course_name: str
    title: str
    instructions: str | None
    due_at: datetime | None
    points: int | None
    allow_late: bool
    attachment_name: str | None
    created_at: datetime
    total: int
    turned_in: int
    returned: int
    late: int


class SubmissionRead(BaseModel):
    id: int | None
    student: MemberRead
    status: SubmissionStatus
    submitted_at: datetime | None
    late: bool
    text: str | None
    file_name: str | None
    grade: int | None
    feedback: str | None


class GradeRequest(BaseModel):
    grade: int | None = Field(default=None, ge=0, le=1000)
    feedback: str | None = Field(default=None, max_length=4000)
    return_to_student: bool = True


class TeamsStatus(BaseModel):
    configured: bool
    status: Literal["not_connected", "connected", "needs_consent", "expired", "error"]
    account: str | None
    last_synced_at: datetime | None
    last_error: str | None
    last_result: dict | None
    auto_sync_minutes: int


class ConnectResponse(BaseModel):
    auth_url: str


class TimetableUploadRead(BaseModel):
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    storage_provider: str
    uploaded_at: datetime
    file_url: str
