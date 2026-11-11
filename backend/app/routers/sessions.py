import json
import re
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import selectinload

from ..db import SessionLocal, get_db
from ..models import PracticeSession, Report, Turn, User
from ..schemas import (
    CreateSessionIn,
    CreateSessionOut,
    HistoryItem,
    ReportOut,
    SessionDetailOut,
    SessionPlan,
    SessionTurnOut,
    TurnIn,
    TurnOut,
)
from ..security import get_current_user
from ..timeutil import utc_iso
from ..services.agent import critic, plan_session, progress, should_finish
from ..services.llm import StreamUnavailable, chat_reply, fallback_reply, open_chat_stream
from ..services.study import cards_from_fixes, create_cards
from ..services.llm_config import LLMConfig, UserKeyInvalid, get_llm_config
from ..services.outbound import UnsafeBaseURL
from ..services.report_view import report_out
from ..services.rules import apply_to_report
from ..services.scenes import get_scene
from ..services.scoring import generate_report
from ..services.tools import call as call_tool
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
    # 不传难度就用设置里的偏好（难度从首页搬进设置后，练习页不再单独选）
    difficulty = (body.difficulty or "").strip().lower() or (
        user.practice_difficulty or "medium"
    ).strip().lower()
    if difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="难度只能是 easy / medium / hard")
    sess = PracticeSession(
        user_id=user.id, scene_id=body.scene_id, difficulty=difficulty
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    # Planner：进对话前先定 3 个目标。模型不可用时退回场景清单，绝不让建会话失败。
    weakness = call_tool("recent_weakness", db=db, user_id=user.id) or []
    plan = plan_session(scene, difficulty, weakness, llm)
    sess.plan_json = json.dumps(plan, ensure_ascii=False)
    db.add(Turn(session_id=sess.id, role="ai", content=scene["opening"]))
    db.commit()
    return CreateSessionOut(
        session_id=sess.id,
        opening_question=scene["opening"],
        plan=SessionPlan(**plan),
    )


@dataclass
class _TurnCtx:
    """一轮作答校验通过后要用到的纯数据（不带 ORM 对象，流式生成器里也能安全用）。"""

    session_id: int
    scene: dict
    difficulty: str
    transcript: str
    input_mode: str
    audio_json: str
    history: list
    user_count: int
    plan: dict


def _plan_of(sess: PracticeSession) -> dict:
    """会话的 plan_json → dict；老会话没有这一列时按空 plan 处理。"""
    try:
        data = json.loads(sess.plan_json or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _prepare_turn(
    session_id: int, body: TurnIn, user: User, db: OrmSession, llm: LLMConfig
) -> "_TurnCtx | JSONResponse":
    """/turn 与 /turn/stream 共用的校验，顺序与报错保持一致。"""
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
    # 目标进度在每轮提交时现算：纯规则，不额外调模型
    plan = _plan_of(sess)
    if plan.get("goals"):
        user_text = " ".join(t["content"] for t in history if t["role"] == "user")
        plan = progress(sess.scene_id, plan, user_text)
    return _TurnCtx(
        session_id=sess.id,
        scene=scene,
        difficulty=sess.difficulty,
        transcript=transcript,
        input_mode=input_mode,
        audio_json=audio_json,
        history=history,
        user_count=user_count,
        plan=plan,
    )


def _save_turn_pair(db: OrmSession, ctx: _TurnCtx, reply: str) -> None:
    db.add(
        Turn(
            session_id=ctx.session_id,
            role="user",
            content=ctx.transcript,
            input_mode=ctx.input_mode,
            audio_json=ctx.audio_json,
        )
    )
    db.add(Turn(session_id=ctx.session_id, role="ai", content=reply, input_mode="voice"))
    db.commit()


def _turn_out(ctx: _TurnCtx, reply: str, degraded: bool) -> TurnOut:
    return TurnOut(
        turn_index=ctx.user_count,
        ai_reply=reply,
        is_follow_up=True,
        should_finish=should_finish(ctx.plan, ctx.user_count),
        degraded=degraded,
        plan=SessionPlan(**ctx.plan),
    )


@router.post("/sessions/{session_id}/turn", response_model=TurnOut)
def add_turn(
    session_id: int,
    body: TurnIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    ctx = _prepare_turn(session_id, body, user, db, llm)
    if isinstance(ctx, JSONResponse):
        return ctx
    try:
        reply, degraded = chat_reply(
            ctx.scene, ctx.difficulty, ctx.history, ctx.user_count, llm, ctx.plan
        )
    except UserKeyInvalid:
        db.rollback()
        return key_invalid_response()
    except UnsafeBaseURL as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.message)

    _save_turn_pair(db, ctx, reply)
    return _turn_out(ctx, reply, degraded)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/sessions/{session_id}/turn/stream")
def add_turn_stream(
    session_id: int,
    body: TurnIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    """同 /turn，但 AI 回复按 SSE 逐段推送：`delta` 若干条，最后一条 `done`（即 TurnOut）。

    - 校验失败、密钥被拒、地址不安全：和 /turn 一样直接返回 4xx/5xx，不开流。
    - 上游流中途断了：丢掉已收到的半句，`done` 里换成预设追问并标 degraded，
      前端用 `done.ai_reply` 覆盖气泡。
    - 整句收完才落库；客户端中途断开则这一轮不记录（和 /turn 失败不落库一致）。
    - `event: error` 只在落库失败时出现，这一轮同样没有记录。
    """
    ctx = _prepare_turn(session_id, body, user, db, llm)
    if isinstance(ctx, JSONResponse):
        return ctx
    try:
        stream = open_chat_stream(ctx.scene, ctx.difficulty, ctx.history, llm, ctx.plan)
    except UserKeyInvalid:
        return key_invalid_response()
    except UnsafeBaseURL as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except StreamUnavailable as exc:
        print(f"[llm] 流式对话降级为预设追问：{exc}", flush=True)
        stream = None

    def events():
        parts: list[str] = []
        broken = stream is None
        if stream is not None:
            try:
                for piece in stream:
                    parts.append(piece)
                    yield _sse("delta", {"text": piece})
            except Exception as exc:  # noqa: BLE001 - 中途断流降级，不让整轮失败
                print(f"[llm] 流式对话中途断开：{type(exc).__name__}", flush=True)
                broken = True
            finally:
                stream.close()
        reply = "".join(parts).strip()
        degraded = broken or not reply
        if degraded:
            reply = fallback_reply(ctx.scene["id"], ctx.user_count)
        # 请求级 db 会话不保证活到流结束，落库用独立会话
        with SessionLocal() as wdb:
            try:
                sess = wdb.get(PracticeSession, ctx.session_id)
                if not sess or sess.status != "active":
                    yield _sse("error", {"detail": "会话已结束，这一轮没有记录"})
                    return
                _save_turn_pair(wdb, ctx, reply)
            except Exception as exc:  # noqa: BLE001
                wdb.rollback()
                print(f"[sessions] 流式对话落库失败：{type(exc).__name__}", flush=True)
                yield _sse("error", {"detail": "保存这一轮失败，请重发"})
                return
        yield _sse("done", _turn_out(ctx, reply, degraded).model_dump())

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
        # 带上 db：重复打开时也要返回这次自动建的学习卡，和第一次一致
        return report_out(sess.report, db)
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
    # Critic：出报告前复盘目标达成度。示例报告不计分，也就只按关键词规则算，不调模型。
    plan = _plan_of(sess)
    if plan.get("goals"):
        if data.get("source") == "llm":
            plan = critic(scene, plan, history, user_text, llm)
        else:
            plan = progress(sess.scene_id, plan, user_text)
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
        plan_json=json.dumps(plan, ensure_ascii=False),
        comment=data.get("comment", ""),
    )
    db.add(rep)
    sess.status = "finished"
    # §16.4：只给 spelling / stiffness 自动建卡（草稿、立即可复习），其余类型由用户手动加入
    create_cards(db, user.id, sess.id, cards_from_fixes(data.get("sentence_fixes") or []))
    try:
        db.commit()
    except IntegrityError:
        # 两个 finish 并发：另一个请求已经写了报告（session_id 唯一），返回那一份
        db.rollback()
        existing = db.query(Report).filter(Report.session_id == sess.id).first()
        if not existing:
            raise
        return report_out(existing, db)
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
    plan = _plan_of(sess)
    if plan.get("goals"):
        plan = progress(
            sess.scene_id,
            plan,
            " ".join(t.content for t in sess.turns if t.role == "user"),
        )
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
        plan=SessionPlan(**plan),
    )


@router.get("/sessions", response_model=list[HistoryItem])
def list_sessions(
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """不传 limit 返回全部（兼容现有前端）；传了就分页。"""
    query = (
        db.query(PracticeSession)
        .options(selectinload(PracticeSession.turns), selectinload(PracticeSession.report))
        .filter(PracticeSession.user_id == user.id)
        .order_by(PracticeSession.id.desc())
        .offset(offset)
    )
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
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
