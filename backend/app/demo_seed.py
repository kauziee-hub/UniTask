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

from .academic import link_material_topics, notify, save_questions, save_syllabus, sha256
from .academic_models import (
    Attempt,
    Conversation,
    Exam,
    InboxEvent,
    Material,
    MaterialPage,
    Message,
    Profile,
    RevisionCard,
    StudySession,
    TimetableEntry,
    Topic,
    TutorMemory,
)
from .ingest import SourceEvent, ingest
from .models import AuditEvent, Course, CourseMember, Coursework, CourseworkChange, Submission, User
from .retrieval import excerpt
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

DBMS_SYLLABUS = [
    {"title": "Data modelling", "topics": ["Entity-relationship model", "Relational model and keys", "Relational algebra"]},
    {"title": "SQL", "topics": ["SQL queries and joins", "Aggregation and nested queries"]},
    {"title": "Database design", "topics": ["Functional dependencies", "Normalization from 1NF to BCNF"]},
    {"title": "Transactions", "topics": ["Transactions and ACID properties", "Concurrency control"]},
    {"title": "Storage and indexing", "topics": ["Indexing and hashing", "B+ tree indexes"]},
]
DBMS_STATUS = {
    "Entity-relationship model": "practised", "Relational model and keys": "revised", "Relational algebra": "revised",
    "SQL queries and joins": "practised", "Aggregation and nested queries": "in_progress", "Functional dependencies": "in_progress",
    "Normalization from 1NF to BCNF": "in_progress",
}
DBMS_NOTES = [
    "Entity-relationship model. An entity set groups similar objects (Student, Course); each entity is described by attributes, and a "
    "key attribute identifies it uniquely. A relationship set such as Enrols connects entity sets and has a cardinality: one-to-one, "
    "one-to-many or many-to-many. Total participation is drawn with a double line. A weak entity set (Dependent) has no key of its own "
    "and is identified through its owner. Mapping to the relational model: every strong entity set becomes a table whose primary key "
    "is the entity key; a many-to-many relationship becomes its own table whose key combines the keys of both sides.",
    "Relational algebra and SQL queries and joins. Selection keeps the rows that satisfy a condition; projection keeps chosen columns; "
    "the natural join combines rows that agree on common attributes; union, set difference and rename complete the core operators. "
    "In SQL, SELECT ... FROM ... WHERE corresponds to projection, product and selection. An inner join keeps only matching rows, while "
    "a left outer join keeps every row of the left table and fills missing values with NULL. Aggregation uses GROUP BY with COUNT, SUM "
    "or AVG, and HAVING filters groups. A nested query uses IN, EXISTS or a scalar subquery in the WHERE clause.",
    "Functional dependencies and normalization from 1NF to BCNF. A functional dependency X -> Y means rows that agree on X agree on Y. "
    "1NF requires atomic values. 2NF removes partial dependencies of non-key attributes on part of a composite key. 3NF removes "
    "transitive dependencies: for every X -> A, either X is a superkey or A is part of a candidate key. BCNF is stricter: every "
    "non-trivial dependency X -> Y must have X as a superkey. Decompose using the violating dependency and check that the "
    "decomposition is lossless; BCNF may not preserve every dependency, while 3NF always can.",
    "Transactions and ACID properties. A transaction is a unit of work that must be atomic (all or nothing), consistent (moves the "
    "database between valid states), isolated (concurrent transactions behave as if run one at a time) and durable (committed changes "
    "survive crashes, using the log). Concurrency control keeps schedules serializable. Two-phase locking has a growing phase and a "
    "shrinking phase; strict 2PL holds exclusive locks until commit, which avoids cascading aborts. Deadlocks are detected with a "
    "wait-for graph or prevented with timestamp schemes such as wait-die and wound-wait.",
    "Indexing and hashing. An index maps search-key values to records. A primary (clustered) index follows the file order; a "
    "secondary index does not. Hashing is fast for equality search but useless for ranges. B+ tree indexes keep every key in the leaf "
    "level, link the leaves for range scans and keep the tree balanced: every node except the root is at least half full, so "
    "search, insertion and deletion cost O(log n) page reads. Insertion splits a full node and pushes the middle key up.",
]
NETWORKS_SYLLABUS = [
    {"title": "Network models", "topics": ["OSI reference model", "TCP/IP model"]},
    {"title": "Data link layer", "topics": ["Error detection and CRC", "Sliding window protocols"]},
    {"title": "Network layer", "topics": ["IP addressing and subnetting", "Routing algorithms"]},
    {"title": "Transport layer", "topics": ["UDP and TCP", "TCP congestion control"]},
    {"title": "Application layer", "topics": ["DNS name resolution", "HTTP request and response"]},
]
NETWORKS_STATUS = {
    "OSI reference model": "revised", "TCP/IP model": "revised", "Error detection and CRC": "revised",
    "Sliding window protocols": "in_progress", "IP addressing and subnetting": "in_progress", "UDP and TCP": "in_progress",
}
NETWORKS_NOTES = [
    "OSI reference model and TCP/IP model. The OSI reference model has seven layers: physical, data link, network, transport, "
    "session, presentation and application. Each layer offers a service to the layer above and adds its own header. The TCP/IP model "
    "used on the Internet has four or five layers: link, internet (IP), transport (UDP and TCP) and application. Session and "
    "presentation duties are left to applications. Data units: frame at the link layer, packet at the network layer, segment at transport.",
    "Error detection and CRC. Parity bits detect single-bit errors; the Internet checksum adds 16-bit words in one's complement. "
    "A cyclic redundancy check treats the frame as a polynomial, appends r zero bits, divides by a generator of degree r using "
    "modulo-2 arithmetic and sends the remainder as the CRC; the receiver divides again and expects a zero remainder. Sliding window "
    "protocols: stop-and-wait sends one frame at a time; Go-Back-N resends everything after a lost frame; Selective Repeat resends only "
    "the lost frame and needs a window of at most half the sequence space.",
    "IP addressing and subnetting. An IPv4 address has 32 bits written as four decimal octets. CIDR notation /24 gives the prefix "
    "length; a /26 subnet has 64 addresses and 62 usable hosts. Routing algorithms: distance vector routers send their table to "
    "neighbours and update with Bellman-Ford, which can suffer from count-to-infinity (split horizon helps). Link state routers flood "
    "link costs to every router and each one runs Dijkstra's shortest path algorithm. RIP is distance vector; OSPF is link state.",
    "UDP and TCP. UDP is connectionless and adds only ports and a checksum. TCP is connection-oriented: a three-way handshake, "
    "sequence numbers, cumulative ACKs and flow control through the receiver window. TCP congestion control: slow start doubles cwnd "
    "every RTT until it reaches ssthresh; congestion avoidance then adds one MSS per RTT (additive increase). Three duplicate ACKs "
    "trigger fast retransmit and fast recovery, halving cwnd (multiplicative decrease). A timeout sets ssthresh to half the window "
    "and restarts slow start from one MSS.",
    "DNS name resolution and HTTP request and response. DNS maps names to addresses through a hierarchy of root, top-level domain and "
    "authoritative servers. A resolver usually queries iteratively and caches answers for their TTL; record types include A, AAAA, "
    "CNAME, MX and NS. HTTP is a request and response protocol over TCP: a request line (GET /index.html HTTP/1.1), headers and an "
    "optional body; the response carries a status code such as 200, 301 or 404. HTTP/1.1 keeps connections persistent; cookies add "
    "state on top of a stateless protocol.",
]


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


