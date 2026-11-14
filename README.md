# SpeakPal · 可验证的 AI 英语口语诊断陪练

> **传智杯 AI-Web 网页开发挑战赛参赛作品**
> 代码版本：`v0.2.0`（后端 `FastAPI(title="SpeakPal API", version="0.2.0")` / 前端 `speakpal-frontend@0.2.0`）
> 文档版本：`v2.2` · 更新日期：`2026-11-13`
> 核心定位：**真实场景多轮口语对练 + 模型与可测规则融合诊断 + 离线统计可验证闭环 + SM-2 间隔重复学习闭环**

---

## 1. 项目简介

**SpeakPal** 是一个面向高校学生与英语学习者的场景化 AI 英语口语诊断陪练系统。用户注册登录后，可选择 6 类高频真实场景（求职面试、咖啡店点单、雅思 Part 1、酒店入住、机场值机、餐厅点餐），通过**语音录入或打字输入**与 AI 角色进行多轮沉浸式对话（支持 SSE 流式回复与语音合成朗读）。

与传统"只陪聊、黑盒给分"的口语工具不同，SpeakPal 重点解决两个核心问题：

1. **分数可解释、可验证**：采用 **LLM 评分 + 客观规则特征分（语速 WPM、停顿占比、填充词率、MTLD 词汇多样性、平均句长、交际功能清单）只压不抬融合算法**，输出 0–100 综合分、IELTS Band（0.5 步长）、CEFR 等级（A2–C2）与跨作答模式可比档位（`comparable_band`），并配套纯 Python 标准库实现的 `evaluation/` 离线信效度验证套件（ICC、Cohen/Fleiss Kappa、Pearson/Spearman、MAE/RMSE、Bland-Altman）。
2. **练习结束即学习起点**：诊断报告中的语法、词汇、拼写、语用错误可自动转化为 **SM-2 间隔重复学习卡（`study_items`）**，结合内置 **600 核心词库（高考 / 四级 / 六级各 200 词）、60 张语法卡、60 张口语地道表达卡**、错句 85% 相似度跟读重说（Drills）、2×10 组最小对立对发音辨析（Minimal Pairs）及随堂笔记，形成完整学习闭环。

### 1.1 诚实边界

以下内容**不在**当前实现范围内，请勿据此推断系统已具备相应能力：

- **不做声学测评**：发音维度由大模型**依据转写文本推断**；报告页该维标题固定显示「发音清晰度」（`Report.vue:43`），只是给人看的栏目名，不代表声学清晰度测量。正常报告注脚为「分数由模型分与可测规则分融合得出，仅供参考」。
- **不保存原始音频**：仅入库录音的**统计元信息**（时长、有声时长、停顿序列），录音文件只存在于浏览器本地 IndexedDB，用于回放。
- **无真实人工评分数据**：`evaluation/demo_data.csv` 是固定随机种子（`seed=42`）生成的 20 条合成数据，仅用于验证统计脚本链路可跑通，**不构成任何有效性结论**。
- **无多租户 / 班级 / 教师端**：管理台只做只读统计与账号运维。

---

## 2. 核心特性一览

