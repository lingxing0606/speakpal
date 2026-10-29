# SpeakPal 评分量表与 band 换算（v1 草案）

> 目的：把「评分」从 LLM 黑箱输出，改成**可测特征 → 规则子分 → 与模型分融合 → 落到 CEFR / 雅思 band** 的一条链，
> 并给 `evaluation/validate.py` 提供 `system_band` 的取整契约。
>
> 本文档只定标准，不改代码。实现映射见 §7。

## 0. 证据等级图例

| 标记 | 含义 |
|---|---|
| 【官方】 | 取自 CEFR 描述语或雅思官方 Speaking band descriptors。**本文为转述**，正式引用请核对官方原 PDF。 |
| 【文献】 | 来自口语评测 / 二语流利度研究中的常见区间，非本标准原创。 |
| 【自定】 | **本作品自定锚点**，没有外部出处。初版取值，必须用 §6 的验证协议校准；答辩时应主动说明。 |

**关于转述的诚实声明**：写作时无法在线核对官方原文（ielts.org 与 coe.int 的 PDF 对抓取返回 403），
因此本文所有描述语均为**意思相符的转述**，不是逐字引用。不要把它当官方原文引用。

可核对的入口：
- IELTS 与 CEFR 对照：<https://ielts.org/organisations/ielts-for-organisations/compare-ielts/ielts-and-the-cefr>
- CEFR（含 2020 Companion Volume 新量表）：<https://www.coe.int/en/web/common-european-framework-reference-languages>
- IELTS Speaking band descriptors（public version）— 官方 PDF，**未核对原文**。

---

## 1. 量表骨架：0–100 ↔ 雅思 band ↔ CEFR

### 1.1 单一线性锚

每个维度先按雅思 0–9 的 band 评，再换成 0–100 展示分。**只做一次线性换算**，不允许在别处再自创映射：

```
S = 10 × B + 10          # B: 雅思 band（0–9，0.5 步长）
B = (S − 10) / 10
```

性质：B=4.0 → 50 分，B=6.5 → 75 分，B=8.0 → 90 分。单调、可逆、只有一个锚。

> 为什么不用「0–100 均分五档」：那样 0–100 和 band 是两套锚，答辩时会被问「75 分和 6.5 分是同一个东西吗」。
> 单一线性锚的好处是**永远只有一个数是权威的**，另一个是它的等价表示。

### 1.2 CEFR 分段（由官方 band 对照推得）

官方对照（【官方】，ielts.org 对照表）：C2 = 8.5–9.0，C1 = 7.0–8.0，B2 = 5.5–6.5，B1 = 4.0–5.0。
IELTS 官方不认证 4.0 以下的等级，所以 A2 那一行是【自定】推断。

| CEFR | 雅思 band【官方】 | 0–100 分段 | 说明 |
|---|---|---|---|
| C2 | 8.5–9.0 | 95–100 | 本作品不主动评到 C2，仅作上限 |
| C1 | 7.0–8.0 | 80–90 | |
| B2 | 5.5–6.5 | 65–75 | |
| B1 | 4.0–5.0 | 50–60 | 校赛作品的主力区间 |
| A2 | 3.0–4.0【自定】 | 40–50 | 4.0 以下雅思不认证，区间为推断 |
| A1 / 未达标 | — | < 40 | 报告显示「低于 A2」，不给 band |

**过渡带**（61–64、76–79、91–94）不是 bug：雅思 band 是 0.5 台阶，两个档位之间本来就有空隙。
落在过渡带的原始分，按 §4 的取整规则落到最近的 0.5 档，**不允许出现 5.25 这种不存在的 band**。

区间上界不含：50.0 分对应 B=4.0，按 §4.2 归 **B1**，不归 A2；40.0 分是 A2 下缘，39 分起不给 band。

---

## 2. 四个维度 × 四个等级的锚点

维度命名对齐代码：`pronunciation / fluency / grammar_vocab / task_completion`。
注意 `grammar_vocab` 承担「语言复杂度」，`task_completion` 承担「任务完成度 + 语用得体性」。

### 2.1 pronunciation（发音）

