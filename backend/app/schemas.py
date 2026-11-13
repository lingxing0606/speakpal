from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(max_length=128)
    nickname: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    nickname: str = ""

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    token: str
    user: UserOut


class ProfileOut(UserOut):
    """改密码会签发新 token：旧 token 立刻失效，当前设备用这个继续。"""

    token: str | None = None


class ProfileUpdateIn(BaseModel):
    """自己改资料：昵称直接改；改密码必须给出旧密码。"""

    nickname: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, max_length=128)
    current_password: str | None = None


class AdminUserUpdateIn(BaseModel):
    """管理员改用户：不需要旧密码，但不能把昵称/密码同时留空。"""

    nickname: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, max_length=128)


class SceneOut(BaseModel):
    id: str
    name: str
    icon: str
    desc: str


class CreateSessionIn(BaseModel):
    scene_id: str
    # 不传就用设置里的偏好难度，见 PATCH /api/me/preferences
    difficulty: str | None = None


class SessionPlan(BaseModel):
    """Agent 本场计划（AI 架构方案 §三.1 方案 A）。

    目标只能取自场景任务清单，达成由关键词规则算（services/agent.py），
    `source` / `review` 分别记录「谁定的目标」「谁复盘的达成度」。
    """

    goals: List[str] = []
    focus: List[str] = []  # 用词提示（中文，注入对话 prompt，不给用户看）
    achieved: List[str] = []
    missing: List[str] = []
    rule_hits: List[str] = []  # 关键词命中，用于报告里核对 Critic 有没有放宽
    source: str = "rule"  # llm | rule
    review: str = ""  # llm | rule；空表示还没复盘
    comment: str = ""


class CreateSessionOut(BaseModel):
    session_id: int
    opening_question: str
    plan: SessionPlan = SessionPlan()


class AudioMeta(BaseModel):
    duration_sec: float | None = None
    speech_time_sec: float | None = None
    pauses: List[float] = []


class TurnIn(BaseModel):
    transcript: str
    audio: AudioMeta | None = None
    # voice | typed。不传就按有没有音频推断（前端打字时 audio 为空）
    input_mode: str | None = None


class TurnOut(BaseModel):
    turn_index: int
    ai_reply: str
    is_follow_up: bool = True
    should_finish: bool = False
    # 模型没回上来，这一轮用的是预设追问（前端据此提示）
    degraded: bool = False
    # 本场目标与最新进度（老会话为空 plan）
    plan: SessionPlan = SessionPlan()


class SentenceFix(BaseModel):
    original: str
    better: str
    reason: str
    # docs/design.md §16.4：错误分类 + 更自然的说法
    error_type: str = "grammar"  # spelling | grammar | stiffness | wordiness
    natural: str = ""
    # 拼写类才有的字段（报告页展示单词讲解和近义/反义/同类词）
    word: str = ""
    related: Dict[str, Any] = {}


class StudyItemOut(BaseModel):
    """学习卡（docs/design.md §16.1）。"""

    id: int
    kind: str  # word | phrase | spelling
    term: str
    context: str = ""
    meaning_zh: str = ""
    example: str = ""
    related: Dict[str, Any] = {}
    source_session_id: int | None = None
    # vocab = 从词库学的新词（计入每日新词上限）；空 = 报告/手动加的卡
    source: str = ""
    reps: int = 0
    lapses: int = 0
    interval_days: float = 0
    due_at: str
    due: bool = False
    last_result: str | None = None
    created_at: str


class ReportOut(BaseModel):
    report_id: int
    # 降级报告（模型不可用）不计分：total_score / band / cefr 均为 None
    total_score: int | None = None
    band: float | None = None
    cefr: str | None = None
    source: str = "llm"  # llm | mock
    # 仅 source=mock 时会有值：not_configured | invalid_key | unavailable
    mock_reason: str | None = None
    # voice | typed | mixed；comparable_band 跨模式可比（只含共享维度）
    answer_mode: str | None = None
    comparable_band: float | None = None
    dimensions: Dict[str, int] = {}
    bands: Dict[str, float] = {}
    sentence_fixes: List[SentenceFix] = []
    # 这次练习自动建的学习卡（拼写 / 句型）
    study_items: List[StudyItemOut] = []
    comment: str = ""
    features: Dict[str, Any] = {}
    scoring_detail: Dict[str, Any] = {}
    # 本轮目标达成（老报告为空 plan，报告页据此隐藏这一块）
    plan: SessionPlan = SessionPlan()
    # 多量表派生视图（雅思/CEFR/托福/多邻国/四六级），见 evaluation/scales.py；
    # 不落库：有 band 就现算，旧报告自动获得
    scales: Dict[str, Any] = {}
    note: str = "分数由 AI 估算，仅供参考。"


