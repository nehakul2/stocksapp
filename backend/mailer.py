"""Sends email through Resend (https://resend.com), using only the standard library.

Settings (environment variables):
  RESEND_API_KEY     your Resend API key. Without it, email is switched off.
  EMAIL_FROM         sender, default "Stock Insights <onboarding@resend.dev>" (Resend's test sender).
  EMAIL_ALLOWED_TO   comma-separated addresses that may receive email. While Resend has no
                     verified domain, it can only deliver to your own address, so set this to it.
                     Leave empty to allow everyone (once you own a verified domain).
  FRONTEND_URL       the website address, used for links inside emails.
"""
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("mailer")
API_URL = "https://api.resend.com/emails"


def configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY", "").strip())


def allowed(address: str) -> bool:
    """True if email may be sent to this address."""
    if not configured():
        return False
    allow = [a.strip().lower() for a in os.environ.get("EMAIL_ALLOWED_TO", "").split(",") if a.strip()]
    return not allow or address.strip().lower() in allow


def frontend_url() -> str:
    url = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")
    if url:
        return url
    first = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")[0].strip().rstrip("/")
    return first


def send(to: str, subject: str, text: str) -> None:
    """Sends one plain-text email. Raises on any failure. Tests replace this function."""
    body = json.dumps({
        "from": os.environ.get("EMAIL_FROM", "Stock Insights <onboarding@resend.dev>"),
        "to": [to], "subject": subject, "text": text,
    }).encode()
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}",
            "Content-Type": "application/json",
            # Resend's edge rejects Python's default "Python-urllib" client name with a bare 403.
            "User-Agent": "stocksapp/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"Resend answered with status {resp.status}.")
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode(errors="replace").strip()
        except Exception:
            pass
        detail = ""
        try:
            detail = str(json.loads(raw).get("message", ""))
        except Exception:
            # Not Resend's own JSON: show a short piece of what came back so the cause is visible.
            detail = " ".join(raw.split())[:150]
        raise RuntimeError(f"Resend said no ({e.code}): {detail or e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Couldn't reach Resend: {e.reason}")