| 模块分类 | 核心能力 | 关键实现与工程亮点 |
|---|---|---|
| **场景化多轮对练** | 6 大真实场景 + 3 档难度（`easy` / `medium` / `hard`）+ 句型脚手架（Frames） | 支持 **SSE 流式回复**（`/api/sessions/{id}/turn/stream`）与非流式自动回退；仅在完整生成后落库，杜绝半截脏数据 |
| **双模态输入与音频分析** | Web Speech API 语音识别 + Web Audio API 50ms RMS 包络采样 + 浏览器本地录音回放 | 实时提取说话时长、有效发音时长、停顿次数与停顿序列；原始录音仅存于浏览器 IndexedDB/ObjectURL，**零音频上传**保护隐私 |
| **模型 + 规则融合评分** | 动态维度（纯录音 4 维 / 纯打字 3 维 / 混合 5 维）+ 单一换算锚 `S = 10B + 10` | 规则分对模型分执行"高出 20 分即压回规则分 +10"的防虚高约束；完整融合明细落库 `scoring_json`，前端可展开验算 |
| **跨模式可比与降级保护** | 共享维度可比档（`comparable_band`）+ 诚实降级策略 | 成长曲线基于 `grammar_vocab` 与 `task_completion` 计算跨模式可比档；无密钥或断网降级报告（`source=mock`）显式标注「示例报告（模型不可用）· 本次不计分」，严禁伪造分数与假造原句 |
| **SM-2 学习闭环** | 今日待复习队列 + 四大板块（复习 / 新词 / 语法 / 口语）+ 随堂笔记（`notes`） | 报告错句自动建卡 + 离线 JSON 题库（高考/四级/六级词库、时态/冠词/介词/从句语法卡、书面转口语卡），支持拼写、选句、造句客观判分驱动 SM-2 调度 |
| **针对性专项训练** | 错句跟读重说（Drills）+ 最小对立对发音训练（Minimal Pairs） | 报告错句支持语音跟读与词级相似度实时比对（≥0.85 达标）；内置 `/iː/ vs /ɪ/`、`/θ/ vs /s/` 等高频易混音素对立训练 |
| **学习数据看板** | 连续打卡天数（Streak）+ 12 周练习热力图 + 维度均分 + 近 7 天进步幅度 | 按用户本地时区（`tz_offset`）切日聚合，自动过滤非正式计分报告，支持历史记录多维筛选 |
| **自带密钥与安全加固** | 浏览器端 BYOK（`X-LLM-Key` / `X-TTS-Key`）+ `token_version` 踢旧设备 + SSRF 防护 | 服务端不存模型密钥；改密即递增 `token_version` 使旧 JWT 秒级失效；启动自动替换弱密钥；内置登录防暴破与内网地址 SSRF 拦截 |
| **离线信效度验证层** | 纯标准库统计引擎 `evaluation/` + 内容静态检查器 `tools/check_content.py` | 零第三方科学计算库依赖即可复现 ICC(2,1)/ICC(2,k)、Kappa、Bland-Altman 等统计量；一键校验 720 条内置教研内容质量 |

---

## 3. 技术栈

### 3.1 前端（`frontend/`）

- **核心框架**：Vue 3（`<script setup>` 组合式 API）+ Vite 5
- **路由与状态**：Vue Router 4（History 模式 + 登录守卫 + catch-all 兜底）+ Pinia 2
- **样式体系**：Tailwind CSS 3 + 自定义语义化设计令牌（`style.css`）
- **网络与流式通信**：Axios（统一 JWT 注入、`X-Auth-Reason` 401 分流拦截、`X-LLM-Key` 透传）+ 原生 `fetch` + `ReadableStream`（SSE 流式解析）
- **浏览器原生能力**：Web Speech API（`SpeechRecognition` / `speechSynthesis`）、Web Audio API（`AudioContext` + `AnalyserNode` 时域 RMS 包络检测）、MediaRecorder + IndexedDB（本地录音持久化回放）

### 3.2 后端（`backend/`）

- **Web 框架**：FastAPI（自动 OpenAPI Schema + 本地化离线 Swagger UI `/docs`）
- **数据持久化**：SQLite + SQLAlchemy 2.x ORM + 启动期幂等 Schema 自动演进（`_ensure_schema()`）
- **安全与认证**：PBKDF2-HMAC-SHA256（120,000 次迭代 + 16 字节随机盐）+ PyJWT（HS256 + `token_version` 会话代次校验）+ 滑动窗口登录防暴破 + SSRF 私网 IP 校验
- **大模型与语音接入**：`httpx` 调用任意 OpenAI 兼容 REST 接口（默认适配 DeepSeek `deepseek-chat`，支持流式 SSE 与 `/audio/speech` TTS 语音合成）

