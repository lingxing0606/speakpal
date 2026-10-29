from typing import Any, Dict, List

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=4, max_length=64)
    nickname: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    nickname: str = ""

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    token: str
    user: UserOut


class ProfileUpdateIn(BaseModel):
    """自己改资料：昵称直接改；改密码必须给出旧密码。"""

    nickname: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=4, max_length=64)
    current_password: str | None = None


class AdminUserUpdateIn(BaseModel):
    """管理员改用户：不需要旧密码，但不能把昵称/密码同时留空。"""

    nickname: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=4, max_length=64)


class SceneOut(BaseModel):
    id: str
    name: str
    icon: str
    desc: str


class CreateSessionIn(BaseModel):
    scene_id: str
    difficulty: str = "medium"


class CreateSessionOut(BaseModel):
    session_id: int
    opening_question: str


class AudioMeta(BaseModel):
    duration_sec: float | None = None
    speech_time_sec: float | None = None
    pauses: List[float] = []


class TurnIn(BaseModel):
    transcript: str
    audio: AudioMeta | None = None


class TurnOut(BaseModel):
    turn_index: int
    ai_reply: str
    is_follow_up: bool = True
    should_finish: bool = False


class SentenceFix(BaseModel):
    original: str
    better: str
    reason: str


class ReportOut(BaseModel):
    report_id: int
    # 降级报告（模型不可用）不计分：total_score / band / cefr 均为 None
    total_score: int | None = None
    band: float | None = None
    cefr: str | None = None
    source: str = "llm"  # llm | mock
    # 仅 source=mock 时会有值：not_configured | invalid_key | unavailable
    mock_reason: str | None = None
    dimensions: Dict[str, int] = {}
    bands: Dict[str, float] = {}
    sentence_fixes: List[SentenceFix] = []
    comment: str = ""
    features: Dict[str, Any] = {}
    scoring_detail: Dict[str, Any] = {}
    note: str = "分数由 AI 估算，仅供参考。"


class HistoryItem(BaseModel):
    id: int
    scene_id: str
    scene_name: str
    total_score: int | None = None
    created_at: str


class SessionTurnOut(BaseModel):
    id: int
    role: str  # ai | user
    content: str
    created_at: str


class SessionDetailOut(BaseModel):
    """刷新页面 / 从历史点回来时，用它把对话和状态回填。"""

    id: int
    scene_id: str
    scene_name: str
    difficulty: str
    status: str  # active | finished
    created_at: str
    turns: List[SessionTurnOut] = []
    report_id: int | None = None
    total_score: int | None = None
