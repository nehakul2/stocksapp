import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import core

client = TestClient(api.app)


def series(daily, n=300, start=100.0, tz=None):
    """Closes that move by exactly the given daily %, repeating the pattern."""
    pct = np.resize(np.array(daily, dtype=float) / 100, n)
    close = start * np.cumprod(1 + pct)
    idx = pd.date_range("2025-01-01", periods=n, tz=tz)
    return pd.DataFrame({"Close": close, "Open": close, "High": close, "Low": close, "Volume": 1e6}, index=idx)


@pytest.fixture(autouse=True)
def patch(monkeypatch):
    market = [1.0, -1.0]                      # S&P: +1%, -1% repeating
    wild = [2.0, -2.0]                        # exactly twice as bumpy, same direction
    data = {"WILD": series(wild), "CALM": series([0.2, -0.2]), "^GSPC": series(market), "TZ": series(wild, tz="America/New_York")}
    monkeypatch.setattr(core, "fetch_history", lambda t, p: data[t] if t in data else (_ for _ in ()).throw(ValueError("no data")))
    core.get_fundamentals.cache_clear()


def test_beta_and_label_for_a_stock_twice_as_bumpy_as_the_market():
    r = core.risk_stats("WILD")
    assert r["beta"] == pytest.approx(2.0, abs=0.05)
    assert r["label"] == "more volatile than the market"
    assert r["volatility_pct"] == pytest.approx(2 * r["market_volatility_pct"], rel=0.02)
    assert r["worst_day"]["pct"] == pytest.approx(-2.0, abs=0.01)
    assert r["typical_day_pct"] == pytest.approx(2.0, abs=0.01)


def test_calm_stock_is_labelled_calmer():
    r = core.risk_stats("CALM")
    assert r["label"] == "calmer than the market" and r["beta"] == pytest.approx(0.2, abs=0.02)


def test_drawdown_and_distance_from_high_are_worked_out_from_prices(monkeypatch):
    close = np.concatenate([np.linspace(100, 200, 150), np.linspace(200, 120, 100), np.linspace(120, 150, 52)])
    df = pd.DataFrame({"Close": close, "Open": close, "High": close, "Low": close, "Volume": 1e6}, index=pd.date_range("2025-01-01", periods=len(close)))
    orig = core.fetch_history
    monkeypatch.setattr(core, "fetch_history", lambda t, p: df if t == "DD" else orig(t, p))
    r = core.risk_stats("DD")
    assert r["max_drawdown_pct"] == pytest.approx(-40.0, abs=0.5)   # 200 down to 120
    assert r["from_high_pct"] == pytest.approx(-25.0, abs=0.5)      # 150 vs 200
    assert any("25% below its highest price" in line for line in r["lines"])


def test_time_zone_aware_history_still_lines_up_with_the_market():
    assert core.risk_stats("TZ")["beta"] == pytest.approx(2.0, abs=0.05)


def test_too_little_history_is_an_error(monkeypatch):
    short = series([1, -1], n=40)
    orig = core.fetch_history
    monkeypatch.setattr(core, "fetch_history", lambda t, p: short if t == "SHORT" else orig(t, p))
    with pytest.raises(ValueError):
        core.risk_stats("SHORT")


def test_fundamentals_compute_yield_from_dividend_and_price(monkeypatch):
    class T:
        info = {"marketCap": 1.2e12, "trailingPE": 31.5, "forwardPE": None, "trailingEps": 4.2, "dividendRate": 0.8,
                "currentPrice": 100.0, "sector": "Consumer Defensive", "industry": "Discount Stores", "dividendYield": 0.0075}
    monkeypatch.setattr(core.yf, "Ticker", lambda t: T())
    f = core.get_fundamentals("WMT")
    assert f["market_cap"] == 1.2e12 and f["pe"] == 31.5 and f["forward_pe"] is None
    assert f["dividend_yield_pct"] == 0.8  # 0.8 / 100 * 100, ignoring Yahoo's yield field


def test_fundamentals_with_empty_info_are_all_none(monkeypatch):
    class T:
        info = {}
    monkeypatch.setattr(core.yf, "Ticker", lambda t: T())
    f = core.get_fundamentals("ZZZ")
    assert f["market_cap"] is None and f["dividend_yield_pct"] is None and f["sector"] == ""


def test_risk_endpoint_returns_both_parts_and_survives_one_failing(monkeypatch):
    monkeypatch.setattr(core, "get_fundamentals", lambda t: {"market_cap": 5.0, "pe": None, "forward_pe": None, "eps": None,
                                                              "dividend_yield_pct": None, "sector": "", "industry": ""})
    body = client.get("/api/stocks/wild/risk").json()
    assert body["ticker"] == "WILD" and body["risk"]["label"] == "more volatile than the market" and body["fundamentals"]["market_cap"] == 5.0
    # no price history for this one: fundamentals still come back
    body = client.get("/api/stocks/nohist/risk").json()
    assert body["risk"] is None and body["fundamentals"]["market_cap"] == 5.0


def test_risk_endpoint_404_when_nothing_loads(monkeypatch):
    def boom(t):
        raise RuntimeError("down")
    monkeypatch.setattr(core, "get_fundamentals", boom)
    assert client.get("/api/stocks/nohist/risk").status_code == 404


def test_label_follows_how_much_it_swings_not_beta(monkeypatch):
    # Swings 5x the market's size but in an unrelated pattern: beta is near zero, yet it is not "calmer".
    rng = np.random.default_rng(7)
    pct = rng.normal(0, 5, 300)
    close = 100 * np.cumprod(1 + pct / 100)
    df = pd.DataFrame({"Close": close, "Open": close, "High": close, "Low": close, "Volume": 1e6}, index=pd.date_range("2025-01-01", periods=300))
    orig = core.fetch_history
    monkeypatch.setattr(core, "fetch_history", lambda t, p: df if t == "RANDOM" else orig(t, p))
    r = core.risk_stats("RANDOM")
    assert abs(r["beta"]) < 0.6
    assert r["label"] == "more volatile than the market"
