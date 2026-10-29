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
- 账号、密码；注册时多一个昵称；字段带标签，Enter 提交
- 登录 / 注册 切换
- 错误提示（账号已存在、密码错误）
- 登录成功 → 存 token → 跳首页
- **token 过期回跳**：`client.js` 遇 401 跳 `/login?expired=1&next=<原路径>`；`next` 只接受 `/` 开头、排除 `//` 与 `/login`（防开放重定向），登录成功后优先回 `next`
- **被踢要说原因**：改密码导致 `token_version` 失效时，401 响应带原因码，前端拦截器把 `?reason=password_changed` 带到登录页并显示「密码已修改，请重新登录」，
  不再一律显示「登录状态已过期」——用户分不清是自己掉线还是账号在别的设备被改。

### Home 首页 / 场景选择（需登录）
- 顶部：昵称 + 退出登录
- 6 张场景卡（图标、场景名、一句描述）：求职面试 `job_interview` / 咖啡店点单 `cafe_order` / 雅思 Part 1 `ielts_part1` / 酒店入住 `hotel_checkin` / 机场值机 `airport_checkin` / 餐厅点餐 `restaurant_order`
- 难度选择（简单 / 中等 / 困难）
- 开始按钮
- 「历史记录」入口

### Practice 练习页（需登录）
- 路由 `/practice/:id`，会话 id 在地址栏里——刷新不丢，能从历史「继续练习」回到同一场
- 顶部：场景名 + 当前轮次（如 2/4）；难度显示中文（简单/中等/困难），不显示 `medium` 这种原值
- 进页面用 `GET /api/sessions/{id}` 回填历史对话与 `status`：`finished` 的会话直接给报告入口，不再让人往里说
- 对话区：AI 气泡在左、用户气泡在右，逐条出现
- 麦克风按钮：点击开始录音，实时显示转写文字；再点结束。识别结果先进**输入条**确认再发送，失败给中文文案（如「没有麦克风权限」），不裸露 `not-allowed` 这类英文码
- 手动输入：切到「手动输入」后，用**页面内的输入条**提交。交互约定：自动聚焦、Enter 发送、Shift+Enter 换行、Esc 收起并保留草稿（另给清空草稿）。
  **禁止用 `window.prompt` / `alert` / `confirm`**——浏览器弹窗会打断对话流，看起来也很突兀（`Practice.vue:111` 原来就是 `window.prompt`，已改掉）
- 无可用模型密钥时，点「开始练习」或「发送」都会被拦下并引导到 `/settings`（见 §13.1），不进入一段注定 mock 的对话
- 每句 AI 气泡带「播放」按钮（speechSynthesis）
- 底部：只有一个「结束并生成报告」
- **作答方式要分开记**：每轮存 `input_mode`（`voice` / `typed`）。前端能显式传就传，不传则后端按「有没有 audio_json」推断（`sessions.py:107-109`）。
  录音轮和打字轮在报告里算不同维度，气泡上也应标出「打字 / 录音」，别让人分不清自己哪句是说的。入口

### Report 复盘页（需登录）
- 综合分大数字（衬线、等宽，切报告时不抖），旁边是「B1 · 雅思 5.5」这类档位文字；**分数不配红绿灯**，红绿只给错误/成功
- 4 个维度：分数 + 各自 band
- 逐句纠错列表：原句 → 更地道说法 → 原因（中文原因，英文原句与改写保持英文）；无改写的不显示删除线
- 「评分依据（可复现）」默认收起，展开看每维模型分/规则分/最终分/钳制原因/输入特征
- 降级报告用琥珀横幅（不是红色——那不是用户做错），按 `mock_reason` 分文案：「未配置/兜底密钥失效」给「去设置」，「服务不可用」只提示稍后重试
- 直接输地址进未完成会话时给「这次练习还没有报告 + 重新练一次」，不显示「加载报告失败」
- 维度集合**随作答方式变化**，不是固定 4 个：有录音轮才出现「发音 / 流利度」，有打字轮才出现 **`written_expression`（文字表达）**。
  纯打字只有 3 维、纯录音 4 维、混合 5 维；模型多给了也会被后端丢掉（`rules.py:343-347`）。
