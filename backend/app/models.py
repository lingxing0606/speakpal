
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .db import Base
from .timeutil import utcnow


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nickname = Column(String(64), default="")
    # 改密码时 +1，让其他设备上签发的 token 立即失效
    token_version = Column(Integer, default=0, nullable=False)
    # 设置页的偏好：练习难度（easy|medium|hard）、新词词库范围（gaokao|cet4|cet6）
    practice_difficulty = Column(String(16), default="medium")
    word_scope = Column(String(16), default="cet4")
    # 报告默认展示的量表（ielts/cefr/toefl/duolingo/cet），见 evaluation/scales.py
    report_scale = Column(String(8), default="ielts")
    created_at = Column(DateTime, default=utcnow)

    sessions = relationship("PracticeSession", back_populates="user")


class PracticeSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scene_id = Column(String(64), nullable=False)
    difficulty = Column(String(16), default="medium")
    status = Column(String(16), default="active")  # active | finished
    # Agent 本场计划（目标 / 用词提示 / 由谁定的），见 services/agent.py
    plan_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)

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
    created_at = Column(DateTime, default=utcnow)

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
    # Agent 目标达成度（Critic 复盘结果），示例报告为规则兜底结果
    plan_json = Column(Text, default="{}")
    fixes_json = Column(Text, default="[]")
    features_json = Column(Text, default="{}")
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    session = relationship("PracticeSession", back_populates="report")


class DrillAttempt(Base):
    """跟读重说的每一次尝试，用来算「这句练了几遍、最好到什么程度」。"""

    __tablename__ = "drill_attempts"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    item_index = Column(Integer, nullable=False)
    transcript = Column(Text, nullable=False)
    similarity = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class StudyItem(Base):
    """学习卡（间隔重复）：单词 / 句型 / 拼写错。

    契约见 docs/design.md §16.1，字段名按文档来，别自创。
    """

    __tablename__ = "study_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(8), nullable=False)  # word | phrase | spelling
    term = Column(String(128), nullable=False)  # 卡片正面
    context = Column(Text, default="")  # 出现的那句话（语境）
    meaning_zh = Column(Text, default="")
    example = Column(Text, default="")
    related_json = Column(
        Text, default='{"synonyms":[],"antonyms":[],"similar":[]}'
    )
    source_session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    # vocab = 词库学来的新词（计入每日新词上限）；'' = 报告自动建卡 / 手动加入
    source = Column(String(16), default="")
    ease = Column(Float, default=2.5)
    interval_days = Column(Float, default=0)
    due_at = Column(DateTime, default=utcnow, index=True)
    reps = Column(Integer, default=0)
    lapses = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)


class ReviewEvent(Base):
    """每次复习提交的日志（学习模块重构方案 §4.1）。

    只记结果与间隔变化，不存用户原文；「今天复习了几张」「笔记里这条是不是
    今天复习过」都从这张表按本地日统计。
    """

    __tablename__ = "review_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("study_items.id"), nullable=False, index=True)
    result = Column(String(8), nullable=False)  # again | hard | good
    interval_before = Column(Float, nullable=True)
    interval_after = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(128), default="")  # 不填就用正文首行
    body = Column(Text, default="")
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow)


class NoteLink(Base):
    """笔记正文里命中的学习卡（方案 A：纯文本自动识别）。

    start/end 是正文里的字符位置；同一个词出现多次会有多行。
    """

    __tablename__ = "note_links"

    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("study_items.id"), nullable=False, index=True)
    term = Column(String(128), nullable=False)
    start = Column(Integer, nullable=False)
    end = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class NoteLinkMute(Base):
    """用户取消的误关联：同一 (note, item) 只留一行。"""

    __tablename__ = "note_link_mutes"

    note_id = Column(Integer, ForeignKey("notes.id"), primary_key=True)
    item_id = Column(Integer, ForeignKey("study_items.id"), primary_key=True)
    created_at = Column(DateTime, default=utcnow)
