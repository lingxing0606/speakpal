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
- **401 的落点按原因分两路（rc15 定稿，别混）**：
  | 原因 | 落点 |
  |---|---|
  | `user_gone`（账号已注销/被管理员删掉） | `/welcome?again=1`——不是报错，是这个人现在没有账号，让他重新开始 |
  | `token_invalid` / `expired` / `password_changed` | `/login?reason=<原因>&next=<原路径>`——账号还在，只是凭证失效，重新登录就能接着练 |
  启动探测遇到 401 也走这张表：探测是「这个 token 还能不能用」，不是登录动作，所以结果要交给上面的映射决定，不能一律丢欢迎页。

### Welcome 新手引导页（**公开页，不需要登录**）

- 三步说明：选场景 → 开口说或打字 → 拿评分与逐句纠错。
- **未登录先落到这里**：`router/index.js:30-32` 把 `/login`、`/welcome` 划为公开页，未登录访问任何其它地址一律回 `/welcome`，
  **不是**直接怼到登录页。所以双击 `start-all.bat` 第一眼是欢迎页——如果还是直接进登录页，是 Vite 缓存了旧模块，`Ctrl+F5` 或重开前端窗口。
- 按钮文案两种：未登录「开始使用（先注册或登录）」→ 跳 `/login`；已登录「开始第一次练习」→ 跳首页并记 `sp_welcomed=当前用户名`。
- 点过按钮才去登录/注册的，**本次浏览不再弹第二遍**：`sessionStorage.sp_intro_seen`（`Welcome.vue:34` → `Login.vue:88-97`），关掉浏览器就失效，不跨会话。
- 「每个账号只看一次」的记号是 `localStorage.sp_welcomed`，存的是**用户名**；已登录且标记等于当前用户名时访问 `/welcome` 会被弹回首页，`?again=1` 一律放行。
  旧版全局标记 `'1'` 没有用户名，**当「未知」放行一次**，让老账号也能补看一遍。
- 再看一遍的三条路：首页「新手引导」、设置页底部「再看一遍新手引导（30 秒）」、地址栏 `/welcome?again=1`。
- 引导页不是密钥门禁的替代：跳过引导 ≠ 能免 key 开练（门禁在点场景/发送时，见 §13.1）。

### Home 首页 / 场景选择（需登录）
- 顶部：昵称 + 退出登录
- 6 张场景卡（图标、场景名、一句描述）：求职面试 `job_interview` / 咖啡店点单 `cafe_order` / 雅思 Part 1 `ielts_part1` / 酒店入住 `hotel_checkin` / 机场值机 `airport_checkin` / 餐厅点餐 `restaurant_order`
- **难度选择已移出首页**（用户要求）：进「设置 → 练习」改，首页不再摆这个控件；练习页顶部只显示当前难度（只读）
- 开始按钮
- **「今天要复习 N 个」卡片**：`N` 来自 `GET /api/study/summary`（**只调一次**，别再分别打 `/study/due` 和 `/notes`）；N=0 时给空状态（不摆一张空卡）。
  文案定稿（新词当天也到期，别说「错过」）：副行「**到期的词，今天过一遍**」；空状态「**练完一次或学几个新词，这里就会有内容**」。
  **取不到时不要静默当 0**：显示「暂时取不到」，否则「后端挂了」和「今天没卡」在界面上一样，用户会以为学习计划空了。点进 `/study`
- 「历史记录」「笔记」入口

### Practice 练习页（需登录）
- 路由 `/practice/:id`，会话 id 在地址栏里——刷新不丢，能从历史「继续练习」回到同一场
- 顶部：场景名 + 当前轮次（如 2/4）；难度显示中文（简单/中等/困难），不显示 `medium` 这种原值
- 进页面用 `GET /api/sessions/{id}` 回填历史对话与 `status`：`finished` 的会话直接给报告入口，不再让人往里说
- 对话区：AI 气泡在左、用户气泡在右，逐条出现
- 麦克风按钮：点击开始录音，实时显示转写文字；再点结束。识别结果先进**输入条**确认再发送，失败给中文文案（如「没有麦克风权限」），不裸露 `not-allowed` 这类英文码
- 手动输入：切到「手动输入」后，用**页面内的输入条**提交。交互约定：自动聚焦、Enter 发送、Shift+Enter 换行、Esc 收起并保留草稿（另给清空草稿）。
  **空着 8 秒没打字**就在输入框**上方**显示「不知道怎么说？试试这些用法：」+ 三条可用句式（数据取 `GET /api/scenes/{id}/frames`），用户一开始打字立刻收起。
  这是提示，不是教学旁白：别写成「点这里可以…」。
  **禁止用 `window.prompt` / `alert` / `confirm`**——浏览器弹窗会打断对话流，看起来也很突兀（`Practice.vue:111` 原来就是 `window.prompt`，已改掉）
- 无可用模型密钥时，点「开始练习」或「发送」都会被拦下并引导到 `/settings`（见 §13.1），不进入一段注定 mock 的对话
- 每句 AI 气泡带「播放」按钮（speechSynthesis）
- 底部：只有一个「结束并生成报告」
- **作答方式要分开记**：每轮存 `input_mode`（`voice` / `typed`）。前端能显式传就传，不传则后端按「有没有 audio_json」推断（`sessions.py:107-109`）。
  录音轮和打字轮在报告里算不同维度，气泡上也应标出「打字 / 录音」，别让人分不清自己哪句是说的。

