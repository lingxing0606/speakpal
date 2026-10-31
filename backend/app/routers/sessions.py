import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import PracticeSession, Report, Turn, User
from ..schemas import (
    CreateSessionIn,
    CreateSessionOut,
    HistoryItem,
    ReportOut,
    SessionDetailOut,
    SessionTurnOut,
    TurnIn,
    TurnOut,
)
from ..security import get_current_user
from ..timeutil import utc_iso
from ..services.learning import upsert_items
from ..services.llm import chat_reply
from ..services.llm_config import LLMConfig, UserKeyInvalid, get_llm_config
from ..services.report_view import report_out
from ..services.rules import apply_to_report
from ..services.scenes import get_scene
from ..services.scoring import generate_report
from evaluation.features import fluency_features, speech_features, tokenize

router = APIRouter(prefix="/api", tags=["sessions"])

KEY_INVALID_BODY = {
    "kind": "key_invalid",
    "detail": "模型密钥无效或被拒绝，请到「设置」更换密钥后再试",
}
KEY_REQUIRED_BODY = {
    "kind": "llm_not_configured",
    "detail": "还没有接入模型密钥",
}

# 单轮回答的长度上限：再长就说明不是一句话，前端也不好展示
MAX_TRANSCRIPT_CHARS = 2000


def key_invalid_response() -> JSONResponse:
    """用户自己的密钥被拒：502 + key_invalid，明确让人去换 key，不降级。"""
    return JSONResponse(status_code=502, content=KEY_INVALID_BODY)


def key_required_response() -> JSONResponse:
    """没有任何可用密钥：没有模型就没法对话，直接拦住，不假装能练。"""
    return JSONResponse(status_code=409, content=KEY_REQUIRED_BODY)


