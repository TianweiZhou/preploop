import os

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

# Fake settings so nothing ever touches a real AWS account or Google.
os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "TABLE_NAME": "PrepLoopTest",
    "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
    "ALLOWED_EMAIL": "me@example.com",
    "JWT_SECRET": "test-secret-that-is-long-enough-for-hs256",
    "FEEDBACK_MODEL_ID": "test-model-id",
    "BEDROCK_REGION": "us-east-1",
})

from app import auth, db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def anon_client():
    """Not signed in, backed by a fresh moto DynamoDB table."""
    with mock_aws():
        db.table.cache_clear()
        db.create_table(os.environ["TABLE_NAME"])
        # https so the Secure cookie gets sent back.
        yield TestClient(app, base_url="https://testserver")
        db.table.cache_clear()


@pytest.fixture
def client(anon_client):
    """Signed in as the allowed user."""
    anon_client.cookies.set(auth.COOKIE_NAME, auth.make_session_token("me@example.com"))
    return anon_client