### Report 复盘页（需登录）
- 综合分大数字（衬线、等宽，切报告时不抖），旁边是「B1 · 雅思 5.5」这类档位文字；**分数不配红绿灯**，红绿只给错误/成功
- 4 个维度：分数 + 各自 band
- 逐句纠错列表：原句 → 更地道说法 → 原因（中文原因，英文原句与改写保持英文）；无改写的不显示删除线
- **每条纠错带错误类型标签**（`error_type`：拼写 / 语法 / 僵硬 / 啰嗦，见 §16.4）和「加入学习清单」；`stiffness` 的卡额外显示 `natural`（更自然的说法 + 为什么）。
  拼写类、僵硬类由后端自动落成学习卡草稿，用户不必手动点；语法/啰嗦类由用户自己决定加不加。
- 「评分依据（可复现）」默认收起，展开看每维模型分/规则分/最终分/钳制原因/输入特征
- **顶卡不要出现「分数由 AI 估算」**：那是降级/mock 的兜底文案。正常报告顶卡显示 `scoring_note`（「分数由模型分与可测指标融合得出」），
  否则同一张卡上「AI 估算」和「模型分与可测指标融合」并存，等于自己打自己。
- **跟读失败要在跟读面板里就地提示**：识别错、相似度不达标，提示出现在按钮下方，不要塞进页面顶部全局错误条——用户正看着面板，顶部提示在视口外，看起来就是「点了没反应」。
- **报告页的 band 要标口径**：顶卡给的是本模式加权档；历史/成长曲线用的是 `comparable_band`（共享两维）。同一场混合会话两个值差 0.5 是正常的，报告页至少要么标「本模式口径」，要么旁白能解释清楚。
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
- 空状态：还没练过时给「去练一次」，不写「暂无数据」。

### Study 学习页（需登录，`/study`）——**四个板块，不是「学习=复习」**

顶部四个 tab，各自只显示自己的内容；从首页对应卡片直接进到对应 tab（`/study?tab=review|new|grammar|speaking`，tab 缺失时默认复习）。

- **复习**：到期队列，一次一张卡。卡分三类：拼写卡（只给中文释义 + 语境，默写判档，不显示 `term`）、单词/句型/口语卡（正面 `term` + `context`，翻面给释义、例句、近近义/同类词，三档自评）、语法卡（语法点 + 规则一句 + 正误对照，自评）。
- **学新词**：选范围（高考 / 四级 / 六级，各「精选 200 词」）→ 选数量（10 / 20 / 30 / 全部）→ 批量加入 → 当天进复习队列。
  **没有每日数量上限**，选多少加多少；`daily_limit` 字段保留但恒 `null`（见 §18.3）。
  每个范围卡显示**自己**的「已学 N / 精选 200」，不共用一个总数。
  加入后要就地给确认（绿字「已加入 10 个，1 个之前学过」/「这 10 个之前都学过」），不能只让数字悄悄变——A2 会以为按钮没反应；确认要在刷新完之后再写，别被刷新清掉。
- **语法**：四组（时态 / 冠词 / 介词 / 从句，各 15 张），一次批加入，进同一套 SRS。
- **口语**：60 张「书面说法 → 更自然口语说法 + 为什么」，同样可批量加入、走同一套 SRS。
- 朗读按钮（喇叭）常驻在卡上：单词/句型/口语卡都能听（TTS 失败回落浏览器朗读，见 §13.4）。
- 队列走完给完成状态 + 下次什么时候再来；空状态说明现状 + 「去练一次」，不摆空卡片，不写「点一下看释义」这类旁白（§17）。

### Notes 笔记页（需登录，`/notes`）

- 列表：标题（没填就用正文首行）、更新时间、来源练习（若挂了会话）；点开编辑。
- 编辑：标题可选、正文纯文本保留换行、可关联某次练习（从报告页「记一条笔记」带入）；**标题与正文都为空时保存按钮置灰**，不要点了没反应。
- 空状态给「新建第一条笔记」；搜索无结果单独给状态，不要和「一条都没有」混用同一句。
- 删除用**常驻的「⋯」菜单 + 一步确认**，不要靠 hover 才出现（手机没有 hover，桌面一滑就误删），也不要跳页。

### 导航（桌面头部 / 移动端底部 tab）

- **桌面头部只放 4 个主入口**：首页 / 学习 / 笔记 / 设置。历史记录并进学习页顶部（练过的会话本来就是学习记录）；
  新手引导从头部撤掉（设置页底部与欢迎页都有入口）；「退出」收进设置页底部。
- **移动端用底部 tab 栏**（首页 / 学习 / 笔记 / 我的），头部只留 logo：宽 390 的版心只有 358px，6 个链接必然挤爆，别再往头部加东西。
- 底部 tab 规格：高 56px + `env(safe-area-inset-bottom)`；图标 20px 线性 + 11px 文字；选中态 `brand-600` 文字 + `brand-50` 药丸底（不用下划线）；未选中 `ink-mute`；间距走 8px 刻度。
- **返回键统一（用户明确要求）**：学习 / 笔记 / 历史 / 设置这四个二级页面，返回都放在**页头左上角**，同一个图标、同一尺寸、同一种行为——「回上一级」（`router.back()`，没有历史回首页）。
  不允许一半在左一半在右、也不允许有的页面没有返回（`BackLink.vue` 统一实现，别各页自己写一个）。
- 为什么不在头部堆：按 390 屏算 6 项约 418px，溢出 60px，藏字标也救不回来——这是布局约束，不是审美偏好。

### Settings 设置页（需登录）

五块（「数据存储位置」已按用户要求从网页移除，见 §13.3）：

- **练习**：难度（简单 / 中等 / 困难，默认中等）+ 词库范围（高考 / 四级 / 六级，默认四级）。存在服务端，换设备跟着走（§18.1）。