@router.post("/sessions", response_model=CreateSessionOut)
def create_session(
    body: CreateSessionIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    if not llm.configured:
        return key_required_response()
    scene = get_scene(body.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    difficulty = (body.difficulty or "medium").strip().lower()
    if difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="难度只能是 easy / medium / hard")
    sess = PracticeSession(
        user_id=user.id, scene_id=body.scene_id, difficulty=difficulty
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    db.add(Turn(session_id=sess.id, role="ai", content=scene["opening"]))
    db.commit()
    return CreateSessionOut(session_id=sess.id, opening_question=scene["opening"])


@router.post("/sessions/{session_id}/turn", response_model=TurnOut)
def add_turn(
    session_id: int,
    body: TurnIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if sess.status != "active":
        raise HTTPException(status_code=400, detail="会话已结束")
    if not llm.configured:
        return key_required_response()

    transcript = (body.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="这一轮没有听到内容，请再说一遍或手动输入")
    if not re.search(r"[A-Za-z0-9]", transcript):
        # 纯标点 / 纯表情 / 纯中文都不算英语作答；但 "40" 这种数字短答是合法的（年龄、件数、房间号）
        raise HTTPException(status_code=400, detail="这一轮没有可识别的内容，请用英文或数字回答")
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"单轮回答太长了（上限 {MAX_TRANSCRIPT_CHARS} 字符），可以分两句说",
        )

    scene = get_scene(sess.scene_id)
    audio_json = (
        json.dumps(body.audio.model_dump(), ensure_ascii=False) if body.audio else "{}"
    )
    # 打字还是录音：优先用前端显式传的，否则按有没有音频推断
    input_mode = (body.input_mode or "").strip().lower()
    if input_mode not in ("voice", "typed"):
        input_mode = "voice" if body.audio else "typed"

    # 先把这一轮拼进内存里的 history，模型调用成功后才落库。
    # 否则 502 之后用户那句已经写进 turns，换好 key 重试会在对话里出现两遍。
    history = [{"role": t.role, "content": t.content} for t in sess.turns]
    history.append({"role": "user", "content": transcript})
    user_count = sum(1 for t in history if t["role"] == "user")

    try:
        reply = chat_reply(scene, sess.difficulty, history, user_count, llm)
    except UserKeyInvalid:
        db.rollback()
        return key_invalid_response()

    db.add(
        Turn(
            session_id=sess.id,
            role="user",
            content=transcript,
            input_mode=input_mode,
            audio_json=audio_json,
        )
    )
    db.add(Turn(session_id=sess.id, role="ai", content=reply, input_mode="voice"))
    db.commit()

    return TurnOut(
        turn_index=user_count,
        ai_reply=reply,
        is_follow_up=True,
        should_finish=user_count >= 4,
    )


@router.post("/sessions/{session_id}/finish", response_model=ReportOut)
def finish_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if sess.report:
        return report_out(sess.report)
    # finish 故意不拦「没有 key」：练习已经做完，key 中途被删也该给出一份报告，
    # 走 not_configured 的示例报告（分数留空），而不是把用户卡在报告页外面。
    # 拦只在 create_session / add_turn 两个“进入对话”的入口做。

    scene = get_scene(sess.scene_id)
    user_turns = [t for t in sess.turns if t.role == "user"]
    if not user_turns:
        # 一句没说就出报告，只会拿到一份“没有可展示的句子”的空报告，没有意义
        raise HTTPException(status_code=400, detail="还没有任何回答，先至少聊一轮再生成报告")

    voice_turns = [t for t in user_turns if (t.input_mode or "voice") == "voice"]
    typed_turns = [t for t in user_turns if (t.input_mode or "voice") == "typed"]
    typed_count = len(typed_turns)

    history = [
        {
            "role": t.role,
            "content": t.content,
            "input_mode": t.input_mode or "voice",
        }
        for t in sess.turns
    ]
    user_text = " ".join(t.content for t in user_turns)
    voice_text = " ".join(t.content for t in voice_turns)
    audio_metas = [json.loads(t.audio_json or "{}") for t in voice_turns]

    # 先算可测特征，再打分：规则子分要拿 features 才能和模型分融合。
    # 词汇多样性、句长这类文本特征用全部发言；填充词、语速、停顿只从录音轮算——
    # 打字里写的 like / well 不是口头填充，不能拉低流利度（否则和「打字不计流利度」矛盾）。
    features = fluency_features(user_text)
    if voice_turns:
        voice_features = fluency_features(voice_text)
        features["filler_count"] = voice_features.get("filler_count", 0)
        features["filler_rate"] = voice_features.get("filler_rate", 0.0)
        features.update(
            speech_features([len(tokenize(t.content)) for t in voice_turns], audio_metas)
        )
        features["voice_word_count"] = len(tokenize(voice_text))
    else:
        # 纯打字：填充词/停顿是口头指标，不产出，报告页也就不会显示
        for key in ("filler_count", "filler_rate", "pause_count", "mean_pause_sec"):
            features.pop(key, None)
    features["voice_turns"] = len(voice_turns)
    features["typed_turns"] = typed_count
    try:
        data = generate_report(scene, sess.difficulty, history, llm)
    except UserKeyInvalid:
        return key_invalid_response()
    data = apply_to_report(
        data,
        features,
        sess.scene_id,
        user_text,
        has_voice=bool(voice_turns),
        has_typed=typed_count > 0,
    )
    detail = data.get("scoring_detail") or {}
    scoring_json = json.dumps(
        {
            "dimensions": detail,
            "note": data.get("scoring_note", ""),
            # 作答模式与跨模式可比子分：打字/录音报告的综合分口径不同，
            # 报告页和历史曲线要用 comparable_*，不能拿 total_score 跨模式比。
            "answer_mode": data.get("answer_mode"),
            "comparable_score": data.get("comparable_score"),
            "comparable_band": data.get("comparable_band"),
        },
        ensure_ascii=False,
    )

    rep = Report(
        session_id=sess.id,
        total_score=data.get("total_score"),
        band=data.get("band"),
        cefr=data.get("cefr"),
        source=data.get("source", "llm"),
        mock_reason=data.get("mock_reason"),
        answer_mode=data.get("answer_mode"),
        comparable_band=data.get("comparable_band"),
        dimensions_json=json.dumps(data.get("dimensions", {}), ensure_ascii=False),
        bands_json=json.dumps(data.get("bands", {}), ensure_ascii=False),
        fixes_json=json.dumps(data.get("sentence_fixes", []), ensure_ascii=False),
        features_json=json.dumps(features, ensure_ascii=False),
        scoring_json=scoring_json,
        comment=data.get("comment", ""),
    )
    db.add(rep)
    sess.status = "finished"
    # 这次诊断出的薄弱点落成可复习的学习卡（去重：同类型同目标只留一条）
    upsert_items(db, user.id, sess.id, data.get("learning_items") or [])
    db.commit()
    db.refresh(rep)
    return report_out(rep, db)


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
def get_session_detail(
    session_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """单个会话的完整对话，用于刷新页面或从历史回到练习页时回填。"""
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    scene = get_scene(sess.scene_id)
    return SessionDetailOut(
        id=sess.id,
        scene_id=sess.scene_id,
        scene_name=scene["name"] if scene else sess.scene_id,
        difficulty=sess.difficulty,
        status=sess.status,
        created_at=utc_iso(sess.created_at),
        turns=[
            SessionTurnOut(
                id=t.id,
                role=t.role,
                content=t.content,
                input_mode=t.input_mode or "voice",
                created_at=utc_iso(t.created_at),
            )
            for t in sess.turns
        ],
        report_id=sess.report.id if sess.report else None,
        total_score=sess.report.total_score if sess.report else None,
    )


@router.get("/sessions", response_model=list[HistoryItem])
def list_sessions(
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    rows = (
        db.query(PracticeSession)
        .filter(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.id.desc())
        .all()
    )
    out = []
    for s in rows:
        scene = get_scene(s.scene_id)
        voice_n = sum(
            1 for t in s.turns if t.role == "user" and (t.input_mode or "voice") == "voice"
        )
        typed_n = sum(
            1 for t in s.turns if t.role == "user" and (t.input_mode or "voice") == "typed"
        )
        out.append(
            HistoryItem(
                id=s.id,
                scene_id=s.scene_id,
                scene_name=scene["name"] if scene else s.scene_id,
                status=s.status,
                report_id=s.report.id if s.report else None,
                total_score=s.report.total_score if s.report else None,
                band=s.report.band if s.report else None,
                cefr=s.report.cefr if s.report else None,
                comparable_band=s.report.comparable_band if s.report else None,
                answer_mode=s.report.answer_mode if s.report else None,
                voice_turns=voice_n,
                typed_turns=typed_n,
                created_at=utc_iso(s.created_at),
            )
        )
    return out
