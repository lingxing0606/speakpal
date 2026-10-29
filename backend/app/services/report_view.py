import json

from ..models import Report
from ..schemas import ReportOut
from .scoring import DEFAULT_NOTE, MOCK_NOTE


def report_out(rep: Report) -> ReportOut:
    """Report ORM → API 结构。降级报告（source=mock）的分数与档位为 None。"""
    source = rep.source or "llm"
    return ReportOut(
        report_id=rep.id,
        total_score=rep.total_score,
        band=rep.band,
        cefr=rep.cefr,
        source=source,
        dimensions=json.loads(rep.dimensions_json or "{}"),
        bands=json.loads(rep.bands_json or "{}"),
        sentence_fixes=json.loads(rep.fixes_json or "[]"),
        comment=rep.comment or "",
        features=json.loads(rep.features_json or "{}"),
        note=MOCK_NOTE if source == "mock" else DEFAULT_NOTE,
    )
