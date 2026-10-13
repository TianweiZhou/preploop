"""Practice mode: pick the next question (weighted) and save ratings.

A practice session goes through each matching question once. The browser
sends the ids it has already seen, so the server stays stateless.
"""

import random
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.feedback import public
from app.models import QuestionOut, QuestionType
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


def pick(questions: list[dict], now: datetime, rng=random) -> dict | None:
    if not questions:
        return None
    return rng.choices(questions, weights=[weight(q, now) for q in questions], k=1)[0]


class NextRequest(BaseModel):
    type: QuestionType | None = None
    tag: str | None = Field(None, max_length=40)
    seen: list[str] = Field(default_factory=list, max_length=5000)  # ids already shown this session


class NextResponse(BaseModel):
    question: QuestionOut | None  # None when the session is done
    total: int  # questions matching the filter
    remaining: int  # not yet seen, including the one returned


@router.post("/next", response_model=NextResponse)
def next_question(body: NextRequest):
    candidates = [q for q in db.list_questions() if matches(q, body.type, body.tag, None, None, None)]
    seen = set(body.seen)
    unseen = [q for q in candidates if q["id"] not in seen]
    q = pick(unseen, datetime.now(timezone.utc))
    return {"question": public(q) if q else None, "total": len(candidates), "remaining": len(unseen)}


class Rating(BaseModel):
    confidence: int = Field(ge=1, le=5)


@router.post("/{question_id}/rate", response_model=QuestionOut)
def rate(question_id: str, body: Rating):
    q = db.record_practice(question_id, body.confidence, db.now_iso())
    if not q:
        raise HTTPException(404, "Question not found")
    return public(q)