### 3.3 离线验证与工具链（`evaluation/` & `tools/`）

- **统计评估包**：Python 3 纯标准库（`math` / `csv` / `json` / `statistics`），手写双向随机效应 ANOVA 计算 ICC
- **教研内容校验**：`tools/check_content.py`（校验 600 词汇屈折形态匹配、60 语法卡、60 口语卡完整性与跨档去重）
- **自动化截图工具**：`tools/screenshot/shoot.mjs`（基于 Playwright 的全流程页面快照脚本）

---

## 4. 目录结构

```text
传智杯ai-web网页开发挑战赛/
├── README.md                       # 项目说明文档（本文档）
├── SpeakPal_技术文档.pdf            # 交付级 PDF 技术文档
├── setup.ps1                       # 一键初始化脚本（Python 虚拟环境 + 前端依赖安装）
├── start-all.bat                   # Windows 一键启动脚本（双窗口启动前后端并打开浏览器）
├── start-backend.bat / .ps1        # 后端独立启动脚本（含 8000 端口占用自动清理）
├── start-frontend.bat / .ps1       # 前端独立启动脚本（Vite Dev Server :5173）
├── backend/                        # FastAPI 后端工程
│   ├── .env.example                # 环境变量配置模板
│   ├── requirements.txt            # Python 依赖清单
│   ├── speakpal.db                 # SQLite 数据库文件（运行期自动生成/迁移）
│   └── app/
│       ├── main.py                 # 应用入口、CORS、幂等表结构迁移、路由挂载
│       ├── config.py               # 配置解析、弱密钥自动轮换、数据目录优先级解析
│       ├── db.py                   # SQLAlchemy Engine 与 Session 生命周期管理
│       ├── models.py               # 10 张核心 ORM 表模型定义
│       ├── schemas.py              # Pydantic 入参校验与响应 DTO
│       ├── security.py             # PBKDF2 散列、JWT 签发校验、Admin 鉴权
│       ├── timeutil.py             # UTC 时间戳与带 Z ISO8601 格式化工具
│       ├── data/                   # 离线教研数据包（wordbanks ×3 / grammar ×4 / spoken.json）
│       ├── routers/                # 12 个路由模块（auth / scenes / sessions / reports /
│       │                           #   exercises / hints / study / words / account / system / tts / admin）
│       ├── services/               # 20 个领域服务（agent / llm / scoring / rules / srs / study /
│       │                           #   dashboard / wordbank / library / pronunciation /
│       │                           #   outbound / llm_config / storage …）
│       ├── tests/                  # unittest 回归（test_api.py / test_scales.py）
│       └── static/                 # 运营后台单页（admin.html）与离线 Swagger UI 静态资源
├── frontend/                       # Vue 3 + Vite 前端工程
│   ├── package.json                # 前端依赖与脚本定义
│   ├── vite.config.js              # Vite 配置（127.0.0.1:5173 及 /api 反向代理至 :8000）
│   ├── public/                     # 品牌 Logo 与 Favicon 矢量资源
│   └── src/
│       ├── main.js / App.vue / style.css
│       ├── router/index.js         # 13 条业务路由 + catch-all 兜底与认证守卫
│       ├── api/                    # Axios 实例封装（client.js）与 SSE 流式客户端（stream.js）
│       ├── stores/                 # Pinia 状态仓库（auth / session / settings）
│       ├── components/             # AppHeader / HintCard / StudyDashboard / TabBar / BrandLogo /
│       │                           #   SceneIcon / CountUp / EmptyState / BackLink / MnemonicCard
│       ├── utils/                  # 语音转写（speech.js）、音频包络（audio.js）、
│       │                           #   录音存储（recordings.js）、密钥门禁（llmGate.js）
│       └── views/                  # 12 个页面视图（Login / Home / Practice / Report /
│                                   #   History / Review / StudyHome / StudyScope / StudyLearn /
│                                   #   Notes / Pronunciation / Settings）
├── evaluation/                     # 离线评分信效度统计验证子系统（同时供后端提取特征）
│   ├── agreement.py                # ICC(2,1)/ICC(2,k)、Kappa、Pearson/Spearman、MAE/RMSE、Bland-Altman
│   ├── bands.py                    # 维度权重、0-100 分与 IELTS Band / CEFR 映射、跨模式可比档
│   ├── scales.py                   # 多量表换算（雅思 / CEFR / 托福 / 多邻国 / 四六级）
│   ├── features.py                 # 文本流利度与词汇多样性（TTR / MTLD）及音频停顿特征提取
│   ├── validate.py                 # CLI 验证报告生成器
│   ├── make_demo.py                # 固定随机种子合成演示数据生成脚本
│   ├── demo_data.csv               # 20 条合成评估样本数据
│   └── demo_report.json            # 验证结果输出样本
├── tools/                          # 工程辅助工具
│   ├── check_content.py            # 离线词库/语法/口语 JSON 质量校验脚本
│   ├── generate_pdf.py             # PDF 技术文档生成脚本（ReportLab + 微软雅黑）
│   ├── requirements-pdf.txt        # 该脚本的工具链依赖（reportlab，锁版本；不进后端运行时）
│   ├── node/                       # 便携版 Node.js（脚本自动探测，无需全局安装）
│   └── screenshot/                 # Playwright 自动化截图脚本
└── docs/                           # 详细设计与专项说明文档库
    ├── 技术文档.md                 # 完整技术文档（Markdown；PDF 副本由脚本生成、不入库）
    ├── design.md                   # 产品设计与接口契约基线文档（口径来源）
    ├── rubric-band.md              # 评分量表、规则分锚点与 IELTS/CEFR 换算规范
    ├── validation.md               # 评估与验证方法论说明
    ├── ui-visual.md / logo.md      # 视觉规范与品牌资产
    ├── manual-walkthrough.md       # 评委手动验收走查手册
    ├── demo-script.md              # 校赛答辩演示脚本
    └── screenshot-guide.md         # 截图与素材采集指南
```

