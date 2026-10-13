"""Google sign-in for a single allowed user, plus our own session cookie.

Flow: the browser gets a Google ID token, we verify it here, then set a
signed JWT in an HttpOnly cookie. Every protected route checks that cookie.
"""

import os
import time
from functools import lru_cache

import boto3
import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, Field

COOKIE_NAME = "preploop_session"
SESSION_SECONDS = 7 * 24 * 3600

router = APIRouter(prefix="/api", tags=["auth"])


def google_client_id() -> str:
    return os.environ["GOOGLE_CLIENT_ID"]


def allowed_email() -> str:
    return os.environ["ALLOWED_EMAIL"].strip().lower()


def cookie_secure() -> bool:
    # Only turn this off for local http dev.
    return os.environ.get("COOKIE_SECURE", "true").lower() != "false"


@lru_cache
def jwt_secret() -> str:
    """JWT_SECRET for local dev, otherwise read once from SSM and cache."""
    if os.environ.get("JWT_SECRET"):
        return os.environ["JWT_SECRET"]
    resp = boto3.client("ssm").get_parameter(Name=os.environ["JWT_SECRET_PARAM"], WithDecryption=True)
    return resp["Parameter"]["Value"]


def make_session_token(email: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": email, "iat": now, "exp": now + SESSION_SECONDS}, jwt_secret(), algorithm="HS256")


def require_user(session: str | None = Cookie(None, alias=COOKIE_NAME)) -> str:
    """Route dependency. Returns the signed-in email or raises 401."""
    if not session:
        raise HTTPException(401, "Not signed in")
    try:
        claims = jwt.decode(session, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired or invalid")
    # Re-check the email so changing ALLOWED_EMAIL kicks out old sessions.
    if claims.get("sub") != allowed_email():
        raise HTTPException(401, "Session expired or invalid")
    return claims["sub"]


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=1, max_length=4096)


@router.get("/config")
def config():
    # The client ID is public, the browser needs it to show the Google button.
    return {"googleClientId": google_client_id()}


@router.post("/auth/google")
def google_login(body: GoogleLogin, response: Response):
    try:
        # Checks signature, expiry, issuer, and audience.
        info = id_token.verify_oauth2_token(
            body.credential, google_requests.Request(), google_client_id(), clock_skew_in_seconds=10
        )
    except ValueError:
        raise HTTPException(401, "Invalid Google token")

    email = (info.get("email") or "").lower()
    if not info.get("email_verified") or email != allowed_email():
        raise HTTPException(403, "This account isn't allowed")

    response.set_cookie(
        COOKIE_NAME, make_session_token(email), max_age=SESSION_SECONDS,
        httponly=True, secure=cookie_secure(), samesite="strict", path="/",
    )
    return {"email": email}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, httponly=True, secure=cookie_secure(), samesite="strict", path="/")
    return {"ok": True}


@router.get("/me")
def me(email: str = Depends(require_user)):
    return {"email": email}
