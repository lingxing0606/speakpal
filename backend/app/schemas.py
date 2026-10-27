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
    total_score: int
    dimensions: Dict[str, int]
    sentence_fixes: List[SentenceFix]
    comment: str
    features: Dict[str, Any] = {}
    note: str = "分数由 AI 估算，仅供参考。"


class HistoryItem(BaseModel):
    id: int
    scene_id: str
    scene_name: str
    total_score: int | None = None
    created_at: str
