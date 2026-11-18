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


# ---- test email button
def test_test_email_sends_to_the_signed_in_user():
    h, email = new_user()
    r = client.post("/api/settings/test-email", headers=h)
    assert r.status_code == 200 and r.json() == {"sent_to": email}
    assert len(sent_to(email)) == 1 and "test" in sent_to(email)[0][1].lower()


def test_test_email_explains_each_way_it_can_fail(monkeypatch):
    h, email = new_user()
    assert client.post("/api/settings/test-email").status_code == 401
    monkeypatch.setenv("EMAIL_ALLOWED_TO", "other@example.com")
    r = client.post("/api/settings/test-email", headers=h)
    assert r.status_code == 400 and "approved list" in r.json()["detail"] and email in r.json()["detail"]
    monkeypatch.delenv("EMAIL_ALLOWED_TO")
    monkeypatch.delenv("RESEND_API_KEY")
    r = client.post("/api/settings/test-email", headers=h)
    assert r.status_code == 400 and "RESEND_API_KEY" in r.json()["detail"]


def test_test_email_passes_on_the_providers_message(monkeypatch):
    h, _ = new_user()
    def refuse(*a):
        raise RuntimeError("Resend said no (403): You can only send testing emails to your own email address.")
    monkeypatch.setattr(mailer, "send", refuse)
    r = client.post("/api/settings/test-email", headers=h)
    assert r.status_code == 502 and "only send testing emails to your own" in r.json()["detail"]


def test_mailer_turns_resend_errors_into_readable_messages(monkeypatch):
    import io, json, urllib.error, urllib.request
    monkeypatch.undo()  # use the real mailer.send
    monkeypatch.setenv("RESEND_API_KEY", "k")
    err = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(json.dumps({"message": "Only your own address"}).encode()))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(err))
    with pytest.raises(RuntimeError, match=r"403.*Only your own address"):
        mailer.send("a@b.c", "s", "t")


def test_mailer_sends_a_client_name_and_shows_non_json_errors(monkeypatch):
    import io, urllib.error, urllib.request
    monkeypatch.undo()
    monkeypatch.setenv("RESEND_API_KEY", "k")
    seen = {}

    def fake(req, *a, **k):
        seen["ua"] = req.get_header("User-agent")
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"<html>\n error code: 1010 \n</html>"))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(RuntimeError, match=r"403.*error code: 1010"):
        mailer.send("a@b.c", "s", "t")
    assert seen["ua"] == "stocksapp/1.0"


def test_email_says_when_the_alert_was_first_seen(monkeypatch):
    h, email = new_user(); setup_alert(h); turn_on(h)
    monkeypatch.setenv("ALERT_TIMEZONE", "America/Los_Angeles")
    cycle()
    body = sent_to(email)[0][2]
    assert "first seen " in body and ("PST" in body or "PDT" in body) and ("AM" in body or "PM" in body)


def test_fmt_time_uses_the_configured_zone_and_falls_back_to_utc(monkeypatch):
    from datetime import datetime, timezone
    t = datetime(2026, 11, 18, 22, 31, tzinfo=timezone.utc)
    monkeypatch.setenv("ALERT_TIMEZONE", "America/Los_Angeles")
    assert notify.fmt_time(t) == "Nov 18, 2:31 PM PST"
    monkeypatch.setenv("ALERT_TIMEZONE", "Not/AZone")
    assert notify.fmt_time(t) == "Nov 18, 10:31 PM UTC"
    monkeypatch.delenv("ALERT_TIMEZONE")
    assert notify.fmt_time(t.replace(tzinfo=None)) == "Nov 18, 10:31 PM UTC"
