import time

import jwt
import pytest

from app import auth

CLIENT_ID = "test-client-id.apps.googleusercontent.com"


@pytest.fixture
def google(monkeypatch):
    """Fake Google verify. Token strings map to claims; audience is checked like the real one."""
    tokens = {
        "good": {"aud": CLIENT_ID, "email": "me@example.com", "email_verified": True},
        "good-upper": {"aud": CLIENT_ID, "email": "Me@Example.com", "email_verified": True},
        "other-user": {"aud": CLIENT_ID, "email": "someone@example.com", "email_verified": True},
        "unverified": {"aud": CLIENT_ID, "email": "me@example.com", "email_verified": False},
        "other-app": {"aud": "another-app.apps.googleusercontent.com", "email": "me@example.com",
                      "email_verified": True},
    }

    def fake_verify(token, request, audience, clock_skew_in_seconds=0):
        if token not in tokens:
            raise ValueError("bad signature")
        claims = tokens[token]
        if claims["aud"] != audience:
            raise ValueError("wrong audience")
        return claims

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)


def login(client, token):
    return client.post("/api/auth/google", json={"credential": token})


def test_valid_login_sets_cookie(anon_client, google):
    r = login(anon_client, "good")
    assert r.status_code == 200
    assert r.json() == {"email": "me@example.com"}

    cookie = r.headers["set-cookie"].lower()
    for flag in ["httponly", "secure", "samesite=strict", "max-age=604800", "path=/"]:
        assert flag in cookie

    assert anon_client.get("/api/me").json() == {"email": "me@example.com"}
    assert anon_client.get("/api/questions").status_code == 200


def test_email_match_ignores_case(anon_client, google):
    assert login(anon_client, "good-upper").status_code == 200


@pytest.mark.parametrize("token", ["other-user", "unverified"])
def test_wrong_or_unverified_email_is_403(anon_client, google, token):
    r = login(anon_client, token)
    assert r.status_code == 403
    assert "set-cookie" not in r.headers


@pytest.mark.parametrize("token", ["other-app", "garbage"])
def test_wrong_audience_or_bad_token_is_401(anon_client, google, token):
    r = login(anon_client, token)
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


def test_protected_routes_need_session(anon_client):
    assert anon_client.get("/api/me").status_code == 401
    assert anon_client.get("/api/questions").status_code == 401
    assert anon_client.post("/api/questions", json={"type": "technical", "question": "x"}).status_code == 401


def test_open_routes(anon_client):
    assert anon_client.get("/api/health").status_code == 200
    assert anon_client.get("/api/config").json() == {"googleClientId": CLIENT_ID}
    assert anon_client.post("/api/logout").status_code == 200


def test_bad_sessions_rejected(anon_client):
    now = int(time.time())
    bad = [
        "not-a-jwt",
        jwt.encode({"sub": "me@example.com", "exp": now + 60}, "wrong-secret-wrong-secret-wrong-secret", "HS256"),
        jwt.encode({"sub": "me@example.com", "exp": now - 60}, auth.jwt_secret(), "HS256"),
        jwt.encode({"sub": "someone@example.com", "exp": now + 60}, auth.jwt_secret(), "HS256"),
    ]
    for token in bad:
        anon_client.cookies.set(auth.COOKIE_NAME, token)
        assert anon_client.get("/api/me").status_code == 401, token


def test_logout_clears_cookie(anon_client, google):
    login(anon_client, "good")
    assert anon_client.get("/api/me").status_code == 200

    r = anon_client.post("/api/logout")
    assert r.status_code == 200
    assert "max-age=0" in r.headers["set-cookie"].lower()
    assert anon_client.get("/api/me").status_code == 401