DEMO_VERSION = 2  # bump when the demo data changes; SEED_DEMO=true servers then rebuild it


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
    normalization = post(dbms, arjun, "Normalization case study", _at(2, 17), 25, "Normalise the library schema from class to BCNF. Show each decomposition step.")
    late = post(dbms, arjun, "ER diagram: hospital system", _at(-1, 17), 15, "Draw the ER diagram for the hospital case. Late work accepted with a penalty.")
    tcp_lab = post(networks, arjun, "TCP congestion control lab", _at(9, 23, 59), 20, "Run the simulation and report congestion window behaviour under loss.", "lab")
    graded = post(networks, arjun, "Socket programming: chat server", _at(-4, 23, 59), 30, "Build a multi-client chat server.", allow_late=False)
    lab3 = post(compilers, meera, "Lab 3: Lexical analyser", _at(-6, 23, 59), 20,
                "Write a lexer for the mini-C token set from Module 1. Include a token table and test inputs.", "lab")
    problem_set2 = post(networks, arjun, "Problem set 2: framing and CRC", _at(-8, 23, 59), 10, "Five problems on bit stuffing, parity and CRC division.")
    problem_set3 = post(networks, arjun, "Problem set 3: IP addressing and subnetting", _at(0, 23, 59), 10,
                        "Subnet the given /24 for four departments and show each network, broadcast and host range.")
    for student in (aditya, sneha):
        db.add(Submission(coursework_id=lab.id, student_id=student.id, status="turned_in", text="Parser and FIRST/FOLLOW sets attached.",
                          submitted_at=datetime.now(timezone.utc) - timedelta(hours=3)))
    db.add(Submission(coursework_id=graded.id, student_id=riya.id, status="returned", text="Server code in the repo link.", grade=26,
                      feedback="Clean design. Handle client disconnects gracefully.", submitted_at=_at(-5, 20), returned_at=_at(-2, 10)))
    db.add(Submission(coursework_id=late.id, student_id=riya.id, status="working", effort_minutes=90))
    db.add(Submission(coursework_id=lab.id, student_id=riya.id, status="working", effort_minutes=150))
    db.add(Submission(coursework_id=normalization.id, student_id=riya.id, status="assigned", effort_minutes=120))
    db.add(Submission(coursework_id=problem_set3.id, student_id=riya.id, status="assigned", effort_minutes=45))
    for student, grade, submitted in ((riya, 18, _at(-7, 21, 30)), (aditya, 16, _at(-6, 22)), (sneha, 19, _at(-7, 18))):
        db.add(Submission(coursework_id=lab3.id, student_id=student.id, status="returned", text="Lexer source and token table attached.", grade=grade,
                          feedback="Good token table. Add test cases for nested comments." if student is riya else "Clear and well tested.",
                          submitted_at=submitted, returned_at=_at(-1, 16)))
    # One late (late work was allowed), so the on-time rate isn't a suspicious 100%.
    db.add(Submission(coursework_id=problem_set2.id, student_id=riya.id, status="turned_in", text="Scanned answers attached.", submitted_at=_at(-7, 10, 30)))

    # Riya's own workspace.
    db.add(Profile(user_id=riya.id, university="Demo University", semester="Semester 5 (demo)", timezone="Asia/Kolkata", day_start="08:00",
                   day_end="23:00", daily_study_minutes=240, pace="steady", explain_style="examples", attendance_threshold=75,
                   background="Comfortable with programming in C and Python. Automata theory felt abstract; I learn best from worked examples.",
                   onboarded=True))
    save_syllabus(db, riya.id, compilers.id, COMPILER_SYLLABUS, confirmed=True, origin="manual")
    save_syllabus(db, riya.id, dbms.id, DBMS_SYLLABUS, confirmed=True, origin="manual")
    save_syllabus(db, riya.id, networks.id, NETWORKS_SYLLABUS, confirmed=True, origin="manual")
    db.flush()
    compiler_notes = _material(db, riya, compilers, "Compiler Design lecture notes (demo)", "notes", COMPILER_NOTES)
    for year, text in COMPILER_PAPERS.items():
        _material(db, riya, compilers, f"Compiler Design past paper {year} (demo)", "pyq", [text], year)
    dbms_notes = _material(db, riya, dbms, "Database Systems lecture notes (demo)", "notes", DBMS_NOTES)
    networks_notes = _material(db, riya, networks, "Computer Networks lecture notes (demo)", "notes", NETWORKS_NOTES)
    topics = {t.title: t for t in db.scalars(select(Topic).where(Topic.user_id == riya.id, Topic.course_id == compilers.id))}
    for title in ("Tokens, lexemes and patterns", "Regular expressions"):
        topics[title].status = "revised"
    topics["Finite automata"].status = "in_progress"
    dbms_topics = {t.title: t for t in db.scalars(select(Topic).where(Topic.user_id == riya.id, Topic.course_id == dbms.id))}
    net_topics = {t.title: t for t in db.scalars(select(Topic).where(Topic.user_id == riya.id, Topic.course_id == networks.id))}
    for table, statuses in ((dbms_topics, DBMS_STATUS), (net_topics, NETWORKS_STATUS)):
        for title, status in statuses.items():
            table[title].status = status
    db.add(Exam(user_id=riya.id, course_id=compilers.id, title="Compiler Design mid-term (demo)", starts_at=_at(3, 10), duration_minutes=90, location="Demo hall 2"))
    dbms_quiz = Exam(user_id=riya.id, course_id=dbms.id, title="Database Systems quiz (demo)", starts_at=_at(8, 14), duration_minutes=60,
                     notes="Covers modules 1-3: ER model, relational algebra, SQL and normalization.")
    dbms_quiz.topics = [dbms_topics[t] for t in ("Entity-relationship model", "Relational model and keys", "Relational algebra", "SQL queries and joins",
                                                 "Aggregation and nested queries", "Functional dependencies", "Normalization from 1NF to BCNF")]
    db.add(dbms_quiz)
    for weekday, start, end, course, kind in [
        (0, "09:00", "10:00", compilers, "class"), (0, "14:00", "16:00", dbms, "lab"), (1, "10:00", "11:00", networks, "class"),
        (2, "09:00", "10:00", compilers, "class"), (2, "11:00", "12:00", dbms, "class"), (3, "10:00", "11:00", networks, "class"),
        (3, "15:00", "17:00", compilers, "lab"), (4, "09:00", "10:00", dbms, "class"),
    ]:
        db.add(TimetableEntry(user_id=riya.id, course_id=course.id, title=course.name.replace(" (Demo)", ""), weekday=weekday, start=start, end=end,
                              kind=kind, location="Demo block", source="manual", confirmed=True))
    # One ingest call, so the personal tasks don't each raise a "new work" inbox event.
    personal = ingest(db, riya.id, "demo", [
        SourceEvent("demo", "riya-1", "Revise Module 2 for the mid-term", _at(2, 21), subject="CS301", kind="task", confidence="manual",
                    description="Personal task (demo): FIRST/FOLLOW and LL(1) tables."),
        SourceEvent("demo", "riya-2", "Email project guide about review slot", None, kind="task", confidence="manual"),
        # No subject on these: a personal task filed under a teacher's class currently shows up in that teacher's coursework list.
        SourceEvent("demo", "riya-3", "Finish DBMS lab record", _at(-3, 18), kind="task", confidence="manual"),
        SourceEvent("demo", "riya-4", "Read the transport layer chapter before the TCP lab", _at(-2, 22), kind="task", confidence="manual"),
        SourceEvent("demo", "riya-5", "Practise FIRST and FOLLOW problems", _at(-5, 21), kind="task", confidence="manual"),
    ]).item_ids
    for work_id, finished, minutes in ((personal[2], _at(-3, 11, 15), 60), (personal[3], _at(-2, 20, 40), 45), (personal[4], _at(-5, 19), 40)):
        db.add(Submission(coursework_id=work_id, student_id=riya.id, status="turned_in", submitted_at=finished, effort_minutes=minutes))
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
    every_topic = {**topics, **dbms_topics, **net_topics}  # titles are unique across the three demo syllabi
    _activity(db, riya, every_topic, {"lab": lab, "lab3": lab3, "late": late}, {"dbms": dbms_notes, "networks": networks_notes})
    _tutor(db, riya, every_topic, compiler_notes)
    _inbox(db, riya, arjun, normalization=normalization, problem_set3=problem_set3, tcp_lab=tcp_lab, lab3=lab3,
           materials=(dbms_notes, networks_notes))
    db.add(AuditEvent(user_id=None, action="demo_seed", detail={"version": DEMO_VERSION}))
    db.commit()
    logger.info("Seeded synthetic demo accounts (version %s).", DEMO_VERSION)
    return True


