"""Offline tests: Yahoo Finance is replaced with synthetic data."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import core


def fake_history(ticker, period):
    if ticker == "BAD":
        raise ValueError("No price history found for BAD. Check the symbol.")
    n = 300
    rng = np.random.default_rng(1)
    close = np.cumsum(rng.standard_normal(n)) + 100
    close[-1] = close[-2] * 1.06  # a 6% jump on the last day
    vol = np.r_[np.full(n - 1, 1e6), 3e6]
    idx = pd.date_range("2025-01-01", periods=n)
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": vol}, index=idx)


@pytest.fixture(autouse=True)
def patch(monkeypatch):
    monkeypatch.setattr(core, "fetch_history", fake_history)
    monkeypatch.setattr(core, "get_stock_summary", lambda t: {"name": t, "ticker": t, "price": 150.0, "currency": "USD", "exchange": "NasdaqGS"})
    monkeypatch.setattr(core, "get_news", lambda t, max_items=5: [{"title": "Big news", "publisher": "Wire", "link": None}])
    monkeypatch.setattr(core, "get_next_earnings_date", lambda t: "")
    monkeypatch.setattr(core, "search_tickers", lambda q, max_results=8: [{"symbol": "TGT", "name": "Target", "exchange": "NYQ", "type": "Equity"}])


client = TestClient(api.app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_search():
    assert client.get("/api/search", params={"q": "target"}).json()["results"][0]["symbol"] == "TGT"
    assert client.get("/api/search", params={"q": "t"}).status_code == 422


def test_overview_and_alias():
    r = client.get("/api/overview", params={"tickers": "tgt, gold, BAD"}).json()["rows"]
    assert [x["ticker"] for x in r] == ["TGT", "GC=F", "BAD"]
    assert r[0]["sma_200"] is not None and "error" in r[2]


def test_attention_flags_big_move():
    items = client.get("/api/attention", params={"tickers": "TGT"}).json()["items"]
    assert items and any("Moved up" in x for x in items[0]["reasons"])


def test_detail():
    d = client.get("/api/stocks/TGT").json()
    assert d["summary"]["price"] == 150.0
    assert d["explanation"]["pct_change"] == pytest.approx(6.0, abs=0.5)
    assert d["trend"]["direction"] in ("upward", "downward", "flat")
    assert set(d["smas"]) == {"5", "20", "50", "100", "200"}


def test_history_json_safe():
    bars = client.get("/api/stocks/TGT/history", params={"range": "1mo"}).json()["bars"]
    assert len(bars) == 22 and bars[-1]["sma_5"] is not None


def test_errors():
    assert client.get("/api/stocks/BAD").status_code == 404
    assert client.get("/api/stocks/TGT", params={"range": "9y"}).status_code == 400
    assert client.post("/api/stocks/TGT/ai-summary").status_code == 400
    assert client.get("/api/overview", params={"tickers": ",".join(f"T{i}" for i in range(40))}).status_code == 400


def test_trend_estimates_anchor_to_last_close():
    t = client.get("/api/stocks/TGT").json()["trend"]
    last = fake_history("TGT", "2y")["Close"].iloc[-1]
    up = t["direction"] == "upward"
    assert (t["estimates"]["1_day"] > last) == up
    assert (t["estimates"]["30_day"] > last) == up


def test_sma_200_available_for_default_range():
    d = client.get("/api/stocks/TGT").json()
    assert d["smas"]["200"] is not None


def _two_series(stock_last, market_last):
    def hist(ticker, period):
        n = 300
        base = np.full(n, 100.0)
        last = market_last if ticker == "^GSPC" else stock_last
        base[-1] = 100.0 * (1 + last / 100)
        idx = pd.date_range("2025-01-01", periods=n)
        return pd.DataFrame({"Open": base, "High": base, "Low": base, "Close": base, "Volume": np.full(n, 1e6)}, index=idx)
    return hist


def test_market_note_held_up_better_before_earnings(monkeypatch):
    from datetime import datetime, timedelta
    monkeypatch.setattr(core, "fetch_history", _two_series(-0.4, -1.0))
    monkeypatch.setattr(core, "get_next_earnings_date", lambda t: (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    e = client.get("/api/stocks/TGT").json()["explanation"]
    assert "outperformed" in e["market_note"] and "specific to the stock" not in e["market_note"]
    assert e["earnings_note"]


def test_market_note_large_gap_without_earnings(monkeypatch):
    monkeypatch.setattr(core, "fetch_history", _two_series(-4.0, 0.0))
    e = client.get("/api/stocks/TGT").json()["explanation"]
    assert "lagged" in e["market_note"] and "specific to the stock" in e["market_note"]