class HistoryItem(BaseModel):
    id: int
    scene_id: str
    scene_name: str
    # 前端靠这两个字段决定点开去哪：有 report_id → 报告页；status=active → 继续练习
    status: str = "active"  # active | finished
    report_id: int | None = None
    total_score: int | None = None
    # 报告档位与跨模式可比档：成长曲线按 comparable_band 画，别拿 total 跨模式比
    band: float | None = None
    cefr: str | None = None
    comparable_band: float | None = None
    answer_mode: str | None = None
    # 这一场里录音/打字各说几句，历史卡片可以直接标「有打字」
    voice_turns: int = 0
    typed_turns: int = 0
    created_at: str


class SessionTurnOut(BaseModel):
    id: int
    role: str  # ai | user
    content: str
    input_mode: str = "voice"  # ai 轮恒为 voice，无意义
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
    # 这一场的目标与当前进度（刷新 / 从历史回来时回填）
    plan: SessionPlan = SessionPlan()


class DrillItem(BaseModel):
    index: int
    source: str  # 用户原句里要改的那句
    target: str  # 改写后的目标句，跟读这句
    focus: str = ""
    attempts: int = 0
    best_similarity: float | None = None
    passed: bool = False


class DrillsOut(BaseModel):
    report_id: int
    pass_threshold: float
    items: List[DrillItem] = []


class DrillAttemptIn(BaseModel):
    transcript: str


class DrillAttemptOut(BaseModel):
    index: int
    similarity: float
    passed: bool
    attempts: int
    best_similarity: float
    feedback: str


class SceneFrame(BaseModel):
    en: str
    zh: str


class SceneFramesOut(BaseModel):
    scene_id: str
    frames: List[SceneFrame] = []


class HintItem(BaseModel):
    """一条可以照着说的提示：英文 / 中文 / 这条在答什么（3–5 字）。"""

    en: str
    zh: str
    tag: str


class HintsIn(BaseModel):
    """「换一批」带 nonce：参与缓存 key 并绕过缓存命中；不传就按原口径查缓存。"""

    nonce: str | None = Field(default=None, max_length=32)


class HintsOut(BaseModel):
    """手动输入提示（任务二）：source=llm 是模型生成，frames 是场景通用句型回退。"""

    hints: List[HintItem] = []
    source: str = "frames"  # llm | frames
    cached: bool = False


class RecommendationOut(BaseModel):
    recommended_difficulty: str  # easy | medium | hard
    last_band: float | None = None
    cefr: str | None = None
    last_scene_id: str | None = None
    reason: str


class StudyItemIn(BaseModel):
    kind: str  # word | phrase | spelling
    term: str
    context: str = ""
    meaning_zh: str = ""
    example: str = ""
    related: Dict[str, Any] = {}
    source_session_id: int | None = None
    # report | vocab | review，不传按 report（报告页「加入学习清单」）
    source: str | None = None


class StudyReviewIn(BaseModel):
    # 句型卡自评三档（grade，兼容旧字段 result）；拼写卡用 answer 默写、由后端判档
    grade: str | None = None  # again | hard | good
    result: str | None = None
    answer: str | None = None


class WordAssistIn(BaseModel):
    """AI 助记：term 必填，用户已给中文时优先保留用户的中文。"""

    term: str = Field(min_length=1, max_length=64)
    meaning_zh: str = Field(default="", max_length=200)


class WordAssistOut(BaseModel):
    term: str
    meaning_zh: str = ""
    pos: str = ""
    # 无 key / 超时 / JSON 坏时为 null，不阻塞前端
    assist: Dict[str, Any] | None = None
    source: str = "meaning"  # llm | meaning
    cached: bool = False


class WordImportIn(BaseModel):
    """自由扩充：粘贴一段文本；use_ai=False 时未命中词库的词只存用户给的中文。"""

    text: str = Field(default="", max_length=10000)
    use_ai: bool = True


