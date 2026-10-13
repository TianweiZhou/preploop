import os

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

# Fake AWS settings so nothing ever touches a real account.
os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "TABLE_NAME": "PrepLoopTest",
})

from app import db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    """Test client backed by a fresh moto DynamoDB table."""
    with mock_aws():
        db.table.cache_clear()
        db.create_table(os.environ["TABLE_NAME"])
        yield TestClient(app)
        db.table.cache_clear()