| CEFR / band | 0–100 | 描述语锚点（转述） | 出处 |
|---|---|---|---|
| B1 / 4.0–5.0 | 50–60 | 一般能被听懂，但明显口音；偶有单词发音错误让听者需要反应一下 | CEFR 2001 phonological control A2/B1【官方】 |
| B2 / 5.5–6.5 | 65–75 | 用到的发音特征有一定控制但不稳定；个别词或音的错误会降低清晰度 | IELTS Pronunciation band 6【官方】 |
| C1 / 7.0–8.0 | 80–90 | 发音特征使用范围较宽且较稳定，偶有失误；整体容易听懂，母语口音影响很小 | IELTS Pronunciation band 7–8【官方】 |
| A2 / 3.0–4.0 | 40–50 | 基本能被听懂，但口音明显，对话者会不时要求重复 | CEFR 2001 A2【官方】 |

**重要限制**：本作品**没有声学/音素级分析**，这一维不能从音频直接算出。
报告里必须写「本维度为文本推断 + 转写置信度代理，非声学测评」，不允许宣称发音准确度。
可用的真信号（见 §3.5）：转写置信度、同句重读的自一致性。

### 2.2 fluency（流利度）

| CEFR / band | 0–100 | 描述语锚点（转述） | 出处 |
|---|---|---|---|
| B1 / 4.0–5.0 | 50–60 | 通常能维持语流，但靠重复、自我纠正、放慢来维持；复杂表达时流利度明显下降 | IELTS FC band 5【官方】 |
| B2 / 5.5–6.5 | 65–75 | 愿意长段输出，但偶有重复/犹豫/自我纠正导致连贯性中断；连接词用得不够总得当 | IELTS FC band 6【官方】 |
| C1 / 7.0–8.0 | 80–90 | 能较长篇幅表达而不费力，几乎没有明显连贯性丢失；犹豫多为内容性而非语言性 | IELTS FC band 7【官方】 |
| A2 / 3.0–4.0 | 40–50 | 不靠明显停顿就难以持续表达；语速慢，重复和自我纠正频繁 | IELTS FC band 4【官方】 |

### 2.3 grammar_vocab（语法 + 词汇，= 语言复杂度）

| CEFR / band | 0–100 | 描述语锚点（转述） | 出处 |
|---|---|---|---|
| B1 / 4.0–5.0 | 50–60 | 基本句能较准确产出；复杂结构范围有限且常带错误；能谈熟悉话题，词汇灵活性有限 | IELTS GRA+LR band 5【官方】 |
| B2 / 5.5–6.5 | 65–75 | 简单句与复杂句混用但灵活性有限；复杂结构常出错但极少影响理解；词汇量够长段讨论 | IELTS GRA+LR band 6【官方】 |
| C1 / 7.0–8.0 | 80–90 | 复杂结构有一定灵活性，无错句出现频率高；能灵活使用词汇，偶有搭配/文体不当 | IELTS GRA+LR band 7【官方】 |
| A2 / 3.0–4.0 | 40–50 | 以基本句为主，复杂句很少且错误多；词汇限于具体、高频的日常表达 | CEFR A2 + IELTS band 4 转述【官方】 |

**拆开看**：这一维实际是两件事——
- **范围（range）**：MTLD / 句长 / 复杂结构数 → 可由规则算，见 §3.3；
- **准确度（accuracy）**：错误率 → 只能从逐句纠错里数，或由 LLM 判。
最终分 = 范围规则分与准确度分的融合，报告里两者都要写出来，否则「语法词汇 75」还是黑箱。

### 2.4 task_completion（任务完成度 + 语用得体性）

| CEFR / band | 0–100 | 描述语锚点（转述） | 出处 |
|---|---|---|---|
| B1 / 4.0–5.0 | 50–60 | 能完成基本信息交换与请求，能简单表达观点和态度；礼貌表达基本到位 | CEFR 2001 交际功能 / CEFR 2020 CV 语用得体性 B1【官方】 |
| B2 / 5.5–6.5 | 65–75 | 能按场合调整表达，能维持互动、接住对方的话题；偶尔语域不当 | CEFR 2020 CV 语用得体性 B2【官方】 |
| C1 / 7.0–8.0 | 80–90 | 语域、礼貌、委婉等得体性稳定；能主动引导对话、处理意外情况 | CEFR 2020 CV 语用得体性 C1【官方】 |
| A2 / 3.0–4.0 | 40–50 | 能完成最基本的问答交换；表达常直译，缺少礼貌/缓冲语 | CEFR 2001 A2【官方】 |