---

## 5. 快速开始（Windows 推荐流程）

### 5.1 环境要求

- **操作系统**：Windows 10 / 11（推荐终端使用 PowerShell 7 `pwsh`）
- **Python**：`>= 3.10`（实测 `Python 3.14.4` 完美运行）
- **Node.js**：`>= 18`（项目已内置/自动探测 `tools/node` 便携版 Node，无需全局配置亦可运行）
- **浏览器**：**Google Chrome** 或 **Microsoft Edge**（Web Speech API 语音识别依赖 Chromium 内核）

### 5.2 首次安装依赖

在项目根目录打开 PowerShell，执行一键安装脚本：

```powershell
.\setup.ps1
```

> `setup.ps1` 会自动完成：创建 `backend\.venv` 虚拟环境、安装 `backend\requirements.txt` 依赖、将临时目录指向仓库内 `.tmp` 规避权限问题，并自动定位 Node.js 执行 `frontend` 的 `npm install`。

### 5.3 一键启动服务

直接双击根目录下的 **`start-all.bat`**，或在终端运行：

```powershell
.\start-all.bat
```

启动器会自动拉起两个服务窗口并打开默认浏览器：

- **前端应用（用户端）**：<http://127.0.0.1:5173>
- **后端运营管理台**：<http://127.0.0.1:8000/admin>
- **离线 Swagger API 文档**：<http://127.0.0.1:8000/docs>

如果希望分别在两个终端窗口手动启动：

```powershell
# 终端 1：启动 FastAPI 后端（自动清理被占用的 8000 端口）
.\start-backend.ps1

# 终端 2：启动 Vite 前端开发服务器
.\start-frontend.ps1
```

> ⚠️ 两个服务均只监听 `127.0.0.1`，局域网其他设备无法访问。答辩若需投屏演示，需改为 `--host 0.0.0.0`，并注意这会把管理台暴露出去。

