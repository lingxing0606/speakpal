<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import TabBar from '../components/TabBar.vue'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import { clearRecordings } from '../utils/recordings'
import { resetTtsProbe } from '../utils/speech'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const settings = useSettingsStore()

// 左侧分区导航：滚动时高亮当前分区
const SECTIONS = [
  { id: 'profile', label: '个人资料' },
  { id: 'prefs', label: '练习偏好' },
  { id: 'key', label: '对话密钥' },
  { id: 'tts', label: '语音合成' },
  { id: 'data', label: '清除记录' },
  { id: 'account', label: '注销账号' },
]
const activeSection = ref('profile')
let sectionObserver = null

function watchSections() {
  if (!('IntersectionObserver' in window)) return
  sectionObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible.length) activeSection.value = visible[0].target.id
    },
    { rootMargin: '-80px 0px -55% 0px' }
  )
  for (const sec of SECTIONS) {
    const el = document.getElementById(sec.id)
    if (el) sectionObserver.observe(el)
  }
}

onBeforeUnmount(() => sectionObserver?.disconnect())

const onboarding = computed(() => route.query.onboarding === '1')

const DIFFICULTIES = [
  { value: 'easy', label: '简单' },
  { value: 'medium', label: '中等' },
  { value: 'hard', label: '困难' },
]

function diffLabel(value) {
  return DIFFICULTIES.find((d) => d.value === value)?.label || '中等'
}

const keyInput = ref(settings.apiKey)
const baseInput = ref(settings.baseUrl)
const modelInput = ref(settings.model)
const server = ref({ env_configured: null, error: '' })
const saveTip = ref('')
const testState = ref({ running: false, ok: null, message: '' })

// 语音合成（可选）：不填就用浏览器朗读
const ttsInput = ref({
  key: settings.ttsKey,
  base: settings.ttsBaseUrl,
  model: settings.ttsModel,
  voice: settings.ttsVoice,
})
const ttsTip = ref('')
const ttsTest = ref({ running: false, ok: null, message: '' })

// 留空时实际会用到的默认值。页面上教的供应商是硅基流动，所以：
// 服务端给了「非 OpenAI 出厂值」的默认就尊重它，否则用硅基流动这套——
// 否则用户拿了硅基流动的 key、字段留空，请求会打到 api.openai.com 然后 401
const TTS_FALLBACK = {
  base: 'https://api.siliconflow.cn/v1',
  model: 'FunAudioLLM/CosyVoice2-0.5B',
  voice: 'FunAudioLLM/CosyVoice2-0.5B:alex',
}

function ttsDefaults() {
  const s = server.value || {}
  const isStockOpenAi = /api\.openai\.com/i.test(s.default_tts_base_url || '')
  return {
    base: (!isStockOpenAi && s.default_tts_base_url) || TTS_FALLBACK.base,
    model: (s.default_tts_model && s.default_tts_model !== 'tts-1' ? s.default_tts_model : '') || TTS_FALLBACK.model,
    voice: (s.default_tts_voice && s.default_tts_voice !== 'alloy' ? s.default_tts_voice : '') || TTS_FALLBACK.voice,
  }
}

function saveTts() {
  const d = ttsDefaults()
  // 把「实际会用到的值」真的写进去，而不是留空只靠 placeholder：
  // 否则用户拿了硅基流动的 key、字段留空，请求会打到别的默认供应商，界面还显示保存成功
  settings.saveTts({
    key: ttsInput.value.key,
    baseUrl: (ttsInput.value.base || '').trim() || d.base,
    model: (ttsInput.value.model || '').trim() || d.model,
    voice: (ttsInput.value.voice || '').trim() || d.voice,
  })
  // 新 key 存好了，清掉「本会话不再试服务端」的标记，让下一次朗读立刻用上
  resetTtsProbe()
  ttsInput.value = {
    key: settings.ttsKey,
    base: settings.ttsBaseUrl,
    model: settings.ttsModel,
    voice: settings.ttsVoice,
  }
  ttsTip.value = '已保存到本浏览器（Base URL / 模型 / 音色已填成实际会用的值）。'
}