**可测化**：这一维最难「可测」，所以用**场景交际功能清单**（task checklist）来兜底，命中率可复算。
做法参照任务型对话评测（MultiWOZ / τ-bench）里「任务成功 = 预定清单是否达成」的思路【文献】。

| 场景 | 必须命中的交际功能（每项 1 分） |
|---|---|
| job_interview | 自我介绍 / 项目或经历 / 本人职责或角色 / 挑战或结果 / 反问或收尾 |
| cafe_order | 点单饮品 / 规格（冷热或大小）/ 加料或餐点 / 堂食或外带 / 结账或致谢 |
| ielts_part1 | 直接回答 / 给出原因或细节 / 举例 / 延伸或对比 |

清单本身是【自定】（按场景任务分析法拆的，没有外部出处）；命中判定由规则（关键词）与 LLM 双路给出，
两者不一致的样本进人工标注集，用来校准。

---

## 3. 规则子分公式（可复现，纯标准库）

所有规则分都用 `evaluation/features.py` 已有的字段 + `audio_json`，不引入新依赖。

### 3.1 输入来源

| 特征 | 来源 | 备注 |
|---|---|---|
| `word_count`, `filler_rate`, `ttr`, `mtld`, `sentence_count`, `mean_sentence_len` | `fluency_features()` | 文本 |
| `speech_rate_wpm`, `pause_ratio`, `pause_count`, `mean_pause_sec`, `audio_duration_sec` | `speech_features()` | 仅当 `audio_json` 有值 |
| `articulation_rate_wpm` | 同上 | 剔除静音后的语速 |

### 3.2 流利度规则子分

三个归一化项，各自 0–1：

```
f_wpm(w)   = clamp((w − 70) / 60, 0, 1)                    ; 70 ≤ w ≤ 130
           = 1                                             ; 130 < w ≤ 200
           = clamp(1 − (w − 200) / 60, 0, 1)               ; w > 200

f_pause(p) = clamp((0.45 − p) / 0.30, 0, 1)                ; p = pause_ratio
f_filler(q) = clamp((0.15 − q) / 0.12, 0, 1)               ; q = filler_rate
```

合成（权重【自定】）：

```
combined      = 0.40·f_wpm + 0.35·f_pause + 0.25·f_filler
S_fluency_rule = 45 + 45·combined            # 落在 45–90，对应雅思 3.5–8.0
```

**为什么锚在这些数**：流利二语口语常见语速 120–160 wpm，低于 100 wpm 通常被判为不流利【文献】；
`pause_ratio` 0.15 左右接近自然停顿水平，0.45 以上是明显的表达困难【文献，区间为本作品取整】。
`filler_rate` 在 STT 转写里天然偏低（Chrome 常不转写 um/uh），所以阈值取得宽【自定】。

**已修复的坑（`filler_rate` 曾大量假阳性）**：旧实现是「词表命中即计」，`FILLERS` 里含 `like / well / actually / basically`，
于是 `I'd like a latte` 必然被算成填充词（实测 3 句点单场景 3/3 误判，一句话少 3.8 分）。
现改为 `find_fillers()` 位置判定：硬词（um/uh/erm/hmm/mm/ah）直计；软标记只在句首、标点/停顿之后、
或紧跟一个已计的填充词时才计——`as well as` 里的 `well` 前面是 `as`，不算。修复后同样 3 句为 0/3。

**`sentence_count` 只用于「有标点」的输入**：Chrome 的语音转写通常不带标点，此时 `sentence_count` 恒为 1，
`mean_sentence_len` 会退化成整段词数。规则层因此只在句数 ≥2 时使用句长项；没有标点时用停顿估句数，
两者都没有就把句长项的权重让给从句标记（见 §3.3）。

