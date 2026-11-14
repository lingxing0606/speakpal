"""多量表换算与取整规则的纯函数回归（不启动应用、不碰数据库）。

运行（在 backend 目录）：
    .venv/Scripts/python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND.parent))  # evaluation 包在仓库根目录

from evaluation import bands, scales  # noqa: E402
from app.services import rules  # noqa: E402


class RoundingTests(unittest.TestCase):
    """0–100 取整半值向上（floor(x+0.5)），与 docs/rubric-band.md §4.2 同一规则。"""

    def test_unweighted_fallback_rounds_half_up(self):
        # 只剩共享维度 → 等权平均；62 与 63 平均 62.5，旧的 int(round()) 会给 62
        self.assertEqual(bands.weighted_total({"grammar_vocab": 62, "task_completion": 63}), 63)
        self.assertEqual(bands.weighted_total({"grammar_vocab": 67, "task_completion": 68}), 68)

    def test_comparable_score_rounds_half_up(self):
        self.assertEqual(bands.comparable_score({"grammar_vocab": 62, "task_completion": 63}), 63)
        self.assertEqual(bands.comparable_score({"grammar_vocab": 67, "task_completion": 68}), 68)

    def test_weighted_total_half_up_with_mode_weights(self):
        # 纯录音权重 20/20/30/30：加权正好 62.5
        scores = {"pronunciation": 62, "fluency": 63, "grammar_vocab": 62, "task_completion": 63}
        self.assertEqual(bands.weighted_total(scores, "voice"), 63)

    def test_score_to_band_keeps_half_step_up(self):
        self.assertEqual(bands.score_to_band(62.5), 5.5)
        self.assertEqual(bands.score_to_band(67.5), 6.0)
        self.assertEqual(bands.score_to_band(63), 5.5)
        self.assertEqual(bands.score_to_band(40), 3.0)
        self.assertIsNone(bands.score_to_band(39))

    def test_dimension_scores_stay_integers(self):
        out = bands.report_bands({"grammar_vocab": 6.5, "task_completion": 6.0})
        self.assertEqual(out["dimensions"], {"grammar_vocab": 75, "task_completion": 70})
        self.assertTrue(all(isinstance(v, int) for v in out["dimensions"].values()))

    def test_apply_to_report_dimensions_round_half_up(self):
        # model band 5.25 / 5.75 → 62.5 / 67.5；旧的 int(round()) 会把 62.5 舍成 62
        data = {"source": "llm", "bands": {"pronunciation": 5.25, "written_expression": 5.75}}
        out = rules.apply_to_report(
            data, {}, "job_interview", "", has_voice=True, has_typed=True
        )
        self.assertEqual(
            out["dimensions"], {"pronunciation": 63, "written_expression": 68}
        )


class ScaleTableTests(unittest.TestCase):
    """方案 §2.2 换算表：每个档的雅思/CEFR/托福/多邻国/四六级展示值。"""

    def items(self, score):
        return scales.scales_for_band(bands.score_to_band(score))["items"]

    def test_every_tier_boundary(self):
        cases = [
            (100, 9.0, "C2", "118–120", "145–160", None, "650+"),
            (95, 8.5, "C2", "118–120", "145–160", None, "650+"),
            (90, 8.0, "C1", "95–120", "120–140", "600+", "550–649"),
            (75, 6.5, "B2", "72–94", "90–115", "500–599", "450–549"),
            (65, 5.5, "B2", "72–94", "90–115", "500–599", "450–549"),
            (60, 5.0, "B1", "42–71", "60–85", "425–499", "425–449"),
            (40, 3.0, "A2", "<42", "10–55", "<425", "<425"),
        ]
        for score, ielts, cefr, toefl, duolingo, cet4, cet6 in cases:
            with self.subTest(score=score):
                items = self.items(score)
                self.assertEqual(items["ielts"]["value"], ielts)
                self.assertEqual(items["ielts"]["display"], f"{ielts:.1f}")
                self.assertEqual(items["ielts"]["tier"], "official")
                self.assertEqual(items["cefr"]["value"], cefr)
                self.assertEqual(items["toefl"]["display"], toefl)
                self.assertEqual(items["duolingo"]["display"], duolingo)
                self.assertEqual(items["cet"]["cet4"], cet4)
                self.assertEqual(items["cet"]["cet6"], cet6)
                self.assertEqual(items["cet"]["tier"], "reference")

    def test_transition_band_picks_nearest_half_step(self):
        # 62.5 → band 5.5；67.5 → band 6.0（过渡带不是 bug）
        self.assertEqual(self.items(62.5)["ielts"]["value"], 5.5)
        self.assertEqual(self.items(67.5)["ielts"]["value"], 6.0)

    def test_ranges_expose_numbers_only_when_both_bounds_known(self):
        self.assertEqual(self.items(75)["toefl"]["range"], [72, 94])
        self.assertEqual(self.items(75)["duolingo"]["range"], [90, 115])
        self.assertIsNone(self.items(40)["toefl"]["range"])  # A2 只有「<42」
        self.assertEqual(self.items(40)["duolingo"]["range"], [10, 55])

    def test_below_a2_has_no_items_and_is_not_clamped(self):
        payload = scales.scales_for_band(None)
        self.assertIsNone(payload["items"])
        self.assertEqual(payload["reason"], "below_a2")
        self.assertEqual(payload["version"], scales.SCALE_VERSION)
        # 39 分不给 band，也不截到 40
        self.assertIsNone(scales.scales_for_band(bands.score_to_band(39))["items"])

    def test_dimensions_only_expose_ielts_and_cefr(self):
        payload = scales.scales_for_band(6.5, {"grammar_vocab": 6.0, "fluency": None})
        self.assertEqual(payload["dimensions"], {"grammar_vocab": {"ielts": 6.0, "cefr": "B2"}})

    def test_gaokao_is_a_label_without_score(self):
        self.assertEqual(scales.GAOKAO_LABEL, "难度 ≈ A2–B1")
        self.assertNotIn("gaokao", scales.SCALE_ORDER)
        self.assertNotIn("gaokao", scales.scales_for_band(6.5)["items"])

    def test_scale_order_and_default(self):
        self.assertEqual(scales.SCALE_ORDER, ("ielts", "cefr", "toefl", "duolingo", "cet"))
        self.assertEqual(scales.SCALE_IDS, scales.SCALE_ORDER)
        self.assertEqual(scales.DEFAULT_SCALE, "ielts")
        for band in (3.0, 4.5, 6.5, 8.0, 9.0):
            payload = scales.scales_for_band(band)
            self.assertEqual(list(payload["items"]), list(scales.SCALE_ORDER))
            self.assertEqual(payload["primary"], "ielts")

    def test_cefr_thresholds_are_left_closed(self):
        cases = {
            9.0: "C2",
            8.5: "C2",
            8.0: "C1",
            7.0: "C1",
            6.5: "B2",
            5.5: "B2",
            5.0: "B1",
            4.0: "B1",
            3.5: "A2",
            3.0: "A2",
        }
        for band, label in cases.items():
            with self.subTest(band=band):
                self.assertEqual(bands.band_to_cefr(band), label)


if __name__ == "__main__":
    unittest.main()
