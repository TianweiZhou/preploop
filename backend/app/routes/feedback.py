"""POST /api/feedback: AI feedback on a saved question or on a raw answer.

For saved questions, results are stored on the question. Asking again about
the same answer (same type, question, and text) with the same model returns
the stored result without calling Bedrock, unless force is true.
"""

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
    force: bool = False  # skip the stored result and ask the model again

    @model_validator(mode="after")
    def need_id_or_question(self):
        if not self.question_id and not (self.question and self.type):
            raise ValueError("send question_id, or question and type")
        return self


@router.post("/feedback")
def get_feedback(body: FeedbackRequest):
    q = None
    if body.question_id:
        q = db.get_question(body.question_id)
        if not q:
            raise HTTPException(404, "Question not found")
        type, question, tags = q["type"], q["question"], q.get("tags", [])
        # A fresh answer typed in practice mode wins over the saved one.
        answer = body.answer if body.answer is not None else feedback.review_text(q.get("answer", ""), q.get("star"))
    else:
        type, question, tags, answer = body.type, body.question, body.tags, body.answer or ""

    if not answer.strip():
        raise HTTPException(400, "There's no answer to review yet.")

    model = feedback.model_id()
    hash = feedback.answer_hash(type, question, answer)
    if q and not body.force:
        stored = feedback.find_stored(q, hash, model)
        if stored:
            return {"feedback": stored["feedback"], "model_id": stored["modelId"],
                    "created_at": stored["createdAt"], "cached": True}

    try:
        result = feedback.get_feedback(type, question, answer, tags).model_dump()
    except feedback.FeedbackError as e:
        raise HTTPException(e.status, e.message)

    entry = {"answerHash": hash, "modelId": model, "feedback": result, "createdAt": db.now_iso()}
    if q:
        db.save_feedback(q["id"], feedback.add_stored(q, entry))
    return {"feedback": result, "model_id": model, "created_at": entry["createdAt"], "cached": False}