def _demo_users(db: Session) -> list[User]:
    emails = [e for _, e in TEACHERS + STUDENTS]
    return [u for u in db.scalars(select(User).where(User.email.in_(emails))) if u.name.endswith("(Demo)")]


def is_current(db: Session) -> bool:
    for event in db.scalars(select(AuditEvent).where(AuditEvent.action == "demo_seed")):
        if (event.detail or {}).get("version", 0) >= DEMO_VERSION:
            return True
    return False


def refresh(db: Session) -> bool:
    """Replace an older demo workspace with the current one. Only touches the synthetic "(Demo)" accounts."""
    if _demo_users(db) and is_current(db):
        return False
    for user in _demo_users(db):
        db.delete(user)  # classes, work, files metadata and activity cascade with the account
    db.flush()
    db.commit()
    return seed(db)


def _activity(db: Session, riya: User, topics: dict[str, Topic], work: dict[str, Coursework], notes: dict[str, Material]) -> None:
    """Two weeks of believable study: focus sessions, practice answers (some weak, some strong) and cards due today."""
    now = datetime.now(timezone.utc)
    sessions = [
        # days ago, local start, minutes, kind, title, topic, coursework, outcome
        (3, (19, 0), 75, "assignment", "Lab 4: LL(1) parser", None, "lab", "FIRST/FOLLOW table done; parsing table half filled."),
        (3, (21, 30), 30, "revision", "Revision: compiler cards", "FIRST and FOLLOW sets", None, None),
        (5, (18, 0), 45, "topic", "SQL queries and joins", "SQL queries and joins", None, "Outer joins make sense now."),
        (6, (20, 0), 90, "assignment", "ER diagram: hospital system", None, "late", "Entities and relationships drafted; cardinalities left."),
        (8, (17, 30), 60, "assignment", "Lab 3: Lexical analyser", None, "lab3", "Lexer passes the sample inputs."),
        (10, (19, 0), 50, "topic", "Error detection and CRC", "Error detection and CRC", None, None),
        (11, (18, 30), 25, "revision", "Revision: OSI and TCP/IP", "OSI reference model", None, None),
    ]
    for days_ago, (hour, minute), minutes, kind, title, topic, work_key, outcome in sessions:
        started = _at(-days_ago, hour, minute)
        db.add(StudySession(user_id=riya.id, topic_id=topics[topic].id if topic else None, coursework_id=work[work_key].id if work_key else None,
                            kind=kind, title=title, planned_minutes=minutes, state="completed", started_at=started,
                            ended_at=started + timedelta(minutes=minutes), active_seconds=minutes * 60, checklist=[], outcome=outcome))

    practice = [
        # topic, prompt, (correct, confidence 1-5, days ago) per answer
        ("LL(1) parsing", "Is S -> aSb | ab LL(1)? Justify with FIRST sets.", [(False, 2, 6), (True, 2, 4), (False, 2, 3), (False, 1, 2)]),
        ("Regular expressions", "Write a regular expression for identifiers that start with a letter.", [(True, 4, 9), (True, 4, 7), (False, 3, 5), (True, 4, 3), (True, 5, 1)]),
        ("SQL queries and joins", "List students with no enrolments using a LEFT JOIN.", [(True, 4, 6), (True, 4, 5), (True, 5, 2)]),
        ("Normalization from 1NF to BCNF", "Is R(A, B, C) with A -> B and B -> C in BCNF? Decompose it if not.", [(False, 3, 4), (True, 3, 2), (False, 2, 1)]),
    ]
    for title, prompt, answers in practice:
        for correct, confidence, days_ago in answers:
            db.add(Attempt(user_id=riya.id, topic_id=topics[title].id, kind="question", correct=correct, confidence=confidence, prompt=prompt,
                           created_at=now - timedelta(days=days_ago, hours=3)))

    due_today = min(now - timedelta(minutes=5), _at(0, 7))
    cards = [
        ("What must hold for a relation to be in BCNF?", "For every non-trivial functional dependency X -> Y, X is a superkey.", "Normalization from 1NF to BCNF", "dbms", 3),
        ("What does isolation (the I in ACID) guarantee?", "Concurrent transactions behave as if they ran one at a time.", "Transactions and ACID properties", "dbms", 4),
        ("Why are the leaves of a B+ tree linked?", "So a range query can scan keys in order without going back up the tree.", "B+ tree indexes", "dbms", 5),
        ("What does TCP do on a timeout?", "Sets ssthresh to half the window, drops cwnd to one MSS and restarts slow start.", "TCP congestion control", "networks", 4),
        ("Distance vector vs link state routing?", "Distance vector shares tables with neighbours (Bellman-Ford); link state floods link costs and runs Dijkstra.", "Routing algorithms", "networks", 3),
    ]
    for front, back, topic, notes_key, page in cards:
        db.add(RevisionCard(user_id=riya.id, topic_id=topics[topic].id, course_id=topics[topic].course_id, front=front, back=back,
                            material_id=notes[notes_key].id, page_no=page, origin="manual", due_at=due_today))


