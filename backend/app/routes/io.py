"""Import from / export to JSON or CSV.

CSV columns: type, question, answer, tags, confidence (tags separated by ";").
Export also writes notes, STAR parts, and practice stats so nothing is lost,
and import reads them back if present.
"""

import csv
import io
import json
import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ValidationError

from app import db
from app.models import Question, QuestionIn

router = APIRouter(prefix="/api", tags=["import-export"])

MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 2000
STAR_KEYS = ["situation", "task", "action", "result"]
CSV_COLUMNS = ["type", "question", "answer", "tags", "confidence", "notes", *STAR_KEYS,
               "timesPracticed", "lastPracticed", "createdAt"]


# ---- Export ----

def _csv_row(q: dict) -> dict:
    star = q.get("star") or {}
    return {
        **{k: q.get(k, "") for k in ["type", "question", "answer", "confidence", "notes",
                                     "timesPracticed", "createdAt"]},
        "tags": ";".join(q.get("tags", [])),
        "lastPracticed": q.get("lastPracticed") or "",
        **{k: star.get(k, "") for k in STAR_KEYS},
    }


@router.get("/export")
def export(format: Literal["json", "csv"] = "json"):
    items = sorted(db.list_questions(), key=lambda q: q.get("createdAt", ""))
    filename = f"preploop-export-{date.today().isoformat()}.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if format == "json":
        return Response(json.dumps(items, indent=2, ensure_ascii=False), media_type="application/json",
                        headers=headers)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(_csv_row(q) for q in items)
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


# ---- Import ----

def _parse_json(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("questions", [])
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError("JSON must be a list of question objects")
    return data


def _parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "question" not in [f.strip().lower() for f in reader.fieldnames]:
        raise ValueError("CSV needs a header row with at least: type, question")
    rows = []
    for raw in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        star = {k: row.pop(k) for k in STAR_KEYS if k in row}
        rows.append({
            **row,
            "tags": [t for t in row.get("tags", "").split(";")],
            "confidence": row.get("confidence") or 3,
            "star": star if any(star.values()) else None,
        })
    return rows


def _key(question: str) -> str:
    """Duplicate check: same text, ignoring case and extra whitespace."""
    return " ".join(question.split()).lower()


def _valid_iso(value) -> str | None:
    try:
        return datetime.fromisoformat(value).isoformat() if value else None
    except (TypeError, ValueError):
        return None


def _to_question(row: dict, now: str) -> Question:
    """Validate one row. Keeps practice stats from a previous export if present."""
    row = {**row, "type": str(row.get("type", "")).strip().lower()}
    if isinstance(row.get("tags"), str):
        row["tags"] = row["tags"].split(";")
    fields = QuestionIn.model_validate(row).model_dump()
    try:
        times = max(0, int(row.get("timesPracticed") or 0))
    except (TypeError, ValueError):
        times = 0
    return Question(
        **fields,
        id=str(uuid.uuid4()),
        timesPracticed=times,
        lastPracticed=_valid_iso(row.get("lastPracticed")),
        createdAt=_valid_iso(row.get("createdAt")) or now,
        updatedAt=now,
    )


def _error_text(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'row'}: {err['msg']}" for err in e.errors())


@router.post("/import")
async def import_questions(request: Request):
    """Body is the raw file contents (JSON or CSV). Detected by the first character."""
    if int(request.headers.get("content-length") or 0) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "File is too big (max 1 MB)")
    body = await request.body()
    if len(body) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "File is too big (max 1 MB)")

    try:
        text = body.decode("utf-8-sig")  # -sig drops the BOM Excel adds
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 text")
    if not text.strip():
        raise HTTPException(400, "File is empty")

    try:
        rows = _parse_json(text) if text.lstrip()[0] in "[{" else _parse_csv(text)
    except (ValueError, csv.Error) as e:
        raise HTTPException(400, f"Couldn't read file: {e}")
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(400, f"Too many rows (max {MAX_IMPORT_ROWS})")

    seen = {_key(q["question"]) for q in db.list_questions()}
    now = db.now_iso()
    new, duplicates, errors = [], 0, []
    # Row numbers match what you'd see in a spreadsheet (header is row 1) or the JSON list (from 1).
    first_row = 1 if text.lstrip()[0] in "[{" else 2
    for i, row in enumerate(rows, start=first_row):
        try:
            q = _to_question(row, now)
        except ValidationError as e:
            errors.append({"row": i, "error": _error_text(e)})
            continue
        if _key(q.question) in seen:
            duplicates += 1
            continue
        seen.add(_key(q.question))
        new.append(q.model_dump())

    db.put_many(new)
    return {"imported": len(new), "skipped_duplicates": duplicates, "errors": errors[:50],
            "error_count": len(errors)}
