"""Exam Rescue: pick what to study when there isn't time for everything, and say why.

Value of a topic = how often it appeared in the student's own previous-year papers
                 + how many other topics depend on it
                 + how little of it has been covered.
Then a greedy value-per-minute selection inside the real time budget, with prerequisites kept ahead
of the topics that need them. Historical frequency is evidence, not a prediction.
"""

from dataclasses import dataclass

STATUS_MINUTES = {"not_started": 60, "in_progress": 40, "revised": 20, "practised": 10}
MODES = {
    "tomorrow": {"label": "Exam tomorrow", "factor": 0.5, "only_weak": False},
    "three_day": {"label": "Three-day revision", "factor": 0.8, "only_weak": False},
    "week": {"label": "One-week revision", "factor": 1.0, "only_weak": False},
    "zero": {"label": "Start from zero", "factor": 1.0, "only_weak": False},
    "weak": {"label": "Weak topics only", "factor": 0.8, "only_weak": True},
    "pyq": {"label": "Previous-year questions", "factor": 0.6, "only_weak": False},
}


@dataclass
class TopicInput:
    id: int
    title: str
    module: str
    status: str
    pyq_count: int = 0
    dependants: int = 0
    prerequisites: tuple[int, ...] = ()
    has_material: bool = False
    weak: bool = False
    est_minutes: int | None = None


@dataclass
class Pick:
    topic: TopicInput
    minutes: int
    value: float
    reason: str


def topic_minutes(topic: TopicInput, mode: str) -> int:
    status = "not_started" if mode == "zero" else topic.status
    base = topic.est_minutes or STATUS_MINUTES.get(status, 60)
    if mode == "pyq":
        base = 30 if topic.pyq_count else 15
    return max(10, int(round(base * MODES[mode]["factor"] / 5) * 5))


def topic_value(topic: TopicInput, mode: str) -> tuple[float, str]:
    coverage_gap = {"not_started": 2.0, "in_progress": 1.2, "revised": 0.5, "practised": 0.2}.get(
        "not_started" if mode == "zero" else topic.status, 1.0
    )
    value = 1.0 + topic.pyq_count * 1.5 + topic.dependants * 0.8 + coverage_gap + (0.2 if topic.has_material else 0) + (1.0 if topic.weak else 0)
    reasons = []
    if topic.pyq_count:
        reasons.append(f"asked {topic.pyq_count}× in your past papers")
    if topic.dependants:
        reasons.append(f"{topic.dependants} other topic{'s' if topic.dependants > 1 else ''} build on it")
    if topic.weak:
        reasons.append("your recent answers here were weak")
    reasons.append({"not_started": "not started yet", "in_progress": "half done", "revised": "already revised once", "practised": "already practised"}.get(topic.status, ""))
    return value, "; ".join(r for r in reasons if r)


def plan(topics: list[TopicInput], budget_minutes: int, mode: str) -> tuple[list[Pick], list[tuple[TopicInput, int, str]], int]:
    """Returns (chosen in study order, excluded with minutes+reason, minutes needed for everything)."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode}")
    pool = [t for t in topics if not MODES[mode]["only_weak"] or t.weak or t.status in {"not_started", "in_progress"}]
    if mode == "pyq":
        pool = [t for t in pool if t.pyq_count] or pool
    by_id = {t.id: t for t in pool}
    needed_total = sum(topic_minutes(t, mode) for t in pool)
    usable = int(budget_minutes * 0.9)  # leave a buffer: nobody studies at 100% efficiency

    scored = []
    for t in pool:
        value, reason = topic_value(t, mode)
        minutes = topic_minutes(t, mode)
        scored.append((value / minutes, value, minutes, t, reason))
    scored.sort(key=lambda row: row[0], reverse=True)

    chosen: dict[int, Pick] = {}
    spent = 0
    for _, value, minutes, topic, reason in scored:
        if topic.id in chosen:
            continue
        bundle = [(topic, minutes, value, reason)]
        for pre_id in topic.prerequisites:
            pre = by_id.get(pre_id)
            if pre and pre.id not in chosen and pre.status in {"not_started", "in_progress"}:
                pv, pr = topic_value(pre, mode)
                bundle.insert(0, (pre, topic_minutes(pre, mode), pv, f"prerequisite for {topic.title}; {pr}"))
        cost = sum(b[1] for b in bundle)
        if spent + cost > usable:
            continue
        for t, m, v, r in bundle:
            chosen[t.id] = Pick(t, m, v, r)
        spent += cost

    excluded = []
    for _, value, minutes, topic, reason in scored:
        if topic.id not in chosen:
            excluded.append((topic, minutes, f"Didn't fit in {budget_minutes} min; lower value per minute ({reason})"))

    # Study order: prerequisites first, then highest value.
    ordered: list[Pick] = []
    placed: set[int] = set()

    def place(pick: Pick) -> None:
        if pick.topic.id in placed:
            return
        for pre_id in pick.topic.prerequisites:
            if pre_id in chosen:
                place(chosen[pre_id])
        placed.add(pick.topic.id)
        ordered.append(pick)

    for pick in sorted(chosen.values(), key=lambda p: p.value, reverse=True):
        place(pick)
    return ordered, excluded, needed_total
