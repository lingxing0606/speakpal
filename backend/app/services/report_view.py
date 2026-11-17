import json

from ..models import Report, StudyItem, Turn
from ..schemas import ReportOut
from evaluation.scales import REASON_NOT_SCORED, scales_for_band
from .scoring import DEFAULT_NOTE, MOCK_NOTE
from .study import item_out


def _score_ratios(detail: dict) -> dict | None:
    """按各维融合权重算模型分 / 规则分占比（百分数，和为 100）。"""
    model_shares = []
    for one in (detail.get("dimensions") or {}).values():
        if not isinstance(one, dict) or one.get("model_score") is None:
            continue
        weight_rule = one.get("weight_rule")
        if isinstance(weight_rule, (int, float)):
            model_shares.append(1.0 - float(weight_rule))
    if not model_shares:
        return None
    model_ratio = round(100 * sum(model_shares) / len(model_shares))
    return {"model_ratio": model_ratio, "rule_ratio": 100 - model_ratio}


def _safety_counts(db, session_id: int) -> dict:
    flagged = replaced = 0
    if db is None:
        return {"flagged_inputs": 0, "replaced_replies": 0}
    rows = (
        db.query(Turn.role, Turn.safety_flag)
        .filter(Turn.session_id == session_id)
        .all()
    )
    for role, flag in rows:
        value = flag or ""
        if role == "user" and ("injection" in value or "risk" in value):
            flagged += 1
        if role == "ai" and "replaced" in value:
            replaced += 1
    return {"flagged_inputs": flagged, "replaced_replies": replaced}


def _transparency(rep: Report, db, coach: dict | None, source: str) -> dict | None:
    """「AI 透明度」：模型、安全标记、分数构成、教练证据覆盖；mock 报告不给。"""
    if source == "mock":
        return None
    try:
        detail = json.loads(rep.scoring_json or "{}")
    except (TypeError, ValueError):
        detail = {}
    if not isinstance(detail, dict):
        detail = {}
    priorities = (coach or {}).get("priorities") or []
    grounded = sum(1 for p in priorities if isinstance(p, dict) and p.get("grounded"))
    return {
        "model": str(detail.get("model") or ""),
        "safety": _safety_counts(db, rep.session_id),
        "scores": _score_ratios(detail),
        "coach": {"grounded": grounded, "total": len(priorities)} if priorities else None,
    }


def report_out(rep: Report, db=None) -> ReportOut:
    """Report ORM → API 结构。降级报告（source=mock）的分数与档位为 None。

    传了 db 就把这次练习自动建的学习卡一并带上（报告页要直接给「加入学习清单 / 去复习」）。
    多量表不落库：有 band 就现算，旧报告读时自动补齐（见 evaluation/scales.py）。
    """
    source = rep.source or "llm"
    bands = json.loads(rep.bands_json or "{}")
    scales = scales_for_band(rep.band, bands)
    # 教练诊断：旧报告 / 示例报告没有这一段，前端整块不渲染
    try:
        coach = json.loads(rep.coach_json or "{}")
    except (TypeError, ValueError):
        coach = {}
    if not isinstance(coach, dict) or not coach:
        coach = None
    if source == "mock":
        # 示例报告没有分数，不能按「低于 A2」解释
        scales["items"] = None
        scales["reason"] = REASON_NOT_SCORED
    study_items = []
    if db is not None:
        rows = (
            db.query(StudyItem)
            .filter(StudyItem.source_session_id == rep.session_id)
            .order_by(StudyItem.id.asc())
            .all()
        )
        study_items = [item_out(row) for row in rows]
    return ReportOut(
        report_id=rep.id,
        total_score=rep.total_score,
        band=rep.band,
        cefr=rep.cefr,
        source=source,
        mock_reason=rep.mock_reason,
        answer_mode=rep.answer_mode,
        comparable_band=rep.comparable_band,
        dimensions=json.loads(rep.dimensions_json or "{}"),
        bands=bands,
        sentence_fixes=json.loads(rep.fixes_json or "[]"),
        study_items=study_items,
        comment=rep.comment or "",
        features=json.loads(rep.features_json or "{}"),
        scoring_detail=json.loads(rep.scoring_json or "{}"),
        plan=json.loads(rep.plan_json or "{}"),
        coach=coach,
        scales=scales,
        transparency=_transparency(rep, db, coach, source),
        note=MOCK_NOTE if source == "mock" else DEFAULT_NOTE,
    )