---

## 6. 大模型密钥配置说明（BYOK 机制）

SpeakPal 采用**浏览器端自带密钥（Bring Your Own Key）**安全架构：

1. **服务端零对话密钥存储**：后端 `.env` 不保存 `LLM_API_KEY`（即使写了也不会被读取），所有对话与评分请求均由前端通过请求头 `X-LLM-Key`、`X-LLM-Base-Url`、`X-LLM-Model` 动态传入，密钥仅保存在用户当前浏览器的 `localStorage` 中。
2. **首次使用引导**：注册/登录进入系统后，点击右上角或底部导航进入 **「设置」（`/settings`）** 页面：
   - **默认供应商**：DeepSeek（接口地址 `https://api.deepseek.com/v1`，模型 `deepseek-chat`），也可填入任意兼容 OpenAI `/v1/chat/completions` 协议的接口（如 OpenAI、通义千问、硅基流动、Moonshot 等）。
   - 填入 API Key 后点击 **「测试连接」**，验证通过后即可回到首页开启场景对练。
3. **本地私有模型（如 Ollama）**：出于 SSRF 安全防护，后端默认拒绝请求本机与内网地址。若需连接本机 Ollama，请在 `backend/.env` 中设置 `ALLOW_PRIVATE_LLM_HOSTS=1` 后重启后端。
4. **可选语音合成（TTS）**：默认使用浏览器内置 `speechSynthesis` 免费朗读；如需高自然度神经网络语音，可在「设置」页配置兼容 OpenAI `/v1/audio/speech` 的 TTS 密钥与模型（如 OpenAI `tts-1` 或硅基流动 `FunAudioLLM/CosyVoice2-0.5B`）。前端先试 `POST /api/tts`，**任何失败都回落 `speechSynthesis`**。

---

## 7. 核心工作流与验证命令

### 7.1 30 秒核心体验路径

1. **注册/登录**：访问 `http://127.0.0.1:5173/login` 创建账号。
2. **配置密钥**：在 `/settings` 填入 DeepSeek / OpenAI 兼容 API Key 并测试通过。
3. **开启对练**：在首页选择「求职面试」或「咖啡店点单」，使用麦克风录音或打字对话：3 个目标都达成、或到 6 轮上限，就会提示可以出报告（无目标的老会话回退 4 轮；可展开「句型提示」辅助表达）。
4. **查看诊断报告**：点击「结束并出报告」，查看综合分、IELTS Band / CEFR 等级、各维规则分与模型分融合明细、流利度客观特征，以及逐句地道改写。
5. **跟读与复习**：在报告页直接点击「跟读重说」训练错句（相似度 ≥0.85 通关），随后进入「学习」（`/study`）模块体验 SM-2 卡片复习、词汇拓展与语法/口语专项训练。

### 7.2 运行离线统计验证（`evaluation/`）

在仓库根目录下可执行以下命令复现人机评分一致性验证报告：

```powershell
# 1. 生成固定随机种子的合成演示数据（20 条双盲人评 vs 系统分样本）
python -m evaluation.make_demo

# 2. 运行一致性验证 CLI，输出终端中文报告与 JSON 结构化结果
python -X utf8 -m evaluation.validate `
  --csv evaluation/demo_data.csv `
  --raters human1,human2 `
  --system system `
  --bands human1_band,human2_band `
  --system-band system_band `
  --out evaluation/demo_report.json
```

### 7.3 运行内置教研内容质量校验（`tools/`）

```powershell
python tools/check_content.py
```

> 返回码 `0` 表示 600 条高考/四六级核心词库、60 条语法卡、60 条地道口语卡（合计 720 条）全部通过字段完整性、词形匹配与跨档去重检查。

### 7.4 重新生成 PDF 技术文档

```powershell
python tools/generate_pdf.py
```