**示例**：38 词 / 30 秒 → 76 wpm；pause_ratio 0.35；filler_rate 0.10

```
f_wpm = (76−70)/60 = 0.10
f_pause = (0.45−0.35)/0.30 = 0.33
f_filler = (0.15−0.10)/0.12 = 0.42
combined = 0.04 + 0.117 + 0.104 = 0.26
S = 45 + 45×0.26 = 56.7  →  B = 4.7 → 取整 4.5  →  B1
```

**缺失数据**：没录音（手动输入或麦克风失败）时 `f_wpm`、`f_pause` 不存在，
`S_fluency_rule = None`，**不要**用 filler 单独硬凑。报告写「无语音证据，流利度为文本推断」，
融合时把权重让给模型分并标注（见 §5）。

### 3.3 语言复杂度规则子分

```
f_mtld = clamp((mtld − 30) / 60, 0, 1)                  # 30 → 0，90 → 1
f_msl  = clamp((mean_sentence_len − 6) / 10, 0, 1)      # 6 → 0，16 → 1
f_cx   = clamp(complex_markers / N, 0, 1)               # 每句 ≥1 个从句标记即满分
         # N = 可用句数：标点句数 ≥2 时直接用；否则用 1 + pause_count 估（上限 word_count/4）；
         # 两条路都拿不到句数时 f_cx 不计入（不是把分母当 1，那样一个标记就顶格）
S_complexity_rule = 45 + 45·(0.45·f_mtld + 0.35·f_msl + 0.20·f_cx)
```

`complex_markers`：`because, although, though, while, whereas, which, who, that, when, if, so that, in order to, unless`
这类从句/连接词的计数（词表【自定】）。**必须按整词匹配**：按子串匹配时 `although` 里的 `though` 会被重复计一次
（实测踩到过，2 个标记被算成 3 个）。`that / who` 噪声大（很多 `that` 是普通从句引导词），校准时要重点看是否保留。

**两个必须处理的已知坑**：

1. **`sentence_count` 在语音输入下不可靠**：Chrome 的 Web Speech API 转写**通常不带标点**，
   而 `fluency_features()` 用 `[.!?]+` 分句 → 实际几乎总是 `sentence_count = 1`、`mean_sentence_len` = 整段词数。
   这会让 `f_msl` 变成「总词数」的代理，方向是错的。
   **实现【自定，已落地】**：句数 ≥2（有标点）直接用；只有录音时用 `1 + pause_count` 估句数（上限 `word_count/4`）；
   两者都没有则丢弃句长项，把它 0.35 的权重让给从句标记（MTLD 0.45 + 从句 0.55）。
   报告里会写清句数是从标点来还是从停顿估的（`sentence_source`）。
2. **MTLD 对短文本不稳**：MTLD 的原始研究建议文本长度 ≥100 词，且对长度仍有依赖【文献，McCarthy & Jarvis 2010】。
   本作品单轮多为 10–40 词，整场累计可能才 100 词左右。
   **规则【自定】**：整场用户总词数 < 50 时，词汇多样性回退到 TTR（并按词数标注「样本过短」）；
   ≥ 50 才用 MTLD。这一条必须写进报告，否则「词汇多样性 0.83」在 12 个词上会被追问。

   **已实测**：`"I like coffee very much and I usually order a latte in the morning"`（14 词、几乎无重复）
   算出 `mtld = 54.88`，按上面的公式 `f_mtld = 0.85`——一句简单句几乎拿到词汇多样性的满分。
   这不是我们的实现出错，是 MTLD 在 14 词上本来就没有意义。**这条回退规则不是保守，是必须。**

   更麻烦的是：**过了 50 词 MTLD 依然偏高**。一段 73 词、B1 水平的普通段落实测 `mtld = 93.26`，
   按原先 `25→0 / 60→1` 的锚会直接顶格。所以 v1 先把锚放宽到 `30→0 / 90→1`（仍是【自定】），
   并接受一个现实：**MTLD 在本作品这个长度上区分力弱，只能作低权重参考，不能当主证据。**

