"""Add a few sample questions to the deployed DynamoDB table.

Usage (from the repo root):
    AWS_PROFILE=dev AWS_REGION=us-east-1 .venv/bin/python scripts/seed_sample_data.py <TableName>

TableName is in the stack outputs. Questions that already exist (same text) are skipped,
so it's safe to run more than once.
"""

import sys
import uuid
from pathlib import Path

import boto3

# Reuse the app's validation so seeded items match what the API writes.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.db import now_iso  # noqa: E402
from app.models import Question, QuestionIn  # noqa: E402

SAMPLES = [
    {"type": "technical", "question": "How would you evaluate a RAG pipeline?",
     "tags": ["RAG", "evaluation"], "confidence": 2},
    {"type": "technical", "question": "When would you fine-tune a model instead of using RAG?",
     "tags": ["RAG", "LLM"], "confidence": 2},
    {"type": "technical", "question": "How do you reduce hallucinations in an LLM app?",
     "tags": ["LLM", "evaluation"], "confidence": 3},
    {"type": "technical", "question": "What causes Lambda cold starts and how do you reduce them?",
     "tags": ["AWS", "serverless"], "confidence": 3},
    {"type": "technical", "question": "Design a serverless document Q&A system on AWS.",
     "tags": ["AWS", "system design", "RAG"], "confidence": 1},
    {"type": "behavioral", "question": "Tell me about a time you disagreed with your manager.",
     "tags": ["conflict", "leadership"], "confidence": 3},
    {"type": "behavioral", "question": "Tell me about a project that failed. What did you learn?",
     "tags": ["failure", "growth"], "confidence": 2},
    {"type": "behavioral", "question": "Describe a time you had to learn something new quickly.",
     "tags": ["learning"], "confidence": 4},
]


def main(table_name: str) -> None:
    table = boto3.resource("dynamodb").Table(table_name)
    existing = set()
    kwargs = {}
    while True:
        resp = table.scan(ProjectionExpression="question", **kwargs)
        existing |= {" ".join(i["question"].split()).lower() for i in resp["Items"]}
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    added = 0
    for sample in SAMPLES:
        fields = QuestionIn.model_validate(sample).model_dump()
        if " ".join(fields["question"].split()).lower() in existing:
            continue
        now = now_iso()
        q = Question(**fields, id=str(uuid.uuid4()), createdAt=now, updatedAt=now).model_dump()
        table.put_item(Item={"pk": f"Q#{q['id']}", **q})
        added += 1
    print(f"Added {added} sample questions ({len(SAMPLES) - added} already there).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
