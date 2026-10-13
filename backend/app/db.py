"""DynamoDB access. One table, pk = "Q#<id>". The dataset is small, so lists use a full Scan."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

import boto3


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@lru_cache
def table():
    # Created lazily so tests can set env vars and start moto first.
    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def _pk(question_id: str) -> str:
    return f"Q#{question_id}"


def _clean(item: dict) -> dict:
    """Turn DynamoDB Decimals back into ints and drop the internal pk."""
    out = {}
    for k, v in item.items():
        if k == "pk":
            continue
        out[k] = int(v) if isinstance(v, Decimal) else v
    return out


def list_questions() -> list[dict]:
    items, kwargs = [], {}
    while True:
        resp = table().scan(**kwargs)
        items.extend(resp["Items"])
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return [_clean(i) for i in items]


def get_question(question_id: str) -> dict | None:
    item = table().get_item(Key={"pk": _pk(question_id)}).get("Item")
    return _clean(item) if item else None


def put_question(question: dict) -> None:
    table().put_item(Item={"pk": _pk(question["id"]), **question})


def put_many(questions: list[dict]) -> None:
    """Bulk write, used by import."""
    with table().batch_writer() as batch:
        for q in questions:
            batch.put_item(Item={"pk": _pk(q["id"]), **q})


def record_practice(question_id: str, confidence: int, when: str) -> dict | None:
    """Save a practice rating. Returns the updated question, or None if it doesn't exist."""
    try:
        resp = table().update_item(
            Key={"pk": _pk(question_id)},
            UpdateExpression="SET confidence = :c, lastPracticed = :t ADD timesPracticed :one",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":c": confidence, ":t": when, ":one": 1},
            ReturnValues="ALL_NEW",
        )
    except table().meta.client.exceptions.ConditionalCheckFailedException:
        return None
    return _clean(resp["Attributes"])


def delete_question(question_id: str) -> bool:
    """Returns False if it didn't exist."""
    resp = table().delete_item(Key={"pk": _pk(question_id)}, ReturnValues="ALL_OLD")
    return "Attributes" in resp


def create_table(name: str) -> None:
    """Only for tests and local dev. SAM creates the real table."""
    boto3.client("dynamodb").create_table(
        TableName=name,
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