- 综合分 = **按作答模式加权**（`evaluation/bands.py:33-52` 的 `DIMENSION_WEIGHTS`，由 `rules.py:414-415` 调用）：纯录音 20/20/30/30、纯打字 35/35/30、混合 15/15/20/25/25。
  缺失维度按剩余权重重新归一，不当作 0 分；认不出模式时才退回等权（`bands.py:75-91`）。
  同模式内的总分可比，**跨模式的 `total_score` 仍不可直接连线**——权重不同。
  报告顶部写明作答方式（纯打字：「发音 / 流利度未计入」；混合：录音 N 轮、打字 M 轮各算哪一维）。
- 一句总评
- 按钮：再来一次 / 导出 PDF / 返回首页

### History 历史页（需登录）
- 只显示当前用户的记录
- 列表：时间、场景、综合分（降级报告显示「—」，不显示 0）
- **按 `status` / `report_id` 分支，不做 404 试探**（`HistoryItem` 里这两个字段就是为它加的）：
  `report_id` 非空 → 报告页（降级报告也能看）；`status=active` → `/practice/{id}` 接着练；只有「已完成却没有报告」这种罕见情况才落报告页的空报告说明。
- 卡片右侧相应显示「进行中」药丸 +「继续练习」/ 衬线综合分 +「看报告」。**未出分 / 降级 / 未完成的会话都必须能点开**——点不开等于用户看不到自己那次练习；`History.vue:21` 原来只给有分的会话绑跳转，是 bug。

### Settings 设置页（需登录）

两块（「数据存储位置」已按用户要求从网页移除，见 §13.3）：

- **模型密钥**：输入 → 「测试连接」→ 成功显示脱敏结果（只露后四位）→ 可删除本地密钥。key 只存 localStorage，不落库、不打日志。
- **个人资料**：改昵称、改密码。改密码必须填**当前密码**（服务端会校验，`account.py:44-49`），不填或填错返 400——防的是别人借你电脑直接改密。
  接口 `PATCH /api/me/profile`，`{nickname?, password?, current_password?}`，两项都不给返 400；昵称 ≤32 字、密码 4–64 位（`schemas.py:ProfileUpdateIn`）。
  只改昵称不必带密码；**改密码会让其他设备掉线**：`token_version` +1，旧 token 立刻 401，当前设备用响应里新签发的 `token` 续命（前端要 `auth.setAuth` 存回去），见 §14。
  **不要在界面上写「不影响其他设备」之类的小字**——行为相反，留着就是错。
- **我的数据**：清除练习记录（手打「删除」）；注销账号（手打「注销」，账号与全部记录一起删，不可恢复）。

首次登录若本浏览器与服务端都没有密钥，会引导到 `/settings?onboarding=1`，但**可以跳过**；真正拦住的是开始练习时（§13.1）。

## 6. 接口设计

所有接口前缀 `/api`，返回 JSON。

