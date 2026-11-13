import base64
import hashlib
import hmac
import json
import os
import time
import unicodedata

from app import config

ITERATIONS = 60000


def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password, stored):
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(calc.hex(), dk)
    except Exception:
        return False


def normalize_flag(value):
    return unicodedata.normalize("NFC", value.strip())


def flag_digest(value):
    return hashlib.sha256(normalize_flag(value).encode()).hexdigest()


def flag_matches(value, digest):
    return hmac.compare_digest(flag_digest(value), digest)


def _sign(data):
    return hmac.new(config.SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()


def make_token(uid):
    payload = base64.urlsafe_b64encode(json.dumps({"uid": uid, "exp": int(time.time()) + config.SESSION_HOURS * 3600}).encode())
    return payload.decode() + "." + _sign(payload)


def read_token(token):
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(_sign(payload.encode()), sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        if data["exp"] < time.time():
            return None
        return data["uid"]
    except Exception:
        return None