async function testTts() {
  ttsTest.value = { running: true, ok: null, message: '正在合成一句试听…' }
  try {
    const { data } = await api.post(
      '/tts',
      { text: 'Hi there! What can I get for you today?', speed: 1 },
      { responseType: 'blob', timeout: 20000 }
    )
    if (!data || !data.size) throw new Error('empty audio')
    const url = URL.createObjectURL(data)
    const audio = new Audio(url)
    audio.onended = () => URL.revokeObjectURL(url)
    await audio.play()
    ttsTest.value = { running: false, ok: true, message: '试听成功：语音合成已生效，练习里的朗读会用它。' }
  } catch (e) {
    const status = e?.response?.status
    // 失败体是 blob（responseType: blob），读回来才知道是 key 被拒还是连不上
    let kind = ''
    const body = e?.response?.data
    if (body && typeof body.text === 'function') {
      try {
        kind = JSON.parse(await body.text())?.kind || ''
      } catch {
        kind = ''
      }
    }
    let msg = '试听失败：连不上语音合成服务，或返回的不是音频。练习里会自动用浏览器朗读。'
    if (status === 409) msg = '试听失败：没读到你的 key，服务端也没有兜底，练习里会用浏览器朗读。'
    else if (status === 502 && kind === 'tts_key_invalid') msg = '试听失败：key 被语音服务拒绝了，检查是不是复制少了字符。练习里会先用浏览器朗读。'
    else if (status === 502 && kind === 'tts_unavailable') msg = '试听失败：Base URL 不可达或超时。检查地址和网络，练习里会先用浏览器朗读。'
    else if (status === 400) msg = '试听失败：请求被拒，检查 Base URL 是否指向 OpenAI 兼容的 /audio/speech。'
    ttsTest.value = { running: false, ok: false, message: msg }
  }
}

function clearTts() {
  settings.saveTts({ key: '', baseUrl: '', model: '', voice: '' })
  ttsInput.value = { key: '', base: '', model: '', voice: '' }
  ttsTip.value = '已删除语音合成密钥，会用浏览器朗读。'
  ttsTest.value = { running: false, ok: null, message: '' }
}

const nicknameInput = ref(auth.user?.nickname || '')
const profileState = ref({ running: false, tip: '', error: '' })
const pwd = ref({ current: '', next: '', confirm: '' })
const pwdState = ref({ running: false, tip: '', error: '' })

const confirming = ref(false)
const confirmWord = ref('')
const dataState = ref({ running: false, tip: '', error: '' })

const accountOpen = ref(false)
const accountWord = ref('')
const accountState = ref({ running: false, error: '' })

function errText(e) {
  const detail = e?.response?.data?.detail
  // FastAPI 校验错误是数组，别把整段英文 JSON 甩给用户
  if (Array.isArray(detail)) {
    const first = detail[0]
    return first?.msg ? `输入格式不对：${first.msg}` : '输入格式不对，检查一下再提交'
  }
  return detail || e?.message || '未知错误'
}

async function loadServerStatus() {
  try {
    const { data } = await api.get('/config/llm')
    server.value = {
      env_configured: data?.env_configured ?? null,
      tts_env_configured: data?.tts_env_configured ?? null,
      default_tts_base_url: data?.default_tts_base_url || '',
      default_tts_model: data?.default_tts_model || '',
      default_tts_voice: data?.default_tts_voice || '',
      error: '',
    }
    if (!modelInput.value && data?.default_model) modelInput.value = data.default_model
    if (!baseInput.value && data?.default_base_url) baseInput.value = data.default_base_url
    // 语音合成的输入框也填「页面上教的供应商」那套，而不是服务端的 OpenAI 出厂值：
    // 服务端默认值只用于 placeholder，避免「保存成功但请求打到别家」
    const d = ttsDefaults()
    if (!ttsInput.value.base) ttsInput.value.base = d.base
    if (!ttsInput.value.model) ttsInput.value.model = d.model
    if (!ttsInput.value.voice) ttsInput.value.voice = d.voice
  } catch (e) {
    server.value = { env_configured: null, tts_env_configured: null, error: errText(e) }
  }
}