| 方法 | 路径 | 说明 | 需登录 |
|---|---|---|---|
| POST | /api/auth/register | 注册 | 否 |
| POST | /api/auth/login | 登录 | 否 |
| GET | /api/auth/me | 当前用户 | 是 |
| GET | /api/scenes | 场景列表 | 是 |
| POST | /api/sessions | 开始会话 | 是 |
| POST | /api/sessions/{id}/turn | 用户作答一轮（body 可带 `input_mode: voice|typed`，见 §5） | 是 |
| POST | /api/sessions/{id}/finish | 结束并生成报告 | 是 |
| GET | /api/sessions/{id} | 单个会话完整对话，用于刷新/回填；每轮带 `input_mode`（见 §5） | 是 |
| GET | /api/sessions | 历史会话列表（当前用户，带 `status` / `report_id` / `band` / `cefr` / `comparable_band` / `answer_mode` / `voice_turns` / `typed_turns`） | 是 |
| GET | /api/sessions/{id}/report | 读取某次报告（带 `answer_mode` / `comparable_band`） | 是 |
| POST | /api/stt | （可选）后端兜底转写 | 是 |
| GET | /api/sessions/{id}/drills | 跟读重说队列：报告里每条改写 → 目标句 + 通过阈值（0.85） | 是 |
| POST | /api/sessions/{id}/drills/{index}/attempt | 提交一次跟读（转写），回相似度与是否通过 | 是 |
| GET | /api/scenes/{id}/frames | 句型脚手架（`cafe_order` 3 条等） | 是 |
| GET | /api/pronunciation/minimal-pairs | 最小对立对题组（`sets`，两组各 10 对） | 是 |
| POST | /api/pronunciation/check | 判一次最小对立对（`correct` / `partner_heard` / `reason`） | 是 |
| GET | /api/me/recommendation | 按最近报告给的难度建议 | 是 |
| POST | /api/config/llm/test | 验证用户自带 API key（见 §13） | 是 |
| GET | /api/config/llm | 服务端兜底 key 是否配置（不回显 key） | 是 |
| GET | /api/system/storage | 数据目录/库文件/可写性（运维用，网页不展示，见 §13.3） | 是 |
| PATCH | /api/me/profile | 改昵称 / 密码（改密码要带 `current_password`，见 §5 设置页） | 是 |
| DELETE | /api/me/data | 清除自己的练习记录（只接受 `scope=records`，见 §13.2） | 是 |
| DELETE | /api/me/account | 注销账号：删记录 + 删用户，`confirm="注销"`（见 §13.2） | 是 |
| DELETE | /api/admin/data | 清空全库（ADMIN_KEY，`confirm="删除"`，`scope=account` 连用户） | 否（管理密钥） |
| PUT | /api/admin/storage | 改数据目录，重启生效（运维用，网页不展示） | 否（管理密钥） |
| PATCH | /api/admin/users/{id} | 改某用户的昵称 / 密码（ADMIN_KEY） | 否（管理密钥） |
| DELETE | /api/admin/users/{id} | 删某用户及其全部练习数据（ADMIN_KEY） | 否（管理密钥） |

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
users(id, username UNIQUE, password_hash, nickname, created_at, token_version)  -- token_version: 改密码即 +1，见 §14
sessions(id, user_id, scene_id, difficulty, status, created_at)                   -- status: active | finished
turns(id, session_id, role, content, audio_json, input_mode, created_at)         -- role: ai | user；input_mode: voice | typed
reports(id, session_id, total_score, band, cefr, bands_json, dimensions_json,
        fixes_json, comment, source, mock_reason, scoring_json,
        answer_mode, comparable_band, created_at)                        -- answer_mode: voice | typed | mixed
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

状态：后端已落地（`4e78966` 密钥层、`7592fc5` 数据位置 + 清数据/注销）；前端除「数据存储位置」那块外已在 `86fc0bd` / `4b344ff` 落地，该块按用户 11:32 要求移除。
本节按「代码优先」定稿过一轮：key 与管理密钥都走请求头，迁移参数是 `{path, copy_existing}`，原因字段是 `error_kind` / `mock_reason`。

### 13.1 用户自带 API key