- **模型密钥（对话）**：输入 → 「测试连接」→ 成功显示脱敏结果（只露后四位）→ 可删除本地密钥。key 只存 localStorage，不落库、不打日志。旁边要有「怎么拿 key」的说明和**真实可用**的官方链接。
- **语音合成密钥（可选）**：`key / base_url / model / voice` 四项；说明写清「不填就用浏览器内置朗读，填了走第三方计费」，同样附官方链接与获取步骤。
  它不参与评分，填错只影响朗读（回落 `speechSynthesis`），接口与错误码见 §13.4。
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
| POST | /api/sessions/{id}/turn/stream | 同上，AI 回复按 SSE 逐段推送（见下方「流式对话」） | 是 |
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
| GET | /api/config/llm | 默认 base_url / model；**`env_configured` 恒 false**（服务端不再提供兜底 key） | 是 |
| GET | /api/system/storage | 数据目录/库文件/可写性（运维用，网页不展示，见 §13.3） | 是 |
| PATCH | /api/me/profile | 改昵称 / 密码（改密码要带 `current_password`，见 §5 设置页） | 是 |
| POST | /api/tts | 语音合成（可选；无 key 409，key 被拒/不可达 502，见 §13.4） | 是 |
| DELETE | /api/me/data | 清除自己的练习记录（只接受 `scope=records`，见 §13.2） | 是 |
| GET | /api/study/due | 今天到期的学习卡（`date(due_at) <= today`，见 §16.5） | 是 |
| GET | /api/study/today | **复习统一队列**：按 `word → spelling → grammar → spoken → phrase` 分组，组内按 `due_at` 升序（见 §18.4） | 是 |
| GET | /api/study/summary | 首页聚合：`{due_count, notes_count, total, word_count, phrase_count, spelling_count}`（不是单独的业务操作，见 §16.5） | 是 |
| GET | /api/study/vocab | 词库取词：`?scope=gaokao|cet4|cet6&limit=`，只返还没建卡的词（见 §18.3） | 是 |
| POST | /api/study/vocab/add | 把选中的词落成学习卡（按 user+term+kind 去重，**无每日上限**） | 是 |
| GET | /api/study/grammar | 语法卡：四组（时态/冠词/介词/从句）+ 未学列表（见 §18.4） | 是 |
| POST | /api/study/grammar/add | 批量加入语法卡（`kind=grammar, source=grammar`） | 是 |
| GET | /api/study/spoken | 口语卡：书面说法 → 更自然说法 + 为什么（60 张） | 是 |
| POST | /api/study/spoken/add | 批量加入口语卡（`kind=phrase, source=spoken`） | 是 |
| GET | /api/me/settings | 用户偏好：`{practice_difficulty, word_scope}`（见 §18.1） | 是 |
| PATCH | /api/me/settings | 改偏好（局部更新，枚举外返 400） | 是 |
| POST | /api/study/items | 新建学习卡（手动加入 / 报告页「加入学习清单」） | 是 |
| POST | /api/study/items/{id}/review | 提交复习 `{grade: again|hard|good}` 或拼写卡 `{answer}`，推进 `due_at` | 是 |
| DELETE | /api/study/items/{id} | 删学习卡（只能删自己的） | 是 |
| GET | /api/notes | 笔记列表 | 是 |
| POST | /api/notes | 新建笔记（标题可选，可挂会话） | 是 |
| GET | /api/notes/{id} | 读取笔记 | 是 |
| PATCH | /api/notes/{id} | 修改笔记 | 是 |
| DELETE | /api/notes/{id} | 删除笔记 | 是 |
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

`POST /api/sessions/{id}/turn/stream`（流式对话，练习页默认走这个）

- 请求体、校验、错误码与 `/turn` 完全相同；校验失败 / 密钥被拒（502 `key_invalid`）/ 地址不安全（400）都**不开流**，直接返回 JSON。
- 成功时 `Content-Type: text/event-stream`，依次推送：
  - `event: delta` · `data: {"text": "Great, "}`（若干条）
  - `event: done` · `data: <TurnOut>`（与 `/turn` 响应相同）
  - `event: error` · `data: {"detail": "..."}`（只在落库失败时出现）
- **整句收完才落库**。上游中途断流时丢掉半句，`done.ai_reply` 换成预设追问并 `degraded: true`；前端一律用 `done.ai_reply` 覆盖气泡。
- 客户端在 `done` 前断开，这一轮不记录，前端撤回并提示重发。
- 前端遇到 401 / 404 / 405 回落到 `/turn`（401 走 axios 拦截器登出；404/405 兼容旧后端）。

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
drill_attempts(id, report_id, item_index, transcript, similarity, created_at)   -- 跟读重说
study_items(id, user_id, kind, term, context, meaning_zh, example, related_json,
            source_session_id, ease, interval_days, due_at, reps, lapses, created_at)  -- 见 §16.1