### 3.4 任务完成规则子分

```
hit_rate = 命中交际功能数 / 清单总数
S_task_rule = 40 + 60·hit_rate          # 0 项命中 = 40（A2 下缘），全命中 = 100
S_task_final = 0.6·S_task_rule + 0.4·S_pragmatic_llm     # 40% 来自语用得体性判断
```

`S_pragmatic_llm` 为模型按 §2.4 描述语给的 band 换分。权重【自定】，
理由是清单只测「有没有做」，不测「做得得不得体」。

### 3.5 发音的可测代理（v1 不参与融合，先采集）

现状：`pronunciation` 完全由模型看文本猜。两个可以变成真证据的信号，现在都被丢掉了：

| 信号 | 现状 | 做法 |
|---|---|---|
| `SpeechRecognition` 的 `confidence`（每条 alternative 附带 0–1） | `frontend/src/utils/speech.js` 只取了 `transcript`，confidence 丢弃 | 随 `audio_json` 上报；仅作**相对**比较，不同设备/网络的绝对值不可比 |
| 同句重读的一致性 | 没有 | 让用户重读报告里的一句，比较两次转写的编辑距离：`stability = 1 − edit_distance/len`。两次都转错成不同结果 → 发音不稳定；两次都稳定转错 → 转写本身不可信 |

`stability` 是自洽指标，**不需要声学模型**，能在答辩时讲清楚「我们没有音素级测评，但我们有一个可复现的清晰度代理」。
方法为【自定】，v1 只采集与展示，不并入分数；等 §6 的验证跑出相关性再决定权重。

### 3.6 规则分汇总

| 维度 | 规则分来源 | 无语音时 | 融合权重（规则:模型） |
|---|---|---|---|
| pronunciation | 无（仅模型 + 代理信号），报告写「无规则证据」 | 同 | 0 : 1 |
| fluency | §3.2（语速/停顿/填充词） | `None`，只用模型分并标「无语音证据」 | 0.5 : 0.5 |
| grammar_vocab | §3.3（只测**语言范围**；准确度只有模型能给） | 可用（MTLD 回退，句长项可弃） | 0.35 : 0.65 |
| task_completion | §3.4 清单命中率（只测「有没有做」；得体性交给模型） | 可用（文本判定） | 0.6 : 0.4 |

**准确度这一块目前没有规则分**：逐句纠错还没有错误分类，所以数不出错误率，语法准确度完全由模型给。
这是 P1 的活（错误分类 + 错误率），做之前不要在文档里假装有。

---

## 4. 融合与 `system_band` 取整契约

### 4.1 单维融合

```
若 rule 可用:  final = (1−w)·S_llm + w·S_rule      # w 见 §3.6
若 rule 缺失:  final = S_llm，并在报告标「本维度无规则证据」
```

先按权重取加权平均，再套下面的钳制（钳制作用在加权结果上，不是替换加权结果的计算过程）。

**只做单向钳制（防虚高）【自定】**：

```
若 S_llm − S_rule > 20  →  final = S_rule + 10      # 模型比可测证据高出 2 档，压回
若 S_rule − S_llm > 20  →  不钳制，但报告标「模型分显著低于可测指标，请人工复核」
```

理由：评分产品最伤信任的是「虚高」；规则分偏低时更可能是规则没覆盖到（比如内容很好但词表没命中），
所以只压不抬。所有钳制必须在报告里可见，不能静默改分。

**可复现**：每次融合都把 `model_score`（模型原分）、`rule_score`、`final_score`、`clamped`、`clamp_reason`
和参与计算的输入（wpm、停顿占比、填充词占比、MTLD、清单命中）一起写进 `scoring_json` 落库，
报告页「评分依据（可复现）」逐维展示。压分之后模型原分不会丢，答辩时能当场说明哪一维被压、压了多少。

> 字段名注意：**落库列是 `reports.scoring_json`，接口出参字段是 `scoring_detail`**（`report_view.py` 反序列化时改名）。
> 按 `scoring_json` 去查响应体、或按 `scoring_detail` 去查数据库列，都会扑空。

