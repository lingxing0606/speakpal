// 尽可能做一次「真的执行」：把 SFC 编译成 ESM，在 Node 里用 Vue 的 SSR 渲染每个页面，
// 抓运行时错误（未定义变量、组件解析失败、store/router 注入错误）。
// 它不能替代浏览器：没有 CSS、没有真实事件、没有 Web Speech / AudioContext。
import fs from 'node:fs'
import path from 'node:path'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const ROOT = process.cwd()
const SRC = path.join(ROOT, 'src')
const OUT = path.join(ROOT, '.tmp-render')
fs.rmSync(OUT, { recursive: true, force: true })

const files = []
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full)
    else if (/\.(vue|js)$/.test(entry.name) && !entry.name.endsWith('.spec.js')) files.push(full)
  }
}
walk(SRC)

function outPath(file) {
  const rel = path.relative(SRC, file)
  return path.join(OUT, 'src', rel).replace(/\.vue$/, '.mjs')
}

function finalPathFor(file) {
  // .vue 编译成 .mjs；普通 .js 也落成 .mjs，避免 Node 当成 CommonJS
  return outPath(file).replace(/\.js$/, '.mjs')
}

function rewriteSpecifiers(code, fromFile) {
  return code.replace(/(from\s+|import\s*\(\s*)(['"])([^'"]+)\2/g, (whole, lead, quote, spec) => {
    if (!spec.startsWith('.')) return whole
    const base = path.resolve(path.dirname(fromFile), spec)
    let target = null
    if (fs.existsSync(base) && fs.statSync(base).isFile()) target = base
    else if (fs.existsSync(`${base}.vue`)) target = `${base}.vue`
    else if (fs.existsSync(`${base}.js`)) target = `${base}.js`
    else if (fs.existsSync(path.join(base, 'index.js'))) target = path.join(base, 'index.js')
    if (!target) return whole
    let rel = path.relative(path.dirname(finalPathFor(fromFile)), finalPathFor(target)).replace(/\\/g, '/')
    if (!rel.startsWith('.')) rel = `./${rel}`
    return `${lead}${quote}${rel}${quote}`
  })
}

// 1. 编译所有文件
const compiled = new Map()
for (const file of files) {
  const code = fs.readFileSync(file, 'utf8')
  let output
  if (file.endsWith('.vue')) {
    const { descriptor, errors } = parse(code, { filename: file })
    if (errors.length) {
      console.log(`COMPILE-FAIL ${path.relative(ROOT, file)} :: ${errors[0].message}`)
      continue
    }
    const id = path.basename(file)
    if (!descriptor.script && !descriptor.scriptSetup) {
      const tpl = compileTemplate({ source: descriptor.template?.content || '', filename: file, id, mode: 'module' })
      if (tpl.errors.length) {
        console.log(`COMPILE-FAIL ${path.relative(ROOT, file)} :: ${tpl.errors[0]}`)
        continue
      }
      output = `${tpl.code}\nexport default { render }\n`
    } else {
      output = compileScript(descriptor, { id, inlineTemplate: true }).content
    }
  } else {
    output = code
  }
  const dest = finalPathFor(file)
  fs.mkdirSync(path.dirname(dest), { recursive: true })
  fs.writeFileSync(dest, rewriteSpecifiers(output, file))
  compiled.set(file, dest)
}

// 2. 浏览器环境替身（只为让模块能 import，不参与断言）
const noop = () => {}
// CountUp 在 setup 里就会 cancelAnimationFrame；SSR 里没有这两个全局，补上以免误报
globalThis.requestAnimationFrame = () => 0
globalThis.cancelAnimationFrame = noop
globalThis.localStorage = {
  store: new Map(),
  getItem(k) { return this.store.has(k) ? this.store.get(k) : null },
  setItem(k, v) { this.store.set(k, String(v)) },
  removeItem(k) { this.store.delete(k) },
}
globalThis.window = {
  location: { pathname: '/', search: '', href: '' },
  speechSynthesis: { cancel: noop, speak: noop },
  SpeechRecognition: undefined,
  webkitSpeechRecognition: undefined,
  AudioContext: class { createAnalyser() { return {} } close() {} },
  webkitAudioContext: undefined,
  localStorage: globalThis.localStorage,
}
globalThis.history = { state: {}, pushState: noop, replaceState: noop, back: noop, go: noop }
globalThis.location = globalThis.window.location
try {
  globalThis.navigator = { userAgent: 'node' }
} catch {
  // Node 24 的 navigator 是只读 getter，跳过即可
}
globalThis.document = {
  querySelector: () => null,
  querySelectorAll: () => [],
  getElementById: () => null,
  createElement: () => ({ style: {}, setAttribute() {}, appendChild() {} }),
  head: { appendChild: noop },
  body: { appendChild: noop },
  addEventListener: noop,
  removeEventListener: noop,
}

const { createSSRApp } = await import('vue')
const { renderToString } = await import('vue/server-renderer')
const { createPinia } = await import('pinia')
const { createRouter, createMemoryHistory } = await import('vue-router')

const views = ['Login', 'Home', 'Practice', 'Report', 'History', 'Settings', 'Pronunciation']
const routes = [
  { path: '/login', component: { template: '<div />' } },
  { path: '/', component: { template: '<div />' } },
  { path: '/practice/:id', component: { template: '<div />' } },
  { path: '/report/:id', component: { template: '<div />' } },
  { path: '/history', component: { template: '<div />' } },
  { path: '/settings', component: { template: '<div />' } },
]

let failed = 0
for (const name of views) {
  const file = path.join(SRC, 'views', `${name}.vue`)
  const target = compiled.get(file)
  if (!target) {
    console.log(`SKIP ${name}: not compiled`)
    failed += 1
    continue
  }
  try {
    const mod = await import(`file:///${target.replace(/\\/g, '/')}`)
    const component = mod.default
    const app = createSSRApp(component)
    const router = createRouter({ history: createMemoryHistory(), routes })
    app.use(createPinia())
    app.use(router)
    await router.push(name === 'Login' ? '/login' : name === 'Home' ? '/' : name === 'History' ? '/history' : name === 'Settings' ? '/settings' : `/${name.toLowerCase()}/1`)
    await router.isReady()
    const html = await renderToString(app)
    fs.writeFileSync(path.join(OUT, `${name}.html`), html)
    const textLen = html.replace(/<[^>]+>/g, '').trim().length
    console.log(`OK   ${name}: rendered ${html.length} bytes html, ${textLen} chars text`)
  } catch (err) {
    failed += 1
    console.log(`FAIL ${name} :: ${err?.message?.split('\n')[0]}`)
  }
}

console.log(`\n${views.length - failed}/${views.length} views rendered without runtime errors`)
process.exit(failed ? 1 : 0)

