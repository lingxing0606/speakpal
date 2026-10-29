"""生成合成示例数据，仅用于演示验证脚本，不是真实证据。

    python -m evaluation.make_demo
"""
from __future__ import annotations

import csv
import os
import random

from .bands import cefr_of_score


def band(score: int) -> str:
    """档位统一用 CEFR 字母（A2/B1/B2/C1），不再用 A/B/C 粗档。

    依据：validate.py 要对 system_band 和人评 band 算 kappa，类别必须同档位、同命名。
    """
    return cefr_of_score(score) or "A2"


def main():
    random.seed(42)
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "demo_data.csv")
    rows = []
    for i in range(1, 21):
        true = random.gauss(70, 12)
        h1 = max(0, min(100, round(true + random.gauss(0, 4))))
        h2 = max(0, min(100, round(true + random.gauss(0, 4))))
        system = max(0, min(100, round(true + random.gauss(0, 7))))
        rows.append(
            {
                "id": f"s{i:03d}",
                "human1": h1,
                "human2": h2,
                "system": system,
                "human1_band": band(h1),
                "human2_band": band(h2),
                "system_band": band(system),
            }
        )
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "human1",
                "human2",
                "system",
                "human1_band",
                "human2_band",
                "system_band",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"已生成 {path}（合成数据，仅演示用）")


if __name__ == "__main__":
    main()
