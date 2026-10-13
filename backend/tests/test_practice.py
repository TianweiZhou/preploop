import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.routes.practice import pick, weight

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def q(id, confidence, days_ago=None):
    last = (NOW - timedelta(days=days_ago)).isoformat() if days_ago is not None else None
    return {"id": id, "confidence": confidence, "lastPracticed": last}


def test_weight_prefers_low_confidence():
    assert weight(q("a", 1, 3), NOW) > weight(q("b", 5, 3), NOW)


def test_weight_prefers_stale_and_never_practiced():
    assert weight(q("a", 3, 10), NOW) > weight(q("b", 3, 0), NOW)
    assert weight(q("a", 3), NOW) > weight(q("b", 3, 1), NOW)
    # Staleness caps out, so very old == never practiced.
    assert weight(q("a", 3, 100), NOW) == weight(q("b", 3), NOW)


def test_weight_range():
    assert weight(q("a", 1), NOW) == 40
    assert weight(q("b", 5, 0), NOW) == 1


def test_pick_distribution_favors_weak_questions():
    questions = [q("weak", 1), q("strong", 5, 0)]
    rng = random.Random(42)
    counts = Counter(pick(questions, NOW, rng=rng)["id"] for _ in range(2000))
    # Expected ratio is 40:1.
    assert counts["weak"] > counts["strong"] * 15


def test_pick_empty():
    assert pick([], NOW) is None


def make(client, **overrides):
    body = {"type": "technical", "question": "Q?", "confidence": 3, **overrides}
    return client.post("/api/questions", json=body).json()


def next_q(client, **body):
    r = client.post("/api/practice/next", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_next_respects_filters(client):
    make(client, question="Tech", tags=["AWS"])
    make(client, question="Behav", type="behavioral", tags=["leadership"])

    for _ in range(10):
        assert next_q(client, type="behavioral")["question"]["question"] == "Behav"
        assert next_q(client, tag="aws")["question"]["question"] == "Tech"

    assert next_q(client, tag="nope") == {"question": None, "total": 0, "remaining": 0}


def test_session_goes_through_each_question_once(client):
    ids = {make(client, question=f"Q{i}")["id"] for i in range(4)}
    seen = []
    for expected_remaining in [4, 3, 2, 1]:
        r = next_q(client, seen=seen)
        assert r["total"] == 4 and r["remaining"] == expected_remaining
        assert r["question"]["id"] not in seen
        seen.append(r["question"]["id"])
    assert set(seen) == ids
    assert next_q(client, seen=seen) == {"question": None, "total": 4, "remaining": 0}


def test_rate_updates_stats(client):
    created = make(client, confidence=2)
    r = client.post(f"/api/practice/{created['id']}/rate", json={"confidence": 4})
    assert r.status_code == 200
    rated = r.json()
    assert rated["confidence"] == 4
    assert rated["timesPracticed"] == 1
    assert rated["lastPracticed"] is not None

    again = client.post(f"/api/practice/{created['id']}/rate", json={"confidence": 5}).json()
    assert again["timesPracticed"] == 2
    assert client.get(f"/api/questions/{created['id']}").json()["confidence"] == 5


def test_rate_errors(client):
    assert client.post("/api/practice/missing/rate", json={"confidence": 3}).status_code == 404
    created = make(client)
    assert client.post(f"/api/practice/{created['id']}/rate", json={"confidence": 9}).status_code == 422


def test_practice_needs_login(anon_client):
    assert anon_client.post("/api/practice/next", json={}).status_code == 401