### 4.2 取整规则（给 `validate.py` 用）

```
def to_band(S):                    # S: 0–100 总分或维度分
    B = (S − 10) / 10              # 原始 band，可为 .25/.75 这种非法值
    if B < 3.0:  return None       # 低于 A2 下缘，不给 band
    if B > 9.0:  B = 9.0
    return floor(B × 2 + 0.5) / 2  # 最近的 0.5 档；.25/.75 平票一律向上
```

```
def to_cefr(B):
    if B is None: return "preA2"
    if B >= 8.5:  return "C2"
    if B >= 7.0:  return "C1"
    if B >= 5.5:  return "B2"
    if B >= 4.0:  return "B1"
    return "A2"
```

举例：S=56.7 → B=4.67 → 4.5 → B1；S=63 → B=5.3 → 5.5 → B2；S=90 → 8.0 → C1。

档位统一用 **CEFR 字母**（A2/B1/B2/C1），不再用 A/B/C 粗档：`validate.py` 要对系统档位和人评档位算 kappa，
类别必须同档位、同命名。`make_demo.py` 已跟着改成输出 CEFR 字母（`system_band` 列名不变，值改了）。

`validate.py` 的接线（**已实现**）：一个列、一个开关。

| 列名 | 例 | 用途 |
|---|---|---|
| `system_band` | `B2` | 与人评 CEFR 做一致率 / 档位距离 / Cohen kappa |
| `human1_band`、`human2_band` | `B1`、`B2` | 人评档位，`--bands` 传入 |

```powershell
D:\python\python.exe -m evaluation.validate --csv evaluation/demo_data.csv `
  --raters human1,human2 --system system `
  --bands human1_band,human2_band --system-band system_band
```

输出里的 `system_band_agreement`：

| 字段 | 含义 |
|---|---|
| `n` / `skipped` | 参与比较的样本数 / 缺字段被跳过的数 |
| `exact_rate` | 系统档位与人评多数票完全一致的比例 |
| `adjacent_rate` | 相差 ≤1 档的比例（口径【自定】，口语评测常用“相邻档可接受”） |
| `mean_abs_cefr_distance` | 平均相差几档 |
| `kappa_vs_human_majority` | 系统 vs 人评多数票的 Cohen kappa（平票取较低档，保守） |
| `kappa_per_human` | 系统分别与每位评分者的 kappa |

**不要**把 `system_band` 塞进 `--bands`：Fleiss kappa 要求所有列都是评分者，把系统当第三个人算出来的数没有解释力。

**合成数据上的实测**（`demo_data.csv`，n=20，仅证明脚本通路，不是真实结论）：
exact_rate 0.70、adjacent_rate 1.00、平均差 0.30 档、kappa 0.49（中等）。真实结论必须换成真人标注。

### 4.3 样本量与结论

n < 10 时 kappa 的置信区间宽到没有意义：只打印「样本不足，不作结论」。
n ≥ 20 才在报告里写一致性数字（对齐 `docs/validation.md` 的采样要求）。

---

## 5. 降级路径必须诚实（对应 P0-3）

原状（已修）：`scoring.py` 在 key 为空、超时、解析失败三种情况下都静默返回 `_mock_report`，
里面是写死的分数和一句用户没说过的话（`I am very interest in this job.`）。演示时网络抖一下就是事故。

报告必须带 `source` 字段（**已实现**）：

| `source` | 触发 | 报告展示 |
|---|---|---|
| `llm` | 正常 | 正常分数 + band |
| `mock` | 模型不可用（未配置 key / 超时 / 返回无法解析） | **不给 band、不给总分**，标「示例报告（模型不可用）· 本次不计分」，`sentence_fixes` 只列用户真实说过的句子 |
| `llm_rules_fallback` | **未实现**（规则层已就绪，`rules.py` 已上线） | 计划：只给规则分和 band，标「模型不可用，本报告仅含可测指标」。当前代码不允许：`rules.apply_to_report()` 对非 `source=llm` 直接原样返回（`rules.py:307`），降级报告不借规则分凑成绩 |

两条硬约束，都在代码里做了校验，不只靠 prompt：

