# SpeakPal · 场景化 AI 英语口语陪练 — 设计文档 v0.2

> 单人参赛 / 校赛 / Vue3 + FastAPI / 可调用大模型 API
> v0.2 更新：加入注册/登录与用户体系

## 1. 一句话定位

用户注册登录后，选一个真实场景，和 AI 角色多轮语音对话，结束后拿到发音、流利度、表达、任务完成度的评分，以及逐句「更地道说法」的纠错报告。

目标用户：准备求职面试、出国旅游/留学、想练日常口语的大学生。

## 2. 核心闭环

注册/登录 → 选场景 → AI 语音开场提问 → 用户语音作答（转写为文字）→ AI 追问 2–3 轮 → 结束 → 生成复盘报告（按用户保存）。

## 3. 功能范围

### MVP（必须做）
- 注册 / 登录（账号 + 密码 + JWT），每个用户独立历史
- 3 个场景：求职面试 / 咖啡店点单 / 雅思 Part 1
- 语音录入 + 转写（Web Speech API）
- 多轮对话 + 追问
- 评分卡（综合分 + 4 个维度分）
- 逐句纠错报告
- 历史记录

### 加分项（有时间再做）
- AI 语音开口（浏览器 speechSynthesis）
- 成长曲线
- 报告导出 PDF
- 录音回放
- 头像 / 昵称

### 明确不做
- 双向实时语音流式对话
- 第三方 OAuth、手机验证码（除非校赛明确要求）
- 波形级精确发音分析

## 4. 项目结构

```
speakpal/
├── frontend/                     # Vue3 + Vite
│   ├── src/
│   │   ├── main.js
│   │   ├── App.vue
│   │   ├── router/index.js        # 含登录路由守卫
│   │   ├── api/client.js          # axios 封装（自动带 token）
│   │   ├── stores/
│   │   │   ├── auth.js            # 登录态 / token
│   │   │   └── session.js         # 当前对话/评分
│   │   ├── views/
│   │   │   ├── Login.vue          # 登录 / 注册
│   │   │   ├── Home.vue           # 场景选择
│   │   │   ├── Practice.vue       # 对话练习页
│   │   │   ├── Report.vue         # 复盘报告
│   │   │   └── History.vue        # 历史记录
│   │   ├── components/
│   │   │   ├── SceneCard.vue
│   │   │   ├── ChatBubble.vue
│   │   │   ├── MicButton.vue      # 录音 + 转写
│   │   │   ├── ScoreCard.vue
│   │   │   └── SentenceFix.vue
│   │   └── utils/speech.js        # Web Speech API 封装
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── package.json
├── backend/                      # FastAPI
│   ├── app/
│   │   ├── main.py                # 入口 + 路由注册
│   │   ├── config.py              # 读环境变量
│   │   ├── db.py                  # SQLite + SQLAlchemy
│   │   ├── models.py              # ORM（User/Session/Turn/Report）
│   │   ├── schemas.py             # Pydantic
│   │   ├── security.py            # 密码哈希 + JWT + 当前用户依赖
│   │   ├── services/
│   │   │   ├── llm.py             # LLM 调用封装
│   │   │   ├── scoring.py         # rubric 评分
│   │   │   └── scenes.py          # 场景配置
│   │   └── routers/
│   │       ├── auth.py            # 注册/登录/当前用户
│   │       ├── scenes.py
│   │       ├── sessions.py
│   │       └── reports.py
│   ├── requirements.txt
│   └── .env.example
├── docs/
│   └── design.md
└── README.md
```

## 5. 页面设计

### Login 登录 / 注册页
- 账号、密码；注册时多一个昵称
- 登录 / 注册 切换
- 错误提示（账号已存在、密码错误）
- 登录成功 → 存 token → 跳首页

### Home 首页 / 场景选择（需登录）
- 顶部：昵称 + 退出登录
- 3 张场景卡（图标、场景名、一句描述）
- 难度选择（简单 / 中等 / 困难）
- 开始按钮
- 「历史记录」入口

### Practice 练习页（需登录）
- 顶部：场景名 + 当前轮次（如 2/4）
- 对话区：AI 气泡在左、用户气泡在右，逐条出现
- 麦克风按钮：点击开始录音，实时显示转写文字；再点结束
- 每句 AI 气泡带「播放」按钮（speechSynthesis）
- 底部：结束并生成报告

### Report 复盘页（需登录）
- 综合分大数字
- 4 个维度条形图/雷达图
- 逐句纠错列表：原句 → 更地道说法 → 原因
- 一句总评
- 按钮：再来一次 / 导出 PDF / 返回首页

