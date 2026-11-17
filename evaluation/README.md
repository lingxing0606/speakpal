# evaluation · 评估与验证

纯标准库实现，不额外装包。

| 文件 | 作用 |
|---|---|
| `agreement.py` | Pearson / Spearman、MAE / RMSE、Bland-Altman、Cohen / Fleiss kappa、ICC(2,1) / ICC(2,k) |
| `features.py` | 从转写（可选词级时间戳）提取流利度与词汇多样性特征 |
| `validate.py` | 人评一致性验证 CLI |
| `rag_eval.py` | RAG（BM25）检索离线评测：Recall@1/3、MRR vs 随机基线 |
| `rag_cases.json` | 40 条人工错句与期望卡片 id |
| `rag_report.json` | `rag_eval.py` 的实测结果 |
| `make_demo.py` | 生成合成演示数据（不是真实证据） |
| `demo_data.csv` | 合成示例 |

## 快速用法

```powershell
python -m evaluation.make_demo
python -m evaluation.validate --csv evaluation/demo_data.csv --raters human1,human2 --system system --bands human1_band,human2_band
```

详见 `docs/validation.md`。