1. `original` 必须能在用户转写里找到（归一化后比对：忽略大小写和标点），找不到就丢弃这条改写。
   模型如果编了一句用户没说过的话，这条不会出现在报告里。
2. 降级报告 `total_score / band / cefr` 全部写 `NULL`，DB 里也是 `NULL`，历史页显示「—」而不是 0，
   避免把「没测」显示成「得了 0 分」。

---

## 6. 验证协议（怎么证明这套规则站得住）

### 6.1 单测级（确定、可重复）

1. **边界**：空文本、全填充词、只有 1 个词、`pause_ratio = 0`、`wpm = 0`、`wpm = 300` → 不报错，分数落在 40–100。
2. **单调性**：固定其它输入，只调 `pause_ratio` 从 0.1 到 0.5 → `S_fluency_rule` 必须单调不增。
3. **取整**：`to_band` 对 0.5 步长全表扫一遍，输出只可能是 `{4.0,4.5,…,9.0}`；`to_cefr(to_band(S))` 与 §1.2 表一致。

### 6.2 敏感性（证明规则真的测到了东西）

同一学习者、同一段内容，读三遍：正常 / 带 1–2 秒长停顿 / 加大量 um-uh。
预期：长停顿版 `S_fluency_rule` 比正常版低 ≥5 分；填充词版 `filler_rate` 上升、分数下降。
**方向错了说明公式错了，不是数据错了。**

### 6.3 模型稳定性（决定 LLM 权重）

同一份对话记录，重复调用 `finish` 3 次，记录每个维度分的标准差。
判据【自定】：维度标准差 ≤3 分才允许 `S_llm` 权重 ≥50%；超过 5 分则应把规则权重提到 0.6–0.7。
这个实验很便宜（3 次调用），但它把「要不要信模型分」从感觉变成数字。

### 6.4 人评一致性（最终证据）

n ≥ 20，2–3 名英语教师独立盲评（不给系统分），用同一份 §2 的量表。

| 指标 | 验收线 | 依据 |
|---|---|---|
| 人评 ICC(2,1) | ≥ 0.75（良好） | Koo & Li (2016)【文献】 |
| 系统 vs 人评均值 Pearson / Spearman | ≥ 0.70 | 【自定，工程验收线】 |
| MAE | ≤ 8 分（0–100 量表） | 【自定，约 0.8 个 band】 |
| Bland-Altman 平均差 | \|bias\| ≤ 5 分 | 【自定】 |
| CEFR 档 Cohen kappa（system vs 人评多数票） | ≥ 0.61（较强） | Landis & Koch (1977)【文献】 |

跑法（`--system-band` 为 §4.2 已实现的开关，列里放 CEFR 字母）：

```powershell
D:\python\python.exe -m evaluation.validate --csv <真实标注>.csv `
  --raters human1,human2 --system system `
  --bands human1_band,human2_band `
  --system-band system_band `
  --out evaluation/real_report.json
```

**仍然必须先说清楚**：`demo_data.csv` 是合成数据，跑出来的数只证明脚本能跑，不构成任何真实结论。

### 6.5 校准记录

每条【自定】参数（wpm 阈值、权重、MTLD 区间、钳制阈值）校准后，把「改前 → 改后 → 依据数据」记到本节。
参数一改，`docs/validation.md` 的结论就作废，必须重跑。

| # | 日期 | 参数 | 改前 → 改后 | 依据 |
|---|---|---|---|---|
| 1 | 10-29 | `f_mtld` 区间 | 25→0 / 60→1 改为 30→0 / 90→1 | 73 词 B1 普通段落实测 MTLD=93.26，旧锚顶格；仍属【自定】，待真人样本校准 |
| 2 | 10-29 | 填充词判定 | 词表命中即计 → 硬词直计、软标记按位置 | 点单场景 `I'd like a latte` 被误计（3 句实测旧逻辑 3/3 假阳性，新逻辑 0/3） |
| 3 | 10-29 | 从句标记匹配 | 子串匹配 → 整词匹配 | `although` 里的 `though` 被重复计：2 个标记算成 3 个，字数越长的句子越虚高 |
| 4 | 10-29 | 规则权重 | 语法维度统一 0.5 → 语法规则 0.35、任务 0.6 | 语法规则分只测「语言范围」，不测准确度；任务清单只测「有没有做」，不测得体性，权重给模型多留一点 |
| 5 | 10-29 | 钳制位置 | 钳制加权结果 → 先加权再钳制 | 否则 0.5/0.5 下永远差不到 20 分，钳制形同虚设 |