const SCOPES = [
  { id: 'gaokao', label: '高考' },
  { id: 'cet4', label: '四级' },
  { id: 'cet6', label: '六级' },
]
const prefsTip = ref({ running: false, message: '' })

// 偏好存服务端（换设备跟着走），localStorage 只当兜底缓存
async function loadPrefs() {
  try {
    const { data } = await api.get('/me/settings')
    if (data?.practice_difficulty) settings.setPrefDifficulty(data.practice_difficulty)
    if (data?.word_scope) settings.setWordScope(data.word_scope)
  } catch {
    // 接口不可用就用本地缓存
  }
}

async function pickDifficulty(value) {
  prefsTip.value = { running: true, message: '' }
  try {
    await api.patch('/me/settings', { practice_difficulty: value })
    settings.setPrefDifficulty(value)
    prefsTip.value = { running: false, message: `已设为${diffLabel(value)}` }
  } catch (e) {
    prefsTip.value = { running: false, message: '保存失败：' + (e?.response?.data?.detail || e.message) }
  }
}

async function pickScope(id) {
  prefsTip.value = { running: true, message: '' }
  try {
    await api.patch('/me/settings', { word_scope: id })
    settings.setWordScope(id)
    prefsTip.value = { running: false, message: `新词范围已设为${SCOPES.find((s) => s.id === id)?.label || id}` }
  } catch (e) {
    prefsTip.value = { running: false, message: '保存失败：' + (e?.response?.data?.detail || e.message) }
  }
}

onMounted(() => nextTick(watchSections))

onMounted(async () => {
  await loadPrefs()
  await loadServerStatus()
  // 从「去设置填密钥」跳进来时，直接落到模型密钥那块，别让人对着个人资料找。
  // 上面两块内容刚撑开，等两帧再滚，并在 120ms 后补一次，避免布局变化把位置顶回去
  if (!onboarding.value) return
  await nextTick()
  const jumpToKey = () => {
    const el = document.getElementById('key')
    if (!el) return
    const top = el.getBoundingClientRect().top + window.scrollY - 72
    window.scrollTo({ top: Math.max(0, top), behavior: 'auto' })
  }
  requestAnimationFrame(() => {
    jumpToKey()
    setTimeout(jumpToKey, 120)
  })
})

function saveKey() {
  settings.save({ apiKey: keyInput.value, baseUrl: baseInput.value, model: modelInput.value })
  saveTip.value = '已保存到本浏览器。'
  if (onboarding.value && settings.configured) router.push('/')
}

async function testKey() {
  testState.value = { running: true, ok: null, message: '正在发一次最小请求…' }
  settings.save({ apiKey: keyInput.value, baseUrl: baseInput.value, model: modelInput.value })
  try {
    const { data } = await api.post('/config/llm/test', {})
    if (data.ok) {
      testState.value = { running: false, ok: true, message: `连通 · 模型 ${data.model || '—'} · ${data.latency_ms ?? '—'} ms` }
    } else {
      const labels = {
        invalid_key: '密钥无效或被拒绝',
        timeout: '请求超时',
        unreachable: '服务不可达',
      }
      const why = labels[data.error_kind] || '调用失败'
      testState.value = { running: false, ok: false, message: `${why}${data.error ? '：' + data.error : ''}` }
    }
  } catch (e) {
    testState.value = { running: false, ok: false, message: errText(e) }
  }
}

function clearKey() {
  settings.clear()
  keyInput.value = ''
  baseInput.value = ''
  modelInput.value = ''
  saveTip.value = '已从本浏览器删除。'
}

async function saveNickname() {
  const nickname = nicknameInput.value.trim()
  profileState.value = { running: true, tip: '', error: '' }
  if (!nickname) {
    profileState.value = { running: false, tip: '', error: '昵称不能为空' }
    return
  }
  try {
    const { data } = await api.patch('/me/profile', { nickname })
    auth.setAuth(auth.token, { ...(auth.user || {}), ...data })
    nicknameInput.value = data?.nickname || nickname
    profileState.value = { running: false, tip: '昵称已更新。', error: '' }
  } catch (e) {
    profileState.value = { running: false, tip: '', error: errText(e) }
  }
}