> 输出 `SpeakPal_技术文档.pdf`（根目录交付版，入库）与 `docs/技术文档.pdf`（同源副本，本地生成、不入库）。
> 依赖 `reportlab`，属工具链依赖而非后端运行时依赖，单独安装：`pip install -r tools/requirements-pdf.txt`（已锁 `reportlab==5.1.0`）。

---

## 8. 评分口径速查

> 完整量表推导与校准记录见 `docs/rubric-band.md`；以下数值均以代码为准。

### 8.1 维度权重（随作答模式变化，`evaluation/bands.py::DIMENSION_WEIGHTS`）

| 作答模式 | pronunciation | fluency | written_expression | grammar_vocab | task_completion |
|---|---|---|---|---|---|
| `voice`（纯录音） | 20 | 20 | — | 30 | 30 |
| `typed`（纯打字） | — | — | 35 | 35 | 30 |
| `mixed`（混合） | 15 | 15 | 20 | 25 | 25 |

缺失维度按剩余权重重新归一，不当 0 分；认不出模式才退回等权平均。
`comparable_band` 仅取两模式共享的 `grammar_vocab` + `task_completion` 等权平均，供历史成长曲线跨模式比较。

### 8.2 融合权重与只压不抬（`backend/app/services/rules.py`）

| 维度 | 规则分权重 | 模型分权重 | 说明 |
|---|---|---|---|
| `pronunciation` | 0 | 1.0 | 无声学证据，由模型依转写推断 |
| `fluency` | 0.50 | 0.50 | 规则分 = 语速 / 停顿占比 / 填充词率加权 |
| `grammar_vocab` | 0.35 | 0.65 | 规则分只测语言范围，准确度来自模型 |
| `task_completion` | 0.60 | 0.40 | 规则分 = 场景交际清单命中率 |
| `written_expression` | 0 | 1.0 | 仅打字轮出现 |

**只压不抬**：模型分 − 规则分 `> 20` 时，最终分强制压回 `规则分 + 10` 并标记 `clamped=true`；模型分显著低于规则分（差 `> 20`）**不抬分**，仅在报告中标注「请人工复核」。

### 8.3 单一换算锚与 CEFR 映射（`evaluation/bands.py`）

- 换算锚：`S = 10 × B + 10`（反向 `B = (S − 10) / 10`），向最近 0.5 档取整，区间 3.0–9.0；`S < 40` 不给 band。
- CEFR：`≥8.5 → C2`、`≥7.0 → C1`、`≥5.5 → B2`、`≥4.0 → B1`、`≥3.0 → A2`。

### 8.4 SM-2 调度（`backend/app/services/srs.py`）

只有 **again / hard / good** 三档反馈，`ease ∈ [1.3, 2.8]`，间隔上限 60 天：

| 反馈 | ease | 间隔 | 其它 |
|---|---|---|---|
| `again` | −0.2 | 置 1 天，但 `due_at = now + 10 分钟`（当天内还会再出现） | `reps + 1`、`lapses + 1` |
| `hard` | −0.15 | `max(1, round(interval × 1.2))` 天 | `reps + 1` |
| `good` | +0.1 | `max(1, round(interval × 2.5))` 天 | `reps + 1` |

---

## 9. 环境变量参考（`backend/.env`）

