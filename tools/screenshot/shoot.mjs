// SpeakPal 无头截图：Chrome DevTools 协议（Node 24 自带 WebSocket，不装依赖）
// 用法见同目录 README.md
import { writeFileSync } from 'node:fs'

const port = process.env.SP_CDP_PORT || '9222'
const base = `http://127.0.0.1:${port}`
const token = process.env.SP_TOKEN || ''
const seed = process.env.SP_SEED || '' // 额外注入的 localStorage（JSON 字符串）
const pages = (process.env.SP_PAGES || '').split(',').map((s) => s.trim()).filter(Boolean)
const clip = process.env.SP_CLIP ? JSON.parse(process.env.SP_CLIP) : null
const width = Number(process.env.SP_WIDTH || 1280)
const height = Number(process.env.SP_HEIGHT || 1000)
const wait = Number(process.env.SP_WAIT || 2400)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

if (!pages.length) {
  console.error('SP_PAGES 为空，示例：SP_PAGES="/ >.tmp/home.png,/history>.tmp/history.png"')
  process.exit(1)
}

for (let i = 0; i < 80; i++) {
  try {
    if ((await fetch(`${base}/json/version`)).ok) break
  } catch {}
  await sleep(250)
}

const tab = await (await fetch(`${base}/json/new?about:blank`, { method: 'PUT' })).json()
const ws = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((res, rej) => {
  ws.onopen = res
  ws.onerror = rej
})

let seq = 0
const pending = new Map()
const errors = []
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id)
    pending.delete(m.id)
    m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result || {})
    return
  }
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params?.exceptionDetails
    errors.push(d?.exception?.description || d?.text || 'exception')
  }
  if (m.method === 'Runtime.consoleAPICalled' && m.params?.type === 'error') {
    errors.push('console.error: ' + m.params.args.map((a) => a.value ?? a.description).join(' '))
  }
}
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const id = ++seq
    pending.set(id, { res, rej })
    ws.send(JSON.stringify({ id, method, params }))
  })

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 })

// 先落到登录页取得同源上下文，再注入 token / 引导标记
await send('Page.navigate', { url: 'http://127.0.0.1:5173/login' })
await sleep(1200)
if (token) {
  const payload = { sp_token: token, ...(seed ? JSON.parse(seed) : {}) }
  await send('Runtime.evaluate', {
    expression: Object.entries(payload)
      .map(([k, v]) => `localStorage.setItem(${JSON.stringify(k)},${JSON.stringify(v)})`)
      .join(';'),
  })
}

for (const spec of pages) {
  const [path, out] = spec.split('>').map((s) => s.trim())
  if (!out) {
    console.error(`页面 "${spec}" 缺少输出路径，格式：/path>.tmp/x.png`)
    continue
  }
  await send('Page.navigate', { url: `http://127.0.0.1:5173${path}` })
  await sleep(wait)
  const shot = clip
    ? { format: 'png', captureBeyondViewport: true, clip }
    : { format: 'png' }
  const { data } = await send('Page.captureScreenshot', shot)
  writeFileSync(out, Buffer.from(data, 'base64'))
  const info = await send('Runtime.evaluate', {
    expression: `JSON.stringify({url:location.pathname+location.search,w:innerWidth,sw:document.documentElement.scrollWidth,txt:document.body.innerText.slice(0,120).replace(/\\s+/g,' ')})`,
    returnByValue: true,
  })
  console.log(`${out} ${info.result.value}`)
}

console.log(errors.length ? 'JS ERRORS: ' + [...new Set(errors)].slice(0, 5).join(' | ') : 'JS errors: none')
ws.close()
