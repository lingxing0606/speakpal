import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import PracticeSession, Report, Turn, User
from ..schemas import (
    CreateSessionIn,
    CreateSessionOut,
    HistoryItem,
    ReportOut,
    TurnIn,
    TurnOut,
)
from ..security import get_current_user
from ..services.llm import chat_reply
from ..services.scenes import get_scene
from ..services.scoring import generate_report
from evaluation.features import fluency_features, speech_features, tokenize

router = APIRouter(prefix="/api", tags=["sessions"])


def _report_out(rep: Report) -> ReportOut:
    return ReportOut(
        report_id=rep.id,
        total_score=rep.total_score,
        dimensions=json.loads(rep.dimensions_json or "{}"),
        sentence_fixes=json.loads(rep.fixes_json or "[]"),
        comment=rep.comment,
        features=json.loads(rep.features_json or "{}"),
        note="分数由 AI 估算，仅供参考。",
    )


@router.post("/sessions", response_model=CreateSessionOut)
def create_session(
    body: CreateSessionIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    scene = get_scene(body.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    sess = PracticeSession(
        user_id=user.id, scene_id=body.scene_id, difficulty=body.difficulty
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
):
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if sess.status != "active":
        raise HTTPException(status_code=400, detail="会话已结束")

    scene = get_scene(sess.scene_id)
    audio_json = (
        json.dumps(body.audio.model_dump(), ensure_ascii=False) if body.audio else "{}"
    )
    db.add(
        Turn(
            session_id=sess.id,
            role="user",
            content=body.transcript,
            audio_json=audio_json,
        )
    )
    db.commit()
    db.refresh(sess)

    history = [{"role": t.role, "content": t.content} for t in sess.turns]
    user_count = sum(1 for t in history if t["role"] == "user")
    reply = chat_reply(scene, sess.difficulty, history, user_count)

    db.add(Turn(session_id=sess.id, role="ai", content=reply))
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
):
    sess = db.get(PracticeSession, session_id)
    if not sess or sess.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if sess.report:
        return _report_out(sess.report)

    scene = get_scene(sess.scene_id)
    history = [{"role": t.role, "content": t.content} for t in sess.turns]
    data = generate_report(scene, sess.difficulty, history)
    user_text = " ".join(t["content"] for t in history if t["role"] == "user")
    features = fluency_features(user_text)
    user_turns = [t for t in sess.turns if t.role == "user"]
    audio_metas = [json.loads(t.audio_json or "{}") for t in user_turns]
    features.update(
        speech_features([len(tokenize(t.content)) for t in user_turns], audio_metas)
    )

    rep = Report(
        session_id=sess.id,
        total_score=int(data.get("total", 0)),
        dimensions_json=json.dumps(data.get("dimensions", {}), ensure_ascii=False),
        fixes_json=json.dumps(data.get("sentence_fixes", []), ensure_ascii=False),
        features_json=json.dumps(features, ensure_ascii=False),
        comment=data.get("comment", ""),
    )
    db.add(rep)
    sess.status = "finished"
    db.commit()
    db.refresh(rep)
    return _report_out(rep)


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
        out.append(
            HistoryItem(
                id=s.id,
                scene_id=s.scene_id,
                scene_name=scene["name"] if scene else s.scene_id,
                total_score=s.report.total_score if s.report else None,
                created_at=s.created_at.isoformat(),
            )
        )
    return out
