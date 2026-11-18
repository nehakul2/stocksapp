import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import ai
import api
import core

client = TestClient(api.app)


def history(last_day_change, month_change):
    """60 flat days at 100, then a final day that moves by last_day_change.
    The close 22 days back is set so the 1-month move equals month_change."""
    close = np.full(60, 100.0)
    close[-1] = 100.0 * (1 + last_day_change)
    close[-22] = close[-1] / (1 + month_change)
    idx = pd.date_range("2025-01-01", periods=60)
    return pd.DataFrame({"Close": close, "Open": close, "High": close, "Low": close, "Volume": 1e6}, index=idx)


MOVES = {"TGT": (-0.04, 0.10), "WMT": (-0.01, 0.0), "COST": (0.01, 0.0), "^GSPC": (0.005, 0.0)}


@pytest.fixture(autouse=True)
def patch(monkeypatch):
    monkeypatch.setattr(core, "fetch_history", lambda t, p: history(*MOVES[t]) if t in MOVES else (_ for _ in ()).throw(ValueError("no data")))
    monkeypatch.setattr(core, "find_peers", lambda t: {
        "sector": "Consumer Defensive", "industry": "Discount Stores", "source": "industry",
        "peers": [{"ticker": "WMT", "name": "Walmart"}, {"ticker": "COST", "name": "Costco"}, {"ticker": "ZZZZ", "name": "Broken"}],
    })


def test_comparison_has_self_peers_and_market_and_skips_broken_peers():
    out = core.compare_with_peers("TGT")
    kinds = [(r["kind"], r["ticker"]) for r in out["rows"]]
    assert kinds == [("self", "TGT"), ("peer", "WMT"), ("peer", "COST"), ("market", "^GSPC")]
    assert out["rows"][0]["day_pct"] == pytest.approx(-4.0)
    assert out["rows"][0]["month_pct"] == pytest.approx(10.0)
    assert out["peer_median_day_pct"] == pytest.approx(0.0)  # median of -1 and +1


def test_peer_facts_sentence():
    note = core.peer_facts(core.compare_with_peers("TGT"))
    assert "WMT -1.00%" in note and "COST +1.00%" in note and "median +0.00%" in note


def test_peer_facts_empty_without_peers(monkeypatch):
    monkeypatch.setattr(core, "find_peers", lambda t: {"sector": "", "industry": "", "peers": [], "source": "none"})
    assert core.peer_facts(core.compare_with_peers("TGT")) == ""


def test_peers_endpoint():
    r = client.get("/api/stocks/tgt/peers")
    assert r.status_code == 200
    body = r.json()
    assert body["industry"] == "Discount Stores" and len(body["rows"]) == 4


def test_peers_endpoint_unknown_ticker_is_404():
    assert client.get("/api/stocks/NOPE/peers").status_code == 404


def test_find_peers_falls_back_to_builtin_group(monkeypatch):
    core.find_peers.cache_clear() if hasattr(core.find_peers, "cache_clear") else None
    import importlib
    real = importlib.reload(core)  # restore the real find_peers after the autouse patch
    monkeypatch.setattr(real.yf, "Ticker", lambda t: (_ for _ in ()).throw(RuntimeError("yahoo down")))
    out = real.find_peers("TGT")
    assert out["source"] == "builtin"
    assert "TGT" not in [p["ticker"] for p in out["peers"]] and len(out["peers"]) == real.MAX_PEERS


def test_find_peers_unknown_stock_has_none(monkeypatch):
    import importlib
    real = importlib.reload(core)
    monkeypatch.setattr(real.yf, "Ticker", lambda t: (_ for _ in ()).throw(RuntimeError("yahoo down")))
    assert real.find_peers("QQQQQ")["source"] == "none"


def test_prompt_includes_peer_numbers_and_the_tighter_instructions():
    seen = {}
    def fake(key, prompt, max_tokens=500):
        seen["p"] = prompt
        return json.dumps({"summary": "x", "relevant": []})
    import unittest.mock as m
    with m.patch.object(ai, "ask_claude", fake):
        ai.explain_move("k", "TGT", {"pct_change": -4.0, "magnitude": "a notable move"}, [], "Similar companies today: WMT -1.00%.")
    p = seen["p"]
    assert "WMT -1.00%" in p
    assert "3-4 short sentences" in p and "do not repeat the caveat" in p and "say so plainly" in p
