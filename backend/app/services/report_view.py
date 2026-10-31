import json

from ..models import Report, StudyItem
from ..schemas import ReportOut
from .scoring import DEFAULT_NOTE, MOCK_NOTE
from .study import item_out


def report_out(rep: Report, db=None) -> ReportOut:
    """Report ORM → API 结构。降级报告（source=mock）的分数与档位为 None。

    传了 db 就把这次练习自动建的学习卡一并带上（报告页要直接给「加入学习清单 / 去复习」）。
    """
    source = rep.source or "llm"
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
        bands=json.loads(rep.bands_json or "{}"),
        sentence_fixes=json.loads(rep.fixes_json or "[]"),
        study_items=study_items,
        comment=rep.comment or "",
        features=json.loads(rep.features_json or "{}"),
        scoring_detail=json.loads(rep.scoring_json or "{}"),
        note=MOCK_NOTE if source == "mock" else DEFAULT_NOTE,
    )
