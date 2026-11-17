import json
import queue
import re
import threading
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
from ..services.agent import coach, critic, plan_session, progress, should_finish
from ..services.llm import (
    SafetyBlocked,
    StreamUnavailable,
    chat_reply,
    fallback_reply,
    open_chat_stream,
    system_prompt,
)
from ..services.safety import check_input, check_reply
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
# 图片场景细节 / 目标词的上限（方案 §4.2）
MAX_CONTEXT_CHARS = 300
MAX_KEY_VOCAB = 8


def _clean_context(value: str | None) -> str:
    """图片场景细节：限长、去尖括号（防闭合 <context> 标签）、命中注入就丢掉。"""
    text = (value or "").replace("<", "").replace(">", "").strip()[:MAX_CONTEXT_CHARS]
    if text and check_input(text)["flag"]:
        print("[safety] 图片场景细节命中注入检测，已丢弃", flush=True)
        return ""
    return text


def _clean_key_vocab(items) -> list[dict]:
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()[:64]
        if not term:
            continue
        out.append({"term": term, "zh": str(item.get("zh") or "").strip()[:40]})
        if len(out) >= MAX_KEY_VOCAB:
            break
    return out


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
    # 拍照生成的场景细节与目标词：只作为数据注入 prompt，不参与目标校验
    context = _clean_context(body.context)
    key_vocab = _clean_key_vocab(body.key_vocab)
    if context:
        plan = {**plan, "context": context}
    if key_vocab:
        plan = {**plan, "key_vocab": key_vocab}
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
    asr_source: str | None
    safety_flag: str
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
    # 转写来源：只有前端明确说 cloud / browser 才记，别的值当没有
    asr_source = (body.asr_source or "").strip().lower()
    if asr_source not in ("cloud", "browser"):
        asr_source = None
    # 注入检测只打标记，不拦截：学习者可能正在练这类句子
    safety_flag = check_input(transcript)["flag"] or ""

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
        asr_source=asr_source,
        safety_flag=safety_flag,
        history=history,
        user_count=user_count,
        plan=plan,
    )


def _save_turn_pair(
    db: OrmSession,
    ctx: _TurnCtx,
    reply: str,
    *,
    replaced: bool = False,
    risk: bool = False,
) -> None:
    user_flag = ",".join(f for f in (ctx.safety_flag, "risk" if risk else "") if f)
    db.add(
        Turn(
            session_id=ctx.session_id,
            role="user",
            content=ctx.transcript,
            input_mode=ctx.input_mode,
            audio_json=ctx.audio_json,
            asr_source=ctx.asr_source,
            safety_flag=user_flag,
        )
    )
    db.add(
        Turn(
            session_id=ctx.session_id,
            role="ai",
            content=reply,
            input_mode="voice",
            safety_flag="replaced" if replaced else "",
        )
    )
    db.commit()


