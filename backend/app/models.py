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
    # 改密码时 +1，让其他设备上签发的 token 立即失效
    token_version = Column(Integer, default=0, nullable=False)
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
    # user 轮的输入方式：voice（录音）/ typed（打字），报告据此决定哪些维度能算
    input_mode = Column(String(8), default="voice")
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
    # 降级原因：not_configured | invalid_key | unavailable，前端据此给不同提示
    mock_reason = Column(String(24), nullable=True)
    # 作答模式 voice/typed/mixed；comparable_band 是跨模式可比档（只含共享维度）
    answer_mode = Column(String(8), nullable=True)
    comparable_band = Column(Float, nullable=True)
    dimensions_json = Column(Text, default="{}")
    bands_json = Column(Text, default="{}")
    scoring_json = Column(Text, default="{}")
    fixes_json = Column(Text, default="[]")
    features_json = Column(Text, default="{}")
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("PracticeSession", back_populates="report")


class DrillAttempt(Base):
    """跟读重说的每一次尝试，用来算「这句练了几遍、最好到什么程度」。"""

    __tablename__ = "drill_attempts"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    item_index = Column(Integer, nullable=False)
    transcript = Column(Text, nullable=False)
    similarity = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LearningItem(Base):
    """从一次练习里诊断出来的薄弱点：拼写错误 / 表达僵硬 / 语法问题。

    每条都是一个可复习的卡：有触发句、目标词/句、中文讲解、例子、近义反义同类词，
    以及间隔重复（SM-2 简化版）的调度状态。
    """

    __tablename__ = "learning_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    type = Column(String(16), nullable=False)  # spelling | natural | grammar
    trigger = Column(Text, nullable=False)  # 用户原句（问题现场）
    target = Column(Text, nullable=False)  # 正确拼写 / 更自然的说法
    explanation = Column(Text, default="")  # 中文讲解
    examples_json = Column(Text, default="[]")
    related_json = Column(Text, default="[]")  # [{word, relation, meaning_zh}]
    review_prompt = Column(Text, default="")
    status = Column(String(12), default="active")  # active | suspended
    reps = Column(Integer, default=0)
    lapses = Column(Integer, default=0)
    ease = Column(Float, default=2.5)
    interval_days = Column(Integer, default=0)
    due_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(120), default="")
    content = Column(Text, default="")
    learning_item_id = Column(Integer, ForeignKey("learning_items.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