### History 历史页（需登录）
- 只显示当前用户的记录
- 列表：时间、场景、综合分
- 点击进入该次报告

## 6. 接口设计

所有接口前缀 `/api`，返回 JSON。

| 方法 | 路径 | 说明 | 需登录 |
|---|---|---|---|
| POST | /api/auth/register | 注册 | 否 |
| POST | /api/auth/login | 登录 | 否 |
| GET | /api/auth/me | 当前用户 | 是 |
| GET | /api/scenes | 场景列表 | 是 |
| POST | /api/sessions | 开始会话 | 是 |
| POST | /api/sessions/{id}/turn | 用户作答一轮 | 是 |
| POST | /api/sessions/{id}/finish | 结束并生成报告 | 是 |
| GET | /api/sessions | 历史会话列表（当前用户） | 是 |
| GET | /api/sessions/{id}/report | 读取某次报告 | 是 |
| POST | /api/stt | （可选）后端兜底转写 | 是 |
| POST | /api/config/llm/test | 验证用户自带 API key（见 §13） | 是 |
| GET | /api/config/llm | 服务端兜底 key 是否配置（不回显 key） | 是 |
| GET | /api/system/storage | 数据目录/库文件/可写性（见 §13.3） | 是 |
| DELETE | /api/me/data | 清除自己的练习记录（见 §13.2） | 是 |
| DELETE | /api/admin/data | 清空全库（ADMIN_KEY） | 否（管理密钥） |
| PUT | /api/admin/storage | 改数据目录，重启生效（ADMIN_KEY） | 否（管理密钥） |

除 `/api/auth/register`、`/api/auth/login` 外，其余接口都要带 `Authorization: Bearer <token>`，并按 token 里的 user_id 隔离数据。

### 请求/响应示例

`POST /api/auth/register`
```json
// req
{"username": "alice", "password": "123456", "nickname": "小A"}
// resp
{"token": "eyJ...", "user": {"id": 1, "username": "alice", "nickname": "小A"}}
```

`POST /api/auth/login`
```json
// req
{"username": "alice", "password": "123456"}
// resp
{"token": "eyJ...", "user": {"id": 1, "username": "alice", "nickname": "小A"}}
```

`GET /api/scenes` →
```json
[
  {"id": "job_interview", "name": "求职面试", "icon": "briefcase", "desc": "和 AI 面试官聊一轮自我介绍与项目经历"},
  {"id": "cafe_order", "name": "咖啡店点单", "icon": "coffee", "desc": "点单、加料、结账的日常对话"},
  {"id": "ielts_part1", "name": "雅思 Part 1", "icon": "book", "desc": "雅思口语第一部分常见话题"}
]
```

`POST /api/sessions`
```json
// req
{"scene_id": "job_interview", "difficulty": "medium"}
// resp
{"session_id": "s_001", "opening_question": "Hi, thanks for coming in. Could you tell me a bit about yourself?"}
```

`POST /api/sessions/{id}/turn`
```json
// req
{"transcript": "I am a senior student majoring in computer science..."}
// resp
{"turn_index": 2, "ai_reply": "Nice. What was the most challenging project you worked on?", "is_follow_up": true}
```

`POST /api/sessions/{id}/finish` →
```json
{
  "report_id": "r_001",
  "total_score": 78,
  "dimensions": {
    "pronunciation": 72,
    "fluency": 80,
    "grammar_vocab": 75,
    "task_completion": 85
  },
  "sentence_fixes": [
    {
      "original": "I am very interest in this job.",
      "better": "I'm very interested in this role.",
      "reason": "interest 是名词/动词；这里需要形容词 interested，搭配 in。"
    }
  ],
  "comment": "整体表达清楚，能完成面试任务；建议多用具体项目细节，减少填充词。",
  "note": "分数由 AI 估算，仅供参考。"
}
```

## 7. 数据模型（SQLite）

```
users(id, username UNIQUE, password_hash, nickname, created_at)
sessions(id, user_id, scene_id, difficulty, status, created_at)
turns(id, session_id, role, content, created_at)      -- role: ai | user
reports(id, session_id, total_score, dimensions_json, fixes_json, comment, created_at)
```

## 8. AI 设计

### 8.1 对话（考官/店员）
System prompt 模板：

```
你是 {场景角色}。用户是英语学习者，正在练习口语。
要求：
1. 用简短、口语化的英语提问，每次只问一个问题。
2. 用户回答后，先自然回应一句，再追问一个相关问题。
3. 最多 {max_turns} 轮，语气友好。
4. 不要在对话中纠正语法，纠错留给复盘。
5. 难度={difficulty}：简单用短句常用词；困难用更长、更自然的表达。
```

