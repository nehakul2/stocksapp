import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import core
import mailer
import notify
import push
from db import SessionLocal, init_db

init_db()
client = TestClient(api.app)
_n = [0]
PRICES = {"TGT": [100, 110]}
SENT = []
PUSHED = []


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
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    PUSHED.clear()


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
    assert s == {"email": email, "email_alerts": False, "email_configured": True, "email_available": True,
                 "push_configured": False, "push_devices": 0}
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


def wl_alerts(h):
    wid = client.get("/api/watchlists", headers=h).json()["watchlists"][0]["id"]
    return client.get(f"/api/watchlists/{wid}/alerts", headers=h).json()["alerts"]


def test_alerts_start_switched_on():
    h, _ = new_user(); setup_alert(h)
    assert wl_alerts(h)[0]["paused"] is False


def test_paused_alert_is_not_checked_does_not_show_or_email_and_can_be_resumed():
    h, email = new_user(); aid = setup_alert(h); turn_on(h)
    r = client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": True})
    assert r.status_code == 200 and r.json()["paused"] is True
    assert wl_alerts(h)[0]["paused"] is True
    chk = client.post("/api/alerts/check", headers=h).json()
    assert chk["firing"] == [] and chk["checked"] == 0
    cycle()
    assert sent_to(email) == []
    assert client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": False}).json()["paused"] is False
    assert wl_alerts(h)[0]["paused"] is False
    assert len(client.post("/api/alerts/check", headers=h).json()["firing"]) == 1
    cycle()
    assert len(sent_to(email)) == 1


def test_pausing_while_firing_then_resuming_emails_again():
    h, email = new_user(); aid = setup_alert(h); turn_on(h)
    cycle()
    assert len(sent_to(email)) == 1
    client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": True})
    client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": False})
    cycle()
    assert len(sent_to(email)) == 2


def test_pausing_twice_is_fine_and_other_users_cannot_pause():
    h, _ = new_user(); aid = setup_alert(h)
    assert client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": True}).status_code == 200
    assert client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": True}).status_code == 200
    other, _ = new_user()
    assert client.patch(f"/api/alerts/{aid}", headers=other, json={"paused": False}).status_code == 404
    assert client.patch("/api/alerts/999999", headers=h, json={"paused": True}).status_code == 404
    assert client.patch(f"/api/alerts/{aid}", json={"paused": True}).status_code == 401


def test_deleting_a_paused_alert_works():
    h, _ = new_user(); aid = setup_alert(h)
    client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": True})
    assert client.delete(f"/api/alerts/{aid}", headers=h).status_code == 200
    assert wl_alerts(h) == []


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


def test_a_new_alert_never_inherits_a_deleted_alerts_pause():
    h, _ = new_user(); aid = setup_alert(h)
    client.patch(f"/api/alerts/{aid}", headers=h, json={"paused": True})
    client.delete(f"/api/alerts/{aid}", headers=h)
    wid = client.get("/api/watchlists", headers=h).json()["watchlists"][0]["id"]
    new = client.post(f"/api/watchlists/{wid}/alerts", headers=h, json={"ticker": "TGT", "type": "price_above", "value": 105}).json()
    assert wl_alerts(h)[0]["paused"] is False and new["paused"] is False


# ------------------------------------------------------------------ push
def enable_push(monkeypatch):
    pub, priv = push.generate_keys()
    monkeypatch.setenv("VAPID_PUBLIC_KEY", pub)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", priv)
    monkeypatch.setattr(push, "send", lambda sub, msg, ttl=0: PUSHED.append((sub["endpoint"], msg)))
    return pub


def device(n=1):
    keys_pub, _ = push.generate_keys()
    return {"endpoint": f"https://push.example.com/send/{_n[0]}-{n}", "keys": {"p256dh": keys_pub, "auth": push.b64e(b"0123456789abcdef")}}


def test_push_key_is_null_until_configured_then_served(monkeypatch):
    assert client.get("/api/push/key").json() == {"public_key": None}
    pub = enable_push(monkeypatch)
    assert client.get("/api/push/key").json() == {"public_key": pub}


def test_subscribe_needs_login_and_setup(monkeypatch):
    h, _ = new_user()
    assert client.post("/api/push/subscribe", json=device()).status_code in (401, 403)
    assert client.post("/api/push/subscribe", headers=h, json=device()).status_code == 400
    enable_push(monkeypatch)
    bad = device(); bad["endpoint"] = "http://insecure.example.com/x"
    assert client.post("/api/push/subscribe", headers=h, json=bad).status_code == 400
    r = client.post("/api/push/subscribe", headers=h, json=device())
    assert r.status_code == 200 and r.json()["push_devices"] == 1 and r.json()["push_configured"] is True


def test_subscribing_twice_keeps_one_row_and_unsubscribe_removes_it(monkeypatch):
    enable_push(monkeypatch)
    h, _ = new_user()
    d = device()
    client.post("/api/push/subscribe", headers=h, json=d)
    assert client.post("/api/push/subscribe", headers=h, json=d).json()["push_devices"] == 1
    assert client.post("/api/push/unsubscribe", headers=h, json={"endpoint": d["endpoint"]}).json()["push_devices"] == 0


def test_cannot_remove_someone_elses_device(monkeypatch):
    enable_push(monkeypatch)
    h1, _ = new_user(); h2, _ = new_user()
    d = device()
    client.post("/api/push/subscribe", headers=h1, json=d)
    assert client.post("/api/push/unsubscribe", headers=h2, json={"endpoint": d["endpoint"]}).status_code == 200
    assert client.get("/api/settings", headers=h1).json()["push_devices"] == 1


