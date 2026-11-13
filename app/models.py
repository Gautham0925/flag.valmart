from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False, index=True)
    pw_hash = Column(String(200), nullable=False)
    role = Column(String(16), nullable=False, default="player")
    disabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=now)


class Challenge(Base):
    __tablename__ = "challenges"
    id = Column(String(16), primary_key=True)
    title = Column(String(120), nullable=False)
    category = Column(String(40), nullable=False, default="Web")
    description = Column(Text, nullable=False, default="")
    points = Column(Integer, nullable=False, default=100)
    flag_hash = Column(String(64), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)


class Solve(Base):
    __tablename__ = "solves"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    challenge_id = Column(String(16), ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    points = Column(Integer, nullable=False)
    solved_at = Column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("user_id", "challenge_id", name="uq_solve"),)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    challenge_id = Column(String(16), nullable=False)
    correct = Column(Boolean, nullable=False)
    preview = Column(String(80), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_sub_user_time", "user_id", "created_at"),)
