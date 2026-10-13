"""Practice mode: pick the next question (weighted) and save ratings."""

import random
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.models import Question, QuestionType
from app.routes.questions import matches

router = APIRouter(prefix="/api/practice", tags=["practice"])

# Questions not practiced for this many days (or never) count as fully stale.
STALE_DAYS = 14


def weight(q: dict, now: datetime) -> float:
    """Higher weight = more likely to be picked.

    Low confidence counts up to 5x, staleness up to 8x, so a never-practiced
    confidence-1 question is 40x more likely than a confidence-5 one done today.
    """
    confidence_part = 6 - q["confidence"]  # 1..5
    if q.get("lastPracticed"):
        days = (now - datetime.fromisoformat(q["lastPracticed"])).total_seconds() / 86400
    else:
        days = STALE_DAYS
    recency_part = 1 + min(max(days, 0), STALE_DAYS) / 2  # 1..8
    return confidence_part * recency_part


def pick(questions: list[dict], now: datetime, exclude: str | None = None, rng=random) -> dict | None:
    # Avoid showing the same question twice in a row, unless it's the only one.
    pool = [q for q in questions if q["id"] != exclude] or questions
    if not pool:
        return None
    return rng.choices(pool, weights=[weight(q, now) for q in pool], k=1)[0]


@router.get("/next", response_model=Question)
def next_question(type: QuestionType | None = None, tag: str | None = None, exclude: str | None = None):
    candidates = [q for q in db.list_questions() if matches(q, type, tag, None, None, None)]
    q = pick(candidates, datetime.now(timezone.utc), exclude)
    if not q:
        raise HTTPException(404, "No questions match this filter")
    return q


class Rating(BaseModel):
    confidence: int = Field(ge=1, le=5)


@router.post("/{question_id}/rate", response_model=Question)
def rate(question_id: str, body: Rating):
    q = db.record_practice(question_id, body.confidence, db.now_iso())
    if not q:
        raise HTTPException(404, "Question not found")
    return q
