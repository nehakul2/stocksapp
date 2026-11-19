import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import core

from db import init_db

init_db()
client = TestClient(api.app)
_n = [0]


def new_user():
    _n[0] += 1
    r = client.post("/api/auth/signup", json={"email": f"lists{_n[0]}@example.com", "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def history(closes, n=260):
    """`closes` are the final closes; earlier days are flat at 100."""
    c = np.full(n, 100.0)
    c[-len(closes):] = closes
    idx = pd.date_range("2025-01-01", periods=n)
    return pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": 1e6}, index=idx)


PRICES = {"TGT": [100, 110], "WMT": [100, 90]}


@pytest.fixture(autouse=True)
def patch(monkeypatch):
    monkeypatch.setattr(core, "fetch_history", lambda t, p: history(PRICES[t]) if t in PRICES else (_ for _ in ()).throw(ValueError("no data")))


# ---- watchlists
def test_new_user_gets_one_empty_default_list():
    h = new_user()
    lists = client.get("/api/watchlists", headers=h).json()["watchlists"]
    assert [(w["name"], w["tickers"]) for w in lists] == [("My Watchlist", [])]


def test_existing_single_list_is_carried_into_first_watchlist():
    from db import SessionLocal, User, WatchlistItem
    h = new_user()
    uid = client.get("/api/me", headers=h).json()["id"]
    with SessionLocal() as db:
        db.add(WatchlistItem(user_id=uid, ticker="TGT", position=0))
        db.add(WatchlistItem(user_id=uid, ticker="WMT", position=1))
        db.commit()
    lists = client.get("/api/watchlists", headers=h).json()["watchlists"]
    assert lists[0]["tickers"] == ["TGT", "WMT"]


def test_create_rename_delete_and_rules():
    h = new_user()
    first = client.get("/api/watchlists", headers=h).json()["watchlists"][0]
    r = client.post("/api/watchlists", headers=h, json={"name": "  Retirement  "})
    assert r.status_code == 201 and r.json()["name"] == "Retirement"
    assert client.post("/api/watchlists", headers=h, json={"name": "Retirement"}).status_code == 409
    assert client.post("/api/watchlists", headers=h, json={"name": "   "}).status_code == 400
    wid = r.json()["id"]
    assert client.patch(f"/api/watchlists/{wid}", headers=h, json={"name": "Tech"}).json()["name"] == "Tech"
    assert client.patch(f"/api/watchlists/{wid}", headers=h, json={"name": "My Watchlist"}).status_code == 409
    assert client.delete(f"/api/watchlists/{wid}", headers=h).status_code == 200
    assert client.delete(f"/api/watchlists/{first['id']}", headers=h).status_code == 400  # last one stays


def test_max_ten_watchlists():
    h = new_user()
    client.get("/api/watchlists", headers=h)
    for i in range(9):
        assert client.post("/api/watchlists", headers=h, json={"name": f"L{i}"}).status_code == 201
    assert client.post("/api/watchlists", headers=h, json={"name": "one too many"}).status_code == 400


def test_tickers_are_normalized_and_lists_are_private():
    a, b = new_user(), new_user()
    wid = client.get("/api/watchlists", headers=a).json()["watchlists"][0]["id"]
    r = client.put(f"/api/watchlists/{wid}/tickers", headers=a, json={"tickers": ["tgt", "TGT", ".DJI"]})
    assert r.json()["tickers"] == ["TGT", "^DJI"]
    assert client.put(f"/api/watchlists/{wid}/tickers", headers=b, json={"tickers": ["X"]}).status_code == 404
    assert client.delete(f"/api/watchlists/{wid}", headers=b).status_code == 404


def test_legacy_endpoints_use_first_watchlist():
    h = new_user()
    client.put("/api/watchlist", headers=h, json={"tickers": ["WMT"]})
    assert client.get("/api/watchlists", headers=h).json()["watchlists"][0]["tickers"] == ["WMT"]


# ---- alerts
def setup_list(h, tickers=("TGT", "WMT")):
    wid = client.get("/api/watchlists", headers=h).json()["watchlists"][0]["id"]
    client.put(f"/api/watchlists/{wid}/tickers", headers=h, json={"tickers": list(tickers)})
    return wid


def add(h, wid, ticker, typ, value):
    return client.post(f"/api/watchlists/{wid}/alerts", headers=h, json={"ticker": ticker, "type": typ, "value": value})


def test_alert_validation():
    h = new_user(); wid = setup_list(h)
    assert add(h, wid, "tgt", "price_above", 105).json()["label"] == "Price above 105"
    assert add(h, wid, "TGT", "price_above", 0).status_code == 400
    assert add(h, wid, "TGT", "sma_cross_above", 30).status_code == 400  # not a supported average
    assert add(h, wid, "TGT", "sma_cross_above", 50).status_code == 201
    assert add(h, wid, "TGT", "nonsense", 1).status_code == 400
    assert add(h, wid, "AAPL", "price_above", 1).status_code == 400  # not on this watchlist


def test_removing_a_ticker_removes_its_alerts_and_alerts_are_private():
    a, b = new_user(), new_user()
    wid = setup_list(a)
    aid = add(a, wid, "TGT", "price_above", 105).json()["id"]
    assert client.delete(f"/api/alerts/{aid}", headers=b).status_code == 404
    client.put(f"/api/watchlists/{wid}/tickers", headers=a, json={"tickers": ["WMT"]})
    assert client.get(f"/api/watchlists/{wid}/alerts", headers=a).json()["alerts"] == []


def test_check_fires_price_alerts_and_logs_once_per_day():
    h = new_user(); wid = setup_list(h)
    add(h, wid, "TGT", "price_above", 105)   # TGT closes 110 -> fires
    add(h, wid, "TGT", "price_below", 105)   # does not fire
    add(h, wid, "WMT", "price_below", 95)    # WMT closes 90 -> fires
    out = client.post("/api/alerts/check", headers=h).json()
    assert sorted(f["ticker"] for f in out["firing"]) == ["TGT", "WMT"]
    assert out["checked"] == 3
    client.post("/api/alerts/check", headers=h)  # same day again
    events = client.get("/api/alerts/history", headers=h).json()["events"]
    assert len(events) == 2
    assert client.delete("/api/alerts/history", headers=h).status_code == 200
    assert client.get("/api/alerts/history", headers=h).json()["events"] == []


def test_sma_cross_fires_only_on_the_crossing_day(monkeypatch):
    # flat at 100 for ages, then 99 (below the average) and 101 (back above it): crossed above today
    monkeypatch.setitem(PRICES, "TGT", [99, 101])
    h = new_user(); wid = setup_list(h)
    add(h, wid, "TGT", "sma_cross_above", 20)
    add(h, wid, "TGT", "sma_cross_below", 20)
    out = client.post("/api/alerts/check", headers=h).json()
    assert [f["type"] for f in out["firing"]] == ["sma_cross_above"]
    monkeypatch.setitem(PRICES, "TGT", [101, 102])  # above yesterday and today: no new cross
    assert client.post("/api/alerts/check", headers=h).json()["firing"] == []


def test_check_reports_tickers_it_could_not_load(monkeypatch):
    h = new_user(); wid = setup_list(h, ("TGT", "ZZZ"))
    add(h, wid, "ZZZ", "price_above", 1)
    out = client.post("/api/alerts/check", headers=h).json()
    assert out["unavailable"] == ["ZZZ"] and out["firing"] == []


def test_alerts_require_login():
    assert client.post("/api/alerts/check").status_code == 401
    assert client.get("/api/watchlists").status_code == 401


# ---- CSV
def test_export_csv_newest_first_and_validation():
    r = client.get("/api/stocks/tgt/export.csv", params={"start": "2025-09-01", "end": "2025-09-05"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="TGT_2025-09-01_to_2025-09-05.csv"' in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "Date,Open,High,Low,Close"
    assert lines[1].startswith("2025-09-05") and lines[-1].startswith("2025-09-01")
    assert client.get("/api/stocks/tgt/export.csv", params={"start": "2025-09-05", "end": "2025-09-01"}).status_code == 400
    assert client.get("/api/stocks/tgt/export.csv", params={"start": "nope", "end": "2025-09-01"}).status_code == 400
    assert client.get("/api/stocks/tgt/export.csv", params={"start": "2020-01-01", "end": "2020-01-03"}).status_code == 404


# ---- first-load race
def test_two_requests_creating_the_first_watchlist_at_once_both_succeed(monkeypatch):
    """A request that loses the race to create 'My Watchlist' must use the winner's, not crash."""
    from sqlalchemy.orm import Session
    from db import SessionLocal, Watchlist
    h = new_user()
    uid = client.get("/api/me", headers=h).json()["id"]
    real_flush = Session.flush
    fired = []

    def flush_after_a_rival_wins(self, *a, **k):
        if not fired:
            fired.append(1)
            with SessionLocal() as rival:  # the other request gets there first
                rival.add(Watchlist(user_id=uid, name="My Watchlist", position=0))
                rival.commit()
        return real_flush(self, *a, **k)

    monkeypatch.setattr(Session, "flush", flush_after_a_rival_wins)
    r = client.get("/api/watchlists", headers=h)
    assert r.status_code == 200
    assert [w["name"] for w in r.json()["watchlists"]] == ["My Watchlist"]
    monkeypatch.setattr(Session, "flush", real_flush)
    assert len(client.get("/api/watchlists", headers=h).json()["watchlists"]) == 1  # no duplicate was created


def test_parallel_first_requests_all_succeed():
    from concurrent.futures import ThreadPoolExecutor
    h = new_user()
    calls = [lambda: client.get("/api/watchlists", headers=h), lambda: client.post("/api/alerts/check", headers=h)] * 3
    with ThreadPoolExecutor(6) as pool:
        codes = [f.result().status_code for f in [pool.submit(c) for c in calls]]
    assert codes == [200] * 6


def test_history_and_check_carry_timestamps():
    from datetime import datetime, timezone
    h = new_user(); wid = setup_list(h)
    add(h, wid, "TGT", "price_above", 105)
    out = client.post("/api/alerts/check", headers=h).json()
    since = out["firing"][0]["since"]
    ev = client.get("/api/alerts/history", headers=h).json()["events"][0]
    assert since.endswith("Z") and ev["at"].endswith("Z")
    assert abs((datetime.fromisoformat(since[:-1]).replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()) < 120
    again = client.post("/api/alerts/check", headers=h).json()["firing"][0]["since"]
    assert again == since  # the second check doesn't move "first seen"



def test_list_names_are_unique_ignoring_capitals_but_a_list_can_change_its_own_case():
    h = new_user()
    first = client.get("/api/watchlists", headers=h).json()["watchlists"][0]
    banks = client.post("/api/watchlists", headers=h, json={"name": "Banks"})
    assert banks.status_code == 201
    assert client.post("/api/watchlists", headers=h, json={"name": "banks"}).status_code == 409
    assert client.post("/api/watchlists", headers=h, json={"name": "  BANKS "}).status_code == 409
    # renaming onto another list's name, in any case, is refused
    assert client.patch(f"/api/watchlists/{first['id']}", headers=h, json={"name": "bAnKs"}).status_code == 409
    # a list may change its own capitalization
    r = client.patch(f"/api/watchlists/{banks.json()['id']}", headers=h, json={"name": "BANKS"})
    assert r.status_code == 200 and r.json()["name"] == "BANKS"