- 存储位置：**只存浏览器 localStorage**，随请求走 `X-LLM-Key`（另有 `X-LLM-Base-URL` / `X-LLM-Model`）头；后端 `settings.llm_api_key` 为兜底，优先级「浏览器 > `.env`」。
- key 只走请求头，**不进 body**：放 body 就多一份可能被访问日志记下的明文。
- 不写 `.env`、不入库、不打日志。验证接口不回显 key。
- 前端已用 `allow_headers=["*"]`（`backend/app/main.py:58`），自定义头不会触发 CORS 预检失败，无需额外放行。
- 登录后进 `/settings` 引导页，**必须可跳过**：评委没有 key 不能卡在配置页。
- **但跳过不等于可以免 key 开练**（用户已确认）：浏览器与 `.env` 都没有可用 key 时，**`POST /api/sessions` 和 `POST /api/sessions/{id}/turn`**
  返回 `409 {"kind": "llm_not_configured", "detail": "还没有接入模型密钥"}`，由前端引导到 `/settings`（前端 `ab505f0` 起读 `kind`，不看 `detail`）。
  `llm_key_required`、`key_required` 两个字面值作废，验收只认 `kind=llm_not_configured`。
  **不能用 401**——前端 `client.js` 拦截器把任何 401 当登录失效并清 token 跳登录页。
- **门禁的交互定稿（本轮）**：本浏览器没填 key 时，点场景**不出弹窗**，在场景列表上方展开页内面板「去设置填密钥 / 取消」；
  只有 `GET /api/config/llm` 返回 `env_configured=true` 时，面板才多一个「用服务端密钥继续（演示）」。
  没有兜底 key 就必须填，连「演练一下」都进不去——这是用户明确要的，别为了好走演示而放宽。
- 失败分类（定稿口径），**不是所有失败都降级成示例报告**：

  | 情形 | 返回 | 界面 |
  |---|---|---|
  | 用户请求头里的 key 被拒（401/403） | **502** `{"kind": "key_invalid"}`，不生成报告、会话保持 active，换 key 可重试；**这一轮用户发言也不落库**（模型调用成功后才写 `turns`），重试不会出现两条一样的发言 | 「key 无效，去设置里换」+ 重试 |
  | `.env` 兜底密钥失效（请求头没带 key） | 200 + `source=mock` + `mock_reason=invalid_key` | 「服务端密钥失效，本次不计分」 |
  | 超时 / 不可达 / 返回无法解析 | 200 + `source=mock` + `mock_reason=unavailable` | 「模型服务暂时不可用，稍后重试」 |
  | 会话中途失去全部 key 再 finish | 200 + `source=mock` + `mock_reason=not_configured` | 「本次未接入模型，示例报告不计分」 |

- `mock_reason` 保留三个值，但 `invalid_key` 只代表**服务端 `.env` 兜底密钥失效**（运维问题），不代表用户 key 无效——
  用户 key 是 502 且不产生报告。这两件事别混，验收也不能拿 `invalid_key` 当用户 key 的证据。
- **`finish` 不拦**：练习已经做完，用户中途把 key 删了，也应该拿到一份 `not_configured` 的示例报告。
  拦截点只有「建会话」和「每轮对话」（`create_session` / `add_turn`）。这是预期行为，不是 bug，别改。

`GET /api/config/llm`（登录）→ `{"env_configured": true, "default_base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"}`
——前端用它判断服务端有没有兜底 key，**不回显 key 本身**。

`POST /api/config/llm/test`（登录，key 取自 `X-LLM-Key` 头）→ `{"ok": true, "model": "deepseek-chat", "latency_ms": 812}`；
失败 `{"ok": false, "error_kind": "invalid_key" | "timeout" | "unreachable", "error": "..."}`。

> 两个字段别混：`error_kind` 属测试接口（`invalid_key` / `timeout` / `unreachable`，设置页 `Settings.vue:95` 按它出文案），
> `mock_reason` 属报告（`invalid_key` / `unavailable` / `not_configured`）。同名不同义：前者=「你填的 key 不行」，后者=「服务端兜底 key 不行」。

### 13.2 清除数据