### 8.2 评分（复盘）
输入整段对话记录，按 rubric 打分，输出严格 JSON：

```
{"total": 0-100,
 "dimensions": {"pronunciation":0-100,"fluency":0-100,"grammar_vocab":0-100,"task_completion":0-100},
 "sentence_fixes": [{"original":"","better":"","reason":""}],
 "comment": "",
 "note": "分数由 AI 估算，仅供参考。"}
```

注意：pronunciation 基于转写文本与表达流畅度估算，标注「AI 估算」，不要宣称精确发音测评。

## 9. 技术栈

- 前端：Vue3 + Vite + Tailwind CSS + Pinia + axios
- 后端：FastAPI + SQLAlchemy + SQLite
- 认证：密码用 passlib[bcrypt] 哈希，令牌用 PyJWT
- AI：一家 LLM API（DeepSeek / 通义 / 文心 / OpenAI 均可）
- 语音：浏览器 Web Speech API（SpeechRecognition 转写 + speechSynthesis 朗读），免 key
- 部署：前端 Vercel/Netlify，后端一台云服务器；或前端打包由 FastAPI 静态托管

## 10. 三周排期

| 周 | 目标 |
|---|---|
| 第 1 周 | 搭架子 + 注册登录（JWT）+ 3 个场景配置 + 语音转写 + AI 对话端到端跑通 |
| 第 2 周 | 评分 rubric + 复盘报告 + 逐句纠错 + 历史记录（按用户） |
| 第 3 周 | UI 打磨 + 场景扩充 + 部署 + 演练答辩 demo |

## 11. 风险与降级

- 浏览器 STT 仅 Chrome 稳定 → 演示固定用 Chrome；后端 STT 做兜底。
- 评分主观 → 明确 rubric + 标「AI 估算」。
- 大模型延迟 → 流式输出 + loading 态 + 超时重试。
- 麦克风权限 → 演示前预授权并彩排。
- 密码安全 → 只存 bcrypt 哈希，绝不存明文；JWT secret 放环境变量。

## 12. 校赛演示脚本（约 30 秒）

1. 登录进入（体现有用户体系，历史能保存）。
2. 选「求职面试」。
3. AI 开口问「Tell me about yourself」，用户对着麦克风答一段。
4. AI 追问一个项目问题，用户再答一句。
5. 点结束，报告页滑出：综合分 + 4 维 + 逐句改写。
6. 收尾一句：这套流程可复用到雅思、旅行、商务谈判等场景。

## 13. 配置与数据管理（v0.3 新增）

三件事：用户自带 API key、清除数据、显示/更改数据位置。三条都不进评分链，可独立实现与验收。

状态：前端已在 `86fc0bd` 落地（`/settings` 三段 + 请求头拦截器 + 可跳过的引导）；后端接口按本节契约实现中。
本节按「代码优先」定稿过一轮：key 与管理密钥都走请求头，迁移参数是 `{path, copy_existing}`，原因字段是 `error_kind` / `mock_reason`。

### 13.1 用户自带 API key

- 存储位置：**只存浏览器 localStorage**，随请求走 `X-LLM-Key`（另有 `X-LLM-Base-URL` / `X-LLM-Model`）头；后端 `settings.llm_api_key` 为兜底，优先级「浏览器 > `.env`」。
- key 只走请求头，**不进 body**：放 body 就多一份可能被访问日志记下的明文。
- 不写 `.env`、不入库、不打日志。验证接口不回显 key。
- 前端已用 `allow_headers=["*"]`（`backend/app/main.py:58`），自定义头不会触发 CORS 预检失败，无需额外放行。
- 登录后进 `/settings` 引导页，**必须可跳过**：评委没有 key 不能卡在配置页（跳过后走服务端兜底 key，再没有就走示例报告）。
- 三种失败必须在界面上分开，不能都变成「示例报告」。`finish` 仍返回 200 + `source=mock`，但必须带原因字段，前端据此分文案：

  | 情形 | `finish` 返回 | 界面 |
  |---|---|---|
  | 用户配了 key 且校验失败（401/403） | `source=mock`、`mock_reason=invalid_key` | 「key 无效，去设置里换」——**不许显示成普通的「模型不可用」** |
  | key 有效但超时 / 服务不可用 | `source=mock`、`mock_reason=unavailable` | 「模型服务暂时不可用，稍后重试」 |
  | 未配置任何 key | `source=mock`、`mock_reason=not_configured` | 「去配置 key」 |

