"""AI feedback through the Bedrock Converse API.

Converse works the same for Nova and Claude, so switching models is just a
FEEDBACK_MODEL_ID change. Prompts are kept short so cheaper models follow them.
"""

import json
import os
import re
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ReadTimeoutError
from pydantic import BaseModel, ValidationError, field_validator


class FeedbackError(Exception):
    """An error with a message that's safe to show in the UI."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---- Expected output ----

class Scores(BaseModel):
    clarity: int
    structure: int
    specificity: int

    @field_validator("clarity", "structure", "specificity", mode="before")
    @classmethod
    def to_1_5(cls, v):
        # Models sometimes return 3.5 or "4". Round and clamp instead of failing.
        return min(5, max(1, round(float(v))))


class Feedback(BaseModel):
    scores: Scores
    strengths: list[str]
    gaps: list[str]
    suggested_answer: str
    follow_up_questions: list[str]

    @field_validator("strengths", "gaps", "follow_up_questions", mode="before")
    @classmethod
    def to_list(cls, v):
        return [v] if isinstance(v, str) else v

    @field_validator("suggested_answer")
    @classmethod
    def no_em_dashes(cls, v: str) -> str:
        return re.sub(r"\s*—\s*", ", ", v).strip()


def parse_feedback(text: str) -> Feedback:
    """Pull the JSON object out of the model reply. Raises ValueError if it can't."""
    text = re.sub(r"```(?:json)?", "", text)  # strip code fences
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in reply")
    try:
        return Feedback.model_validate(json.loads(text[start:end + 1]))
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        raise ValueError(str(e)) from e


# ---- Prompts ----

SYSTEM_PROMPT = """You are an experienced interviewer reviewing a candidate's practice answer.
Be direct and honest, not flattering. Point out real weaknesses.

Reply with ONLY a JSON object. No markdown, no code fences, no text before or after it.
Use exactly this shape:
{"scores": {"clarity": 1-5, "structure": 1-5, "specificity": 1-5}, "strengths": ["..."], "gaps": ["..."], "suggested_answer": "...", "follow_up_questions": ["..."]}

Scores are whole numbers from 1 (poor) to 5 (excellent). Give 1 to 4 items in each list."""

GUIDANCE = {
    "behavioral": """- Check the STAR structure (situation, task, action, result).
- Flag results that are not measurable.
- Flag vague "we" where the candidate should say "I".
- Keep suggested_answer short enough to say out loud in 1 to 2 minutes.""",
    "technical": """- Check accuracy and depth.
- Flag errors and missing tradeoffs.
- Say what a senior interviewer would expect to hear.""",
}

STYLE = """For suggested_answer: keep the candidate's own voice. Make it concise, natural, and conversational.
No corporate buzzwords. Do not use em dashes."""

RETRY_REMINDER = "That was not valid JSON. Reply again with ONLY the JSON object in the exact shape asked for. No other text."


def build_prompt(type: str, question: str, answer: str, tags: list[str]) -> str:
    return f"""Question type: {type}
Tags: {", ".join(tags) or "none"}

Question:
{question}

Candidate's answer:
{answer}

How to review:
{GUIDANCE[type]}

{STYLE}

Return the JSON now."""


# ---- Bedrock ----

def model_id() -> str:
    return os.environ["FEEDBACK_MODEL_ID"]


@lru_cache
def bedrock_client():
    region = os.environ.get("BEDROCK_REGION") or None
    # Keep total time well under the Lambda timeout. Standard retries handle brief throttling.
    config = Config(read_timeout=25, connect_timeout=5, retries={"max_attempts": 2, "mode": "standard"})
    return boto3.client("bedrock-runtime", region_name=region, config=config)


def _converse(messages: list[dict]) -> str:
    try:
        resp = bedrock_client().converse(
            modelId=model_id(),
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            inferenceConfig={"maxTokens": 1500, "temperature": 0.3},
        )
    except ClientError as e:
        raise _readable_error(e) from e
    except NoCredentialsError as e:
        raise FeedbackError(500, "No AWS credentials found. Locally, set AWS_PROFILE.") from e
    except ReadTimeoutError as e:
        raise FeedbackError(504, "The model took too long to answer. Try again.") from e
    except BotoCoreError as e:
        raise FeedbackError(502, f"Couldn't reach Bedrock: {e}") from e
    parts = resp["output"]["message"]["content"]
    return "".join(p.get("text", "") for p in parts)


def _readable_error(e: ClientError) -> FeedbackError:
    code = e.response.get("Error", {}).get("Code", "")
    region = os.environ.get("BEDROCK_REGION", "your region")
    if code == "ThrottlingException":
        return FeedbackError(429, "Bedrock is busy right now (throttled). Wait a moment and try again.")
    if code == "AccessDeniedException":
        return FeedbackError(502, f"Bedrock denied access to {model_id()}. Check that model access is "
                                  "enabled in the Bedrock console and the IAM policy allows this model.")
    if code in ("ResourceNotFoundException", "ValidationException"):
        return FeedbackError(502, f"Model {model_id()} isn't available in {region}. Check FEEDBACK_MODEL_ID "
                                  "(it may need an inference profile ID like us.amazon.nova-lite-v1:0).")
    if code in ("ModelNotReadyException", "ServiceUnavailableException", "ModelTimeoutException",
                "InternalServerException"):
        return FeedbackError(503, "The model is unavailable right now. Try again in a minute.")
    if code in ("UnrecognizedClientException", "ExpiredTokenException", "InvalidSignatureException"):
        return FeedbackError(500, "AWS credentials are invalid or expired.")
    return FeedbackError(502, f"Bedrock error ({code or 'unknown'}).")


def get_feedback(type: str, question: str, answer: str, tags: list[str]) -> Feedback:
    """Ask the model for feedback. Retries once with a stricter reminder if the JSON is bad."""
    messages = [{"role": "user", "content": [{"text": build_prompt(type, question, answer, tags)}]}]
    reply = _converse(messages)
    try:
        return parse_feedback(reply)
    except ValueError:
        pass
    messages += [
        {"role": "assistant", "content": [{"text": reply or "(empty)"}]},
        {"role": "user", "content": [{"text": RETRY_REMINDER}]},
    ]
    try:
        return parse_feedback(_converse(messages))
    except ValueError as e:
        raise FeedbackError(502, "The model didn't return usable feedback. Try again, "
                                 "or switch to a stronger model.") from e
