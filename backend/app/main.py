"""PrepLoop FastAPI app. Runs locally with uvicorn and on Lambda via Mangum."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mangum import Mangum

STATIC_DIR = Path(__file__).parent / "static"

# No docs UI in production, this is a private app.
app = FastAPI(title="PrepLoop", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Lambda entry point.
handler = Mangum(app, lifespan="off")
