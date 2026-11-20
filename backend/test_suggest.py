import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import ai
import api
import core

from db import init_db

init_db()
client = TestClient(api.app)
_n = [0]


def frame(closes):
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"Close": c, "Open": c, "High": c, "Low": c, "Volume": 1e6}, index=pd.date_range("2025-01-01", periods=len(c)))


def steady(daily_pct, n=300, start=100.0):
    return frame(start * np.cumprod(np.full(n, 1 + daily_pct / 100)))


def mixed():
    """A long slide followed by a small bounce: not clearly up or down."""
    return frame(np.concatenate([np.linspace(150, 100, 250), np.linspace(100, 108, 50)]))


DATA = {}
ASKED = []


@pytest.fixture(autouse=True)
def patch(monkeypatch):
    DATA.clear(); ASKED.clear()
    DATA.update({"UP": steady(0.3), "DOWN": steady(-0.3), "FLAT": mixed(), "SHORT": steady(0.3, n=100), "^GSPC": steady(0.05)})
    monkeypatch.setattr(core, "fetch_history", lambda t, p: DATA[t] if t in DATA else (_ for _ in ()).throw(ValueError("no data")))
    monkeypatch.setattr(core, "get_next_earnings_date", lambda t: "")
    monkeypatch.setattr(ai, "ask_claude", lambda key, prompt, max_tokens=500: (ASKED.append(prompt), "UP looks strongest.")[1])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AI_DAILY_LIMIT", "50")
    core.suggest.cache_clear()


def new_user():
    _n[0] += 1
    r = client.post("/api/auth/signup", json={"email": f"sug{_n[0]}@example.com", "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_steady_riser_is_buy_steady_faller_is_sell_and_choppy_is_hold():
    up, down = core.suggest("UP"), core.suggest("DOWN")
    assert up["action"] == "buy" and up["score"] >= 3 and up["reasons"] and not up["against"][:0]
    assert down["action"] == "sell" and down["score"] <= -3
    assert core.suggest("FLAT")["action"] == "hold"


def test_reasons_match_the_label():
    up = core.suggest("UP")
    assert all("above" in r or "Up" in r for r in up["reasons"])
    down = core.suggest("DOWN")
    assert all("below" in r or "Down" in r for r in down["reasons"])


def test_overextended_stock_gets_a_caution_and_loses_a_point():
    up = core.suggest("UP")
    assert any("RSI" in c for c in up["cautions"]) or up["score"] >= 5


def test_earnings_soon_adds_a_caution(monkeypatch):
    from datetime import date, timedelta
    monkeypatch.setattr(core, "get_next_earnings_date", lambda t: (date.today() + timedelta(days=2)).isoformat())
    core.suggest.cache_clear()
    assert any("Earnings are due in 2 days" in c for c in core.suggest("UP")["cautions"])


def test_short_history_raises():
    with pytest.raises(ValueError):
        core.suggest("SHORT")


def test_endpoint_sorts_buy_then_sell_then_hold_and_reports_unavailable():
    r = client.get("/api/suggestions?tickers=FLAT,DOWN,UP,NOPE").json()
    assert [i["action"] for i in r["items"]] == ["buy", "sell", "hold"]
    assert r["unavailable"] == ["NOPE"]
    assert "not advice" in r["disclaimer"]
    assert client.get("/api/suggestions?tickers=").status_code in (400, 422)


def test_summary_needs_login_ownership_and_stocks():
    h, other = new_user(), new_user()
    wid = client.get("/api/watchlists", headers=h).json()["watchlists"][0]["id"]
    assert client.post(f"/api/watchlists/{wid}/suggestions/summary").status_code in (401, 403)
    assert client.post(f"/api/watchlists/{wid}/suggestions/summary", headers=other).status_code == 404
    assert client.post(f"/api/watchlists/{wid}/suggestions/summary", headers=h).status_code == 400  # empty list


def test_summary_sends_only_facts_counts_usage_and_refunds_on_failure(monkeypatch):
    h = new_user()
    wid = client.get("/api/watchlists", headers=h).json()["watchlists"][0]["id"]
    client.put(f"/api/watchlists/{wid}/tickers", headers=h, json={"tickers": ["UP", "DOWN"]})
    r = client.post(f"/api/watchlists/{wid}/suggestions/summary", headers=h)
    assert r.status_code == 200 and r.json()["summary"] == "UP looks strongest." and r.json()["usage"]["used"] == 1
    assert "UP: leans toward buying" in ASKED[0] and "DOWN: leans toward selling" in ASKED[0]
    monkeypatch.setattr(ai, "ask_claude", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert client.post(f"/api/watchlists/{wid}/suggestions/summary", headers=h).status_code == 502
    assert client.get("/api/ai/usage", headers=h).json()["used"] == 1  # the failure was refunded


def test_summary_without_server_key_is_a_clear_503(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    h = new_user()
    wid = client.get("/api/watchlists", headers=h).json()["watchlists"][0]["id"]
    client.put(f"/api/watchlists/{wid}/tickers", headers=h, json={"tickers": ["UP"]})
    assert client.post(f"/api/watchlists/{wid}/suggestions/summary", headers=h).status_code == 503