复制 `backend/.env.example` 为 `backend/.env` 即可使用（首次启动会自动生成高强度随机密钥）。

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `JWT_SECRET` | 首次启动自动生成 48 字节随机串 | JWT 签名密钥；若检测到空值或公开弱口令会自动轮换并写回 `.env` |
| `JWT_EXPIRE_MINUTES` | `10080` | 登录态有效期（默认 7 天） |
| `ADMIN_KEY` | 首次启动自动生成 12 字节随机串 | 运营后台（`/admin`）管理密钥，生成时会打印在后端启动控制台 |
| `DATABASE_URL` | `sqlite:///./speakpal.db` | 数据库连接串（优先级：真实进程环境变量 > `data_location.json` > `.env` > 默认值） |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | 默认大模型 API 基础地址（用户未在浏览器自定义时使用） |
| `LLM_MODEL` | `deepseek-chat` | 默认对话与评分模型名称 |
| `ALLOW_PRIVATE_LLM_HOSTS` | `0` | SSRF 防护开关：默认 `0` 禁止请求内网/本机地址；使用本地 Ollama 时设为 `1` |
| `CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | 跨域白名单（逗号分隔） |
| `TTS_API_KEY` | 空 | 服务端可选兜底 TTS 密钥（留空则使用浏览器原生朗读或用户自带 TTS Key） |
| `TTS_BASE_URL` / `TTS_MODEL` / `TTS_VOICE` | `https://api.openai.com/v1` / `tts-1` / `alloy` | 可选语音合成端点、模型名与音色配置 |
| `STORAGE_ROOT` | 空 | 管理台「改数据位置」的目录白名单；留空不限目录（始终不覆盖已存在文件） |

---

## 10. 接口规模

后端按业务域划分为 12 个路由模块，共 **61 个 `/api` 操作**（60 个路由注册 + `GET /api/health`），落在 **54 条 `/api` 路径**上（2026-11-13 取自 `GET /openapi.json`），另有 3 个非 API 页面入口：`/` 与 `/admin`（管理控制台 HTML）、`/docs`（离线 Swagger UI）。

| 模块 | 前缀 | 端点数 | 职责 |
|---|---|---|---|
| `auth.py` | `/api/auth` | 3 | 注册、登录、取当前用户 |
| `scenes.py` | `/api` | 2 | 场景列表、句型脚手架 |
| `sessions.py` | `/api` | 6 | 建会话、提交轮次（普通/流式）、结束出报告、会话详情、历史列表 |
| `reports.py` | `/api` | 1 | 读取诊断报告 |
| `exercises.py` | `/api` | 4 | 跟读重说队列与判分、最小对立对题组与判定 |
| `hints.py` | `/api` | 1 | 句型提示 |
| `study.py` | `/api` | 21 | SM-2 学习闭环（今日队列/复习/建卡/词库/语法/口语）与随堂笔记 CRUD |
| `words.py` | `/api/study/words` | 4 | 单词助手、导入、已学列表、造句检查 |
| `account.py` | `/api/me` | 7 | 个人资料、偏好设置、学习看板、难度建议、清数据与注销 |
| `system.py` | `/api` | 3 | LLM 配置查询、密钥连通性测试、存储状态 |
| `tts.py` | `/api` | 1 | 语音合成 |
| `admin.py` | `/api/admin` | 7 | 全局统计、用户管理、清库、改数据目录 |

> 完整清单以运行期的 `GET /openapi.json` 为准——路由变动时先查它，勿依赖手抄表格。

---

## 11. 延伸文档索引

| 文档 | 路径 | 说明 |
|---|---|---|
| PDF 技术文档 | `SpeakPal_技术文档.pdf` | 根目录交付版 |
| Markdown 技术文档 | `docs/技术文档.md` | 与 PDF 同源的完整版 |
| 系统设计与契约基线 | `docs/design.md` | **口径来源**，与技术文档冲突时以此为准 |
| 评分量表与规则融合规范 | `docs/rubric-band.md` | 量表、锚点与校准记录 |
| 离线验证与统计方法论 | `docs/validation.md` | 数据采集规范与统计口径 |
| 手动验收走查指南 | `docs/manual-walkthrough.md` | 评委逐项验收清单 |
| 校赛答辩演示脚本 | `docs/demo-script.md` | 答辩现场操作核对表、演示数据与意外兜底 |
| 视觉规范 / 品牌资产 | `docs/ui-visual.md` / `docs/logo.md` | 配色、组件类、Logo 用法 |

---

*本文档基于仓库当前实现编写。代码改动后，涉及接口、字段、默认值与评分口径的章节需同步更新；口径冲突时以 `docs/design.md` 与代码为准。*
