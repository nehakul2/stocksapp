import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import core
import mailer
import notify
from db import SessionLocal, init_db

init_db()
client = TestClient(api.app)
_n = [0]
PRICES = {"TGT": [100, 110]}
SENT = []


def new_user():
    _n[0] += 1
    email = f"mail{_n[0]}@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, email


def history(closes, n=260):
    c = np.full(n, 100.0)
    c[-len(closes):] = closes
    return pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": 1e6}, index=pd.date_range("2025-01-01", periods=n))


@pytest.fixture(autouse=True)
def patch(monkeypatch):
    SENT.clear()
    PRICES["TGT"] = [100, 110]
    monkeypatch.setattr(core, "fetch_history", lambda t, p: history(PRICES[t]) if t in PRICES else (_ for _ in ()).throw(ValueError("no data")))
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.delenv("EMAIL_ALLOWED_TO", raising=False)
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: SENT.append((to, subject, text)))


def setup_alert(h, typ="price_above", value=105):
    wid = client.get("/api/watchlists", headers=h).json()["watchlists"][0]["id"]
    client.put(f"/api/watchlists/{wid}/tickers", headers=h, json={"tickers": ["TGT"]})
    return client.post(f"/api/watchlists/{wid}/alerts", headers=h, json={"ticker": "TGT", "type": typ, "value": value}).json()["id"]


def sent_to(email):
    return [m for m in SENT if m[0] == email]


def cycle():
    with SessionLocal() as db:
        return notify.run_cycle(db)


def turn_on(h):
    return client.put("/api/settings", headers=h, json={"email_alerts": True})


def test_settings_default_off_and_toggle():
    h, email = new_user()
    s = client.get("/api/settings", headers=h).json()
    assert s == {"email": email, "email_alerts": False, "email_configured": True, "email_available": True}
    assert turn_on(h).json()["email_alerts"] is True
    assert client.put("/api/settings", headers=h, json={"email_alerts": False}).json()["email_alerts"] is False


def test_settings_require_login():
    assert client.get("/api/settings").status_code == 401


def test_cannot_turn_on_when_not_configured_or_not_allowed(monkeypatch):
    h, email = new_user()
    monkeypatch.setenv("EMAIL_ALLOWED_TO", "someone.else@example.com")
    assert client.get("/api/settings", headers=h).json()["email_available"] is False
    assert turn_on(h).status_code == 400
    monkeypatch.delenv("RESEND_API_KEY")
    monkeypatch.delenv("EMAIL_ALLOWED_TO")
    assert client.get("/api/settings", headers=h).json()["email_configured"] is False
    assert turn_on(h).status_code == 400


def test_no_email_when_setting_is_off():
    h, email = new_user(); setup_alert(h)
    cycle()
    assert sent_to(email) == []


def test_emails_once_while_firing():
    h, email = new_user(); setup_alert(h); turn_on(h)
    cycle(); cycle(); cycle()
    assert len(sent_to(email)) == 1
    to, subject, body = sent_to(email)[0]
    assert to == email and "1 alert firing" in subject
    assert "TGT: price 110.00 is above your level of 105" in body and "/alerts" in body


def test_emails_again_after_it_stops_and_fires_again():
    h, email = new_user(); setup_alert(h); turn_on(h)
    cycle()
    PRICES["TGT"] = [100, 100]  # stops firing
    cycle()
    PRICES["TGT"] = [100, 120]  # fires again
    cycle()
    assert len(sent_to(email)) == 2


def test_failed_send_is_retried_next_cycle(monkeypatch):
    h, email = new_user(); setup_alert(h); turn_on(h)
    def boom(*a):
        raise RuntimeError("down")
    monkeypatch.setattr(mailer, "send", boom)
    cycle()
    assert sent_to(email) == []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: SENT.append((to, subject, text)))
    cycle()
    assert len(sent_to(email)) == 1


def test_unavailable_data_does_not_reset_an_alert(monkeypatch):
    h, email = new_user(); setup_alert(h); turn_on(h)
    cycle()
    monkeypatch.setattr(core, "fetch_history", lambda t, p: (_ for _ in ()).throw(ValueError("yahoo down")))
    cycle()
    monkeypatch.setattr(core, "fetch_history", lambda t, p: history(PRICES[t]))
    cycle()
    assert len(sent_to(email)) == 1  # the outage did not make it look like a brand-new firing


def test_allowlist_blocks_other_addresses(monkeypatch):
    h, email = new_user(); setup_alert(h); turn_on(h)
    monkeypatch.setenv("EMAIL_ALLOWED_TO", "not-this-one@example.com")
    cycle()
    assert sent_to(email) == []


def test_cycle_also_writes_history():
    h, _ = new_user(); setup_alert(h); turn_on(h)
    cycle()
    assert len(client.get("/api/alerts/history", headers=h).json()["events"]) == 1