notes(id, user_id, title, body, session_id, created_at, updated_at)              -- 见 §16.3
```

> 学习卡与笔记的字段语义、调度规则、错误类型枚举在 **§16**；这里只列表名，避免两处各写一份。

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

- 存储位置：**只存浏览器 localStorage**，随请求走 `X-LLM-Key`（另有 `X-LLM-Base-URL` / `X-LLM-Model`）头。
  **服务端不再提供兜底 key**（用户 10-31 明确要求）：`.env` 的 `LLM_API_KEY` 清空、代码不再用它兜底，`GET /api/config/llm` 的 `env_configured` 恒为 `false`（字段保留兼容，别再据此显示任何「用服务端密钥」入口）。
- key 只走请求头，**不进 body**：放 body 就多一份可能被访问日志记下的明文。
- 不写 `.env`、不入库、不打日志。验证接口不回显 key。
- 前端已用 `allow_headers=["*"]`（`backend/app/main.py:58`），自定义头不会触发 CORS 预检失败，无需额外放行。
- 登录后进 `/settings` 引导页，**必须可跳过**：评委没有 key 不能卡在配置页。
- **跳过不等于可以免 key 开练**：本浏览器没有 key 时，`POST /api/sessions` 和 `POST /api/sessions/{id}/turn` 返回
  `409 {"kind": "llm_not_configured", "detail": "还没有接入模型密钥"}`；前端在场景列表上方展开页内面板，**只给「去设置填密钥 / 取消」两个出口**。
  没有「用服务端密钥继续（演示）」——服务端没有 key 可借。
  **不能用 401**——前端 `client.js` 拦截器把任何 401 当登录失效并清 token 跳登录页。
- **自动化测试注意**：服务端兜底拿掉后，所有脚本必须自己在 `X-LLM-Key` 头里带真实 key，否则会一路 `409`/示例报告；
  不要为了测试方便把兜底加回来。
- 失败分类（定稿口径），**不是所有失败都降级成示例报告**：

  | 情形 | 返回 | 界面 |
  |---|---|---|
  | 用户请求头里的 key 被拒（401/403） | **502** `{"kind": "key_invalid"}`，不生成报告、会话保持 active，换 key 可重试；**这一轮用户发言也不落库**（模型调用成功后才写 `turns`），重试不会出现两条一样的发言 | 「key 无效，去设置里换」+ 重试 |
  | 超时 / 不可达 / 返回无法解析 | 200 + `source=mock` + `mock_reason=unavailable` | 「模型服务暂时不可用，稍后重试」 |
  | 会话中途失去全部 key 再 finish | 200 + `source=mock` + `mock_reason=not_configured` | 「本次未接入模型，示例报告不计分」 |

- `mock_reason` 现在只有 `unavailable` / `not_configured` 两个活值；`invalid_key` 此前专指「服务端 `.env` 兜底密钥失效」，兜底取消后**不再产生**，历史数据里出现时按 `unavailable` 展示。
- **`finish` 不拦**：练习已经做完，用户中途把 key 删了，也应该拿到一份 `not_configured` 的示例报告。
  拦截点只有「建会话」和「每轮对话」（`create_session` / `add_turn`）。这是预期行为，不是 bug，别改。

`GET /api/config/llm`（登录）→ `{"env_configured": false, "default_base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"}`
——只用于「去设置」页显示默认值，**不回显 key，也不再表示服务端有可用 key**。

`POST /api/config/llm/test`（登录，key 取自 `X-LLM-Key` 头）→ `{"ok": true, "model": "deepseek-chat", "latency_ms": 812}`；
失败 `{"ok": false, "error_kind": "invalid_key" | "timeout" | "unreachable", "error": "..."}`。

> 两个字段别混：`error_kind` 属测试接口（`invalid_key` / `timeout` / `unreachable`，设置页按它出文案），
> `mock_reason` 属报告（现在只有 `unavailable` / `not_configured`）。

### 13.2 清除数据

| 接口 | 权限 | 范围 |
|---|---|---|
| `DELETE /api/me/data` | 登录用户 | 只删自己 `user_id` 的 sessions / turns / reports（只接受 `scope=records`） |
| `DELETE /api/me/account` | 登录用户 | 删记录 + 删 `users` 行，注销账号 |
| `DELETE /api/admin/data` | `X-Admin-Key` 头（错密钥 → **403**） | 清全库，演示前重置用；`scope=account` 连 `users` 一起清空 |
| `DELETE /api/admin/users/{id}` | 同上 | 管理员删单个用户及其全部练习数据 |
| `PATCH /api/admin/users/{id}` | 同上 | 管理员改单个用户的昵称 / 密码（不需要旧密码） |

- `/api/me/data` 响应：`{"deleted_sessions": 3, "deleted_turns": 12, "deleted_reports": 3, "deleted_drill_attempts": 2, "deleted_study_items": 4, "deleted_notes": 1, "deleted_account": 0, "scope": "records"}`。
  **`study_items` / `notes` 必须在这条路径上一起删**，否则「清空我的数据」之后学习卡和笔记还留着（§16.5 末尾）。
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

### 13.4 语音合成密钥（可选，`X-TTS-*`）

朗读默认用浏览器内置 `speechSynthesis`（`frontend/src/utils/speech.js`，不需要 key）。想更自然就填第三方 TTS，**不填不影响任何功能**。

- 设置页第二块「语音合成密钥（可选）」，四个字段：`key / base_url / model / voice`。
  说明必须写清两件事：**不填就用浏览器内置朗读**；**填了走第三方计费**（谁付费、谁承担，讲明白）。
  「怎么拿 key」要给**真实可用的官方链接**（抓一下官网确认，别凭记忆写死地址），和对话 key 那块同样对待。
- 请求头：`X-TTS-Key` / `X-TTS-Base-URL` / `X-TTS-Model` / `X-TTS-Voice`；规则和 LLM key 一致——**只存浏览器、不落库、不打日志**，`.env` 的 `TTS_API_KEY` 只是兜底，优先级「浏览器 > `.env`」。
- 接口：`POST /api/tts`，body `{text, voice?}`，成功返回音频流（`audio/mpeg`）。失败分三种，别混：
  | 情形 | 返回 |
  |---|---|
  | 浏览器与 `.env` 都没有 TTS key | `409 {"kind": "tts_not_configured"}` |
  | 填的 key 被第三方拒（401/403） | `502 {"kind": "tts_key_invalid"}` |
  | 超时 / 不可达 / 返回不是音频 | `502 {"kind": "tts_unavailable"}` |
- **回落是硬要求**：前端先试 `/api/tts`，任何失败（含无 key）都退回 `speechSynthesis` 朗读，
  **不能因为 TTS 挂了就连朗读都没了**——语音是演示里最显眼的一环，宁可声音普通也不能没声音。
- 兼容范围：按 OpenAI 兼容的 `/audio/speech` 做（OpenAI `tts-1`、SiliconFlow、Groq 同一套参数）。
  讯飞/火山那类要 AppID + Secret 三件套的**不在本契约内**，要接得另立一套字段，别硬塞进这四件。
- `.env.example` 必须加 `TTS_API_KEY=` 与一行注释（留空 = 用浏览器朗读）。

### 13.5 验收（最容易漏的几条）

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

## 16. 学习闭环：单词本 / 笔记 / 针对性方案（v0.5 新增，接口已定稿）

一次练习结束不是终点：报告里挑出来的错误要能变成**下次能复习的卡片**。三块数据 + 一个复习调度，全部挂在当前用户名下。

### 16.1 `study_items`（学习卡）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `user_id` | INTEGER FK → users | 按用户隔离，跨账号不可见 |
| `kind` | VARCHAR(8) | `word` / `phrase`（句型或口语说法）/ `spelling` / **`grammar`**（语法卡，v0.6 新增） |
| `source` | VARCHAR(8) | `report`（报告自动建卡）/ `vocab`（词库新词）/ `grammar`（语法模块）/ `spoken`（口语模块）/ `review`（用户手动加入）——清数据只删卡，内置内容库不受影响 |
| `term` | VARCHAR(128) | 卡片正面：要学的词或句型 |
| `context` | TEXT | 出现的那句话（语境学习的关键，别丢） |
| `meaning_zh` | TEXT | 中文释义 |
| `example` | TEXT | 例句 |
| `related_json` | TEXT | 近义词 / 反义词 / 同类词。**接口出参必须是 `synonyms` / `antonyms` / `related` 三个数组**（前端按这三个名字读），库里怎么打包不管 |
| `source_session_id` | INTEGER 可空 | 来自哪次练习 |
| `ease` | REAL | SM-2 的难度因子，初值 2.5 |
| `interval_days` | REAL | 当前间隔（天） |
| `due_at` | DATETIME | 下次到期时间 |
| `reps` / `lapses` | INTEGER | 复习次数 / 忘记次数 |
| `created_at` | DATETIME | |

### 16.2 间隔重复规则（简化 SM-2，按此实现）

三档反馈：`again`（忘了）/ `hard`（模糊）/ `good`（认识）。

| 反馈 | `interval_days` | `due_at` | `ease` |
|---|---|---|---|
| `again` | 不动（保留原间隔） | **+10 分钟**，本场重排到队尾 | −0.2 |
| `hard` | `max(1, interval × 1.2)` | now + 新间隔 | −0.15 |
| `good` | `max(1, interval × 2.5)` | now + 新间隔 | +0.1 |

- `ease` 初值 2.5、**下限 1.3**；既然存了就必须参与调度，否则评审会问「存着不用是为什么」。
- 上限 **60 天**（`MAX_INTERVAL_DAYS = 60`）；`hard` 明确用 `max(1, …)` 兜底，新卡 `interval=0` 时不能算出 0 天。
- `reps` 每次 +1；`again` 另加 `lapses` +1。
- **到期判定按日期，不按时刻**：`date(due_at) <= today`（本地时区）就算今天到期。所以 `again +10 分钟` 的卡当天还会出现、首页计数不会立刻 -1；凌晨打开首页也不会是 0。
- 首页文案是「**今天要复习 N 个**」，不是「现在可以复习 N 个」——两者对同一张早/晚到期的卡会给出不同数字，评审一眼能看出对不上。
- `again` 用 10 分钟而不是 1 天：1 天等于「点了忘了，卡当天消失」，用户会以为卡丢了；10 分钟 + 本场重排到队尾才符合「再练一遍」的直觉。
- 验收（定稿）：三档必须真的改 `due_at` —— `again` 当次会再出现（不是消失）、`good` 间隔明显变长；首页「今天要复习 N 个」的 N 必须等于 `GET /api/study/due` 的条数。

### 16.3 `notes`（笔记）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` / `user_id` | INTEGER | 按用户隔离 |
| `title` | VARCHAR(128) 可空 | 不填就取正文首行前 N 字，别强制用户起标题 |
| `body` | TEXT | 正文（Markdown 不做渲染，纯文本保留换行） |
| `session_id` | INTEGER 可空 | 可挂在某次练习上，从报告页一键新建 |
| `created_at` / `updated_at` | DATETIME | |

