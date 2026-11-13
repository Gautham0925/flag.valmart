import csv
import io
import json
import os
import random
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.db import Base, SessionLocal, engine, get_db
from app.models import Challenge, Solve, Submission, User
from app.security import flag_digest, flag_matches, hash_password, make_token, read_token, verify_password

STATIC = os.path.join(os.path.dirname(__file__), "static")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
COOKIE = "fd_session"


class TTLCache:
    def __init__(self, ttl):
        self.ttl = ttl
        self.lock = threading.Lock()
        self.data = {}

    def get(self, key, build):
        with self.lock:
            hit = self.data.get(key)
            if hit and hit[0] > time.time():
                return hit[1]
        value = build()
        with self.lock:
            self.data[key] = (time.time() + self.ttl, value)
        return value

    def clear(self):
        with self.lock:
            self.data.clear()


cache = TTLCache(3)


def create_tables():
    for attempt in range(8):
        try:
            Base.metadata.create_all(engine)
            return
        except Exception:
            if attempt == 7:
                raise
            time.sleep(0.4 + random.random() * 0.6)


def seed():
    create_tables()
    db = SessionLocal()
    try:
        if db.scalar(select(func.count()).select_from(Challenge)) == 0 and os.path.exists(config.SEED_FILE):
            with open(config.SEED_FILE, encoding="utf-8") as fh:
                items = json.load(fh)
            for i, c in enumerate(items):
                db.add(Challenge(id=c["id"], title=c["title"], category=c.get("category", "Web"), description=c.get("description", ""), points=int(c.get("points", 100)), flag_hash=flag_digest(c["flag"]), position=i, enabled=True))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        if not db.scalar(select(User).where(User.role == "admin")):
            password = config.ADMIN_PASSWORD or secrets.token_urlsafe(12)
            db.add(User(username=config.ADMIN_USERNAME, pw_hash=hash_password(password), role="admin"))
            try:
                db.commit()
                if not config.ADMIN_PASSWORD:
                    print(f"[flagdesk] admin account created: {config.ADMIN_USERNAME} / {password}", flush=True)
            except IntegrityError:
                db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_):
    seed()
    yield


app = FastAPI(title="FlagDesk", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("x-fd") != "1":
            return JSONResponse({"detail": "Missing request header"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    uid = read_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if not user or user.disabled:
        raise HTTPException(401, "Not signed in")
    return user


def admin_user(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Organisers only")
    return user


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(default="", max_length=64)


class FlagIn(BaseModel):
    flag: str = Field(min_length=1, max_length=200)


class ChallengePatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = None
    category: str | None = Field(default=None, max_length=40)
    points: int | None = Field(default=None, ge=0, le=10000)
    enabled: bool | None = None
    flag: str | None = Field(default=None, min_length=1, max_length=200)


class PasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)


def set_cookie(response: Response, uid: int):
    response.set_cookie(COOKIE, make_token(uid), httponly=True, samesite="lax", secure=config.COOKIE_SECURE, max_age=config.SESSION_HOURS * 3600, path="/")


def public_user(user):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.get("/api/config")
def public_config():
    return {"event": config.EVENT_NAME, "registration_open": config.REGISTRATION_OPEN, "needs_code": bool(config.EVENT_CODE)}


@app.post("/api/register")
def register(body: Credentials, response: Response, db: Session = Depends(get_db)):
    if not config.REGISTRATION_OPEN:
        raise HTTPException(403, "Registration is closed")
    if config.EVENT_CODE and not secrets.compare_digest(body.code, config.EVENT_CODE):
        raise HTTPException(403, "Invalid event code")
    if not USERNAME_RE.match(body.username):
        raise HTTPException(422, "Username: 3-32 characters, letters, digits, . _ -")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if config.MAX_PARTICIPANTS:
        count = db.scalar(select(func.count()).select_from(User).where(User.role == "player"))
        if count >= config.MAX_PARTICIPANTS:
            raise HTTPException(403, "The event is full")
    user = User(username=body.username, pw_hash=hash_password(body.password), role="player")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That username is taken")
    set_cookie(response, user.id)
    return public_user(user)


@app.post("/api/login")
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.username) == body.username.lower()))
    if not user or user.disabled or not verify_password(body.password, user.pw_hash):
        raise HTTPException(401, "Invalid username or password")
    set_cookie(response, user.id)
    return public_user(user)


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(func.coalesce(func.sum(Solve.points), 0), func.count(Solve.id)).where(Solve.user_id == user.id)).one()
    return {**public_user(user), "score": int(rows[0]), "solved": int(rows[1])}


def solve_counts(db):
    return cache.get("counts", lambda: dict(db.execute(select(Solve.challenge_id, func.count(Solve.id)).group_by(Solve.challenge_id)).all()))


@app.get("/api/challenges")
def challenges(user: User = Depends(current_user), db: Session = Depends(get_db)):
    chals = cache.get("chals", lambda: db.scalars(select(Challenge).order_by(Challenge.position, Challenge.id)).all())
    mine = {r[0] for r in db.execute(select(Solve.challenge_id).where(Solve.user_id == user.id)).all()}
    counts = solve_counts(db)
    out = []
    for c in chals:
        if not c.enabled and user.role != "admin":
            continue
        out.append({"id": c.id, "title": c.title, "category": c.category, "description": c.description, "points": c.points, "solves": counts.get(c.id, 0), "solved": c.id in mine, "enabled": c.enabled})
    return out


