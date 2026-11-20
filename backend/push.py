"""Web push: sends a notification to a browser or an iPhone Home Screen app.

Written with the `cryptography` and `pyjwt` packages we already have, instead of the
pywebpush library (which needs a compiler to install and can break a deploy).
It follows the Web Push standards: RFC 8291 (message encryption), RFC 8188 (aes128gcm)
and RFC 8292 (VAPID, the server's signed identity).

Settings (environment):
  VAPID_PUBLIC_KEY   the server's public key (a long URL-safe string)
  VAPID_PRIVATE_KEY  the matching private key. Keep it secret.
  VAPID_SUBJECT      a contact address such as mailto:you@example.com (optional)
Make a pair with:  python push.py
"""
import base64
import json
import os
import struct
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

# The cryptography and jwt packages are imported inside the functions that need them, so the
# server still starts (with push switched off) if they are ever missing.


class Gone(Exception):
    """The browser says this subscription no longer exists (404 or 410). Delete it."""


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64d(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


def configured() -> bool:
    return bool(public_key() and os.environ.get("VAPID_PRIVATE_KEY", "").strip())


def generate_keys() -> tuple:
    """Returns (public, private) as URL-safe strings, ready to paste into the settings."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64e(public), b64e(private)


def _private_key():
    from cryptography.hazmat.primitives.asymmetric import ec
    value = int.from_bytes(b64d(os.environ["VAPID_PRIVATE_KEY"]), "big")
    return ec.derive_private_key(value, ec.SECP256R1())


def vapid_headers(endpoint: str) -> dict:
    """The Authorization header that proves the message comes from this server."""
    import jwt
    u = urlparse(endpoint)
    claims = {
        "aud": f"{u.scheme}://{u.netloc}",
        "exp": int(time.time()) + 12 * 3600,
        "sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com"),
    }
    token = jwt.encode(claims, _private_key(), algorithm="ES256")
    return {"Authorization": f"vapid t={token}, k={public_key()}"}


def encrypt(payload: bytes, p256dh: str, auth: str, *, _salt: bytes = None, _eph=None) -> bytes:
    """Encrypts a message for one subscription (RFC 8291, aes128gcm). The result is the
    whole request body. The two underscore arguments exist only so tests can pin the randomness."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    ua_public = b64d(p256dh)
    auth_secret = b64d(auth)
    eph = _eph or ec.generate_private_key(ec.SECP256R1())
    as_public = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public))

    key_info = b"WebPush: info\x00" + ua_public + as_public
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=auth_secret, info=key_info).derive(shared)

    salt = _salt or os.urandom(16)
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)

    record = payload + b"\x02"  # 0x02 marks the last record
    cipher = AESGCM(cek).encrypt(nonce, record, None)
    header = salt + struct.pack(">I", 4096) + bytes([len(as_public)]) + as_public
    return header + cipher


def send(sub: dict, message: dict, ttl: int = 6 * 3600) -> None:
    """Sends one notification. `sub` has endpoint, p256dh and auth. Raises Gone when the
    subscription is dead, and RuntimeError for any other refusal."""
    body = encrypt(json.dumps(message).encode(), sub["p256dh"], sub["auth"])
    headers = {
        **vapid_headers(sub["endpoint"]),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl),
        "Urgency": "high",
        "User-Agent": "stocksapp/1.0",
    }
    req = urllib.request.Request(sub["endpoint"], data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15):
            return
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            raise Gone(str(e.code))
        detail = ""
        try:
            detail = " ".join(e.read().decode("utf-8", "replace").split())[:150]
        except Exception:
            pass
        raise RuntimeError(f"Push service said no ({e.code}): {detail or e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Couldn't reach the push service: {e.reason}")


if __name__ == "__main__":
    pub, priv = generate_keys()
    print("Add these three settings (Railway backend variables, and backend/.env if you run locally):\n")
    print(f"VAPID_PUBLIC_KEY={pub}")
    print(f"VAPID_PRIVATE_KEY={priv}")
    print("VAPID_SUBJECT=mailto:you@example.com")
