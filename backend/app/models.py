from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nickname = Column(String(64), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("PracticeSession", back_populates="user")


class PracticeSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False)
    difficulty = Column(String(16), default="medium")
    status = Column(String(16), default="active")  # active | finished
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    turns = relationship(
        "Turn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Turn.id",
    )
    report = relationship(
        "Report",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(String(8), nullable=False)  # ai | user
    content = Column(Text, nullable=False)
    audio_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("PracticeSession", back_populates="turns")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), unique=True, nullable=False)
    # 降级报告不计分，total_score 允许为空
    total_score = Column(Integer, nullable=True)
    band = Column(Float, nullable=True)  # 雅思 band（0.5 步长），见 docs/rubric-band.md
    cefr = Column(String(8), nullable=True)  # A2 / B1 / B2 / C1 / C2
    source = Column(String(16), default="llm")  # llm | mock（示例报告）
    dimensions_json = Column(Text, default="{}")
    bands_json = Column(Text, default="{}")
    fixes_json = Column(Text, default="[]")
    features_json = Column(Text, default="{}")
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("PracticeSession", back_populates="report")
