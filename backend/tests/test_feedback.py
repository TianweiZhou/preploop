import json

import pytest
from botocore.exceptions import ClientError

from app import feedback
from app.feedback import FeedbackError, get_feedback, parse_feedback

GOOD = {
    "scores": {"clarity": 4, "structure": 3, "specificity": 2},
    "strengths": ["Clear opening"],
    "gaps": ["No measurable result"],
    "suggested_answer": "I led the migration — and we shipped early.",
    "follow_up_questions": ["What would you do differently?"],
}


# ---- Parsing messy model output ----

@pytest.mark.parametrize("text", [
    json.dumps(GOOD),
    "```json\n" + json.dumps(GOOD) + "\n```",
    "Sure! Here is the feedback:\n" + json.dumps(GOOD) + "\nHope this helps.",
    "```\n" + json.dumps(GOOD, indent=2) + "\n```",
])
def test_parse_handles_fences_and_chatter(text):
    fb = parse_feedback(text)
    assert fb.scores.clarity == 4
    assert fb.gaps == ["No measurable result"]


def test_parse_coerces_scores_and_lists():
    messy = {**GOOD, "scores": {"clarity": "4", "structure": 3.6, "specificity": 9}, "strengths": "Just one"}
    fb = parse_feedback(json.dumps(messy))
    assert (fb.scores.clarity, fb.scores.structure, fb.scores.specificity) == (4, 4, 5)
    assert fb.strengths == ["Just one"]


def test_parse_removes_em_dashes():
    assert parse_feedback(json.dumps(GOOD)).suggested_answer == "I led the migration, and we shipped early."


@pytest.mark.parametrize("text", ["", "no json here", "{not json}", json.dumps({"scores": {}})])
def test_parse_rejects_bad_output(text):
    with pytest.raises(ValueError):
        parse_feedback(text)


# ---- Bedrock calls (mocked) ----