class WordImportOut(BaseModel):
    added: int = 0
    skipped: int = 0
    items: List[StudyItemOut] = []


class WordLearnIn(BaseModel):
    """三步学词完成后落卡；三步标记由前端按实际流程回传。"""

    term: str = Field(min_length=1, max_length=64)
    meaning_zh: str = Field(default="", max_length=200)
    example: str = Field(default="", max_length=300)
    context: str = Field(default="", max_length=300)
    recognized: bool = False
    spelled: bool = False
    used: bool = False


class NoteIn(BaseModel):
    title: str | None = Field(default=None, max_length=128)
    body: str = ""
    session_id: int | None = None


class NoteOut(BaseModel):
    id: int
    title: str
    body: str
    session_id: int | None = None
    created_at: str
    updated_at: str


class PreferencesOut(BaseModel):
    """设置页的偏好（跟着账号走，换设备也还在）。难度从首页搬进设置后由这里提供。"""

    practice_difficulty: str = "medium"  # easy | medium | hard
    word_scope: str = "cet4"  # 新词从哪个词库取：gaokao | cet4 | cet6
    # 报告默认量表：ielts | cefr | toefl | duolingo | cet（见 evaluation/scales.py）
    report_scale: str = "ielts"


class PreferencesIn(BaseModel):
    practice_difficulty: str | None = None
    word_scope: str | None = None
    report_scale: str | None = None


class VocabWordOut(BaseModel):
    scope: str
    term: str
    phonetic: str = ""
    pos: str = ""
    meaning_zh: str = ""
    example: str = ""
    example_zh: str = ""
    level: str = ""
    related: Dict[str, Any] = {}


class VocabOut(BaseModel):
    """「今天学几个新词」：范围和进度一起给，前端不用再发一次范围请求。

    每日新词上限已取消：`daily_limit` / `remaining_today` 保留字段但为 null，
    前端不要再据此禁用按钮。
    """

    scope: str
    name: str = ""
    desc: str = ""
    total: int = 0
    learned: int = 0
    remaining: int = 0
    daily_limit: int | None = None
    used_today: int = 0
    remaining_today: int | None = None
    items: List[VocabWordOut] = []
    scopes: List[Dict[str, Any]] = []


class VocabAddIn(BaseModel):
    """两种加法：给出具体词（terms），或按范围直接取 count 个。"""

    terms: List[str] | None = None
    scope: str | None = None
    count: int | None = None


class VocabAddOut(BaseModel):
    """added=新建了几张卡；skipped=已经在清单里；limited 保留但恒为 0（不再限每日数量）。"""

    added: int = 0
    skipped: int = 0
    limited: int = 0
    daily_limit: int | None = None
    used_today: int = 0
    remaining_today: int | None = None
    items: List[StudyItemOut] = []


class GrammarCardOut(BaseModel):
    id: str
    group: str
    group_name: str = ""
    point: str
    rule: str = ""
    wrong: str = ""
    right: str = ""
    blank: str = ""
    answer: str = ""
    learned: bool = False


class GrammarGroupOut(BaseModel):
    id: str
    name: str
    desc: str = ""
    total: int = 0
    learned: int = 0
    items: List[GrammarCardOut] = []


class GrammarOut(BaseModel):
    groups: List[GrammarGroupOut] = []
    total: int = 0
    learned: int = 0


class SpokenCardOut(BaseModel):
    id: str
    formal: str
    natural: str
    why: str = ""
    learned: bool = False


class SpokenOut(BaseModel):
    total: int = 0
    learned: int = 0
    items: List[SpokenCardOut] = []


class LibraryAddIn(BaseModel):
    """语法/口语加卡：`ids` 指定卡；只给 `group` 就加整组；口语可以只给 `count`。"""

    ids: List[str] | None = None
    group: str | None = None
    count: int | None = None


class LibraryAddOut(BaseModel):
    added: int = 0
    skipped: int = 0
    remaining: int = 0
    items: List[StudyItemOut] = []


class TodayGroupOut(BaseModel):
    key: str
    label: str
    count: int = 0
    items: List[StudyItemOut] = []


class TodayOut(BaseModel):
    """「今天」合并队列：组内按到期时间，组间固定顺序（单词 → 拼写 → 语法 → 口语 → 句型）。"""

    groups: List[TodayGroupOut] = []
    total: int = 0
    notes_count: int = 0