| 接口 | 权限 | 范围 |
|---|---|---|
| `DELETE /api/me/data` | 登录用户 | 只删自己 `user_id` 的 sessions / turns / reports（只接受 `scope=records`） |
| `DELETE /api/me/account` | 登录用户 | 删记录 + 删 `users` 行，注销账号 |
| `DELETE /api/admin/data` | `X-Admin-Key` 头（错密钥 → **403**） | 清全库，演示前重置用；`scope=account` 连 `users` 一起清空 |
| `DELETE /api/admin/users/{id}` | 同上 | 管理员删单个用户及其全部练习数据 |
| `PATCH /api/admin/users/{id}` | 同上 | 管理员改单个用户的昵称 / 密码（不需要旧密码） |

- `/api/me/data` 响应：`{"deleted_sessions": 3, "deleted_turns": 12, "deleted_reports": 3, "deleted_account": 0, "scope": "records"}`。
  传 `scope=account` 要回 **400** 并指向 `/api/me/account`——**注销只有一个入口**，不要两条路各做一套。
- `/api/admin/data`：body `{"confirm": "删除", "scope": "records" | "account"}`，`confirm` 不对返 400；`scope=account` 会连 `users` 一起删
  （响应 `{deleted_users, deleted_sessions, deleted_turns, deleted_reports, scope}`）。**删行不删 `.db` 文件**：engine 握着旧文件，删文件会让新连接建出空库、表都没有。
  用户要求「本次清空所有用户数据」时用这个接口的 `scope=account`，或直接删库文件后让后端重建，别手改表。
- `/api/admin/users/{id}`：`PATCH` body `{"nickname"?, "password"?}`，两项都没有返 400，返回 `{id, username, nickname, password_changed}`；
  `DELETE` 不存在返 404，返回 `{deleted_account, deleted_sessions, deleted_turns, deleted_reports, user_id}`。两个都是不可逆操作，前端不做二次确认就别接。
- 账号注销（用户已确认）：`DELETE /api/me/account`，body `{"confirm": "注销"}`。
  服务端校验 `confirm == "注销"`（`account.py:68`），不符返 400——**「删除」也放行的那版已收紧（`5fdbbdd`），现在只认「注销」**。
  删完后 `users` 行没了，该用户旧 token 一律 401。级联顺序：报告 → 对话轮次 → 会话 → 用户，同一事务提交，不留孤儿行。
- 管理密钥走 `X-Admin-Key` 头（FastAPI 由 `x_admin_key` 形参映射到该头），不塞进请求体。
- **管理端点错密钥返 403，不是 401**：`/admin/storage`、`/admin/data` 用 `require_admin_ui`（`admin.py:29-36`）。
  理由和 key 那边同一条——前端拦截器把 401 当登录失效，输错管理密钥不该把人踢回登录页。
  旧的 `/admin/stats`、`/admin/users`、`/admin/sessions` 仍用 `require_admin`（`admin.py:23-25`，401），两者别混。
- 两个确认词别串：清记录是「删除」（`Settings.vue:112`，也用于 `/admin/data`），注销是「注销」（`Settings.vue:158`）。
- 注销不可恢复，前端二次确认要显示账号名与影响范围（`Settings.vue:320` 已做）。

### 13.3 数据位置：显示与更改（**网页不再提供**，仅运维用）

- 用户 11:32 要求：**前端删除「数据存储位置」界面**（`Settings.vue` 里显示路径/大小/迁移的那块），网页不该暴露服务器目录。
  后端接口保留，只给命令行/管理用途；不要因为前端删了就把下面的契约当成作废。
- 如果后续决定连后端接口一起去掉，说一声，届时删这一节与 §6 表里两行，别留半套。

`GET /api/system/storage`（登录即可，方便排错）→
```json
{"path": "D:\\...\\backend\\speakpal.db", "exists": true, "size_bytes": 61440, "writable": true}
```

`PUT /api/admin/storage`（`X-Admin-Key` 头，错密钥返 **403**）req `{"path": "D:\\data\\speakpal", "copy_existing": true}` → `{"path": "D:\\data\\speakpal\\speakpal.db", "copied_bytes": 61440, "restart_required": true}`。

