"""人评一致性验证 CLI。

用法（在项目根目录）：
    python -m evaluation.validate --csv evaluation/demo_data.csv \
        --raters human1,human2 --system system \
        --bands human1_band,human2_band

输出：文本报告 + 可选 JSON。
"""
from __future__ import annotations

import argparse
import csv
import json

from . import agreement


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_report(rows, rater_cols, system_col=None, band_cols=None):
    data = []
    for r in rows:
        scores = [_to_float(r.get(c)) for c in rater_cols]
        if any(s is None for s in scores):
            continue
        data.append(scores)

    n = len(data)
    report = {"n": n, "raters": rater_cols}
    if n < 3:
        report["warning"] = "样本少于 3 条，无法可靠计算一致性"
        return report

    report["icc_2_1"] = agreement.icc_2_1(data)
    report["icc_2_1_interpret"] = agreement.interpret_icc(report["icc_2_1"])
    report["icc_2_k"] = agreement.icc_2_k(data)
    report["icc_2_k_interpret"] = agreement.interpret_icc(report["icc_2_k"])

    pairs = {}
    for i in range(len(rater_cols)):
        for j in range(i + 1, len(rater_cols)):
            x = [row[i] for row in data]
            y = [row[j] for row in data]
            pairs[f"{rater_cols[i]}~{rater_cols[j]}"] = {
                "pearson": agreement.pearson(x, y),
                "spearman": agreement.spearman(x, y),
            }
    report["rater_pairs"] = pairs

    if system_col and rows and system_col in rows[0]:
        system = []
        human_mean = []
        for r in rows:
            s = _to_float(r.get(system_col))
            hs = [_to_float(r.get(c)) for c in rater_cols]
            if s is None or any(h is None for h in hs):
                continue
            system.append(s)
            human_mean.append(sum(hs) / len(hs))
        if len(system) >= 3:
            report["system_vs_human_mean"] = {
                "pearson": agreement.pearson(system, human_mean),
                "spearman": agreement.spearman(system, human_mean),
                "mae": agreement.mae(system, human_mean),
                "rmse": agreement.rmse(system, human_mean),
                "bland_altman": agreement.bland_altman(system, human_mean),
            }

    if band_cols:
        band_rows = []
        for r in rows:
            vals = [r.get(c) for c in band_cols]
            if all(v not in (None, "") for v in vals):
                band_rows.append(vals)
        if len(band_rows) >= 2:
            report["fleiss_kappa"] = agreement.fleiss_kappa(band_rows)
            report["fleiss_kappa_interpret"] = agreement.interpret_kappa(report["fleiss_kappa"])
            if len(band_cols) == 2:
                report["cohens_kappa"] = agreement.cohens_kappa(
                    [r[0] for r in band_rows], [r[1] for r in band_rows]
                )
                report["cohens_kappa_interpret"] = agreement.interpret_kappa(report["cohens_kappa"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="人评一致性验证")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--raters", required=True, help="人评分列，逗号分隔，如 human1,human2")
    parser.add_argument("--system", default=None, help="系统分列名，如 system")
    parser.add_argument("--bands", default=None, help="类别列，逗号分隔，如 human1_band,human2_band")
    parser.add_argument("--out", default=None, help="可选：输出 JSON 路径")
    args = parser.parse_args(argv)

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    rater_cols = [c.strip() for c in args.raters.split(",") if c.strip()]
    band_cols = [c.strip() for c in args.bands.split(",")] if args.bands else None

    report = build_report(rows, rater_cols, args.system, band_cols)

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
