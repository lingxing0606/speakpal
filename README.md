# SpeakPal · 可验证的 AI 英语口语诊断陪练

校赛作品。用户注册登录后，选一个真实场景和 AI 角色多轮语音对话，结束后拿到发音、流利度、表达、任务完成度的评分，以及逐句「更地道说法」的纠错报告。

本版本强调“可验证”：系统评分不是自说自话，而是有 `evaluation/` 的人评一致性验证层，用 ICC / kappa / Bland-Altman 等指标与人评金标准对齐。

技术栈：Vue3 + Vite + Tailwind（前端）/ FastAPI + SQLite + JWT（后端）/ 大模型 API（可 mock）/ 纯标准库一致性统计。

## 目录结构

```
.
├── backend/            # FastAPI 后端
│   ├── app/
│   ├── requirements.txt
│   ├── .env            # 本地配置（JWT、数据库、大模型 key）
│   └── .venv/          # Python 虚拟环境
├── frontend/           # Vue3 前端
│   ├── src/
│   ├── package.json
│   ├── node_modules/
│   └── dist/           # 已构建产物
├── evaluation/         # 评估与验证（人评一致性统计、特征提取）
├── tools/node/         # 便携版 Node（免系统安装）
├── docs/
│   ├── design.md       # 设计文档
│   └── validation.md   # 评估与验证说明
├── start-all.bat       # 双击一键启动（推荐）
├── start-backend.bat
├── start-frontend.bat
├── start-backend.ps1
├── start-frontend.ps1
└── setup.ps1
```

## 快速开始

环境已备好（Python 用系统 D:\python，前端用 tools\node）。**最简单：双击 `start-all.bat`**，它会启动前后端并打开浏览器。

也可以手动启动（两个 PowerShell 窗口）：

1. 启动后端：

```powershell
.\start-backend.ps1
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。接口文档：<http://127.0.0.1:8000/docs>

2. 启动前端：

```powershell
.\start-frontend.ps1
```

浏览器打开 <http://127.0.0.1:5173>，用 Chrome（语音识别只支持 Chrome）。

如果依赖缺失或环境损坏，运行 `.\setup.ps1` 重装。

## 配置大模型

编辑 `backend/.env`：

```
LLM_API_KEY=你的key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

留空 `LLM_API_KEY` 时，后端使用内置 mock 回复，方便先跑通流程。

## 功能

- 注册 / 登录（账号密码 + JWT）
- 3 个场景：求职面试 / 咖啡店点单 / 雅思 Part 1
- 语音录入转写（Web Speech API）+ AI 语音朗读
- 多轮对话 + 追问
- 评分卡（综合 + 4 维）
- 逐句纠错报告
- 按用户隔离的历史记录

## 评分说明

分数由大模型按 rubric 估算，发音维度基于转写文本推断，报告中已标注「AI 估算」，不是专业声学测评。

## 评估与验证（“可验证”的落点）

`evaluation/` 是一个纯标准库的验证层，回答“这个分准不准”：

- `agreement.py`：ICC(2,1) / ICC(2,k)、Cohen / Fleiss kappa、Pearson / Spearman、Bland-Altman、MAE / RMSE。
- `features.py`：从转写（可选词级时间戳）提取流利度与词汇多样性特征。
- `validate.py`：读 CSV，算出人评内部一致性和系统分与人评的一致性。

```powershell
python -m evaluation.make_demo
python -m evaluation.validate --csv evaluation/demo_data.csv --raters human1,human2 --system system --bands human1_band,human2_band
```

注意：`demo_data.csv` 是合成数据，只演示脚本；真实结论必须来自真人评分。详见 [docs/validation.md](docs/validation.md)。

## 校赛演示脚本

1. 登录 → 体现有用户体系。
2. 选「求职面试」，AI 开口问 Tell me about yourself。
3. 对着麦克风答一段，AI 追问。
4. 点「结束并出报告」，展示综合分、4 个维度、逐句改写。
5. 收尾：流程可复用到雅思、旅行、商务谈判等场景。
