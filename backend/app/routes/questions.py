"""Question library CRUD, with filtering, search, and sorting done in Python."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response

from app import db
from app.feedback import public
from app.models import Question, QuestionIn, QuestionOut, QuestionType

router = APIRouter(prefix="/api/questions", tags=["questions"])


def matches(q: dict, type: str | None, tag: str | None, min_conf: int | None,
            max_conf: int | None, text: str | None) -> bool:
    """Shared filter, also used by practice mode."""
    if type and q["type"] != type:
        return False
    if tag and tag.lower() not in (t.lower() for t in q.get("tags", [])):
        return False
    if min_conf is not None and q["confidence"] < min_conf:
        return False
    if max_conf is not None and q["confidence"] > max_conf:
        return False
    if text:
        star = q.get("star") or {}
        haystack = " ".join([q["question"], q.get("answer", ""), q.get("notes", ""),
                             *q.get("tags", []), *star.values()]).lower()
        if text.lower() not in haystack:
            return False
    return True


@router.get("", response_model=list[QuestionOut])
def list_questions(
    type: QuestionType | None = None,
    tag: str | None = None,
    min_conf: int | None = Query(None, ge=1, le=5),
    max_conf: int | None = Query(None, ge=1, le=5),
    q: str | None = Query(None, max_length=200),
    sort: Literal["createdAt", "confidence", "lastPracticed"] = "createdAt",
    order: Literal["asc", "desc"] = "desc",
):
    items = [i for i in db.list_questions() if matches(i, type, tag, min_conf, max_conf, q)]
    # Never-practiced sorts as oldest.
    items.sort(key=lambda i: i.get(sort) or "", reverse=(order == "desc"))
    return [public(i) for i in items]


@router.post("", response_model=QuestionOut, status_code=201)
def create_question(body: QuestionIn):
    now = db.now_iso()
    item = Question(**body.model_dump(), id=str(uuid.uuid4()), createdAt=now, updatedAt=now).model_dump()
    db.put_question(item)
    return public(item)


def get_or_404(question_id: str) -> dict:
    item = db.get_question(question_id)
    if not item:
        raise HTTPException(404, "Question not found")
    return item


@router.get("/{question_id}", response_model=QuestionOut)
def get_question(question_id: str):
    return public(get_or_404(question_id))


@router.put("/{question_id}", response_model=QuestionOut)
def update_question(question_id: str, body: QuestionIn):
    existing = get_or_404(question_id)
    # Replace editable fields, keep id, created date, practice stats, and stored feedback.
    item = Question(**{**existing, **body.model_dump(), "updatedAt": db.now_iso()}).model_dump()
    db.put_question(item)
    return public(item)


@router.delete("/{question_id}", status_code=204)
def delete_question(question_id: str):
    if not db.delete_question(question_id):
        raise HTTPException(404, "Question not found")
    return Response(status_code=204)