### 16.4 报告里的错误分类（`error_type` + `natural`）

每个 `sentence_fix` 增加两个字段：

| 字段 | 取值 | 用途 |
|---|---|---|
| `error_type` | `spelling` / `grammar` / `stiffness` / `wordiness` | 决定给什么方案、落不落学习卡 |
| `natural` | 更自然的说法（英文） | 「语言太僵硬」的针对性方案，和 `better` 并存：`better` 改错，`natural` 换说法 |

- 枚举固定这四个，别自创第五种；模型给了表外的值按 `grammar` 兜底并记日志。
- **自动建卡**：`spelling` → `study_items(kind=spelling)`；`stiffness` → `study_items(kind=phrase)`（`term` 取 `better`/`natural`，`context` 取原句）。
  `grammar` / `wordiness` **不自动建卡**，只在报告里给「加入学习清单」按钮由用户决定——错题本该有取舍，不然复习队列会被语法错灌满。
- 自动建卡写入的是**草稿**（`due_at = 现在`，`reps=0`），用户第一次复习才算正式开始。
- **拼写卡不靠自评，靠默写判分**：复习时只给中文释义 + 出处语境，不显示 `term`；用户默写后由后端按编辑距离判档——
  全对 → `good`、差 1–2 个字母 → `hard`、更多 → `again`。用户不点「认识/模糊/忘了」，否则「拼写诊断 → 默写 → 判分」这条闭环是假的。
  句型卡（`kind=phrase`）保留三档自评。
