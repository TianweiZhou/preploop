"""Pydantic models. Length limits keep junk out of DynamoDB."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

QuestionType = Literal["technical", "behavioral"]


class Star(BaseModel):
    situation: str = Field("", max_length=4000)
    task: str = Field("", max_length=4000)
    action: str = Field("", max_length=4000)
    result: str = Field("", max_length=4000)


class QuestionIn(BaseModel):
    """Fields I can create or edit."""

    type: QuestionType
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field("", max_length=10000)
    star: Star | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    confidence: int = Field(3, ge=1, le=5)
    notes: str = Field("", max_length=4000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question can't be blank")
        return v

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: list[str]) -> list[str]:
        # Trim, drop empties, dedupe (case-insensitive), keep order.
        seen, out = set(), []
        for t in tags:
            t = t.strip()[:40]
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out

    @model_validator(mode="after")
    def star_only_for_behavioral(self):
        if self.type != "behavioral":
            self.star = None
        return self


class QuestionBase(QuestionIn):
    """A question with id and practice stats."""

    id: str
    lastPracticed: str | None = None
    timesPracticed: int = 0
    createdAt: str
    updatedAt: str


class Question(QuestionBase):
    """What's stored in DynamoDB. aiFeedback holds the last few AI reviews
    ({answerHash, modelId, feedback, createdAt}), newest first."""

    aiFeedback: list[dict] = Field(default_factory=list)


class QuestionOut(QuestionBase):
    """What the API returns: just the scores of the latest review of the
    current answer, not the full stored feedback history."""

    lastFeedback: dict | None = None