def test_push_alone_notifies_once_while_firing_even_with_email_off(monkeypatch):
    enable_push(monkeypatch)
    h, email = new_user()
    client.post("/api/push/subscribe", headers=h, json=device())
    setup_alert(h)
    assert cycle() == 1
    assert len(PUSHED) == 1 and "TGT" in PUSHED[0][1]["body"] and PUSHED[0][1]["url"] == "/alerts"
    assert sent_to(email) == []
    assert cycle() == 0 and len(PUSHED) == 1
    PRICES["TGT"] = [100, 100]
    cycle()
    PRICES["TGT"] = [100, 110]
    cycle()
    assert len(PUSHED) == 2


def test_email_and_push_both_go_out_once(monkeypatch):
    enable_push(monkeypatch)
    h, email = new_user()
    turn_on(h)
    client.post("/api/push/subscribe", headers=h, json=device())
    setup_alert(h)
    assert cycle() == 1
    assert len(sent_to(email)) == 1 and len(PUSHED) == 1
    assert cycle() == 0 and len(sent_to(email)) == 1 and len(PUSHED) == 1


def test_push_failure_is_retried_but_email_success_is_not_repeated(monkeypatch):
    enable_push(monkeypatch)
    h, email = new_user()
    client.post("/api/push/subscribe", headers=h, json=device())
    setup_alert(h)
    monkeypatch.setattr(push, "send", lambda sub, msg, ttl=0: (_ for _ in ()).throw(RuntimeError("push down")))
    assert cycle() == 0
    monkeypatch.setattr(push, "send", lambda sub, msg, ttl=0: PUSHED.append((sub["endpoint"], msg)))
    assert cycle() == 1 and len(PUSHED) == 1


def test_expired_device_is_removed(monkeypatch):
    enable_push(monkeypatch)
    h, _ = new_user()
    client.post("/api/push/subscribe", headers=h, json=device())
    setup_alert(h)
    monkeypatch.setattr(push, "send", lambda sub, msg, ttl=0: (_ for _ in ()).throw(push.Gone("410")))
    cycle()
    assert client.get("/api/settings", headers=h).json()["push_devices"] == 0


def test_push_test_endpoint(monkeypatch):
    h, _ = new_user()
    assert client.post("/api/push/test", headers=h).status_code == 400  # not set up
    enable_push(monkeypatch)
    assert client.post("/api/push/test", headers=h).status_code == 400  # no device
    client.post("/api/push/subscribe", headers=h, json=device())
    assert client.post("/api/push/test", headers=h).json() == {"sent": 1}
    monkeypatch.setattr(push, "send", lambda sub, msg, ttl=0: (_ for _ in ()).throw(RuntimeError("Push service said no (403): bad")))
    r = client.post("/api/push/test", headers=h)
    assert r.status_code == 502 and "403" in r.json()["detail"]


def test_scheduler_starts_for_push_only(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    started = []
    monkeypatch.setattr(notify.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: started.append(1)})())
    monkeypatch.setattr(notify, "_started", False)
    notify.start_scheduler()
    assert started == []
    enable_push(monkeypatch)
    notify.start_scheduler()
    assert started == [1]


def test_push_text_summarises_several_alerts():
    one = notify.push_text([{"ticker": "TGT", "message": "TGT: price above 105"}])
    assert one["body"] == "TGT: price above 105"
    many = notify.push_text([{"ticker": "TGT", "message": "a"}, {"ticker": "NEM", "message": "b"}, {"ticker": "TGT", "message": "c"}])
    assert many["body"] == "3 alerts firing: TGT, NEM"


# ------------------------------------------------------------------ the encryption itself
def _decrypt(body: bytes, ua_private, auth_secret: bytes) -> bytes:
    """An independent reader for the aes128gcm format, written from RFC 8188/8291 to check push.encrypt."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
    as_public, cipher = body[21:21 + idlen], body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    ua_public = ua_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = ua_private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = HKDF(hashes.SHA256(), 32, auth_secret, b"WebPush: info\x00" + ua_public + as_public).derive(shared)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    plain = AESGCM(cek).decrypt(nonce, cipher, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_encrypted_message_can_be_read_by_the_receiving_device():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    ua = ec.generate_private_key(ec.SECP256R1())
    ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = b"sixteen byte key"
    body = push.encrypt(b'{"title":"hi"}', push.b64e(ua_pub), push.b64e(auth))
    assert _decrypt(body, ua, auth) == b'{"title":"hi"}'
    assert push.encrypt(b"same", push.b64e(ua_pub), push.b64e(auth)) != push.encrypt(b"same", push.b64e(ua_pub), push.b64e(auth))


def test_vapid_header_is_a_signed_token_for_the_push_service(monkeypatch):
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pub = enable_push(monkeypatch)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:me@example.com")
    h = push.vapid_headers("https://web.push.apple.com/abc123")["Authorization"]
    assert h.startswith("vapid t=") and h.endswith(f"k={pub}")
    token = h[len("vapid t="):].split(",")[0]
    key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.b64d(pub))
    claims = jwt.decode(token, key, algorithms=["ES256"], audience="https://web.push.apple.com")
    assert claims["sub"] == "mailto:me@example.com" and claims["exp"] > __import__("time").time()


def test_generated_keys_have_the_standard_shape():
    pub, priv = push.generate_keys()
    assert len(push.b64d(pub)) == 65 and push.b64d(pub)[0] == 4 and len(push.b64d(priv)) == 32