- **「语言太僵硬」要有可测证据，不能只有模型一句话**：重复词率、连接词密度、句长方差三项与模型的 `stiffness` 判断一起写进 `scoring_json`，
  报告「评分依据」里能展开看——和现在规则分的做法一致，否则这一维和「凭感觉」没区别。

### 16.5 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/study/due` | 今天到期的卡（`date(due_at) <= today`，按到期时间升序）；**默认返回全部、不分页**。`?limit=N` 只为调试保留：**显式传时列表条数可能少于 `summary.due_count`，界面不得用它分页** |
| GET | `/api/study/summary` | **聚合接口**（不是第十个业务操作）：一次返回首页卡片要的数字 `{due_count, notes_count, total, word_count, phrase_count, spelling_count}`，省掉两次请求。`due_count` 的口径与 `/study/due` 完全一致（`date(due_at) <= today`），必须等于它的条数 |
| POST | `/api/study/items` | 新建卡（手动加入 / 报告页「加入学习清单」） |
| POST | `/api/study/items/{id}/review` | 提交一次复习：body `{grade?: "again"|"hard"|"good", answer?: "用户默写的文本"}`；传 `answer` 时由后端判档（拼写卡），否则按 `grade`（单词/句型卡自评） |
| DELETE | `/api/study/items/{id}` | 删卡（只能删自己的） |
| GET/POST | `/api/notes` | 笔记列表 / 新建 |
| GET/PATCH/DELETE | `/api/notes/{id}` | 读取 / 修改 / 删除；**PATCH 必做**，只有增删查不叫笔记功能，改标题/正文都要校验 `user_id` |

约定：全部按 `user_id` 隔离，别人的 id 一律 404（不 403，避免探测存在性）；`grade` 不是三档之一返 400；`due` 只返本用户、只返已到期的；`notes.session_id` 必须校验归属，不能挂到别人的会话上。

**删除路径必须带上这两张表**：`DELETE /api/me/data`、`DELETE /api/me/account`、`DELETE /api/admin/users/{id}`、`DELETE /api/admin/data` 四个入口都要删 `study_items` 和 `notes`，
响应里分别报 `deleted_study_items` / `deleted_notes`。上次 `drill_attempts` 漏删过一次，这次漏了「清空数据」就没法向评委解释。

### 16.6 前端落点（ui 做，依赖上面的接口）

- 首页一张「今天要复习 N 个」卡片（只调 `GET /api/study/summary` 一次；N=0 给空状态，请求失败给「暂时取不到」而不是 0）；点进 `/study` 做翻转卡片复习。
- `/notes` 笔记列表 + 编辑（空状态、搜索无结果状态都要有）；报告页每条纠错旁给「加入学习清单」，拼写类给单词讲解 + 近反义/同类词，句型类给「原句 → 更自然说法 → 为什么」。
- 文案遵守 §17：不写「（可选）」「点击后…」这类旁白，不解释机制本身。

## 17. 文案与设计准则（v0.5 起强制）

用户明确要求：「前端不要写一些不必要的文字，不要专门用括号告诉用户要干什么」。

**文案**
- 界面**不解释自身机制**：删掉「这段引导只出现一次」「（可选）」「点击后会自动保存」这类自述与操作旁白。用户要的是能干什么，不是它怎么运作。
- 括号只用于**必要澄清**（单位、必填标记），不用来补一句说明；一句话只传达一个用户需要的信息。
- 已知要清理的清单（行号为审计时的工作区状态）：
  `Welcome.vue:88` 「开始使用（先注册或登录）」→「开始使用」；`:90` 整句「这段引导只出现一次…」删；
  `Login.vue:175` 昵称 placeholder「昵称（可选）」→「昵称」；
  `Practice.vue:90` 「再说 N 句就能出报告（已说 N 句）」去掉括号那半句；
  `Home.vue:177` 「用服务端密钥继续（演示）」→ 去掉「（演示）」；`:190` 「按间隔重复排好的队列」是术语，改成「之前错过的，今天再来一遍」；
  `Settings.vue:446` 「语音合成密钥（可选）」→「语音合成」；`:409/413/483/487/491` 五个「（可留空用默认）」改成把默认值放进 placeholder；`:382/:465` 两段机制说明各缩到一句（隐私承诺「只存在这个浏览器里」保留）；
  `Study.vue:110` 「点一下看释义」、`:124` 「想好之后点卡片，再选记得的程度」——两句操作旁白都删；
  `Report.vue:416` 「在下面「逐句纠错」里点「重说这句」」删，只留「相似度 ≥85% 算过」。
`Home.vue:142` 「和 AI 角色多轮对话，结束后拿到评分和逐句纠错。」整段删；`Home.vue:149-151` 整块「推荐 中等 · 还没有带分数的记录，先从中等开始」删（`rec` 变量别删，`usedDifficulty` 还要用它兜底）；`Home.vue:258-260` 页脚「每一轮都由 AI 角色追问，结束后按 CEFR / 雅思量表出分」整段删。
`Practice.vue:493` 「点下面的麦克风开口说，或者说不了就点「手动输入」」→ 只留麦克风那半句（后半句与 8 秒提示重复）。
**别误删**：`Report.vue:475` 的「逐句纠错」是真标题；`Welcome.vue:25-26` 那句「按 CEFR、雅思量表给分…」是公开门面页唯一说明评分依据的地方，**是否删要 Chief 拍板**（删了首页就完全不提怎么打分）。
- **边界（别一刀切）**：`Report.vue:531/549-553` 的评分依据说明是给评委复算用的承诺，不是操作旁白，**保留**；
  降级横幅、密钥门禁的说明也属于「用户必须知道才能继续」，保留。判断标准是：这句话是在教人点按钮，还是在解释分数/失败怎么来的。
