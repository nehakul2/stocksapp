"""Alert notifications: the email on/off setting, phone/browser push sign-up, and a
background checker that tells you once when one of your alerts starts firing."""
import logging
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import auth
import lists
import mailer
import push
from db import AlertEmail, PushSubscription, SessionLocal, User, UserSettings, get_db

log = logging.getLogger("notify")
router = APIRouter()


# ------------------------------------------------------------------ settings
class SettingsBody(BaseModel):
    email_alerts: bool


def settings_json(db: Session, user: User) -> dict:
    row = db.get(UserSettings, user.id)
    return {
        "email": user.email,
        "email_alerts": bool(row and row.email_alerts),
        "email_configured": mailer.configured(),
        "email_available": mailer.allowed(user.email),
        "push_configured": push.configured(),
        "push_devices": len(db.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user.id)).all()),
    }


@router.get("/api/settings")
def get_settings(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return settings_json(db, user)


@router.put("/api/settings")
def put_settings(body: SettingsBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if body.email_alerts and not mailer.allowed(user.email):
        raise HTTPException(400, "Email alerts aren't available for this address yet.")
    row = db.get(UserSettings, user.id)
    if row is None:
        row = UserSettings(user_id=user.id)
        db.add(row)
    row.email_alerts = body.email_alerts
    db.commit()
    return settings_json(db, user)


@router.post("/api/settings/test-email")
def test_email(user: User = Depends(auth.current_user)):
    """Sends one test email to the signed-in user, and reports exactly what went wrong if it fails."""
    if not mailer.configured():
        raise HTTPException(400, "Email isn't set up on this server: RESEND_API_KEY is missing.")
    if not mailer.allowed(user.email):
        raise HTTPException(400, f"{user.email} isn't on the approved list (EMAIL_ALLOWED_TO), so email is off for it.")
    try:
        mailer.send(user.email, "Stock Insights: test email",
                    "This is a test from Stock Insights. If you can read this, alert emails will reach you.")
    except Exception as e:
        log.warning("Test email failed: %s", e)
        raise HTTPException(502, str(e))
    return {"sent_to": user.email}


# ------------------------------------------------------------------ push sign-up
class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushBody(BaseModel):
    endpoint: str
    keys: PushKeys


class PushOff(BaseModel):
    endpoint: str


@router.get("/api/push/key")
def push_key():
    """The server's public key, which the browser needs to sign up. Null if push isn't set up."""
    return {"public_key": push.public_key() if push.configured() else None}


@router.post("/api/push/subscribe")
def push_subscribe(body: PushBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if not push.configured():
        raise HTTPException(400, "Push notifications aren't set up on this server yet.")
    if not body.endpoint.startswith("https://") or len(body.endpoint) > 1000:
        raise HTTPException(400, "That doesn't look like a valid push address.")
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if row is None:
        row = PushSubscription(user_id=user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth)
        db.add(row)
    else:  # same device signing in as someone else, or keys refreshed
        row.user_id, row.p256dh, row.auth = user.id, body.keys.p256dh, body.keys.auth
    db.commit()
    return settings_json(db, user)


@router.post("/api/push/unsubscribe")
def push_unsubscribe(body: PushOff, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id))
    if row:
        db.delete(row)
        db.commit()
    return settings_json(db, user)


def push_to_user(db: Session, user: User, message: dict) -> int:
    """Sends to every device this user signed up. Dead subscriptions are removed.
    Returns how many devices accepted it; raises RuntimeError if devices exist but none did."""
    subs = list(db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)))
    ok, last_err = 0, None
    for sub in subs:
        try:
            push.send({"endpoint": sub.endpoint, "p256dh": sub.p256dh, "auth": sub.auth}, message)
            ok += 1
        except push.Gone:
            db.delete(sub)
        except Exception as e:
            last_err = e
            log.warning("Push to user %s failed: %s", user.id, e)
    db.commit()
    if subs and not ok and last_err:
        raise RuntimeError(str(last_err))
    return ok