class FakeBedrock:
    """Returns the queued replies in order. A ClientError in the queue gets raised."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"output": {"message": {"role": "assistant", "content": [{"text": reply}]}}}


@pytest.fixture
def fake(monkeypatch):
    def install(*replies):
        client = FakeBedrock(*replies)
        monkeypatch.setattr(feedback, "bedrock_client", lambda: client)
        return client
    return install


def client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


def test_uses_converse_with_model_from_env(fake):
    bedrock = fake(json.dumps(GOOD))
    get_feedback("behavioral", "Tell me about a conflict", "We fixed it.", ["leadership"])
    call = bedrock.calls[0]
    assert call["modelId"] == "test-model-id"
    prompt = call["messages"][0]["content"][0]["text"]
    assert "STAR" in prompt and "We fixed it." in prompt and "leadership" in prompt
    assert "JSON" in call["system"][0]["text"]


def test_technical_prompt_guidance(fake):
    bedrock = fake(json.dumps(GOOD))
    get_feedback("technical", "What is RAG?", "Retrieval...", [])
    prompt = bedrock.calls[0]["messages"][0]["content"][0]["text"]
    assert "tradeoffs" in prompt and "STAR" not in prompt


def test_retries_once_on_bad_json(fake):
    bedrock = fake("Here you go: scores are good", json.dumps(GOOD))
    fb = get_feedback("technical", "q", "a", [])
    assert fb.scores.clarity == 4
    assert len(bedrock.calls) == 2
    retry_messages = bedrock.calls[1]["messages"]
    assert retry_messages[1]["role"] == "assistant"
    assert "ONLY the JSON" in retry_messages[2]["content"][0]["text"]


def test_gives_up_after_second_bad_reply(fake):
    fake("nope", "still nope")
    with pytest.raises(FeedbackError) as e:
        get_feedback("technical", "q", "a", [])
    assert e.value.status == 502
    assert "didn't return usable feedback" in e.value.message


@pytest.mark.parametrize("code,status,text", [
    ("ThrottlingException", 429, "throttled"),
    ("AccessDeniedException", 502, "model access"),
    ("ValidationException", 502, "isn't available"),
    ("ResourceNotFoundException", 502, "isn't available"),
    ("ModelNotReadyException", 503, "unavailable"),
])
def test_bedrock_errors_are_readable(fake, code, status, text):
    fake(client_error(code))
    with pytest.raises(FeedbackError) as e:
        get_feedback("technical", "q", "a", [])
    assert e.value.status == status
    assert text in e.value.message


# ---- Route ----

def test_route_with_saved_question(client, fake):
    bedrock = fake(json.dumps(GOOD))
    q = client.post("/api/questions", json={
        "type": "behavioral", "question": "Conflict?", "answer": "My answer",
        "star": {"result": "Cut incidents 40%"}, "tags": ["leadership"],
    }).json()

    r = client.post("/api/feedback", json={"question_id": q["id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["model_id"] == "test-model-id"
    assert body["feedback"]["scores"]["clarity"] == 4
    prompt = bedrock.calls[0]["messages"][0]["content"][0]["text"]
    assert "My answer" in prompt and "Result: Cut incidents 40%" in prompt


def test_route_fresh_answer_overrides_saved(client, fake):
    bedrock = fake(json.dumps(GOOD))
    q = client.post("/api/questions", json={"type": "technical", "question": "RAG?", "answer": "old"}).json()
    client.post("/api/feedback", json={"question_id": q["id"], "answer": "brand new answer"})
    prompt = bedrock.calls[0]["messages"][0]["content"][0]["text"]
    assert "brand new answer" in prompt and "old" not in prompt


def test_route_raw_question(client, fake):
    fake(json.dumps(GOOD))
    r = client.post("/api/feedback", json={"type": "technical", "question": "What is RAG?", "answer": "Retrieval"})
    assert r.status_code == 200


def test_route_errors(client, fake):
    fake(client_error("ThrottlingException"))
    assert client.post("/api/feedback", json={"question_id": "missing"}).status_code == 404
    assert client.post("/api/feedback", json={"answer": "no question"}).status_code == 422

    q = client.post("/api/questions", json={"type": "technical", "question": "Empty?"}).json()
    r = client.post("/api/feedback", json={"question_id": q["id"]})
    assert r.status_code == 400

    r = client.post("/api/feedback", json={"type": "technical", "question": "q", "answer": "a"})
    assert r.status_code == 429
    assert "throttled" in r.json()["detail"]


def test_route_needs_login(anon_client):
    assert anon_client.post("/api/feedback", json={"question_id": "x"}).status_code == 401


# ---- Stored feedback (no repeat calls for an unchanged answer) ----

def saved_question(client, **overrides):
    body = {"type": "technical", "question": "RAG?", "answer": "Retrieval", **overrides}
    return client.post("/api/questions", json=body).json()


def test_unchanged_answer_reuses_stored_feedback(client, fake):
    bedrock = fake(json.dumps(GOOD))  # only one reply queued: a second call would fail
    q = saved_question(client)
    assert q["lastFeedback"] is None

    first = client.post("/api/feedback", json={"question_id": q["id"]}).json()
    second = client.post("/api/feedback", json={"question_id": q["id"]}).json()
    assert first["cached"] is False and second["cached"] is True
    assert second["feedback"] == first["feedback"]
    assert second["created_at"] == first["created_at"]
    assert len(bedrock.calls) == 1

    # The card now shows the scores.
    last = client.get(f"/api/questions/{q['id']}").json()["lastFeedback"]
    assert last["scores"] == {"clarity": 4, "structure": 3, "specificity": 2}
    assert last["modelId"] == "test-model-id"
    assert "aiFeedback" not in client.get(f"/api/questions/{q['id']}").json()


def test_edited_answer_calls_model_again(client, fake):
    bedrock = fake(json.dumps(GOOD), json.dumps({**GOOD, "scores": {"clarity": 5, "structure": 5, "specificity": 5}}))
    q = saved_question(client)
    client.post("/api/feedback", json={"question_id": q["id"]})

    edited = client.put(f"/api/questions/{q['id']}", json={"type": "technical", "question": "RAG?",
                                                            "answer": "Retrieval, better"}).json()
    assert edited["lastFeedback"] is None  # old scores no longer match the answer

    r = client.post("/api/feedback", json={"question_id": q["id"]}).json()
    assert r["cached"] is False and len(bedrock.calls) == 2
    assert client.get(f"/api/questions/{q['id']}").json()["lastFeedback"]["scores"]["clarity"] == 5


def test_force_asks_again(client, fake):
    bedrock = fake(json.dumps(GOOD), json.dumps(GOOD))
    q = saved_question(client)
    client.post("/api/feedback", json={"question_id": q["id"]})
    r = client.post("/api/feedback", json={"question_id": q["id"], "force": True}).json()
    assert r["cached"] is False and len(bedrock.calls) == 2


def test_typed_answer_keeps_saved_answer_feedback(client, fake):
    bedrock = fake(json.dumps(GOOD), json.dumps(GOOD))
    q = saved_question(client)
    client.post("/api/feedback", json={"question_id": q["id"]})
    client.post("/api/feedback", json={"question_id": q["id"], "answer": "a typed attempt"})
    assert len(bedrock.calls) == 2

    # Saved answer is still cached, and still shown on the card.
    assert client.post("/api/feedback", json={"question_id": q["id"]}).json()["cached"] is True
    assert client.get(f"/api/questions/{q['id']}").json()["lastFeedback"] is not None

    # Saving the typed answer makes its stored feedback the current one.
    client.put(f"/api/questions/{q['id']}", json={"type": "technical", "question": "RAG?", "answer": "a typed attempt"})
    assert client.post("/api/feedback", json={"question_id": q["id"]}).json()["cached"] is True
    assert len(bedrock.calls) == 2


def test_different_model_is_not_reused(client, fake, monkeypatch):
    bedrock = fake(json.dumps(GOOD), json.dumps(GOOD))
    q = saved_question(client)
    client.post("/api/feedback", json={"question_id": q["id"]})
    monkeypatch.setenv("FEEDBACK_MODEL_ID", "claude-model-id")
    r = client.post("/api/feedback", json={"question_id": q["id"]}).json()
    assert r["cached"] is False and r["model_id"] == "claude-model-id"
    assert len(bedrock.calls) == 2


def test_stored_history_is_capped(client, fake):
    fake(*[json.dumps(GOOD)] * 5)
    q = saved_question(client)
    for i in range(5):
        client.post("/api/feedback", json={"question_id": q["id"], "answer": f"attempt {i}"})
    from app import db
    assert len(db.get_question(q["id"])["aiFeedback"]) == 3


def test_raw_question_is_not_stored(client, fake):
    bedrock = fake(json.dumps(GOOD), json.dumps(GOOD))
    body = {"type": "technical", "question": "q", "answer": "a"}
    assert client.post("/api/feedback", json=body).json()["cached"] is False
    assert client.post("/api/feedback", json=body).json()["cached"] is False
    assert len(bedrock.calls) == 2