- 第二人称、动词开头、不堆形容词；错误提示说清「发生了什么 + 下一步能做什么」。

**设计**
- 留白优先：间距用 **8px 刻度**，组间距 **24/32**；层级靠字号、字重、留白，不靠一层层加边框。
- 卡片要有 **hover 抬升 + 按下微反馈**；可点的东西看起来就该能点。
- **每个列表都要空状态**（历史、今日复习、笔记、搜索无结果），空状态给一句下一步，不写「暂无数据」。
- 配色克制：青玉绿主色 + 珊瑚只给录音；分数不配红绿灯（见 §5 报告页）。
- 参照 figma / claude / canva 那类克制排版：大留白、清晰网格、少量装饰；不做炫技动效。


## 18. 新词学习与用户偏好（v0.6 需求，契约待确认）

用户要的三条：① 能系统学**新单词**，可选词库范围（高考 / 四级 / 六级）；② 难度选项从首页移到**设置**；③ 学习 / 笔记 / 历史 / 设置四个页面都要有**返回**。

### 18.1 用户偏好（服务端存，跟着账号走）

| 字段 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `practice_difficulty` | `easy` / `medium` / `hard` | `medium` | 首页不再选难度，进设置改；练习页顶部显示当前难度（只读） |
| `word_scope` | `gaokao` / `cet4` / `cet6` | `cet4` | 新词学习从哪个词库取；切换只影响**之后**取的新词，已学的卡不动 |

存 `users` 表两列（启动时 `_ensure_schema` 补列），因为换设备要跟着走；不要只放 localStorage。
接口：`GET /api/me/settings` → `{practice_difficulty, word_scope}`；`PATCH /api/me/settings` 局部更新，取值不在枚举内返 400。
**`POST /api/sessions` 不传 `difficulty` 就用设置里的值**——首页、历史「再练一次」、报告「按推荐再练」三个开练入口都不用自己传难度，口径自动一致；`GET /sessions/{id}` 回的就是实际用的那个难度。

### 18.2 词库

- 内置静态词表，每档一个文件：`backend/app/data/wordbanks/{gaokao,cet4,cet6}.json`，条目字段固定 `term` / `meaning_zh` / `example` / `pos` / `related`（`related` 仍是 `{synonyms, antonyms, similar}` 嵌套）。
  **不联网取词、不引第三方词典依赖**——要能在断网机器上跑。
- 每档 **200 词**（精选，不是全量词表）；词表进仓库，不提交音频。加一档只是多一个 JSON，考研/雅思这次没做，别在界面上摆空档位。
- 词库只放单词（`kind=word`），词组/句型不进去。
- 界面文案写「**精选 200 词**」，不要写「四级词汇」——它不是考试大纲全量，写大了会被追问覆盖率。

### 18.3 学新词流程（复用 §16 的 SRS，不另起一套）

1. `GET /api/study/vocab?scope=<scope>&limit=10`（不传 `scope` 用设置里的范围）→
   `{scope, name, desc, total, learned, remaining, daily_limit, used_today, remaining_today, items, scopes}`。
   `scopes` 是三档按钮的数据 `{id, name, desc, total, learned}`——**每个档位都带自己的 `learned`**，不是共用一个总数（前端缺字段时按 0 显示，别显示空白）。
   `items` 只给**用户还没有卡**的词；`limit` 默认 10、上限 200。
   `daily_limit` / `used_today` / `remaining_today` 三个字段**保留但恒 `null`**（每日上限已取消），前端不要据此禁用「加入」按钮，也不要显示「今天还能学 N 个」。
2. `POST /api/study/vocab/add` body `{scope, terms: [...]}`（或 `{scope, count: 10}`）→
   `{added, skipped, limited}`（兼容字段保留，`limited` 恒为 0）：`skipped` = 已在清单。
   **一次批量加，不要循环单条 POST**；落库为 `study_items(kind=word, source='vocab')`，`due_at` 设当天、`ease=2.5 / interval=0 / reps=0`。
3. 去重按 `user_id + term + kind`，**不分大小写**；重复词不建第二张卡。
4. 之后完全走 §16.2 的调度和 §5 学习页——**不新增「新词专用复习逻辑」**，两套调度迟早对不上。
5. 学习页顶部四段（复习 / 新词 / 语法 / 口语，见 §5 Study）；加完当天就进 `/study/due`，首页数字会涨。
6. **没有每日新词上限**：选多少加多少（用户明确要求）。清数据/注销只删 `study_items`，**内置内容库不动**，清完还能重新学。

**到期数与列表必须同源同量**：`/api/study/due` 默认全量返回，`summary.due_count` 统计全量，两边永远相等（总量是三档各 200 词 + 语法 60 + 口语 60 + 报告卡，仍然远不到需要封顶的量级）。
`limit` 参数留作调试，**界面不允许拿它分页**——一旦传了，列表条数就会小于首页数字，又变成「首页说 60、点进去只有 50」。
如果要封顶，必须两处同时截断（`summary` 用 `min(总数, 上限)`），只截单边就是 bug。

### 18.4 语法卡与口语卡（v0.6 新增，复用 `study_items`）

两套内置内容都走同一张表、同一套 SRS，只是 `kind` / `source` 不同；**不新建表**。

| 模块 | `kind` | `source` | 数量 | 字段落法 |
|---|---|---|---|---|
| 语法 | `grammar` | `grammar` | 四组各 15：时态 / 冠词 / 介词 / 从句 | `term`=语法点名（≤6 字，如「一般过去时」）；`meaning_zh`=规则一句话；`context`=错例句；`example`=正确例句；`related.blank`=**挖空句**、`related.answer`=**要填的那个点** |
| 口语 | `phrase` | `spoken` | 60 | `term`=书面说法；`example`=更自然的口语说法；`meaning_zh`=「为什么」一句话（讲语域/语气，如「太正式」「更客气」）；`context`=使用场景 |