@router.post("/api/push/test")
def push_test(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Sends one test notification to every device the user signed up, and says what went wrong if it fails."""
    if not push.configured():
        raise HTTPException(400, "Push notifications aren't set up on this server yet.")
    if not db.scalar(select(PushSubscription.id).where(PushSubscription.user_id == user.id)):
        raise HTTPException(400, "No device has turned on notifications yet.")
    try:
        n = push_to_user(db, user, {"title": "Stock Insights", "body": "Test notification. Alerts will show up like this.", "url": "/alerts", "tag": "test"})
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    if n == 0:
        raise HTTPException(400, "That device had expired, so it was removed. Turn notifications on again.")
    return {"sent": n}


# ------------------------------------------------------------------ the checker
def fmt_time(dt) -> str:
    """'Nov 18, 2:31 PM PST' in ALERT_TIMEZONE (default UTC)."""
    from datetime import timezone
    from zoneinfo import ZoneInfo
    try:
        zone = ZoneInfo(os.environ.get("ALERT_TIMEZONE", "UTC") or "UTC")
    except Exception:
        zone = timezone.utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(zone)
    return f"{local:%b} {local.day}, {local.hour % 12 or 12}:{local:%M} {'AM' if local.hour < 12 else 'PM'} {local.tzname()}"


def email_text(firing: list, since: dict = None) -> tuple:
    since = since or {}
    n = len(firing)
    subject = f"Stock Insights: {n} alert{'s' if n != 1 else ''} firing"
    lines = []
    for f in firing:
        t = since.get((f["watchlist"], f["message"][:200]))
        when = f", first seen {fmt_time(t)}" if t else ""
        lines.append(f"- {f['message']}  (watchlist: {f['watchlist']}{when})")
    body = (
        "These alerts just started firing:\n\n" + "\n".join(lines) +
        f"\n\nSee them in the app: {mailer.frontend_url()}/alerts\n\n"
        "You get one email when an alert starts firing, and another only if it stops and fires again. "
        "Turn email alerts off any time on the Alerts page. This is not financial advice."
    )
    return subject, body


def push_text(firing: list) -> dict:
    n = len(firing)
    if n == 1:
        body = firing[0]["message"]
    else:
        names = ", ".join(dict.fromkeys(f["ticker"] for f in firing))
        body = f"{n} alerts firing: {names}"
    return {"title": "Stock Insights alert", "body": body[:180], "url": "/alerts", "tag": "alerts"}


def run_cycle(db: Session) -> int:
    """One pass over everyone who wants alerts by email or push. Returns how many people were told."""
    sent = 0
    email_users = {u.id: u for u in db.scalars(select(User).join(UserSettings, UserSettings.user_id == User.id).where(UserSettings.email_alerts.is_(True)))}
    push_users = {}
    if push.configured():
        push_users = {u.id: u for u in db.scalars(select(User).join(PushSubscription, PushSubscription.user_id == User.id))}
    for user in list({**email_users, **push_users}.values()):
        by_email = user.id in email_users and mailer.configured() and mailer.allowed(user.email)
        by_push = user.id in push_users
        if not (by_email or by_push):
            continue
        try:
            result = lists.evaluate_user_alerts(db, user)
            firing = result["firing"]
            firing_ids = {f["alert_id"] for f in firing}
            skip = set(result["unavailable_alert_ids"])  # couldn't check: leave their state alone

            # Alerts that stopped firing are forgotten, so they can notify again later.
            for alert_id in result["alert_ids"]:
                if alert_id not in firing_ids and alert_id not in skip:
                    row = db.get(AlertEmail, alert_id)
                    if row:
                        db.delete(row)
            db.commit()

            already = {r.alert_id for r in db.scalars(select(AlertEmail).where(AlertEmail.alert_id.in_(list(firing_ids) or [0])))}
            new = [f for f in firing if f["alert_id"] not in already]
            since = lists.log_firings(db, user, firing)
            if not new:
                continue

            told, errors = False, []
            if by_email:
                try:
                    subject, body = email_text(new, since)
                    mailer.send(user.email, subject, body)
                    told = True
                    print(f"[notify] Emailed user {user.id}: {len(new)} alert(s)", flush=True)
                except Exception as e:
                    errors.append(e)
                    log.warning("Alert email failed for user %s: %s", user.id, e)
            if by_push:
                try:
                    if push_to_user(db, user, push_text(new)):
                        told = True
                        print(f"[notify] Pushed to user {user.id}: {len(new)} alert(s)", flush=True)
                except Exception as e:
                    errors.append(e)
                    log.warning("Alert push failed for user %s: %s", user.id, e)
            if not told:
                if errors:
                    continue  # every channel failed: try again next cycle
                continue  # push devices were all expired; nothing to mark
            for f in new:
                db.add(AlertEmail(alert_id=f["alert_id"]))
            db.commit()
            sent += 1
        except Exception:
            db.rollback()
            log.exception("Alert notification run failed for user %s", user.id)  # tries again next cycle
    return sent


_started = False


def start_scheduler() -> None:
    """Starts a background thread that runs run_cycle every ALERT_EMAIL_MINUTES (default 15).
    Does nothing if neither email nor push is configured."""
    global _started
    if _started or not (mailer.configured() or push.configured()):
        return
    _started = True
    minutes = max(1, int(os.environ.get("ALERT_EMAIL_MINUTES", "15") or 15))

    def loop():
        time.sleep(60)  # let the app finish starting
        while True:
            try:
                with SessionLocal() as db:
                    run_cycle(db)
            except Exception:
                log.exception("Alert cycle crashed")
            time.sleep(minutes * 60)

    threading.Thread(target=loop, name="alert-notifications", daemon=True).start()
    print(f"[notify] Alert checker started (every {minutes} minutes)", flush=True)