def _tutor(db: Session, riya: User, topics: dict[str, Topic], compiler_notes: Material) -> None:
    """What the tutor has learned about Riya, and one short conversation that cites her own notes."""
    now = datetime.now(timezone.utc)
    for kind, topic, text, days_ago in [
        ("understood", "Regular expressions", "Builds an NFA from a regular expression confidently using Thompson's construction.", 9),
        ("preference", None, "Prefers a small worked example before the formal definition.", 12),
        ("misconception", "Finite automata", "Thought each DFA state matches one NFA state; in the subset construction a DFA state is a set of NFA states.", 4),
        ("struggle", "LL(1) parsing", "Mixes up FIRST and FOLLOW when a production can derive epsilon.", 3),
    ]:
        db.add(TutorMemory(user_id=riya.id, topic_id=topics[topic].id if topic else None, kind=kind, text=text, created_at=now - timedelta(days=days_ago)))

    automata = topics["Finite automata"]
    page = next(p for p in compiler_notes.pages if "subset construction" in p.text)
    asked = now - timedelta(days=1, hours=5)
    conversation = Conversation(user_id=riya.id, course_id=automata.course_id, topic_id=automata.id, mode="tutor",
                                title="Subset construction: NFA to DFA", created_at=asked, updated_at=asked + timedelta(minutes=1))
    db.add(conversation)
    db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", created_at=asked,
                   content="I'm fine with Thompson's construction, but why does the subset construction build DFA states out of sets of NFA states?"))
    db.add(Message(
        conversation_id=conversation.id,
        role="tutor",
        created_at=asked + timedelta(minutes=1),
        content=(
            "Think of the DFA as following every NFA path at the same time. After some input the NFA could be in several states at once, "
            "so one DFA state has to stand for that whole set [S1].\n\n"
            "A small example: the start set is {0, 1}. Reading 'a' takes state 0 to 2 and state 1 to 3, so the next DFA state is the "
            "epsilon-closure of {2, 3}. Repeat for every new set and every symbol until no new sets appear. A set is accepting if it "
            "contains any accepting NFA state.\n\n"
            "That's also why the result is deterministic: from each set there is exactly one next set per symbol."
        ),
        citations=[{"label": "S1", "material_id": compiler_notes.id, "title": compiler_notes.title, "page": page.page_no,
                    "excerpt": excerpt(page.text, ["subset construction"])}],
        check={
            "question": "From the DFA state {0, 1}, reading 'b' takes NFA state 0 to 0 and state 1 to 2. State 2 is the only accepting "
            "NFA state and there are no epsilon moves. What is the next DFA state, and is it accepting?",
            "expected": "{0, 2}. It is accepting because it contains NFA state 2.",
        },
    ))


