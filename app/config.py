import os
import secrets
import time


def _bool(name, default):
    return os.environ.get(name, "1" if default else "0").lower() in ("1", "true", "yes")


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/flagdesk.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]


def _secret():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.environ.get("SECRET_FILE", os.path.join(os.path.dirname(__file__), "..", "data", ".secret"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    for _ in range(50):
        with open(path) as fh:
            value = fh.read().strip()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError("could not read secret key")


SECRET_KEY = _secret()
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "organiser")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
EVENT_CODE = os.environ.get("EVENT_CODE", "")
REGISTRATION_OPEN = _bool("REGISTRATION_OPEN", True)
MAX_PARTICIPANTS = int(os.environ.get("MAX_PARTICIPANTS", "0"))
WRONG_LIMIT = int(os.environ.get("WRONG_LIMIT", "8"))
WRONG_WINDOW = int(os.environ.get("WRONG_WINDOW", "60"))
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
COOKIE_SECURE = _bool("COOKIE_SECURE", False)
SEED_FILE = os.environ.get("SEED_FILE", os.path.join(os.path.dirname(__file__), "..", "challenges.seed.json"))
EVENT_NAME = os.environ.get("EVENT_NAME", "VULNMARKET CTF")
POOL_SIZE = int(os.environ.get("POOL_SIZE", "20"))