async function changePassword() {
  pwdState.value = { running: true, tip: '', error: '' }
  if (!pwd.value.current) {
    pwdState.value = { running: false, tip: '', error: '请先填当前密码' }
    return
  }
  if (pwd.value.next.length < 6 || pwd.value.next.length > 64) {
    pwdState.value = { running: false, tip: '', error: '新密码要 6–64 位' }
    return
  }
  if (pwd.value.next !== pwd.value.confirm) {
    pwdState.value = { running: false, tip: '', error: '两次输入的新密码不一致' }
    return
  }
  try {
    const { data } = await api.patch('/me/profile', {
      password: pwd.value.next,
      current_password: pwd.value.current,
    })
    // 改密码会让 token_version +1，其他设备立刻掉线；响应里签发的新 token 必须存回去，
    // 否则这台设备下一次请求也会 401
    const { token: freshToken, ...profile } = data || {}
    if (freshToken) auth.setAuth(freshToken, { ...(auth.user || {}), ...profile })
    pwd.value = { current: '', next: '', confirm: '' }
    pwdState.value = { running: false, tip: '密码已更新，下次登录用新密码。', error: '' }
  } catch (e) {
    pwdState.value = { running: false, tip: '', error: errText(e) }
  }
}

async function clearData() {
  if (confirmWord.value.trim() !== '删除') {
    dataState.value = { running: false, tip: '', error: '请先输入「删除」两个字' }
    return
  }
  dataState.value = { running: true, tip: '', error: '' }
  try {
    const { data } = await api.delete('/me/data')
    await clearRecordings()
    const sessions = data.deleted_sessions ?? 0
    const reports = data.deleted_reports ?? 0
    dataState.value = {
      running: false,
      // 本来就没有数据时要说清「没有可删的」，否则「已删除 0 次练习」看着像没反应
      tip:
        sessions === 0 && reports === 0
          ? '这个账号还没有练习记录，没有可删除的内容。'
          : `已删除 ${sessions} 次练习、${reports} 份报告。`,
      error: '',
    }
    confirming.value = false
    confirmWord.value = ''
  } catch (e) {
    dataState.value = { running: false, tip: '', error: errText(e) }
  }
}

