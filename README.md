# SpeakPal · 可验证的 AI 英语口语诊断陪练

校赛作品。用户注册登录后，选一个真实场景和 AI 角色多轮语音对话，结束后拿到发音、流利度、语法词汇（语言复杂度）、任务完成度的评分，以及逐句「更地道说法」的纠错报告。

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
│   ├── 技术文档.md     # 完整技术文档（架构/接口/评分/部署，提交用）
│   ├── design.md       # 设计与接口口径（改动先改这里）
│   ├── rubric-band.md  # 评分量表与 CEFR/雅思换算
│   ├── validation.md   # 评估与验证说明
│   ├── demo-script.md  # 5 分钟录屏脚本 + 兜底
│   └── ui-visual.md    # 视觉规范
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

留空 `LLM_API_KEY` 时，后端用内置 mock 回复把对话流程跑通（方便先看界面），但报告会标成「示例报告（模型不可用）· 本次不计分」，**不给分也不给档位**，逐句纠错只列用户真实说过的句子。

## 后端控制台

后端启动后，打开 <http://127.0.0.1:8000/> 就是管理控制台（`/admin` 同页）：

- 用户数、练习会话数、报告数、平均分
- 最近练习记录（用户、场景、状态、得分、时间）
- 接口文档入口：<http://127.0.0.1:8000/docs>

管理密钥：`ADMIN_KEY` 为空或仍是旧默认值 `admin123` 时，后端首次启动会随机生成一个、写回 `backend/.env`，并打印在后端控制台（`[config] ADMIN_KEY ...`）。之后在 `backend/.env` 里查看或修改。`JWT_SECRET` 同理自动生成（不打印）。

## 安全相关配置（`backend/.env`）

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | 跨域白名单，逗号分隔 |
| `ALLOW_PRIVATE_LLM_HOSTS` | `0` | 默认拒绝把模型 / 语音地址指向内网或本机（防 SSRF）；用本机 Ollama 时设 `1` |
| `STORAGE_ROOT` | 空 | 管理台「改数据位置」的目录白名单；留空不限，但始终不覆盖已存在的文件 |

登录同一 IP+账号 5 分钟内失败 5 次会被暂时拒绝（429）。新密码至少 6 位，旧的短密码仍可登录。

## 测试

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -t backend -v
```

测试用 `backend/.tmp-test/` 下的临时库，不碰真实数据，也不访问外网。

## 打包提交

`tools/node/`（便携 Node，约 90MB）、`node_modules/`、`.venv/`、`*.db`、`.env` 都不进仓库。打包作品时同样排除它们，评委机器上运行 `setup.ps1` 会重新安装依赖。

## 功能

- 注册 / 登录（账号密码 + JWT）
- 6 个场景：求职面试 / 咖啡店点单 / 雅思 Part 1 / 酒店入住 / 机场值机 / 餐厅点餐
- 语音录入转写（Web Speech API）+ AI 语音朗读；也可手动打字作答（两种方式分开记分）
- 录音回放：练习页每句录音都能回放，报告页逐句纠错旁可听当时的原声。录音只存在本浏览器（IndexedDB），不上传服务器；保留最近 30 次练习，主动退出或清空数据时一并删除
- 多轮对话 + 追问；AI 回复流式逐字显示（SSE，失败自动回落普通接口）
- 评分卡（综合 + 视作答方式 3–5 维）
- 逐句纠错报告
- 学习数据面板（历史页顶部）：连续打卡、近 12 周热力图、各维度均分雷达、近 7 天档位变化
- 按用户隔离的历史记录；改密码让其他设备掉线

## 评分说明

分数由大模型按雅思 Speaking 描述语打分（0.5 步长），再换算成 0–100 展示分并落到 CEFR 档位（A2–C1）。
其中流利度、语言复杂度、任务完成度会先由可测指标算一个「规则分」（语速、停顿占比、填充词占比、平均句长、从句标记、词汇多样性、场景任务清单），
再与模型分融合；模型分明显高于可测证据时只压不抬。报告页「评分依据（可复现）」逐维显示模型分、规则分、最终分和钳制原因。发音维度没有规则证据，只有模型文本推断。
量表、换算与取整规则见 [docs/rubric-band.md](docs/rubric-band.md)。

**打字和录音分开算**：有录音轮才有「发音 / 流利度」，有打字轮才有「文字表达」；纯打字 3 维、纯录音 4 维、混合 5 维。
综合分**按作答模式加权**（纯录音 20/20/30/30、纯打字 35/35/30、混合 15/15/20/25/25），所以 `total_score` 只在同模式内可比；
跨模式看 `comparable_band`（只用「语言复杂度 + 语用得体性」两个共享维度），报告与历史都会给出。历史成长曲线用它、全部会话都画，打字会话用空心点标出。
发音维度基于转写文本推断，
报告中已标注「AI 估算」，不是专业声学测评。

模型不可用时**不再编造分数**：报告会标成「示例报告（模型不可用）· 本次不计分」，
分数与档位留空，只列出用户真实说过的句子；`original` 字段必须能在用户转写里找到，否则这条改写不会显示。

## 评估与验证（“可验证”的落点）

`evaluation/` 是一个纯标准库的验证层，回答“这个分准不准”：

- `agreement.py`：ICC(2,1) / ICC(2,k)、Cohen / Fleiss kappa、Pearson / Spearman、Bland-Altman、MAE / RMSE。
- `bands.py`：0–100 ↔ 雅思 band ↔ CEFR 的唯一换算入口。
- `features.py`：从转写（可选词级时间戳）提取流利度与词汇多样性特征。
- `validate.py`：读 CSV，算出人评内部一致性和系统分、系统档位与人评的一致性。

```powershell
D:\python\python.exe -m evaluation.make_demo
D:\python\python.exe -m evaluation.validate --csv evaluation/demo_data.csv `
  --raters human1,human2 --system system `
  --bands human1_band,human2_band --system-band system_band
```

注意：`demo_data.csv` 是合成数据，只演示脚本；真实结论必须来自真人评分。详见 [docs/validation.md](docs/validation.md)。

## 校赛演示脚本

1. 登录 → 体现有用户体系。
2. 选「求职面试」，AI 开口问 Tell me about yourself。
3. 对着麦克风答一段，AI 追问。
4. 点「结束并出报告」，展示综合分、4 个维度、逐句改写。
5. 收尾：流程可复用到雅思、旅行、商务谈判等场景。
