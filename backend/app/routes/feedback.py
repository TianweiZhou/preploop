"""POST /api/feedback: AI feedback on a saved question or on a raw answer."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app import db, feedback
from app.models import QuestionType

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """Either question_id (optionally with a fresh answer), or a raw question."""

    question_id: str | None = None
    question: str | None = Field(None, max_length=2000)
    type: QuestionType | None = None
    answer: str | None = Field(None, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def need_id_or_question(self):
        if not self.question_id and not (self.question and self.type):
            raise ValueError("send question_id, or question and type")
        return self


def _with_star(answer: str, star: dict | None) -> str:
    """Add saved STAR notes to the answer so the model sees the full story."""
    parts = [f"{k.capitalize()}: {v}" for k, v in (star or {}).items() if v]
    return "\n\n".join(filter(None, [answer, "\n".join(parts)]))


@router.post("/feedback")
def get_feedback(body: FeedbackRequest):
    if body.question_id:
        q = db.get_question(body.question_id)
        if not q:
            raise HTTPException(404, "Question not found")
        type, question, tags = q["type"], q["question"], q.get("tags", [])
        # A fresh answer typed in practice mode wins over the saved one.
        answer = body.answer if body.answer is not None else _with_star(q.get("answer", ""), q.get("star"))
    else:
        type, question, tags, answer = body.type, body.question, body.tags, body.answer or ""

    if not answer.strip():
        raise HTTPException(400, "There's no answer to review yet.")

    try:
        result = feedback.get_feedback(type, question, answer, tags)
    except feedback.FeedbackError as e:
        raise HTTPException(e.status, e.message)
    return {"feedback": result.model_dump(), "model_id": feedback.model_id()}
