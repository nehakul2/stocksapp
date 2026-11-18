"""Earnings dates: only upcoming dates are returned."""
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import core


class FakeTicker:
    def __init__(self, calendar):
        self.calendar = calendar


def patch(monkeypatch, calendar):
    monkeypatch.setattr(core.yf, "Ticker", lambda t: FakeTicker(calendar))


def iso(d):
    return d.strftime("%Y-%m-%d")


def test_past_date_is_not_shown_as_upcoming(monkeypatch):
    patch(monkeypatch, {"Earnings Date": [date.today() - timedelta(days=20)]})
    assert core.get_next_earnings_date("T1") == ""


def test_future_date_is_returned(monkeypatch):
    soon = date.today() + timedelta(days=5)
    patch(monkeypatch, {"Earnings Date": [soon]})
    assert core.get_next_earnings_date("T2") == iso(soon)


def test_today_counts_as_upcoming(monkeypatch):
    patch(monkeypatch, {"Earnings Date": [date.today()]})
    assert core.get_next_earnings_date("T3") == iso(date.today())


def test_picks_earliest_future_date_from_a_range(monkeypatch):
    past, near, far = (date.today() + timedelta(days=n) for n in (-3, 4, 6))
    patch(monkeypatch, {"Earnings Date": [far, past, near]})
    assert core.get_next_earnings_date("T4") == iso(near)


def test_datetime_and_dataframe_shapes(monkeypatch):
    soon = datetime.now() + timedelta(days=3)
    patch(monkeypatch, {"Earnings Date": [soon]})
    assert core.get_next_earnings_date("T5") == iso(soon.date())
    df = pd.DataFrame({0: [pd.Timestamp(soon)]}, index=["Earnings Date"])
    patch(monkeypatch, df)
    assert core.get_next_earnings_date("T6") == iso(soon.date())


@pytest.mark.parametrize("cal", [None, {}, {"Earnings Date": []}, pd.DataFrame()])
def test_missing_calendar(monkeypatch, cal):
    patch(monkeypatch, cal)
    assert core.get_next_earnings_date("T7") == ""


def test_cached_date_that_has_since_passed_is_not_returned(monkeypatch):
    yesterday = iso(date.today() - timedelta(days=1))
    monkeypatch.setattr(core, "_earnings_dates", lambda t: (yesterday,))
    assert core.get_next_earnings_date("ANY") == ""
