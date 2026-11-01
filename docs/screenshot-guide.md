# 无头截图稿子（ui设计师 维护）

这台机器的沙箱禁止 Chromium 使用命名管道（`mojo platform_channel: 拒绝访问 0x5`），所以普通 `chrome --headless --screenshot`
会崩。可行路线是：**Chrome 用 DevTools 协议跑起来，Node 通过 WebSocket 驱动它**。Node 24 自带 `WebSocket`，不需要装依赖。

脚本：`tools/screenshot/shoot.mjs`。全部参数走环境变量，输出只写 PNG。

## 0. 前置

| 需要 | 说明 |
| --- | --- |
| Chrome | `$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe`（Edge 同理，换 `-FilePath` 即可） |
| Node | 便携版 `tools\node\node.exe`（不要装到系统 PATH） |
| dev server | `127.0.0.1:5173`（`start-all.bat` 或 `npm run dev`） |
| 后端 | `127.0.0.1:8000`，**必须是当前 HEAD 起的进程**，否则新接口 404，截出来是旧行为 |

## 1. 启动 Chrome（一次性提权）

沙箱默认权限下 Chrome 起不来，需要在工具调用里显式给一次 `danger-full-access`（只读本地页面 + 往 `.tmp` 写 PNG）。
启动命令（PowerShell）：

```powershell
$chrome = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
Start-Process -FilePath $chrome -ArgumentList @(
  '--headless=new','--no-sandbox','--disable-gpu',
  '--no-crashpad','--disable-breakpad','--disable-crash-reporter',
  '--hide-scrollbars','--remote-debugging-port=9222',
  "--user-data-dir=$PWD\.tmp\chrome-cdp",'about:blank'
)
```

`--no-crashpad --disable-breakpad --disable-crash-reporter` 是必须的：不关掉 crashpad，它会先因为
`OpenProcess: 拒绝访问` 自杀，页面根本不会渲染。

## 2. 准备一个账号拿 token（截登录态页面才需要）

真库要清空，所以都用临时账号，截完就删：

```powershell
$api = "http://127.0.0.1:8000/api"
$name = "shot_" + (Get-Random -Minimum 1000 -Maximum 9999)
$reg = Invoke-RestMethod "$api/auth/register" -Method Post -ContentType 'application/json' `
  -Body (@{username=$name;password='verify1234';nickname='截图'} | ConvertTo-Json)
$env:SP_TOKEN = $reg.token
$headers = @{ Authorization = "Bearer $($reg.token)" }
```

> 不要再用 `frontend/public/seed.html` 那种「从 URL 灌 token」的注入页：它构建后会变成线上 `/seed.html`，
> 等于给评审留一个后门。`shoot.mjs` 是在 DevTools 里直接写 localStorage，不需要任何线上页面。

## 3. 截图

```powershell
$env:SP_PAGES = "/>.tmp/home.png,/history>.tmp/history.png,/report/12>.tmp/report.png"
& "D:\...\tools\node\node.exe" "D:\...\tools\screenshot\shoot.mjs"
```

| 变量 | 含义 |
| --- | --- |
| `SP_TOKEN` | 登录 token，注入 `sp_token`；不传就截未登录页面 |
| `SP_PAGES` | `路径>输出` 用逗号分隔，路径用前端路由（`/history`、`/practice/7`） |
| `SP_SEED` | 额外 localStorage，JSON 对象，原样合并（例如预置 `sp_llm` 里的难度偏好） |
| `SP_CLIP` | 长页只用一段：`{"x":200,"y":0,"width":880,"height":1250,"scale":1}` |
| `SP_WIDTH` / `SP_HEIGHT` | 视口，默认 1280×1000；手机用 `390`/`844` |
| `SP_CDP_PORT` | 默认 9222，多开 Chrome 时改这个 |
| `SP_WAIT` | 每页渲染等待毫秒，默认 2400（模型回包慢的页面可调到 4000） |

脚本会打印每页的 `path`、`innerWidth`、`scrollWidth`、首屏文字；最后一行是 JS 错误汇总——
`JS errors: none` 才算这页干净，有 `console.error` 会一起列出来。

## 4. 收尾

```powershell
# 删临时账号（连带 sessions/turns/reports/drill_attempts）
Invoke-RestMethod "$api/me/account" -Method Delete -Headers $headers `
  -ContentType 'application/json' -Body (@{confirm='注销'} | ConvertTo-Json)
# 停 Chrome
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddMinutes(-5) } | Stop-Process -Force
```

## 5. 几个坑（都踩过）

1. **Tailwind 只输出 content 里出现过的类**：自己拼 HTML 做预览页时，类名不在扫描范围里就会被 purge，
   渲染出「logo 满屏、分数变小字」的假象。截图必须截真页面（`frontend/src` 在 content 里）。
2. **Chrome 在 Windows 上会把窗口宽度钳到约 500px**：`--window-size=390,844` 拿到的 390 宽图其实是「500 宽的页面被裁掉右边」，
   会误判成横向溢出。手机尺寸一律用脚本里的 `SP_WIDTH=390`（走 DevTools 的 `setDeviceMetricsOverride`），
   再核对打印出来的 `scrollWidth` 是否等于 390。
3. **`/practice/:id` 会跳报告页**：会话已 `finished` 时进练习页会 `replace` 到 `/report/:id`。要截练习页，
   就在 `finish` 之前截，或者新开一个会话只发一轮。
4. **后端不重启就截不到新行为**：`8000` 上是旧进程时，新接口 404、场景只有 3 个、打字报告还会给发音分。
   截之前先确认 `/openapi.json` 的 `paths` 数量，再开始。
5. **未登录一律落 `/login`**：欢迎页已删除，未带 `SP_TOKEN` 只能截到登录页；首页、学习、历史这些页必须带 token。