async function deleteAccount() {
  if (accountWord.value.trim() !== '注销') {
    accountState.value = { running: false, error: '请先输入「注销」两个字' }
    return
  }
  accountState.value = { running: true, error: '' }
  try {
    await api.delete('/me/account', { data: { confirm: accountWord.value.trim() } })
    settings.clear()
    auth.logout()
    router.push('/login')
  } catch (e) {
    accountState.value = { running: false, error: errText(e) }
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="设置" back="/">
      <button class="sp-btn-ghost sm:hidden" @click="logout">退出</button>
    </AppHeader>

    <main class="sp-shell pb-16 pt-10">
      <div class="mb-8">
        <div class="sp-eyebrow">设置</div>
        <h1 class="sp-title mt-2">账号、密钥与偏好</h1>
        <p class="sp-lede">密钥只存在你自己的浏览器里；练习数据按账号存在服务端，可以随时自己删掉。</p>
      </div>
      <div class="sp-grid items-start">
      <aside class="lg:sticky lg:top-24 lg:col-span-3">
        <nav class="flex gap-1.5 overflow-x-auto pb-1 lg:flex-col lg:gap-0.5 lg:overflow-visible" aria-label="设置分区">
          <a
            v-for="sec in SECTIONS"
            :key="sec.id"
            :href="`#${sec.id}`"
            class="whitespace-nowrap rounded-xl px-3.5 py-2 text-sm transition duration-200"
            :class="activeSection === sec.id
              ? 'bg-white font-medium text-ink shadow-soft ring-1 ring-line/80'
              : 'text-ink-mute hover:bg-white/70 hover:text-ink'"
            @click="activeSection = sec.id"
          >
            {{ sec.label }}
          </a>
        </nav>
        <button class="sp-btn-ghost mt-4 hidden w-full justify-start lg:inline-flex" @click="logout">退出登录</button>
      </aside>

      <div class="min-w-0 space-y-5 lg:col-span-9">
      <p v-if="onboarding" class="sp-alert-warn">
        配一下你自己的模型密钥，之后每次练习都用它调用评分模型。
        <button class="ml-2 font-medium underline" @click="router.push('/')">先跳过</button>
      </p>


      <section id="profile" class="sp-card scroll-mt-24 p-6 sm:p-7">
        <h2 class="sp-section-title">个人资料</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          昵称只影响显示，不影响登录账号<span v-if="auth.user?.username">（{{ auth.user.username }}）</span>。
        </p>

        <div class="mt-4 flex flex-wrap items-end gap-2">
          <label class="min-w-0 flex-1 text-sm">
            <span class="mb-1.5 block text-xs font-medium text-ink-mute">昵称</span>
            <input v-model="nicknameInput" class="sp-input" placeholder="昵称" maxlength="32" />
          </label>
          <button class="sp-btn-primary" :disabled="profileState.running" @click="saveNickname">保存昵称</button>
        </div>
        <p v-if="profileState.tip" class="mt-2 text-xs text-good">{{ profileState.tip }}</p>
        <p v-if="profileState.error" class="mt-2 text-xs text-danger">{{ profileState.error }}</p>

        <div class="mt-6 border-t border-line pt-5">
          <div class="text-sm font-medium text-ink">修改密码</div>
          <div class="mt-3 grid gap-3 sm:grid-cols-3">
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">当前密码</span>
              <input v-model="pwd.current" type="password" autocomplete="current-password" class="sp-input" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">新密码</span>
              <input v-model="pwd.next" type="password" autocomplete="new-password" class="sp-input" placeholder="6–64 位" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">再输一次</span>
              <input v-model="pwd.confirm" type="password" autocomplete="new-password" class="sp-input" />
            </label>
          </div>
          <div class="mt-3 flex items-center gap-3">
            <button class="sp-btn-secondary" :disabled="pwdState.running" @click="changePassword">
              {{ pwdState.running ? '提交中…' : '修改密码' }}
            </button>
          </div>
          <p v-if="pwdState.tip" class="mt-2 text-xs text-good">{{ pwdState.tip }}</p>
          <p v-if="pwdState.error" class="mt-2 text-xs text-danger">{{ pwdState.error }}</p>
        </div>
      </section>

      <section id="prefs" class="sp-card scroll-mt-24 p-6 sm:p-7">
        <h2 class="sp-section-title">练习偏好</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">新开的练习用这一档，历史和报告里的「再练一次」也用这一档。</p>
        <div class="mt-4 inline-flex rounded-xl bg-canvas p-1 ring-1 ring-line">
          <button
            v-for="d in DIFFICULTIES"
            :key="d.value"
            class="rounded-lg px-4 py-1.5 text-sm transition"
            :class="settings.prefDifficulty === d.value ? 'bg-white font-medium text-brand-700 shadow-sm' : 'text-ink-mute hover:text-ink-soft'"
            :disabled="prefsTip.running"
            @click="pickDifficulty(d.value)"
          >
            {{ d.label }}
          </button>
        </div>

        <div class="mt-6">
          <div class="text-xs font-medium text-ink-mute">新词范围</div>
          <p class="mt-1 text-[11px] leading-5 text-ink-mute">学新单词从这一档里挑。</p>
          <div class="mt-2 inline-flex rounded-xl bg-canvas p-1 ring-1 ring-line">
            <button
              v-for="s in SCOPES"
              :key="s.id"
              class="rounded-lg px-4 py-1.5 text-sm transition"
              :class="settings.wordScope === s.id ? 'bg-white font-medium text-brand-700 shadow-sm' : 'text-ink-mute hover:text-ink-soft'"
              :disabled="prefsTip.running"
              @click="pickScope(s.id)"
            >
              {{ s.label }}
            </button>
          </div>
        </div>

        <p class="mt-3 text-xs leading-5 text-ink-mute">
          {{ prefsTip.message || '换台电脑登录，这一档也跟着你。' }}
        </p>
      </section>

<section id="key" class="sp-card scroll-mt-24 p-6 sm:p-7">
        <h2 class="sp-section-title">模型密钥</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          只存在这个浏览器里，不上传、不写数据库、不写日志。
        </p>
        <p class="mt-1 text-xs leading-5 text-ink-mute">
          没有 key？
          <a
            href="https://platform.deepseek.com/api_keys"
            target="_blank"
            rel="noopener noreferrer"
            class="font-medium text-brand-700 underline-offset-2 hover:underline"
          >打开 DeepSeek 控制台 → API keys</a>
          ：注册登录后点「创建 API key」，复制以 <code>sk-</code> 开头的那串粘到上面。
        </p>

        <div class="mt-4 space-y-3">
          <label class="block text-sm">
            <span class="mb-1.5 block text-xs font-medium text-ink-mute">API Key</span>
            <input
              v-model="keyInput"
              type="password"
              autocomplete="off"
              placeholder="sk-…"
              class="sp-input font-mono"
            />
          </label>

          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">Base URL</span>
              <input v-model="baseInput" placeholder="https://api.deepseek.com/v1" class="sp-input" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">模型</span>
              <input v-model="modelInput" placeholder="deepseek-chat" class="sp-input" />
            </label>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <button class="sp-btn-primary" :disabled="!keyInput.trim()" @click="saveKey">保存</button>
            <button class="sp-btn-secondary" :disabled="testState.running || !keyInput.trim()" @click="testKey">
              {{ testState.running ? '测试中…' : '测试连接' }}
            </button>
            <button v-if="settings.configured" class="sp-btn-ghost text-danger hover:bg-rose-50" @click="clearKey">
              删除本浏览器密钥
            </button>
          </div>

          <p v-if="saveTip" class="text-xs text-good">{{ saveTip }}</p>
          <p
            v-if="testState.message"
            class="text-xs"
            :class="testState.ok === false ? 'text-danger' : 'text-ink-soft'"
          >
            {{ testState.message }}
          </p>
          <p class="text-xs leading-5 text-ink-mute">
            当前：{{ settings.configured ? `已配置 ${settings.masked}` : '本浏览器未配置' }}
            <span v-if="server.error">· 读取服务端状态失败：{{ server.error }}</span>
          </p>
        </div>
      </section>

<section id="tts" class="sp-card scroll-mt-24 p-6 sm:p-7">
        <h2 class="sp-section-title">语音合成</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          <span class="font-medium text-ink">这是朗读用的 key，和上面的对话密钥不是同一把</span>；填错不影响评分，只会让声音不自然。
          不填就用浏览器自带的朗读，不需要任何 key；填了会走第三方语音合成，按你自己的额度计费。
        </p>
        <p class="mt-1 text-xs leading-5 text-ink-mute">
          怎么拿：
          <a
            href="https://cloud.siliconflow.cn/account/ak"
            target="_blank"
            rel="noopener noreferrer"
            class="font-medium text-brand-700 underline-offset-2 hover:underline"
          >硅基流动 → API 密钥</a>
          （<a
            href="https://docs.siliconflow.cn/docs/userguide/capabilities/text-to-speech"
            target="_blank"
            rel="noopener noreferrer"
            class="font-medium text-brand-700 underline-offset-2 hover:underline"
          >语音合成文档</a>
          ）。Base URL、模型、音色留空就用默认值，粘贴 key 保存即可。
        </p>

        <div class="mt-4 space-y-3">
          <label class="block text-sm">
            <span class="mb-1.5 block text-xs font-medium text-ink-mute">语音合成 API Key</span>
            <input
              v-model="ttsInput.key"
              type="password"
              autocomplete="off"
              placeholder="sk-…"
              class="sp-input font-mono"
            />
          </label>

          <div class="grid gap-3 sm:grid-cols-3">
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">Base URL</span>
              <input v-model="ttsInput.base" :placeholder="ttsDefaults().base" class="sp-input" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">模型</span>
              <input v-model="ttsInput.model" :placeholder="ttsDefaults().model" class="sp-input" />
            </label>
            <label class="block text-sm">
              <span class="mb-1.5 block text-xs font-medium text-ink-mute">音色</span>
              <input v-model="ttsInput.voice" :placeholder="ttsDefaults().voice" class="sp-input" />
            </label>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <button class="sp-btn-primary" :disabled="!ttsInput.key.trim()" @click="saveTts">保存</button>
            <button class="sp-btn-secondary" :disabled="ttsTest.running" @click="testTts">
              {{ ttsTest.running ? '试听中…' : '试听一句' }}
            </button>
            <button v-if="settings.ttsConfigured" class="sp-btn-ghost text-danger hover:bg-rose-50" @click="clearTts">
              删除语音合成密钥
            </button>
          </div>

          <p v-if="ttsTip" class="text-xs text-good">{{ ttsTip }}</p>
          <p
            v-if="ttsTest.message"
            class="text-xs leading-5"
            :class="ttsTest.ok === false ? 'text-danger' : 'text-good'"
          >
            {{ ttsTest.message }}
          </p>
          <p class="text-xs leading-5 text-ink-mute">
            当前：{{ settings.ttsConfigured ? `已配置 ${settings.ttsMasked} · 朗读走第三方语音合成` : '未配置 · 使用浏览器朗读' }}
            <span v-if="server.tts_env_configured === true">· 服务端已配置兜底语音密钥</span>
          </p>
        </div>
      </section>

<section id="data" class="sp-card scroll-mt-24 p-6 ring-rose-100 sm:p-7">
        <h2 class="sp-section-title">清除练习记录</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          只删除你自己的练习记录和报告，账号保留，别人的数据不受影响。删除后不可恢复。
        </p>
        <div class="mt-4 space-y-2 text-sm">
          <button v-if="!confirming" class="sp-btn-secondary text-danger hover:ring-rose-300" :disabled="dataState.running" @click="confirming = true">
            清除我的练习数据
          </button>
          <template v-else>
            <p class="text-ink-soft">确认删除你的全部练习记录与报告？输入「删除」两个字再点确认。</p>
            <div class="flex flex-wrap items-center gap-2">
              <input v-model="confirmWord" placeholder="删除" class="sp-input w-24" />
              <button class="sp-btn bg-danger text-white hover:bg-rose-700" :disabled="dataState.running" @click="clearData">
                {{ dataState.running ? '删除中…' : '确认删除' }}
              </button>
              <button class="sp-btn-ghost" @click="confirming = false; confirmWord = ''">取消</button>
            </div>
          </template>
        </div>
        <p v-if="dataState.tip" class="mt-3 text-xs text-good">{{ dataState.tip }}</p>
        <p v-if="dataState.error" class="mt-3 text-xs text-danger">{{ dataState.error }}</p>
      </section>

<section id="account" class="sp-card scroll-mt-24 p-6 ring-rose-100 sm:p-7">
        <h2 class="sp-section-title">注销账号</h2>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          会删除账号本身，以及这个账号名下的全部练习记录、对话和报告，之后无法登录、无法恢复。
          只清记录不删账号的话，用上面那段。
        </p>
        <div class="mt-4 space-y-2 text-sm">
          <button v-if="!accountOpen" class="sp-btn-secondary text-danger hover:ring-rose-300" @click="accountOpen = true">
            注销我的账号
          </button>
          <template v-else>
            <p class="text-ink-soft">确认注销「{{ auth.user?.username || '当前账号' }}」？输入「注销」两个字再点确认。</p>
            <div class="flex flex-wrap items-center gap-2">
              <input v-model="accountWord" placeholder="注销" class="sp-input w-24" />
              <button class="sp-btn bg-danger text-white hover:bg-rose-700" :disabled="accountState.running" @click="deleteAccount">
                {{ accountState.running ? '注销中…' : '确认注销' }}
              </button>
              <button class="sp-btn-ghost" @click="accountOpen = false; accountWord = ''">取消</button>
            </div>
          </template>
          <p v-if="accountState.error" class="text-xs text-danger">{{ accountState.error }}</p>
        </div>
      </section>



      <p class="pb-4 text-center text-xs text-ink-mute">
        密钥只在你的浏览器里；练习数据按账号存在服务端，可以随时自己删掉。
      </p>

      <div class="pb-6 text-center">
        <button class="sp-btn-ghost text-xs" @click="router.push('/welcome?again=1')">再看一遍新手引导</button>
      </div>
      </div>
      </div>
    </main>

    <TabBar />
  </div>
</template>
