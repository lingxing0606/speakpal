import json

from ..models import Report, StudyItem
from ..schemas import ReportOut
from evaluation.scales import REASON_NOT_SCORED, scales_for_band
from .scoring import DEFAULT_NOTE, MOCK_NOTE
from .study import item_out


def report_out(rep: Report, db=None) -> ReportOut:
    """Report ORM → API 结构。降级报告（source=mock）的分数与档位为 None。

    传了 db 就把这次练习自动建的学习卡一并带上（报告页要直接给「加入学习清单 / 去复习」）。
    多量表不落库：有 band 就现算，旧报告读时自动补齐（见 evaluation/scales.py）。
    """
    source = rep.source or "llm"
    bands = json.loads(rep.bands_json or "{}")
    scales = scales_for_band(rep.band, bands)
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
        scales=scales,
        note=MOCK_NOTE if source == "mock" else DEFAULT_NOTE,
    )