def _inbox(db: Session, riya: User, teacher: User, *, normalization: Coursework, problem_set3: Coursework, tcp_lab: Coursework,
           lab3: Coursework, materials: tuple[Material, ...]) -> None:
    """Inbox events from the last three days (new work, a moved deadline, a grade, materials, a reminder). The three newest stay unread."""
    now = datetime.now(timezone.utc)

    def local(value: datetime) -> str:
        return value.astimezone(TZ).strftime("%a %d %b, %H:%M")

    old_due = tcp_lab.due_at - timedelta(days=2)
    moved_at = now - timedelta(hours=20)
    db.add(CourseworkChange(coursework_id=tcp_lab.id, kind="due_changed", old_value=old_due.isoformat(), new_value=tcp_lab.due_at.isoformat(),
                            detected_at=moved_at))
    events = [
        ("new_work", f"New: {normalization.title}", f"new:unitask:{normalization.id}", now - timedelta(hours=66),
         f"{teacher.name} posted this in {normalization.course.name}. Due {local(normalization.due_at)}.", f"/work/{normalization.id}", True),
        ("new_work", f"New: {problem_set3.title}", f"new:unitask:{problem_set3.id}", now - timedelta(hours=50),
         f"{teacher.name} posted this in {problem_set3.course.name}. Due {local(problem_set3.due_at)}.", f"/work/{problem_set3.id}", True),
        *[
            ("material_ready", f"{m.title}: ready to search", f"material:{m.id}:ready:{m.page_count}", now - timedelta(hours=hours),
             f"{m.page_count} pages read with text.", f"/library/{m.id}", True)
            for m, hours in zip(materials, (40, 30))
        ],
        ("due_changed", f"Deadline moved: {tcp_lab.title}", f"due:{tcp_lab.id}:{tcp_lab.due_at.isoformat()}", moved_at,
         f"{local(old_due)} → {local(tcp_lab.due_at)}", f"/work/{tcp_lab.id}", False),
        ("graded", f"Graded: {lab3.title}", f"graded:{lab3.id}", _at(-1, 16),
         "18/20 · Good token table. Add test cases for nested comments.", f"/work/{lab3.id}", False),
        ("reminder", f"Due within 24h: {problem_set3.title}", f"remind24:{problem_set3.id}:{problem_set3.due_at.isoformat()}",
         max(now - timedelta(hours=3), problem_set3.due_at - timedelta(hours=23)), f"Due {local(problem_set3.due_at)}.", f"/work/{problem_set3.id}", False),
    ]
    for kind, title, key, created, body, link, read in events:
        notify(db, riya.id, kind, title, key, body=body, link=link)
        event = db.scalar(select(InboxEvent).where(InboxEvent.user_id == riya.id, InboxEvent.dedupe_key == key))
        event.created_at = min(created, now)
        event.read_at = min(event.created_at + timedelta(minutes=45), now) if read else None