---

## 7. 实现映射（进度）

| 位置 | 改动 | 状态 |
|---|---|---|
| `evaluation/features.py` | `find_fillers()` 位置判定；`lexical_diversity()` 短文本回退 TTR；`mtld` 不足 50 词输出 `None`；新增 `diversity_metric / diversity` 字段 | ✅ 已完成 |
| `evaluation/bands.py` | `score_to_band / band_to_score / band_to_cefr / cefr_of_score / cefr_distance / report_bands`（纯标准库，全项目唯一换算入口） | ✅ 已完成 |
| `evaluation/make_demo.py` | 档位改 CEFR 字母；重新生成 `demo_data.csv`（ICC 未变：0.9022 / 0.9486） | ✅ 已完成 |
| `evaluation/validate.py` | `--system-band` 接线：一致率、档位距离、Cohen kappa（多数票 + 分人）；stdout 强制 UTF-8 | ✅ 已完成 |
| `backend/app/services/scoring.py` | 模型直接输出 band；`original` 必须来自用户转写（否则丢弃）；降级报告不计分、不虚构句子 | ✅ 已完成 |
| `backend/app/models.py` + `main.py` | `reports` 新增 `band / cefr / source / bands_json`，启动时按列补齐（旧库只加列不改数据） | ✅ 已完成 |
| `backend/app/services/report_view.py` | `report_out()` 统一报告出参，`sessions` 与 `reports` 两个路由共用 | ✅ 已完成 |
| `backend/app/schemas.py` | `ReportOut` 增加 `band / cefr / source / bands`，`total_score` 可空 | ✅ 已完成 |
| `frontend/src/views/Report.vue` | 显示「B1 · 雅思 5.0」；每维显示 band；降级横幅；空改写不显示删除线 | ✅ 已完成 |
| `backend/app/services/rules.py` | 规则子分（流利度/复杂度/任务清单）、只压不抬的融合、`scoring_json` 留原值 | ✅ 已完成 |
| `frontend/src/views/Report.vue` 每维「依据」 | 模型分 / 规则分 / 最终分 / 钳制原因 / 输入特征展开 | ✅ 已完成 |
| 发音的可测代理（confidence、同句重读稳定性） | 前端上报 + 相关性实验 | ⏳ 未做（§3.5） |
| 逐句纠错的错误分类与错误率 | 语法准确度规则分 | ⏳ 未做（P1） |
| `docs/validation.md` | 补 CEFR 档 kappa 口径与 0.61 验收线 | ✅ 已完成 |

**已完成部分的实测**（可复跑）：

- `bands.py`：39 例换算全过（含 5.25→5.5、9.5→9.0、39 分→无 band）。
- `rules.py`：24 项单测全过（含「模型虚高 25 分被压回规则+10」、模型偏低只标记不抬、无语音时流利度不用模型硬凑）。
- 后端三模式：mock（12 项断言）、真实模型（33 项断言，含每个维度留了模型原分）、旧库迁移（补 5 列、旧报告仍可读）。
- 真实模型那一次：模型四维 band 5.0–6.0，融合后总分与档位重算一致，`scoring_json` 里每维都能看到 model/rule/final 三个数。

---

## 8. 明确不声称的东西

- 不是雅思官方评分，band 为模型 + 规则的估算。
- 不是音素级发音测评；发音维度只有文本推断和转写置信度代理。
- **语法准确度目前没有规则分**，只有模型判断；规则分只测语言范围（§3.6）。
- 规则权重在**真实标注数据上尚未校准**，§3 全部数值为初版【自定】。
- n < 20 不做任何一致性结论；`demo_data.csv` 的合成结果不算证据。