def _turn_out(ctx: _TurnCtx, reply: str, degraded: bool, replaced: bool = False) -> TurnOut:
    return TurnOut(
        turn_index=ctx.user_count,
        ai_reply=reply,
        is_follow_up=True,
        should_finish=should_finish(ctx.plan, ctx.user_count),
        degraded=degraded,
        replaced=replaced,
        flagged=bool(ctx.safety_flag),
        asr_source=ctx.asr_source,
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
    replaced = False
    risk = False
    try:
        reply, degraded = chat_reply(
            ctx.scene, ctx.difficulty, ctx.history, ctx.user_count, llm, ctx.plan
        )
    except SafetyBlocked:
        # 输入被平台拒绝：换成预设追问，这一轮不重试
        reply, degraded = fallback_reply(ctx.scene["id"], ctx.user_count), False
        replaced = risk = True
    except UserKeyInvalid:
        db.rollback()
        return key_invalid_response()
    except UnsafeBaseURL as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.message)
    if not degraded and not replaced:
        ok, reason = check_reply(reply, system_prompt(ctx.scene, ctx.difficulty, ctx.plan))
        if not ok:
            print(f"[safety] 回复被替换：{reason}", flush=True)
            reply, replaced = fallback_reply(ctx.scene["id"], ctx.user_count), True

    _save_turn_pair(db, ctx, reply, replaced=replaced, risk=risk)
    return _turn_out(ctx, reply, degraded, replaced)


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
    risk = False
    try:
        stream = open_chat_stream(ctx.scene, ctx.difficulty, ctx.history, llm, ctx.plan)
    except SafetyBlocked:
        # 输入被平台拒绝：不开流，等会儿用预设追问顶上
        stream = None
        risk = True
    except UserKeyInvalid:
        return key_invalid_response()
    except UnsafeBaseURL as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except StreamUnavailable as exc:
        print(f"[llm] 流式对话降级为预设追问：{exc}", flush=True)
        stream = None

    def events():
        parts: list[str] = []
        broken = stream is None and not risk
        refused = False
        if stream is not None:
            try:
                for piece in stream:
                    parts.append(piece)
                    yield _sse("delta", {"text": piece})
            except Exception as exc:  # noqa: BLE001 - 中途断流降级，不让整轮失败
                print(f"[llm] 流式对话中途断开：{type(exc).__name__}", flush=True)
                broken = True
            finally:
                refused = bool(getattr(stream, "refused", False))
                stream.close()
        reply = "".join(parts).strip()
        replaced = False
        degraded = broken or not reply
        if risk or refused:
            # 平台拒绝生成：已经推出去的半句收不回来，done 里带替换文本让前端覆盖
            print(f"[safety] 回复被替换：{'risk' if risk else 'refusal'}", flush=True)
            reply = fallback_reply(ctx.scene["id"], ctx.user_count)
            replaced = True
            degraded = False
        elif degraded:
            reply = fallback_reply(ctx.scene["id"], ctx.user_count)
        else:
            ok, reason = check_reply(
                reply, system_prompt(ctx.scene, ctx.difficulty, ctx.plan)
            )
            if not ok:
                print(f"[safety] 回复被替换：{reason}", flush=True)
                reply = fallback_reply(ctx.scene["id"], ctx.user_count)
                replaced = True
        # 请求级 db 会话不保证活到流结束，落库用独立会话
        with SessionLocal() as wdb:
            try:
                sess = wdb.get(PracticeSession, ctx.session_id)
                if not sess or sess.status != "active":
                    yield _sse("error", {"detail": "会话已结束，这一轮没有记录"})
                    return
                _save_turn_pair(wdb, ctx, reply, replaced=replaced, risk=risk)
            except Exception as exc:  # noqa: BLE001
                wdb.rollback()
                print(f"[sessions] 流式对话落库失败：{type(exc).__name__}", flush=True)
                yield _sse("error", {"detail": "保存这一轮失败，请重发"})
                return
        yield _sse("done", _turn_out(ctx, reply, degraded, replaced).model_dump())

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _finish_report(session_id: int, user_id: int, llm: LLMConfig, emit=None) -> ReportOut:
    """finish 与 finish/stream 共用：生成（或读取已有）报告。

    `emit(event, data)` 只给 SSE 用：stage 报阶段进度、tool 报教练的工具调用；
    普通 finish 不传，行为与以前一致。
    """

    def stage(name: str) -> None:
        if emit is not None:
            emit("stage", {"name": name})

    with SessionLocal() as db:
        sess = db.get(PracticeSession, session_id)
        if not sess or sess.user_id != user_id:
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
        stage("scoring")
        data = generate_report(scene, sess.difficulty, history, llm)
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
        stage("critic")
        plan = _plan_of(sess)
        if plan.get("goals"):
            if data.get("source") == "llm":
                plan = critic(scene, plan, history, user_text, llm)
            else:
                plan = progress(sess.scene_id, plan, user_text)
        # 诊断教练：只有真模型报告才跑；失败只回退 skipped，不影响报告
        coach_data: dict = {}
        if data.get("source") == "llm":
            stage("coach")
            coach_data = coach(
                scene,
                history,
                data.get("sentence_fixes") or [],
                db,
                user_id,
                llm,
                on_step=(lambda entry: emit("tool", entry)) if emit is not None else None,
            )
        scoring_json = json.dumps(
            {
                # 阶段 4「AI 透明度」要用：这份报告是哪个模型评的
                "model": llm.model,
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

        stage("cards")
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
            coach_json=json.dumps(coach_data, ensure_ascii=False) if coach_data else "{}",
            comment=data.get("comment", ""),
        )
        db.add(rep)
        sess.status = "finished"
        # §16.4：只给 spelling / stiffness 自动建卡（草稿、立即可复习），其余类型由用户手动加入
        create_cards(db, user_id, sess.id, cards_from_fixes(data.get("sentence_fixes") or []))
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


@router.post("/sessions/{session_id}/finish", response_model=ReportOut)
def finish_session(
    session_id: int,
    user: User = Depends(get_current_user),
    llm: LLMConfig = Depends(get_llm_config),
):
    try:
        return _finish_report(session_id, user.id, llm)
    except UserKeyInvalid:
        return key_invalid_response()


@router.post("/sessions/{session_id}/finish/stream")
def finish_session_stream(
    session_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    """和 /finish 相同的报告生成，但把阶段与教练工具调用实时推送。

    事件：stage（scoring / critic / coach / cards）、tool（教练的一次工具调用）、
    done（完整 ReportOut）、error。校验失败仍在开流前返回普通 HTTP 错误，
    前端遇到 404/405 回落普通 /finish。
    """
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not sess.report and not any(t.role == "user" for t in sess.turns):
        raise HTTPException(status_code=400, detail="还没有任何回答，先至少聊一轮再生成报告")
    user_id = user.id

    def events():
        channel: queue.Queue = queue.Queue()

        def emit(event: str, data: dict) -> None:
            channel.put((event, data))

        def work() -> None:
            try:
                out = _finish_report(session_id, user_id, llm, emit)
            except UserKeyInvalid:
                emit("error", dict(KEY_INVALID_BODY))
            except HTTPException as exc:
                emit("error", {"detail": exc.detail})
            except Exception as exc:  # noqa: BLE001 - 出错也要让前端拿到明确事件
                print(f"[sessions] 流式出报告失败：{type(exc).__name__}", flush=True)
                emit("error", {"detail": "生成报告失败，请重试"})
            else:
                # done 统一带 replaced：出报告没有可替换的回复，这里恒为 False
                emit("done", {**out.model_dump(), "replaced": False})

        threading.Thread(target=work, daemon=True).start()
        while True:
            event, payload = channel.get()
            yield _sse(event, payload)
            if event in ("done", "error"):
                return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
                asr_source=t.asr_source,
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
