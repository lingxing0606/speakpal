"""多量表展示：把雅思 band 派生成各考试的展示值（纯标准库）。

口径见 docs/rubric-band.md 与《多量表评分与动态提示方案》§2：
- band 是唯一权威锚，0–100 分是它的等价表示，托福/多邻国/四六级只是 band 的「视图」；
- 换算是确定性的，不落库、不新增报告分数列，旧报告读时自动补齐；
- 四六级没有官方 CEFR 换算，只做水平段参考，输出里 `tier=reference`；
- 高考英语不给分数，只给内容难度标签（GAOKAO_LABEL）：无官方换算，且构念不同。
"""
from __future__ import annotations

from .bands import band_to_cefr, round_band

SCALE_VERSION = "2026-11"

# 展示顺序：雅思 → CEFR → 托福 → 多邻国 → 四六级；也是偏好白名单
SCALE_ORDER = ("ielts", "cefr", "toefl", "duolingo", "cet")
SCALE_IDS = SCALE_ORDER
DEFAULT_SCALE = "ielts"

# 报告不给分时的原因：低于 A2 下缘（<40 分）/ 示例报告（模型不可用）
REASON_BELOW_A2 = "below_a2"
REASON_NOT_SCORED = "not_scored"

# 高考只做内容标签，不给分数
GAOKAO_LABEL = "难度 ≈ A2–B1"

# 同一 CEFR 档内的展示值（方案 §2.2 换算表）；区间含两端，`range` 为 None 表示只有上界
_TIERS = {
    "C2": {
        "toefl": {"range": [118, 120], "display": "118–120"},
        "duolingo": {"range": [145, 160], "display": "145–160"},
        "cet4": None,
        "cet6": "650+",
    },
    "C1": {
        "toefl": {"range": [95, 120], "display": "95–120"},
        "duolingo": {"range": [120, 140], "display": "120–140"},
        "cet4": "600+",
        "cet6": "550–649",
    },
    "B2": {
        "toefl": {"range": [72, 94], "display": "72–94"},
        "duolingo": {"range": [90, 115], "display": "90–115"},
        "cet4": "500–599",
        "cet6": "450–549",
    },
    "B1": {
        "toefl": {"range": [42, 71], "display": "42–71"},
        "duolingo": {"range": [60, 85], "display": "60–85"},
        "cet4": "425–499",
        "cet6": "425–449",
    },
    "A2": {
        "toefl": {"range": None, "display": "<42"},
        "duolingo": {"range": [10, 55], "display": "10–55"},
        "cet4": "<425",
        "cet6": "<425",
    },
}


def _cet_display(cet4, cet6):
    return f"CET-4 {cet4 or '—'} · CET-6 {cet6 or '—'}"


def _range_item(tier_value):
    return {
        "range": list(tier_value["range"]) if tier_value["range"] else None,
        "display": tier_value["display"],
        "tier": "official",
    }


def dimension_scales(dimension_bands):
    """维度只派生 IELTS + CEFR。

    托福/多邻国/四六级只有整卷总分或不同构念的子分（阅读/听力/口语/写作、
    literacy/comprehension/…），没有与发音/流利度对应的描述语，硬映射不成立。
    """
    out = {}
    for name, band in (dimension_bands or {}).items():
        rounded = round_band(band) if band is not None else None
        if rounded is None:
            continue
        out[name] = {"ielts": rounded, "cefr": band_to_cefr(rounded)}
    return out


def scales_for_band(band, dimension_bands=None):
    """band → 报告用的多量表视图；band 为空时 items 为 None（不截到 40）。

    - `dimension_bands` 传了就附上逐维 `dimensions`（只含雅思与 CEFR）。
    - `primary` 是默认展示项；用户偏好由 `/api/me/settings` 的 `report_scale` 决定。
    """
    rounded = round_band(band) if band is not None else None
    payload = {"version": SCALE_VERSION, "primary": DEFAULT_SCALE}
    if rounded is None:
        payload["items"] = None
        payload["reason"] = REASON_BELOW_A2
        return payload

    cefr = band_to_cefr(rounded)
    tier = _TIERS[cefr]
    payload["items"] = {
        "ielts": {"value": rounded, "display": f"{rounded:.1f}", "tier": "official"},
        "cefr": {"value": cefr, "display": cefr, "tier": "official"},
        "toefl": _range_item(tier["toefl"]),
        "duolingo": _range_item(tier["duolingo"]),
        "cet": {
            "cet4": tier["cet4"],
            "cet6": tier["cet6"],
            "display": _cet_display(tier["cet4"], tier["cet6"]),
            "tier": "reference",
        },
    }
    if dimension_bands:
        payload["dimensions"] = dimension_scales(dimension_bands)
    return payload
