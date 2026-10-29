"""Synthetic demo data for presentations. Every name, class and record here is invented and labelled "Demo".

Nothing is presented as coming from a real university, Microsoft Teams or any other system: the demo items
are personal or UniTask-class records with provider "demo". Safe to run more than once — it stops if the
demo student already exists.
"""

import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import link_material_topics, save_questions, save_syllabus, sha256
from .academic_models import (
    Attempt,
    Exam,
    Material,
    MaterialPage,
    Profile,
    RevisionCard,
    StudySession,
    TimetableEntry,
    Topic,
)
from .ingest import SourceEvent, ingest
from .models import Course, CourseMember, Coursework, Submission, User
from .security import hash_password
from .storage import get_storage

logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Kolkata")
TEACHER_PASSWORD = "demo-teacher-2026"
STUDENT_PASSWORD = "demo-student-2026"
TEACHERS = [("Dr. Meera Iyer (Demo)", "meera.iyer@example.edu"), ("Prof. Arjun Nair (Demo)", "arjun.nair@example.edu")]
STUDENTS = [("Riya Sharma (Demo)", "riya.sharma@example.edu"), ("Aditya Menon (Demo)", "aditya.menon@example.edu"), ("Sneha Pillai (Demo)", "sneha.pillai@example.edu")]

COMPILER_SYLLABUS = [
    {"title": "Lexical analysis", "topics": ["Tokens, lexemes and patterns", "Regular expressions", "Finite automata"]},
    {"title": "Syntax analysis", "topics": ["Context-free grammars", "FIRST and FOLLOW sets", "LL(1) parsing", "LR parsing"]},
    {"title": "Semantic analysis", "topics": ["Syntax-directed translation", "Type checking"]},
    {"title": "Code generation", "topics": ["Intermediate code", "Code optimization"]},
]
COMPILER_NOTES = [
    "Lexical analysis. The lexer reads characters and groups them into tokens. A token is a pair of a token name and an optional "
    "attribute; a lexeme is the actual character sequence; a pattern describes the lexemes of a token. Regular expressions "
    "describe patterns, and each regular expression can be converted to a finite automata recogniser.",
    "Finite automata. A deterministic finite automaton (DFA) has exactly one transition per state and input symbol. An NFA can have "
    "several, including epsilon moves. Thompson's construction turns a regular expression into an NFA; the subset construction "
    "turns an NFA into an equivalent DFA, which is then minimised.",
    "Context-free grammars and FIRST and FOLLOW sets. FIRST(X) is the set of terminals that begin strings derived from X. "
    "FOLLOW(A) is the set of terminals that can appear immediately to the right of A in some sentential form. Both sets are "
    "needed to build an LL(1) parsing table.",
    "LL(1) parsing. A grammar is LL(1) if, for every pair of productions A -> a | b, FIRST(a) and FIRST(b) are disjoint and, if "
    "b can derive epsilon, FIRST(a) and FOLLOW(A) are disjoint. Left recursion must be removed and common prefixes left-factored "
    "before an LL(1) parsing table can be built.",
    "LR parsing. LR parsers read input left to right and build a rightmost derivation in reverse. SLR uses FOLLOW sets to decide "
    "reductions; canonical LR(1) carries a lookahead in each item; LALR merges LR(1) states with identical cores. Shift-reduce "
    "and reduce-reduce conflicts show that a grammar is not in the class.",
    "Syntax-directed translation attaches semantic rules to productions. Synthesized attributes are computed from children; "
    "inherited attributes come from the parent or siblings. An S-attributed definition uses only synthesized attributes and "
    "can be evaluated during bottom-up parsing. Type checking verifies that operators are applied to compatible operands.",
    "Intermediate code and code optimization. Three-address code uses at most one operator per instruction. Basic blocks and "
    "flow graphs support optimization: common subexpression elimination, constant folding, dead code elimination and loop "
    "invariant code motion.",
]
COMPILER_PAPERS = {
    2023: "Q1. Explain FIRST and FOLLOW sets with an example grammar. [10]\nQ2. Construct a DFA from a regular expression using the subset construction. [15]\n"
    "Q3. Explain syntax-directed translation with a suitable example. [10]",
    2024: "Q1. Compute FIRST and FOLLOW sets for the given grammar and explain their use. [10]\nQ2. Explain LL(1) parsing and the conditions for a grammar to be LL(1). [15]\n"
    "Q3. Explain code optimization techniques with examples. [10]",
    2025: "Q1. Explain the FIRST and FOLLOW sets of a grammar with an example. [10]\nQ2. Compare SLR, canonical LR and LALR parsing. [15]\n"
    "Q3. Explain the LL(1) parsing table construction and the LL(1) conditions. [10]",
}