@app.post("/api/challenges/{cid}/submit")
def submit(cid: str, body: FlagIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    chal = db.get(Challenge, cid)
    if not chal or (not chal.enabled and user.role != "admin"):
        raise HTTPException(404, "Challenge not found")
    since = datetime.now(timezone.utc) - timedelta(seconds=config.WRONG_WINDOW)
    wrong = db.scalar(select(func.count()).select_from(Submission).where(Submission.user_id == user.id, Submission.correct.is_(False), Submission.created_at >= since))
    if wrong >= config.WRONG_LIMIT:
        raise HTTPException(429, f"Too many wrong attempts. Wait up to {config.WRONG_WINDOW} seconds.")
    if db.scalar(select(Solve.id).where(Solve.user_id == user.id, Solve.challenge_id == cid)):
        return {"status": "already_solved", "message": "You already solved this one."}
    correct = flag_matches(body.flag, chal.flag_hash)
    db.add(Submission(user_id=user.id, challenge_id=cid, correct=correct, preview=body.flag.strip()[:80]))
    if correct and user.role == "player":
        db.add(Solve(user_id=user.id, challenge_id=cid, points=chal.points))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "already_solved", "message": "You already solved this one."}
    if not correct:
        return {"status": "wrong", "message": "Incorrect flag."}
    cache.clear()
    return {"status": "correct", "message": f"Correct! +{chal.points} points.", "points": chal.points}


def iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def build_scoreboard(db):
    rows = db.execute(
        select(User.id, User.username, func.coalesce(func.sum(Solve.points), 0), func.count(Solve.id), func.max(Solve.solved_at))
        .join(Solve, Solve.user_id == User.id, isouter=True)
        .where(User.role == "player", User.disabled.is_(False))
        .group_by(User.id, User.username)
    ).all()
    rows = sorted(rows, key=lambda r: (-int(r[2]), iso(r[4]) or "~"))
    return [{"rank": i + 1, "id": r[0], "username": r[1], "score": int(r[2]), "solved": int(r[3]), "last_solve": iso(r[4])} for i, r in enumerate(rows)]


@app.get("/api/scoreboard")
def scoreboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return cache.get("board", lambda: build_scoreboard(db))


@app.get("/api/admin/summary")
def admin_summary(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {
        "players": db.scalar(select(func.count()).select_from(User).where(User.role == "player")),
        "submissions": db.scalar(select(func.count()).select_from(Submission)),
        "correct": db.scalar(select(func.count()).select_from(Submission).where(Submission.correct.is_(True))),
        "solves": db.scalar(select(func.count()).select_from(Solve)),
        "registration_open": config.REGISTRATION_OPEN,
    }


@app.get("/api/admin/users")
def admin_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    board = {r["id"]: r for r in build_scoreboard(db)}
    users = db.scalars(select(User).where(User.role == "player").order_by(User.created_at)).all()
    return [{"id": u.id, "username": u.username, "disabled": u.disabled, "created_at": iso(u.created_at), "score": board.get(u.id, {}).get("score", 0), "solved": board.get(u.id, {}).get("solved", 0)} for u in users]


@app.get("/api/admin/submissions")
def admin_submissions(limit: int = 100, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Submission, User.username).join(User, User.id == Submission.user_id).order_by(Submission.id.desc()).limit(min(limit, 500))).all()
    return [{"id": s.id, "username": n, "challenge": s.challenge_id, "correct": s.correct, "preview": s.preview, "at": iso(s.created_at)} for s, n in rows]


@app.patch("/api/admin/challenges/{cid}")
def admin_patch_challenge(cid: str, body: ChallengePatch, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    chal = db.get(Challenge, cid)
    if not chal:
        raise HTTPException(404, "Challenge not found")
    data = body.model_dump(exclude_unset=True)
    flag = data.pop("flag", None)
    for k, v in data.items():
        setattr(chal, k, v)
    if flag:
        chal.flag_hash = flag_digest(flag)
    db.commit()
    cache.clear()
    return {"ok": True}


@app.post("/api/admin/users/{uid}/disable")
def admin_disable(uid: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    user = db.get(User, uid)
    if not user or user.role == "admin":
        raise HTTPException(404, "User not found")
    user.disabled = not user.disabled
    db.commit()
    cache.clear()
    return {"disabled": user.disabled}


@app.post("/api/admin/users/{uid}/password")
def admin_password(uid: int, body: PasswordIn, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    user = db.get(User, uid)
    if not user or user.role == "admin":
        raise HTTPException(404, "User not found")
    user.pw_hash = hash_password(body.password)
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/users/{uid}/solves")
def admin_clear_solves(uid: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    db.query(Solve).filter(Solve.user_id == uid).delete()
    db.commit()
    cache.clear()
    return {"ok": True}


@app.post("/api/admin/reset")
def admin_reset(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    db.query(Solve).delete()
    db.query(Submission).delete()
    db.commit()
    cache.clear()
    return {"ok": True}


@app.get("/api/admin/export.csv")
def admin_export(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["rank", "username", "score", "solved", "last_solve"])
    for r in build_scoreboard(db):
        writer.writerow([r["rank"], r["username"], r["score"], r["solved"], r["last_solve"] or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=scoreboard.csv"})


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
