# 评估与验证

校赛作品大多停在“能聊、能给分”。这一层回答一个更难的问题：**这个分准不准、可不可信。**

## 要证明什么

1. **人评内部一致**：两位老师对同一批回答的打分是否一致（信度）。
2. **系统分与人评分一致**：系统给的分数和人评是否对得上（效度）。

## 数据怎么采

- 2–3 名英语教师，**独立**打分，互不可见。
- 对系统分数**盲评**（不告诉老师系统给了多少）。
- 使用同一份 rubric（对齐 CEFR / IELTS 描述语）。
- 每个样本至少两人评；建议样本 ≥ 20 条（演示数据正好 20 条）。
- 保留原始录音与转写，保证可复现。

## CSV 格式

```csv
id,human1,human2,system,human1_band,human2_band,system_band
s001,72,75,70,B1,B1,B1
s002,85,83,88,C1,C1,B2
```

- `human1/human2`：教师连续分（0–100）
- `system`：系统分
- `*_band`：类别档位，统一用 **CEFR 字母**（A2/B1/B2/C1）。不要混用 A/B/C 粗档，
  否则系统档位和人评档位不在同一套类别里，kappa 没有意义。
- 系统档位由 `evaluation.bands.score_to_band()` 从系统分取整得到（0.5 步长，见 `docs/rubric-band.md` §4.2）。

## 运行

```powershell
# 生成合成演示数据（仅演示脚本，不是真实证据）
D:\python\python.exe -m evaluation.make_demo

# 跑一致性验证（含系统档位 vs 人评档位）
D:\python\python.exe -m evaluation.validate --csv evaluation/demo_data.csv `
  --raters human1,human2 --system system `
  --bands human1_band,human2_band --system-band system_band `
  --out evaluation/demo_report.json
```

Windows 控制台默认代码页不是 UTF-8 时中文会乱码（脚本输出流已强制切 UTF-8，`--out` 写的文件也是 UTF-8）；
若终端里仍看到乱码，用 `python -X utf8 -m evaluation.validate ...` 或先执行 `chcp 65001`。

## 指标怎么看

| 指标 | 含义 | 参考区间 |
|---|---|---|
| ICC(2,1) | 单人评分的信度 | <0.5 差；0.5–0.75 中等；0.75–0.9 良好；>0.9 优秀 |
| ICC(2,k) | 多人平均后的信度 | 通常高于 ICC(2,1) |
| Pearson / Spearman | 系统与人评的相关 | 越高越好；排名一致性看 Spearman |
| MAE / RMSE | 绝对误差 | 越小越好 |
| Bland-Altman | 系统性偏差与一致性界限 | 均值差接近 0、落在界限内比例高 |
| Cohen / Fleiss kappa | 类别一致性（CEFR 档） | <0.2 轻微；0.21–0.4 一般；0.41–0.6 中等；0.61–0.8 较强；>0.8 几乎一致 |
| `system_band_agreement.exact_rate` | 系统档位与人评多数票完全一致的比例 | 越高越好（本作品验收线 ≥0.6，【自定】） |
| `system_band_agreement.adjacent_rate` | 相差 ≤1 档的比例 | 口语评测常用「相邻档可接受」，验收线 ≥0.9（【自定】） |
| `system_band_agreement.kappa_vs_human_majority` | 系统档位与人评多数票的 Cohen kappa | ≥0.61（较强，Landis & Koch 1977） |

阈值来自 Shrout & Fleiss (1979)、Landis & Koch (1977)、Koo & Li (2016) 的常见解释区间。

## 诚实声明

`evaluation/demo_data.csv` 是 `make_demo.py` 用固定随机种子生成的**合成数据**，只用来验证脚本能跑通，**不构成任何真实结论**。真实证据必须来自真人评分（见上）。

## 与题目的关系

新题目是“可验证的 AI 英语口语诊断陪练”。这一层就是“可验证”三个字的落点：

- 系统分不是自说自话，而是与**人评金标准**对齐；
- 一致性指标可复现、可写进报告、可在答辩时被追问；
- 合成数据只是工程自测，真实结论靠真人评分。