- **`related.blank` / `related.answer` 是语法卡判档的关键**：`blank` 是挖空后的句子、`answer` 是要填的语法点。
  **`blank` 为空表示这张卡不挖空**（比如「删掉多余词」的卡），走整句改写判档——别把「没挖空」当 bug 排查。
- 语法卡复习**必须传 `answer`**：填对那个点或整句正确 → `good`；只差一个词 → `hard`；其余 → `again`；不传 `answer` → **400**。
- 口语卡 `answer` 与 `example` 做词级相似度：≥0.7 → `good`，≥0.5 → `hard`；归一化小写、中文标点、压缩空格后再比。
- 接口与词库同构：`GET /api/study/grammar` → `{groups:[{id,name,total}], items, learned}`；`POST /api/study/grammar/add {group|ids}`；
  口语 `GET /api/study/spoken`、`POST /api/study/spoken/add {ids|count}`。同样批量加、同样按 `user_id+term+kind` 去重、同样当天到期，全部走 §16.2 的 SRS（实测 `interval 0→1`、`reps 0→1`，不是只翻卡）。
- **复习队列统一走 `GET /api/study/today`**：分组顺序固定 `word → spelling → grammar → spoken → phrase`，组内按 `due_at` 升序；`summary` 同时给 `grammar_count` 与 `due_word / due_spelling / due_grammar / due_spoken / due_phrase_count`，四个 tab 的数字不用前端自己算。
- 内容放仓库里的 JSON（`backend/app/data/grammar/*.json`、`backend/app/data/spoken/*.json`），**不联网**；`tools/check_content.py` 可离线校验字段、例句含词、跨档无重复。
- 文案要求：语法卡一张只教一个点，错句要真错、改句只动错的那个点；口语卡箭头两边都得是完整句子，口语侧得是母语者真会说的，别把书面句加句 "you know" 当口语。

### 18.5 待确认（不要按这版直接写死）

- 学习页用 `/study?tab=review|new|grammar|spoken` 共用一个路由，还是四个独立路由——目前按查询参数写，ui 出图后可改，但**默认落复习**这条不变。
- 难度是否允许练习页临时覆盖：目前定「设置里改、练习页只读」；要允许临时改得多一个 `override` 参数。
- 词库 200 词/档、语法 60、口语 60 是首批量；扩充时只换 JSON，接口不变。

## 19. 学习数据面板（v0.7）

`GET /api/me/dashboard?tz_offset=<JS getTimezoneOffset()，北京时间 -480>`，显示在历史页顶部。

- **练习日**：这一天至少发过一轮作答（user turn），按用户本地时区切日。
- **连续天数**：从今天往回数；今天还没练不算断，从昨天接着数。同时返回最长连续和累计练习天数。
- **热力图**：近 12 周，周一对齐，最后一列含今天；格子颜色按当天作答轮数。
- **维度均分**：只用正式计分报告（`source=llm`），示例报告不进来；每个维度只在含有它的报告里平均并给样本数（发音/流利度来自录音，文字表达来自打字）。
- **近 7 天变化**：可比 band（`comparable_band`）近 7 天均值减前 7 天均值；任一窗口没有数据时 `delta` 为 null，前端说明“暂时比不了”。

## 19. rc22 之后新增的能力（文档补记，逐条对代码）

这 9 个提交里有四项能力文档此前没有覆盖，补在这里，避免评委问起时发现文档滞后。

### 19.1 SSE 流式回复

- `POST /api/sessions/{id}/turn/stream`：与 `/turn` 同一套校验（404 / 400 已结束 / 409 无 key / 502 key 无效），区别是 AI 回复**逐 token 推送**。
- **只在收到完整回复后才落库**：中途断流不写 `turns`，也不推进轮次——和 502 不落库同一条原则，避免“半句话进了记录”。
- 前端流式失败时回落一次普通 `/turn`（`StreamUnavailable`），保证说话不会因为流断了卡住。
- 非流式 `/turn` 仍保留，是回落与测试的基线，不要删。

### 19.2 录音回放（只在本浏览器）

- 练习页和自己的录音、报告里每条纠错的「听原句」都能回放；录音**只存在浏览器**（IndexedDB/对象 URL），**不上传、不落库**。
- 因此换设备/清缓存后录音不可回放，属预期；报告里音频缺失时按钮隐藏，不要显示灰按钮。
- 隐私口径和 key 一致：音频不进服务端，库里只有转写与 `audio_json` 的时长/停顿特征。

### 19.3 历史学习看板

- `GET /api/me/dashboard`：给历史页顶部的**连续练习天数（streak）**、12 周热力图与分维度均值。
- 热力图按**日期分桶**（与 SRS 一致，用本地日期，不按时刻）；空数据时整块给空状态，不画一张全灰的图。
- 分维度均值只用有该维度的报告（打字报告没有发音/流利度，别把缺维度按 0 算）。

### 19.4 安全加固（rc22 前一轮完成）

四项，细节见 README「安全相关配置」：**SSRF 防护**（模型/语音地址默认拒绝内网与本机，`ALLOW_PRIVATE_LLM_HOSTS=1` 才放开，本地 Ollama 才需要）、**默认密钥**（不设 `JWT_SECRET` 时不再用公开默认值）、**登录暴力破解**（失败计数与锁定）、**重复 finish**（同一会话幂等返回同一份报告，不再生成第二份）。
这四个洞都是“演示时没人问、被问就致命”的类型，验收里要单独验，别只看功能通不通。
