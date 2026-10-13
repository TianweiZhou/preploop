import csv
import io
import json


def upload(client, text):
    return client.post("/api/import", content=text.encode("utf-8"), headers={"Content-Type": "text/plain"})


def all_questions(client):
    return client.get("/api/questions", params={"sort": "createdAt", "order": "asc"}).json()


CSV_TEXT = """type,question,answer,tags,confidence
technical,What is RAG?,Retrieval plus generation,RAG;LLM,2
Behavioral,Tell me about a conflict,I talked to them,leadership,
technical,What is RAG?,duplicate in the same file,,4
"""


def test_import_csv(client):
    r = upload(client, CSV_TEXT)
    assert r.status_code == 200, r.text
    assert r.json() == {"imported": 2, "skipped_duplicates": 1, "errors": [], "error_count": 0}

    qs = all_questions(client)
    rag = next(q for q in qs if q["question"] == "What is RAG?")
    assert rag["tags"] == ["RAG", "LLM"] and rag["confidence"] == 2
    conflict = next(q for q in qs if q["type"] == "behavioral")
    assert conflict["confidence"] == 3  # blank defaults to 3


def test_import_skips_existing_duplicates(client):
    client.post("/api/questions", json={"type": "technical", "question": "what is   RAG?"})
    r = upload(client, CSV_TEXT).json()
    assert r["imported"] == 1
    assert r["skipped_duplicates"] == 2
    assert len(all_questions(client)) == 2


def test_import_json_list_and_wrapped(client):
    rows = [
        {"type": "technical", "question": "Q1", "answer": "A1", "tags": ["AWS"], "confidence": 4},
        {"type": "behavioral", "question": "Q2", "tags": "a;b",
         "star": {"situation": "S", "result": "R"}},
    ]
    assert upload(client, json.dumps(rows)).json()["imported"] == 2
    assert upload(client, json.dumps({"questions": [{"type": "technical", "question": "Q3"}]})).json()["imported"] == 1

    qs = {q["question"]: q for q in all_questions(client)}
    assert qs["Q2"]["tags"] == ["a", "b"]
    assert qs["Q2"]["star"]["result"] == "R"


def test_import_reports_bad_rows(client):
    text = """type,question,answer,tags,confidence
technical,Good one,,,3
other,Bad type,,,3
technical,,missing question,,3
technical,Bad confidence,,,9
"""
    r = upload(client, text).json()
    assert r["imported"] == 1
    assert r["error_count"] == 3
    assert [e["row"] for e in r["errors"]] == [3, 4, 5]


def test_import_rejects_bad_files(client):
    assert upload(client, "").status_code == 400
    assert upload(client, "just,some\nrandom,csv").status_code == 400
    assert upload(client, "[1, 2, 3]").status_code == 400
    assert upload(client, "{not json").status_code == 400
    r = client.post("/api/import", content=b"\xff\xfe\x00bad", headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


def test_import_size_limit(client):
    big = "type,question\n" + "technical,x\n" * 100_000  # ~1.2 MB
    assert upload(client, big).status_code == 413


def test_import_handles_excel_bom(client):
    assert upload(client, "﻿" + CSV_TEXT).json()["imported"] == 2


def test_export_json_round_trip(client):
    upload(client, CSV_TEXT)
    q = all_questions(client)[0]
    client.post(f"/api/practice/{q['id']}/rate", json={"confidence": 5})

    r = client.get("/api/export", params={"format": "json"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert len(data) == 2 and "pk" not in data[0]

    # Delete everything, re-import the export, and check practice stats came back.
    for item in all_questions(client):
        client.delete(f"/api/questions/{item['id']}")
    assert upload(client, r.text).json()["imported"] == 2
    restored = next(x for x in all_questions(client) if x["question"] == q["question"])
    assert restored["timesPracticed"] == 1
    assert restored["confidence"] == 5
    assert restored["lastPracticed"] is not None


def test_export_csv_round_trip(client):
    client.post("/api/questions", json={
        "type": "behavioral", "question": 'Has "quotes", commas', "answer": "Line 1\nLine 2",
        "tags": ["a", "b"], "star": {"situation": "S", "action": "A"}, "notes": "n",
    })
    r = client.get("/api/export", params={"format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert rows[0]["tags"] == "a;b"
    assert rows[0]["situation"] == "S"

    for item in all_questions(client):
        client.delete(f"/api/questions/{item['id']}")
    assert upload(client, r.text).json()["imported"] == 1
    q = all_questions(client)[0]
    assert q["question"] == 'Has "quotes", commas'
    assert q["answer"] == "Line 1\nLine 2"
    assert q["star"]["action"] == "A" and q["notes"] == "n"


def test_io_needs_login(anon_client):
    assert anon_client.get("/api/export").status_code == 401
    assert anon_client.post("/api/import", content=b"x").status_code == 401
