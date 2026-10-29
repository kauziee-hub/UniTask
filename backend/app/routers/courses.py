"""Classes, class work and grading — the Teams-like side of UniTask."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, CourseMember, Coursework, Submission, User
from ..schemas import (
    CourseCreate,
    CourseRead,
    CourseUpdate,
    CourseworkUpdate,
    GradeRequest,
    JoinRequest,
    MemberRead,
    SubmissionRead,
    TeacherCourseworkRead,
)
from ..security import get_current_user, require_student, require_teacher
from ..services import download_link, get_course_for, get_submission, store_upload, to_work_item

router = APIRouter(prefix="/api", tags=["classes"])
JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_join_code() -> str:
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(6))


def _course_read(db: Session, course: Course, my_role: str, user: User) -> CourseRead:
    student_count = db.scalar(
        select(func.count()).select_from(CourseMember).where(
            CourseMember.course_id == course.id, CourseMember.role == "student"
        )
    )
    work_ids = select(Coursework.id).where(Coursework.course_id == course.id, Coursework.removed_at_source.is_(False))
    if my_role == "teacher":
        # Submissions waiting for the teacher to review.
        open_count = db.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.coursework_id.in_(work_ids), Submission.status == "turned_in"
            )
        )
    else:
        total = db.scalar(select(func.count()).select_from(work_ids.subquery()))
        done = db.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.coursework_id.in_(work_ids),
                Submission.student_id == user.id,
                Submission.status.in_(["turned_in", "returned"]),
            )
        )
        open_count = (total or 0) - (done or 0)
    return CourseRead(
        id=course.id,
        name=course.name,
        code=course.code,
        color=course.color,
        source=course.source,
        description=course.description,
        my_role=my_role,
        teacher_name=course.owner.name if course.source == "unitask" else None,
        join_code=course.join_code if my_role == "teacher" else None,
        student_count=student_count or 0,
        open_count=open_count or 0,
    )


@router.get("/courses", response_model=list[CourseRead])
def list_courses(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[CourseRead]:
    owned = list(db.scalars(select(Course).where(Course.owner_id == user.id)))
    joined = list(
        db.scalars(
            select(Course)
            .join(CourseMember, CourseMember.course_id == Course.id)
            .where(CourseMember.user_id == user.id, Course.owner_id != user.id)
        )
    )
    result = []
    for course in owned:
        result.append(_course_read(db, course, "teacher" if course.source == "unitask" else "owner", user))
    for course in joined:
        result.append(_course_read(db, course, "student", user))
    return sorted(result, key=lambda c: (c.source != "unitask", c.name.lower()))


@router.post("/courses", response_model=CourseRead, status_code=201)
def create_course(payload: CourseCreate, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    course = Course(
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        color=payload.color,
        description=payload.description,
        owner_id=user.id,
        source="unitask",
    )
    for _ in range(5):
        course.join_code = _new_join_code()
        db.add(course)
        try:
            db.flush()
            break
        except IntegrityError:
            db.rollback()
    db.add(CourseMember(course_id=course.id, user_id=user.id, role="teacher"))
    db.commit()
    db.refresh(course)
    return _course_read(db, course, "teacher", user)


@router.get("/courses/{course_id}", response_model=CourseRead)
def get_course(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course, role = get_course_for(db, course_id, user)
    return _course_read(db, course, role, user)


@router.patch("/courses/{course_id}", response_model=CourseRead)
def update_course(
    course_id: int, payload: CourseUpdate, user: User = Depends(require_teacher), db: Session = Depends(get_db)
):
    course, role = get_course_for(db, course_id, user)
    if role != "teacher":
        raise HTTPException(403, "Only the class teacher can edit it.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(course, field, value.strip().upper() if field == "code" else value)
    db.commit()
    return _course_read(db, course, role, user)


@router.post("/courses/{course_id}/join-code", response_model=CourseRead)
def rotate_join_code(course_id: int, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    course, role = get_course_for(db, course_id, user)
    if role != "teacher":
        raise HTTPException(403, "Only the class teacher can change the join code.")
    course.join_code = _new_join_code()
    db.commit()
    return _course_read(db, course, role, user)


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course, role = get_course_for(db, course_id, user)
    if role == "student":
        raise HTTPException(403, "Students can leave a class but not delete it.")
    db.delete(course)
    db.commit()
    return Response(status_code=204)


@router.post("/courses/join", response_model=CourseRead)
def join_course(payload: JoinRequest, user: User = Depends(require_student), db: Session = Depends(get_db)):
    course = db.scalar(select(Course).where(Course.join_code == payload.code.strip().upper()))
    if course is None:
        raise HTTPException(404, "No class uses that code. Check it with your teacher.")
    if db.scalar(
        select(CourseMember).where(CourseMember.course_id == course.id, CourseMember.user_id == user.id)
    ) is None:
        db.add(CourseMember(course_id=course.id, user_id=user.id, role="student"))
        db.commit()
    return _course_read(db, course, "student", user)


@router.delete("/courses/{course_id}/members/me", status_code=204)
def leave_course(course_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    member = db.scalar(select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user.id))
    if member is None:
        raise HTTPException(404, "You are not in this class.")
    db.delete(member)
    db.commit()
    return Response(status_code=204)


@router.get("/courses/{course_id}/members", response_model=list[MemberRead])
def list_members(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course, role = get_course_for(db, course_id, user)
    if role != "teacher":
        raise HTTPException(403, "Only the class teacher can see the roster.")
    members = db.scalars(
        select(CourseMember).where(CourseMember.course_id == course.id, CourseMember.role == "student")
    )
    return [MemberRead(id=m.user.id, name=m.user.name, email=m.user.email, joined_at=m.joined_at) for m in members]


@router.delete("/courses/{course_id}/members/{student_id}", status_code=204)
def remove_member(course_id: int, student_id: int, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    course, role = get_course_for(db, course_id, user)
    if role != "teacher":
        raise HTTPException(403, "Only the class teacher can remove students.")
    member = db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == course.id, CourseMember.user_id == student_id, CourseMember.role == "student"
        )
    )
    if member is None:
        raise HTTPException(404, "Student not in this class.")
    db.delete(member)
    db.commit()
    return Response(status_code=204)


# ---------- Class work ----------


def _teacher_work(db: Session, work_id: int, user: User) -> Coursework:
    work = db.get(Coursework, work_id)
    if work is None or work.source != "unitask" or work.course is None:
        raise HTTPException(404, "Assignment not found.")
    _, role = get_course_for(db, work.course_id, user)
    if role != "teacher":
        raise HTTPException(403, "Only the class teacher can manage this assignment.")
    return work


def _teacher_read(db: Session, work: Coursework) -> TeacherCourseworkRead:
    total = db.scalar(
        select(func.count()).select_from(CourseMember).where(
            CourseMember.course_id == work.course_id, CourseMember.role == "student"
        )
    )
    submissions = list(db.scalars(select(Submission).where(Submission.coursework_id == work.id)))
    turned_in = [s for s in submissions if s.status in {"turned_in", "returned"}]
    late = [s for s in turned_in if work.due_at and s.submitted_at and s.submitted_at > work.due_at]
    return TeacherCourseworkRead(
        id=work.id,
        course_id=work.course_id,
        course_name=work.course.name,
        title=work.title,
        instructions=work.instructions,
        due_at=work.due_at,
        points=work.points,
        allow_late=work.allow_late,
        attachment_name=work.attachment_name,
        created_at=work.created_at,
        total=total or 0,
        turned_in=len(turned_in),
        returned=len([s for s in submissions if s.status == "returned"]),
        late=len(late),
    )


@router.get("/courses/{course_id}/coursework")
def list_course_work(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course, role = get_course_for(db, course_id, user)
    works = list(
        db.scalars(
            select(Coursework)
            .where(Coursework.course_id == course.id)
            .order_by(Coursework.due_at.is_(None), Coursework.due_at.asc())
        )
    )
    if role == "teacher":
        return [_teacher_read(db, work) for work in works]
    visible = [w for w in works if w.source == "unitask" or w.owner_id == user.id]
    return [to_work_item(work, get_submission(db, work, user)) for work in visible]


@router.post("/courses/{course_id}/coursework", response_model=TeacherCourseworkRead, status_code=201)
async def create_course_work(
    course_id: int,
    title: str = Form(..., min_length=1, max_length=200),
    instructions: str | None = Form(default=None, max_length=20000),
    due_at: datetime | None = Form(default=None),
    points: int | None = Form(default=None, ge=0, le=1000),
    allow_late: bool = Form(default=True),
    attachment: UploadFile | None = File(default=None),
    user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    course, role = get_course_for(db, course_id, user)
    if role != "teacher":
        raise HTTPException(403, "Only the class teacher can post assignments.")
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    work = Coursework(
        course_id=course.id,
        created_by_id=user.id,
        source="unitask",
        title=title.strip(),
        instructions=(instructions or "").strip() or None,
        due_at=due_at,
        points=points,
        allow_late=allow_late,
    )
    if attachment is not None and attachment.filename:
        work.attachment_key, work.attachment_name, work.attachment_type = await store_upload(
            attachment, f"coursework/{course.id}"
        )
    db.add(work)
    db.commit()
    db.refresh(work)
    return _teacher_read(db, work)


@router.patch("/coursework/{work_id}", response_model=TeacherCourseworkRead)
def update_course_work(
    work_id: int, payload: CourseworkUpdate, user: User = Depends(require_teacher), db: Session = Depends(get_db)
):
    work = _teacher_work(db, work_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(work, field, value)
    db.commit()
    return _teacher_read(db, work)


@router.delete("/coursework/{work_id}", status_code=204)
def delete_course_work(work_id: int, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    work = _teacher_work(db, work_id, user)
    db.delete(work)
    db.commit()
    return Response(status_code=204)


@router.get("/coursework/{work_id}", response_model=TeacherCourseworkRead)
def get_course_work(work_id: int, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    return _teacher_read(db, _teacher_work(db, work_id, user))


@router.get("/coursework/{work_id}/attachment")
def coursework_attachment(work_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    work = db.get(Coursework, work_id)
    if work is None or work.course_id is None or not work.attachment_key:
        raise HTTPException(404, "No attachment.")
    get_course_for(db, work.course_id, user)
    return download_link(work.attachment_key, work.attachment_name or "attachment", work.attachment_type)


@router.get("/coursework/{work_id}/submissions", response_model=list[SubmissionRead])
def list_submissions(work_id: int, user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    work = _teacher_work(db, work_id, user)
    members = db.scalars(
        select(CourseMember).where(CourseMember.course_id == work.course_id, CourseMember.role == "student")
    )
    by_student = {s.student_id: s for s in db.scalars(select(Submission).where(Submission.coursework_id == work.id))}
    rows = []
    for member in members:
        s = by_student.get(member.user_id)
        submitted = s is not None and s.status in {"turned_in", "returned"}
        rows.append(
            SubmissionRead(
                id=s.id if s else None,
                student=MemberRead(id=member.user.id, name=member.user.name, email=member.user.email, joined_at=member.joined_at),
                status=s.status if s else "assigned",
                submitted_at=s.submitted_at if submitted else None,
                late=bool(submitted and work.due_at and s.submitted_at and s.submitted_at > work.due_at),
                text=s.text if submitted else None,
                file_name=s.file_name if submitted else None,
                grade=s.grade if s else None,
                feedback=s.feedback if s else None,
            )
        )
    order = {"turned_in": 0, "returned": 1, "working": 2, "assigned": 3}
    return sorted(rows, key=lambda r: (order[r.status], r.student.name.lower()))


@router.patch("/submissions/{submission_id}/grade", response_model=SubmissionRead)
def grade_submission(
    submission_id: int, payload: GradeRequest, user: User = Depends(require_teacher), db: Session = Depends(get_db)
):
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(404, "Submission not found.")
    work = _teacher_work(db, submission.coursework_id, user)
    if work.points is not None and payload.grade is not None and payload.grade > work.points:
        raise HTTPException(422, f"Grade cannot exceed {work.points} points.")
    submission.grade = payload.grade
    submission.feedback = (payload.feedback or "").strip() or None
    if payload.return_to_student:
        submission.status = "returned"
        submission.returned_at = datetime.now(timezone.utc)
    db.commit()
    member = db.scalar(
        select(CourseMember).where(CourseMember.course_id == work.course_id, CourseMember.user_id == submission.student_id)
    )
    student = submission.student
    return SubmissionRead(
        id=submission.id,
        student=MemberRead(id=student.id, name=student.name, email=student.email, joined_at=member.joined_at if member else submission.updated_at),
        status=submission.status,
        submitted_at=submission.submitted_at,
        late=bool(work.due_at and submission.submitted_at and submission.submitted_at > work.due_at),
        text=submission.text,
        file_name=submission.file_name,
        grade=submission.grade,
        feedback=submission.feedback,
    )


@router.get("/submissions/{submission_id}/file")
def submission_file(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    submission = db.get(Submission, submission_id)
    if submission is None or not submission.file_key:
        raise HTTPException(404, "No file on this submission.")
    if submission.student_id != user.id:
        _teacher_work(db, submission.coursework_id, user)
    return download_link(submission.file_key, submission.file_name or "submission", submission.file_type)


