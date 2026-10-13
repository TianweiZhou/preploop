def make(client, **overrides):
    body = {"type": "technical", "question": "What is RAG?", "answer": "Retrieval...",
            "tags": ["RAG"], "confidence": 3, **overrides}
    r = client.post("/api/questions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_get(client):
    q = make(client)
    assert q["id"] and q["createdAt"] and q["timesPracticed"] == 0
    assert q["lastPracticed"] is None

    r = client.get(f"/api/questions/{q['id']}")
    assert r.status_code == 200
    assert r.json() == q


def test_update_keeps_stats(client):
    q = make(client)
    r = client.put(f"/api/questions/{q['id']}",
                   json={"type": "technical", "question": "What is RAG, really?", "confidence": 5})
    assert r.status_code == 200
    updated = r.json()
    assert updated["question"] == "What is RAG, really?"
    assert updated["confidence"] == 5
    assert updated["createdAt"] == q["createdAt"]
    assert updated["id"] == q["id"]


def test_delete(client):
    q = make(client)
    assert client.delete(f"/api/questions/{q['id']}").status_code == 204
    assert client.get(f"/api/questions/{q['id']}").status_code == 404
    assert client.delete(f"/api/questions/{q['id']}").status_code == 404


def test_missing_returns_404(client):
    assert client.get("/api/questions/nope").status_code == 404
    assert client.put("/api/questions/nope", json={"type": "technical", "question": "x"}).status_code == 404


def test_validation(client):
    bad = [
        {"type": "other", "question": "x"},
        {"type": "technical", "question": "   "},
        {"type": "technical", "question": "x", "confidence": 6},
        {"type": "technical", "question": "x" * 2001},
    ]
    for body in bad:
        assert client.post("/api/questions", json=body).status_code == 422, body


def test_tags_cleaned_and_star_only_behavioral(client):
    q = make(client, tags=[" AWS ", "aws", "", "RAG"],
             star={"situation": "s", "task": "t", "action": "a", "result": "r"})
    assert q["tags"] == ["AWS", "RAG"]
    assert q["star"] is None

    b = make(client, type="behavioral", star={"situation": "s", "result": "r"})
    assert b["star"]["situation"] == "s" and b["star"]["task"] == ""


def test_filters_search_sort(client):
    make(client, question="Explain vector DBs", tags=["RAG"], confidence=2)
    make(client, question="Tell me about a conflict", type="behavioral", tags=["leadership"], confidence=4)
    make(client, question="Lambda cold starts", tags=["AWS"], confidence=5, notes="provisioned concurrency")

    def ids(params):
        return [q["question"] for q in client.get("/api/questions", params=params).json()]

    assert ids({"type": "behavioral"}) == ["Tell me about a conflict"]
    assert ids({"tag": "rag"}) == ["Explain vector DBs"]
    assert ids({"min_conf": 4, "sort": "confidence", "order": "asc"}) == [
        "Tell me about a conflict", "Lambda cold starts"]
    assert ids({"max_conf": 2}) == ["Explain vector DBs"]
    assert ids({"q": "PROVISIONED"}) == ["Lambda cold starts"]
    assert len(ids({})) == 3