- 403 不是 401：前端拦截器把 401 当登录失效，管理密钥输错不该把用户踢回登录页（与 `key_invalid` 用 502 同一个道理）。
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

1. **用户 key**：用错 key 跑 `finish` 必须 **502 `key_invalid`**、不生成报告、会话保持 active（换好 key 能重试）；`grep` 响应体、日志、DB 三处都搜不到 key 明文；**不能用 401**（前端会当成掉登录）。
   `mock_reason` 三个值各自对应一条路：`invalid_key`=服务端 `.env` 兜底密钥失效（请求头不带 key 时才会出现），`unavailable`=超时/不可达/解析失败，`not_configured`=中途丢 key 后 finish。用户 key 无效是 502、**不产生任何 `mock_reason`**。
   无密钥时 `POST /api/sessions` 与 `/turn` 必须 409 `kind=llm_not_configured`；`finish` **不拦**，拿到的应是 `not_configured` 示例报告——这是预期，别报成 bug。
2. **清数据与注销**：`/api/me/data` 只清 records 时 A 的 sessions/turns/reports 归零、**B 不受影响**、三个 `deleted_*` 与实际一致、旧 token 仍有效（账号还在）；传 `scope=account` 必须 400。
   注销单独验 `/api/me/account`：`confirm` 缺省、或值为「删除」，都必须 400（只认「注销」）；正确后 `users` 行没了、旧 token 立即 401、再登录失败、其 sessions/reports 全无。
3. **管理密钥**：`DELETE /api/admin/data`、`PUT /api/admin/storage` 用错 `X-Admin-Key` 必须 **403**；缺 header 也是 403。这两条要单独断言，因为前端把 401 当登录失效。
4. **数据位置**：设了真实 `DATABASE_URL` 时 `PUT` 返回 `409 env_override` 且不写 json；管理密钥错时必须是 **403**（不是 401，否则前端会把人踢回登录页）→ 清掉 env 后改路径、重启生效 → 旧库原位没被删 → 目标目录不存在/不可写时报错且配置没被写坏；`data_location.json` 不在 `git ls-files` 里。


## 14. token_version：改密码即踢其他设备（v0.4）

- `users` 加 `token_version`（默认 0），JWT 里带 `tv`（`security.py:36-43`）。校验时 `token.tv != user.token_version` 直接 401，文案「密码已修改，请重新登录」（`security.py:60-67`）。
- 改密码：`token_version += 1`，**同一响应里返回新签发的 `token`**（`account.py:55-64`）。当前设备把它存回去继续用，其他设备的旧 token 立刻失效——这就是「其他设备掉线」的实现方式。
- 管理员 `PATCH /api/admin/users/{id}` 改密码同样 `+1`（`admin.py:231`），所以管理员重置密码后，该用户所有设备都要重新登录，属预期。
- 只改昵称不动 `token_version`，不登出。
- 旧库启动时补列（`main.py:51-54`）；旧 token 没有 `tv` 时按 0 处理，不会把所有老用户一并踢下线。

## 15. 打字报告 vs 录音报告：能不能比（v0.4 定稿）

- 维度数随作答方式变（纯打字 3 / 纯录音 4 / 混合 5），综合分**按模式加权**，不是等权（权重表见 §5 报告页与 `evaluation/bands.py:33-52`）。
- 跨模式比较一律用 `comparable_band`：只取两种作答都会评的共享维度（`grammar_vocab` + `task_completion`）求平均再换 band（`bands.py:94-103`，`rules.py:426` 起写库）。
  报告与历史接口都带这个字段；**成长曲线纵轴用它，且全部会话都画**（本轮定稿推翻「只画录音」），打字会话用空心点区分、行内标 `answer_mode`。
- `written_expression` 没有规则分，权重 0 : 1（只有模型判断，`rules.py:394-402`）；它的 CEFR/雅思锚点仍待补，别在别处另造一套评分。
