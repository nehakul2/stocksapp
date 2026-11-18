"""Email alerts: the on/off setting, and a background checker that emails you once
when one of your alerts starts firing."""
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
from db import AlertEmail, SessionLocal, User, UserSettings, get_db

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


# ------------------------------------------------------------------ the checker
def email_text(firing: list) -> tuple:
    n = len(firing)
    subject = f"Stock Insights: {n} alert{'s' if n != 1 else ''} firing"
    lines = [f"- {f['message']}  (watchlist: {f['watchlist']})" for f in firing]
    body = (
        "These alerts just started firing:\n\n" + "\n".join(lines) +
        f"\n\nSee them in the app: {mailer.frontend_url()}/alerts\n\n"
        "You get one email when an alert starts firing, and another only if it stops and fires again. "
        "Turn email alerts off any time on the Alerts page. This is not financial advice."
    )
    return subject, body


def run_cycle(db: Session) -> int:
    """One pass over everyone who turned email alerts on. Returns how many emails were sent."""
    sent = 0
    users = db.scalars(select(User).join(UserSettings, UserSettings.user_id == User.id).where(UserSettings.email_alerts.is_(True)))
    for user in list(users):
        if not mailer.allowed(user.email):
            continue
        try:
            result = lists.evaluate_user_alerts(db, user)
            firing = result["firing"]
            firing_ids = {f["alert_id"] for f in firing}
            skip = set(result["unavailable_alert_ids"])  # couldn't check: leave their state alone

            # Alerts that stopped firing are forgotten, so they can email again later.
            for alert_id in result["alert_ids"]:
                if alert_id not in firing_ids and alert_id not in skip:
                    row = db.get(AlertEmail, alert_id)
                    if row:
                        db.delete(row)
            db.commit()

            already = {r.alert_id for r in db.scalars(select(AlertEmail).where(AlertEmail.alert_id.in_(list(firing_ids) or [0])))}
            new = [f for f in firing if f["alert_id"] not in already]
            lists.log_firings(db, user, firing)
            if not new:
                continue
            subject, body = email_text(new)
            mailer.send(user.email, subject, body)
            for f in new:
                db.add(AlertEmail(alert_id=f["alert_id"]))
            db.commit()
            sent += 1
        except Exception:
            db.rollback()
            log.exception("Alert email run failed for user %s", user.id)  # tries again next cycle
    return sent


_started = False


def start_scheduler() -> None:
    """Starts a background thread that runs run_cycle every ALERT_EMAIL_MINUTES (default 15).
    Does nothing if email isn't configured."""
    global _started
    if _started or not mailer.configured():
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
                log.exception("Alert email cycle crashed")
            time.sleep(minutes * 60)

    threading.Thread(target=loop, name="alert-emails", daemon=True).start()
    log.info("Alert email checker started (every %s minutes)", minutes)
