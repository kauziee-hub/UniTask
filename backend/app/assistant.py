from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import Assignment
from .schemas import AssistantResponse


def answer_assignment_question(prompt: str, db: Session) -> AssistantResponse:
    """Answer common deadline and planning questions using deterministic rules."""
    query = prompt.casefold()
    today = date.today()

    statement = (
        select(Assignment)
        .options(joinedload(Assignment.subject))
        .where(Assignment.status != "Completed")
        .order_by(Assignment.due_date.asc(), Assignment.id.asc())
    )
    tasks = list(db.scalars(statement).unique().all())

    if "today" in query:
        tasks = [task for task in tasks if task.due_date == today]
        heading = "Assignments due today:"
    elif "week" in query or "friday" in query:
        end_date = today + timedelta(days=7)
        tasks = [task for task in tasks if today <= task.due_date <= end_date]
        heading = "Assignments due in the next 7 days, ranked by deadline:"
    else:
        heading = "Pending assignments ranked by deadline:"

    if not tasks:
        return AssistantResponse(
            answer="No pending assignments match that request.",
            mode="deterministic",
            assignment_ids=[],
        )

    lines = [
        f"{index}. {task.title} ({task.subject.code}) — due {task.due_date.isoformat()} "
        f"[{task.status}]"
        for index, task in enumerate(tasks[:10], start=1)
    ]
    answer = f"{heading}\n" + "\n".join(lines)
    if "plan" in query or "hour" in query or "priorit" in query or "important" in query:
        answer += (
            "\n\nSuggested approach: start with the earliest deadline, then work through "
            "the remaining tasks in this order. Time estimates are not available."
        )

    return AssistantResponse(
        answer=answer,
        mode="deterministic",
        assignment_ids=[task.id for task in tasks[:10]],
    )
