"""Keyword retrieval over a student's own material pages.

Deliberately simple and portable (works on SQLite and PostgreSQL): candidate pages are fetched with
LIKE on the rarest query terms, then ranked with BM25 in Python. Every hit carries the material id and
page number it came from, which is what citations are built from. Embeddings can replace the ranking
step behind the same `search()` signature once there is evidence keyword search falls short.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Material, MaterialPage

STOP = set(
    "a an and are as at be by do does for from how i in is it its me my of on or the this to was what when where "
    "which who why with explain define describe list write short note notes about between give".split()
)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9+#\-]*", text.lower()) if t not in STOP and len(t) > 1]


@dataclass
class Hit:
    material_id: int
    material_title: str
    course_id: int | None
    page_no: int
    excerpt: str
    score: float
    text: str

    def cite(self) -> dict:
        return {"material_id": self.material_id, "title": self.material_title, "page": self.page_no, "excerpt": self.excerpt}


def excerpt(text: str, terms: list[str], width: int = 260) -> str:
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, min(positions) - width // 3) if positions else 0
    snippet = text[start : start + width].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + snippet + ("…" if start + width < len(text) else "")


def search(
    db: Session,
    user_id: int,
    query: str,
    *,
    course_id: int | None = None,
    material_ids: list[int] | None = None,
    limit: int = 8,
) -> list[Hit]:
    terms = list(dict.fromkeys(tokens(query)))[:8]
    if not terms:
        return []
    statement = (
        select(MaterialPage, Material)
        .join(Material, Material.id == MaterialPage.material_id)
        .where(Material.user_id == user_id, Material.status == "ready")
        .where(or_(*[MaterialPage.text.ilike(f"%{term}%") for term in terms]))
        .limit(400)
    )
    if course_id is not None:
        statement = statement.where(Material.course_id == course_id)
    if material_ids:
        statement = statement.where(Material.id.in_(material_ids))
    rows = db.execute(statement).all()
    if not rows:
        return []

    docs = [(page, material, Counter(tokens(page.text))) for page, material in rows]
    average = sum(sum(c.values()) for _, _, c in docs) / len(docs) or 1
    def term_freq(counts: Counter, term: str) -> int:
        # Exact word, or a word it begins ("normal" -> "normalization") for terms of 4+ letters.
        if len(term) < 4:
            return counts.get(term, 0)
        return sum(n for word, n in counts.items() if word == term or word.startswith(term))

    df = {term: sum(1 for _, _, c in docs if term_freq(c, term)) for term in terms}
    hits: list[Hit] = []
    for page, material, counts in docs:
        length = sum(counts.values()) or 1
        score = 0.0
        for term in terms:
            tf = term_freq(counts, term)
            if not tf:
                continue
            idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        phrase = query.lower().strip()
        if len(phrase) > 4 and phrase in page.text.lower():
            score *= 1.5
        if score > 0:
            hits.append(
                Hit(material.id, material.title, material.course_id, page.page_no, excerpt(page.text, terms), round(score, 3), page.text)
            )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