`GET /api/config/llm`（登录）→ `{"env_configured": true, "default_base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"}`
——前端用它判断服务端有没有兜底 key，**不回显 key 本身**。

`POST /api/config/llm/test`（登录，key 取自 `X-LLM-Key` 头）→ `{"ok": true, "model": "deepseek-chat", "latency_ms": 812}`；
失败 `{"ok": false, "error_kind": "invalid_key" | "timeout" | "unreachable", "error": "..."}`。

### 13.2 清除数据

| 接口 | 权限 | 范围 |
|---|---|---|
| `DELETE /api/me/data` | 登录用户 | 只删自己 `user_id` 的 sessions / turns / reports |
| `DELETE /api/admin/data` | `X-Admin-Key` 头 | 清全库，演示前重置用 |

- 响应：`{"deleted_sessions": 3, "deleted_reports": 3}`。
- 管理密钥走 `X-Admin-Key` 头，直接复用 `admin.py:13` 的 `require_admin`（FastAPI 由 `x_admin_key` 形参映射到该头），不塞进请求体。
- 「连账号一起删」（删 `users` 行、旧 token 401）**尚未实现**：这是不可恢复的破坏性操作，等用户明确点头再做，文档不预先承诺。默认只清记录，账号保留。
- 二次确认的摩擦放在前端：显示影响范围（将删除 N 次练习、M 份报告）+ 手打「删除」才可点；接口本身没有 `confirm` 参数，服务端不校验（别以为后端会拦）。

### 13.3 数据位置：显示与更改

`GET /api/system/storage`（登录即可，方便排错）→
```json
{"path": "D:\\...\\backend\\speakpal.db", "exists": true, "size_bytes": 61440, "writable": true}
```

`PUT /api/admin/storage`（`X-Admin-Key` 头）req `{"path": "D:\\data\\speakpal", "copy_existing": true}` → `{"path": "D:\\data\\speakpal\\speakpal.db", "copied_bytes": 61440, "restart_required": true}`。

- `path` 收目录或 `.db` 文件都行，由后端归一化成库文件路径（不要求前端自己拼）。
- 只写 `backend/data_location.json`，**不热切换**（SQLite engine 在 import 时绑定，`db.py` 建 engine 前就要解析完优先级）。响应固定带 `restart_required: true`。
- 「把现有数据复制过去」是复制不是移动，失败可回滚；旧库原位不删。目标目录不存在或不可写时报错，**不写坏配置**。

**优先级（唯一权威，按此实现）**：

1. 真实进程环境变量 `DATABASE_URL`（部署级覆盖，最高）
2. `backend/data_location.json`
3. `backend/.env` 里的 `DATABASE_URL`
4. 默认 `backend/speakpal.db`

为什么要把 1 和 3 分开：`config.py:5` 在 import 时 `load_dotenv()`，而 `.env.example:3` 写着 `DATABASE_URL=sqlite:///./speakpal.db`。若按「环境变量 > data_location.json」的字面意思实现，`.env` 里这一行会让 `PUT /api/admin/storage` **永远不生效**，界面却提示「重启后生效」——静默失效，而且很难排查。

实现要点：在 `load_dotenv()` **之前**取一份 `os.environ` 快照，只有出现在快照里的 `DATABASE_URL` 才算第 1 级。若第 1 级已生效，`PUT /api/admin/storage` 返回 `409 {"kind": "env_override", "hint": "DATABASE_URL 由环境变量指定，配置文件不会生效"}`，不写 json。

### 13.4 验收（最容易漏的几条）

1. **用户 key**：用错 key 跑 finish，报告必须带 `mock_reason=invalid_key`，界面提示「key 无效」而不是笼统的「模型不可用」；`grep` 响应体、日志、DB 三处都搜不到 key 明文。空 key 是 `not_configured`，超时是 `unavailable`——三者不能合并。
2. **清数据**：A 删完自己的 sessions / reports 归零，**另一个账号的记录不受影响**；`deleted_sessions` / `deleted_reports` 与库内实际删除条数一致。注意「连账号一起删」未实现，所以**不要**断言旧 token 401——账号没删，token 仍有效，前端回登录页靠的是清 localStorage。
3. **数据位置**：设了真实 `DATABASE_URL` 时 `PUT` 返回 `409 env_override` 且不写 json → 清掉 env 后改路径、重启生效 → 旧库原位没被删 → 目标目录不存在/不可写时报错且配置没被写坏；`data_location.json` 不在 `git ls-files` 里。

