"""PrepLoop FastAPI app. Runs locally with uvicorn and on Lambda via Mangum."""

import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mangum import Mangum

from app import auth, db
from app.routes import feedback, practice, questions

STATIC_DIR = Path(__file__).parent / "static"

# Local dev only: an in-memory DynamoDB (moto), so no AWS account is needed.
# Data is lost when the server restarts.
if os.environ.get("LOCAL_MOCK_DB") == "1":
    from moto import mock_aws

    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("TABLE_NAME", "PrepLoopLocal")
    # Bedrock calls still go to real AWS. Use real credentials only if AWS_PROFILE is set.
    mock_aws(config={"core": {
        "mock_credentials": not os.environ.get("AWS_PROFILE"),
        "passthrough": {"urls": [r"https://bedrock-runtime\..*"], "services": []},
        "reset_boto3_session": True,
        "service_whitelist": None,
    }}).start()
    db.create_table(os.environ["TABLE_NAME"])

# No docs UI in production, this is a private app.
app = FastAPI(title="PrepLoop", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)
# Everything below needs a valid session cookie.
protected = [Depends(auth.require_user)]
app.include_router(questions.router, dependencies=protected)
app.include_router(practice.router, dependencies=protected)
app.include_router(feedback.router, dependencies=protected)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Lambda entry point.
handler = Mangum(app, lifespan="off")