def _user(db: Session, name: str, email: str, role: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(name=name, email=email, role=role, password_hash=hash_password(TEACHER_PASSWORD if role == "teacher" else STUDENT_PASSWORD))
        db.add(user)
        db.flush()
    return user


def _material(db: Session, user: User, course: Course, title: str, kind: str, pages: list[str], year: int | None = None) -> Material:
    body = "\n\n".join(pages).encode()
    key = f"materials/{user.id}/demo-{course.id}-{kind}-{year or 0}.txt"
    get_storage().put(key, body, "text/plain")
    material = Material(user_id=user.id, course_id=course.id, kind=kind, title=title, filename=f"{title}.txt", storage_key=key,
                        content_type="text/plain", size_bytes=len(body), sha256=sha256(body + key.encode()), year=year,
                        status="ready", extractor="text", page_count=len(pages))
    db.add(material)
    db.flush()
    for number, text in enumerate(pages, start=1):
        db.add(MaterialPage(material_id=material.id, page_no=number, text=text))
    db.flush()
    db.refresh(material)
    if kind == "pyq":
        save_questions(db, material, pages)
    link_material_topics(db, material)
    return material


def _at(days: int, hour: int, minute: int = 0) -> datetime:
    day = datetime.now(TZ).date() + timedelta(days=days)
    return datetime.combine(day, time(hour, minute), TZ).astimezone(timezone.utc)


def seed(db: Session) -> bool:
    """Create the demo accounts and their synthetic data. Returns False if they already exist."""
    if db.scalar(select(User.id).where(User.email == STUDENTS[0][1])):
        return False
    meera, arjun = (_user(db, n, e, "teacher") for n, e in TEACHERS)
    riya, aditya, sneha = (_user(db, n, e, "student") for n, e in STUDENTS)

    def klass(owner: User, name: str, code: str, color: str, join: str) -> Course:
        course = Course(name=name, code=code, color=color, owner_id=owner.id, source="unitask", join_code=join,
                        description="Synthetic demo class for presentations. Not a real university course.")
        db.add(course)
        db.flush()
        db.add(CourseMember(course_id=course.id, user_id=owner.id, role="teacher"))
        for student in (riya, aditya, sneha):
            db.add(CourseMember(course_id=course.id, user_id=student.id, role="student"))
        return course

    compilers = klass(meera, "Compiler Design (Demo)", "CS301", "#2f5d50", "DEMO01")
    dbms = klass(arjun, "Database Systems (Demo)", "CS305", "#b5562b", "DEMO02")
    networks = klass(arjun, "Computer Networks (Demo)", "CS309", "#2d6a8e", "DEMO03")

    def post(course: Course, owner: User, title: str, due: datetime, points: int, text: str, kind: str = "assignment", allow_late: bool = True) -> Coursework:
        work = Coursework(course_id=course.id, created_by_id=owner.id, source="unitask", title=title, instructions=text, due_at=due,
                          points=points, allow_late=allow_late, kind=kind, due_confidence="verified")
        db.add(work)
        db.flush()
        return work

    lab = post(compilers, meera, "Lab 4: LL(1) parser", _at(1, 23, 59), 20,
               "Implement an LL(1) parser for the expression grammar from Module 2.\nSubmit your source code and a short PDF showing the FIRST and FOLLOW sets.", "lab")
    post(compilers, meera, "Quiz 2: syntax-directed translation", _at(5, 18), 10, "Online quiz on SDDs and SDTs. 20 minutes, open notes.", "quiz")
    post(dbms, arjun, "Normalization case study", _at(2, 17), 25, "Normalise the library schema from class to BCNF. Show each decomposition step.")
    late = post(dbms, arjun, "ER diagram: hospital system", _at(-1, 17), 15, "Draw the ER diagram for the hospital case. Late work accepted with a penalty.")
    post(networks, arjun, "TCP congestion control lab", _at(9, 23, 59), 20, "Run the simulation and report congestion window behaviour under loss.", "lab")
    graded = post(networks, arjun, "Socket programming: chat server", _at(-4, 23, 59), 30, "Build a multi-client chat server.", allow_late=False)
    for student in (aditya, sneha):
        db.add(Submission(coursework_id=lab.id, student_id=student.id, status="turned_in", text="Parser and FIRST/FOLLOW sets attached.",
                          submitted_at=datetime.now(timezone.utc) - timedelta(hours=3)))
    db.add(Submission(coursework_id=graded.id, student_id=riya.id, status="returned", text="Server code in the repo link.", grade=26,
                      feedback="Clean design. Handle client disconnects gracefully.", submitted_at=_at(-5, 20), returned_at=_at(-2, 10)))
    db.add(Submission(coursework_id=late.id, student_id=riya.id, status="working", effort_minutes=90))

    # Riya's own workspace.
    db.add(Profile(user_id=riya.id, university="Demo University", semester="Semester 5 (demo)", timezone="Asia/Kolkata", day_start="08:00",
                   day_end="23:00", daily_study_minutes=240, pace="steady", explain_style="examples", attendance_threshold=75,
                   background="Comfortable with programming in C and Python. Automata theory felt abstract; I learn best from worked examples.",
                   onboarded=True))
    save_syllabus(db, riya.id, compilers.id, COMPILER_SYLLABUS, confirmed=True, origin="manual")
    db.flush()
    _material(db, riya, compilers, "Compiler Design lecture notes (demo)", "notes", COMPILER_NOTES)
    for year, text in COMPILER_PAPERS.items():
        _material(db, riya, compilers, f"Compiler Design past paper {year} (demo)", "pyq", [text], year)
    topics = {t.title: t for t in db.scalars(select(Topic).where(Topic.user_id == riya.id, Topic.course_id == compilers.id))}
    for title in ("Tokens, lexemes and patterns", "Regular expressions"):
        topics[title].status = "revised"
    topics["Finite automata"].status = "in_progress"
    db.add(Exam(user_id=riya.id, course_id=compilers.id, title="Compiler Design mid-term (demo)", starts_at=_at(3, 10), duration_minutes=90, location="Demo hall 2"))
    db.add(Exam(user_id=riya.id, course_id=dbms.id, title="Database Systems quiz (demo)", starts_at=_at(8, 14), duration_minutes=60))
    for weekday, start, end, course, kind in [
        (0, "09:00", "10:00", compilers, "class"), (0, "14:00", "16:00", dbms, "lab"), (1, "10:00", "11:00", networks, "class"),
        (2, "09:00", "10:00", compilers, "class"), (2, "11:00", "12:00", dbms, "class"), (3, "10:00", "11:00", networks, "class"),
        (3, "15:00", "17:00", compilers, "lab"), (4, "09:00", "10:00", dbms, "class"),
    ]:
        db.add(TimetableEntry(user_id=riya.id, course_id=course.id, title=course.name.replace(" (Demo)", ""), weekday=weekday, start=start, end=end,
                              kind=kind, location="Demo block", source="manual", confirmed=True))
    ingest(db, riya.id, "demo", [
        SourceEvent("demo", "riya-1", "Revise Module 2 for the mid-term", _at(2, 21), subject="CS301", kind="task", confidence="manual",
                    description="Personal task (demo): FIRST/FOLLOW and LL(1) tables."),
        SourceEvent("demo", "riya-2", "Email project guide about review slot", None, kind="task", confidence="manual"),
    ])
    cards = [
        ("What does FIRST(X) contain?", "The terminals that can begin a string derived from X (plus epsilon if X can derive epsilon).", "FIRST and FOLLOW sets"),
        ("When is a grammar LL(1)?", "For A -> a | b: FIRST(a) and FIRST(b) are disjoint, and if b derives epsilon, FIRST(a) and FOLLOW(A) are disjoint.", "LL(1) parsing"),
        ("What does the subset construction do?", "Turns an NFA into an equivalent DFA whose states are sets of NFA states.", "Finite automata"),
    ]
    for front, back, topic in cards:
        db.add(RevisionCard(user_id=riya.id, topic_id=topics[topic].id, course_id=compilers.id, front=front, back=back, origin="manual",
                            due_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    for days_ago, minutes, topic in [(1, 50, "Regular expressions"), (2, 35, "Tokens, lexemes and patterns"), (4, 45, "Finite automata")]:
        started = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=2)
        db.add(StudySession(user_id=riya.id, topic_id=topics[topic].id, kind="topic", title=topic, planned_minutes=minutes, state="completed",
                            started_at=started, ended_at=started + timedelta(minutes=minutes), active_seconds=minutes * 60, checklist=[]))
    for correct in (True, False, False):
        db.add(Attempt(user_id=riya.id, topic_id=topics["Finite automata"].id, kind="check", correct=correct, confidence=2,
                       prompt="Demo practice question on finite automata", created_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db.commit()
    logger.info("Seeded synthetic demo accounts.")
    return True
