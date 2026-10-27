"""人评一致性统计（纯标准库实现，可复现）。

提供：
- Pearson / Spearman 相关
- MAE / RMSE
- Bland-Altman（均值差、一致性界限）
- Cohen's kappa（两名评分者 + 类别）
- Fleiss' kappa（多名评分者 + 类别）
- ICC(2,1) / ICC(2,k)（连续分数，两名及以上评分者）

公式参考：
- Shrout & Fleiss (1979) ICC 公式
- Landis & Koch (1977) kappa 解释区间
- Koo & Li (2016) ICC 解释区间
"""
from __future__ import annotations

import math


def _mean(xs):
    return sum(xs) / len(xs)


def pearson(x, y):
    n = len(x)
    if n < 2:
        return float("nan")
    mx, my = _mean(x), _mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def _ranks(xs):
    """平均秩（处理并列）。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x, y):
    return pearson(_ranks(x), _ranks(y))


def mae(system, human):
    return sum(abs(a - b) for a, b in zip(system, human)) / len(system)


def rmse(system, human):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(system, human)) / len(system))


def bland_altman(a, b):
    """a、b 为配对分数。返回均值差、标准差、95% 一致性界限。"""
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    md = _mean(diffs)
    sd = math.sqrt(sum((d - md) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
    lo, hi = md - 1.96 * sd, md + 1.96 * sd
    within = sum(1 for d in diffs if lo <= d <= hi)
    return {
        "n": n,
        "mean_diff": md,
        "sd_diff": sd,
        "loa_lower": lo,
        "loa_upper": hi,
        "within_loa": within,
        "within_loa_ratio": within / n if n else 0.0,
    }


def cohens_kappa(r1, r2):
    if len(r1) != len(r2):
        raise ValueError("两名评分者样本数不一致")
    n = len(r1)
    if n == 0:
        return float("nan")
    cats = sorted(set(r1) | set(r2))
    po = sum(1 for a, b in zip(r1, r2) if a == b) / n
    p1 = {c: sum(1 for a in r1 if a == c) / n for c in cats}
    p2 = {c: sum(1 for b in r2 if b == c) / n for c in cats}
    pe = sum(p1[c] * p2[c] for c in cats)
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def fleiss_kappa(ratings):
    """ratings: 行=样本，列=评分者，值为类别。"""
    n = len(ratings)
    k = len(ratings[0])
    if n == 0 or k < 2:
        return float("nan")
    cats = sorted({c for row in ratings for c in row})
    counts = [[sum(1 for c in row if c == cat) for cat in cats] for row in ratings]
    p_j = [sum(counts[i][j] for i in range(n)) / (n * k) for j in range(len(cats))]
    P_i = []
    for i in range(n):
        s = sum(c * c for c in counts[i])
        P_i.append((s - k) / (k * (k - 1)))
    P_bar = _mean(P_i)
    P_e = sum(p * p for p in p_j)
    if P_e >= 1.0:
        return 1.0
    return (P_bar - P_e) / (1.0 - P_e)


def icc_2_1(matrix):
    return _icc(matrix, average=False)


def icc_2_k(matrix):
    return _icc(matrix, average=True)


def _icc(matrix, average):
    """matrix: 行=样本，列=评分者。"""
    n = len(matrix)
    k = len(matrix[0])
    if n < 2 or k < 2:
        return float("nan")
    grand = _mean([v for row in matrix for v in row])
    row_means = [_mean(row) for row in matrix]
    col_means = [_mean([matrix[i][j] for i in range(n)]) for j in range(k)]

    ss_total = sum((matrix[i][j] - grand) ** 2 for i in range(n) for j in range(k))
    ss_rows = k * sum((r - grand) ** 2 for r in row_means)
    ss_cols = n * sum((c - grand) ** 2 for c in col_means)
    ss_err = ss_total - ss_rows - ss_cols

    df_rows, df_cols, df_err = n - 1, k - 1, (n - 1) * (k - 1)
    ms_rows = ss_rows / df_rows
    ms_cols = ss_cols / df_cols
    ms_err = ss_err / df_err if df_err > 0 else 0.0

    if average:
        denom = ms_rows + (ms_cols - ms_err) / n
    else:
        denom = ms_rows + (k - 1) * ms_err + k * (ms_cols - ms_err) / n
    if denom == 0:
        return float("nan")
    return (ms_rows - ms_err) / denom


def interpret_icc(value):
    if value != value:  # nan
        return "无法计算"
    if value < 0.5:
        return "差（<0.5）"
    if value < 0.75:
        return "中等（0.5–0.75）"
    if value < 0.9:
        return "良好（0.75–0.9）"
    return "优秀（>0.9）"


def interpret_kappa(value):
    if value != value:
        return "无法计算"
    if value < 0:
        return "差（<0）"
    if value < 0.21:
        return "轻微（0–0.2）"
    if value < 0.41:
        return "一般（0.21–0.4）"
    if value < 0.61:
        return "中等（0.41–0.6）"
    if value < 0.81:
        return "较强（0.61–0.8）"
    return "几乎一致（0.81–1）"
