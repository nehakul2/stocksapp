"""Accounts and per-user watchlists."""
import pytest
from fastapi.testclient import TestClient

import api
from db import init_db

init_db()
client = TestClient(api.app)


def signup(email, password="correct horse"):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_login_and_me():
    r = signup("Neha@Example.com")
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "neha@example.com"  # lower-cased
    login = client.post("/api/auth/login", json={"email": "neha@example.com", "password": "correct horse"})
    assert login.status_code == 200
    me = client.get("/api/me", headers=headers(login.json()["token"]))
    assert me.json()["email"] == "neha@example.com"


def test_duplicate_email_rejected():
    signup("dup@example.com")
    assert signup("DUP@example.com").status_code == 409


def test_bad_credentials():
    signup("bad@example.com")
    wrong = client.post("/api/auth/login", json={"email": "bad@example.com", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"email": "who@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # does not reveal which emails exist


@pytest.mark.parametrize("email,password", [("not-an-email", "longenough"), ("a@b.co", "short")])
def test_validation(email, password):
    assert signup(email, password).status_code == 400


def test_watchlist_requires_login():
    assert client.get("/api/watchlist").status_code == 401
    assert client.get("/api/watchlist", headers=headers("garbage")).status_code == 401


def test_watchlists_are_per_user_and_ordered():
    a = signup("a@example.com").json()["token"]
    b = signup("b@example.com").json()["token"]
    r = client.put("/api/watchlist", headers=headers(a), json={"tickers": ["tgt", "WMT", "TGT", ".DJI"]})
    assert r.json()["tickers"] == ["TGT", "WMT", "^DJI"]  # upper-cased, de-duplicated, aliases resolved
    assert client.get("/api/watchlist", headers=headers(a)).json()["tickers"] == ["TGT", "WMT", "^DJI"]
    assert client.get("/api/watchlist", headers=headers(b)).json()["tickers"] == []
    client.put("/api/watchlist", headers=headers(a), json={"tickers": ["WMT"]})
    assert client.get("/api/watchlist", headers=headers(a)).json()["tickers"] == ["WMT"]


def test_cors_only_allows_listed_origins():
    ok = client.options("/api/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    bad = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers
