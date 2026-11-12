<script setup>
import { computed, markRaw, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import { useSessionStore } from '../stores/session'
import { useSettingsStore } from '../stores/settings'
import { loadRecordings, playRecording, stopRecording } from '../utils/recordings'
import { createRecognizer, speakSmart, stopSpeaking } from '../utils/speech'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const settings = useSettingsStore()

const report = ref(null)
const error = ref('')
const drillError = ref('')
const missing = ref(false)
const meta = ref(null)

const MODE_LABELS = { typed: '打字', voice: '录音', mixed: '混合' }

function when(iso) {
  if (!iso) return ''
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 报告首屏要知道「这是哪次练习」：场景 · 作答方式 · 时间
const metaLine = computed(() => {
  const m = meta.value || {}
  const mode = MODE_LABELS[m.answer_mode] || MODE_LABELS[report.value?.answer_mode] || ''
  return [m.scene_name, mode, when(m.created_at || m.finished_at)].filter(Boolean).join(' · ')
})

const dimLabels = {
  pronunciation: '发音清晰度',
  fluency: '流利度',
  grammar_vocab: '语法词汇',
  task_completion: '任务完成度',
  written_expression: '文字表达',
}

const featureLabels = {
  word_count: '词数',
  filler_count: '填充词数',
  filler_rate: '填充词占比',
  ttr: '词汇多样性 TTR',
  mtld: '词汇多样性 MTLD',
  diversity_metric: '多样性口径',
  diversity: '多样性取值',
  sentence_count: '句子数',
  mean_sentence_len: '平均句长',
  audio_duration_sec: '录音时长（秒）',
  speech_rate_wpm: '语速（词/分）',
  articulation_rate_wpm: '发音速度（词/分）',
  pause_count: '停顿次数',
  mean_pause_sec: '平均停顿（秒）',
  pause_ratio: '停顿占比',
  voice_turns: '录音轮数',
  typed_turns: '打字轮数',
  answer_mode: '作答方式',
}

const isMock = computed(() => report.value?.source === 'mock')
// 打字作答不会给发音/流利度打分：这两个键在维度里不出现，就必须在报告顶部讲清楚，
// 否则用户会以为系统替他打了发音分
const typedOnly = computed(() => {
  const dims = Object.keys(report.value?.dimensions || {})
  if (!dims.length) return false
  return !dims.includes('pronunciation') && !dims.includes('fluency')
})
const mixedInput = computed(() => {
  const dims = Object.keys(report.value?.dimensions || {})
  return dims.includes('pronunciation') || dims.includes('fluency')
    ? dims.includes('written_expression')
    : false
})

// 后端直接给 answer_mode，比查维度键更稳；老数据没有这个字段时才退回查键
const answerMode = computed(() => report.value?.answer_mode || '')
const showTypedBanner = computed(
  () => !isMock.value && (answerMode.value === 'typed' || (!answerMode.value && typedOnly.value))
)
const showMixedBanner = computed(
  () => !isMock.value && (answerMode.value === 'mixed' || (!answerMode.value && mixedInput.value))
)
const mockReason = computed(() => report.value?.mock_reason || '')
const mockHint = computed(() => {
  switch (mockReason.value) {
    case 'not_configured':
      return '这次练习没有可用的模型密钥，所以没出分。去「设置」里填一个密钥，再练一次就能拿到完整评分。'
    case 'invalid_key':
      // 服务端兜底已取消，这个值只会出现在历史报告里；按「当时密钥失效」解释，不再提服务端兜底
      return '这次练习用的模型密钥失效了，所以没出分。去「设置」里换一个能用的密钥，再练一次就能拿到完整评分。'
    case 'unavailable':
      return '评分服务这次没连上（网络中断或超时），所以没出分。过一会儿再练一次就行，你的发言记录已经保存。'
    default:
      return '这次没有拿到评分结果，因此不计分、不给等级。下面列出的句子都是你真实说过的内容，不是示例句。'
  }
})
const showMockSettingsLink = computed(
  () => mockReason.value === 'not_configured' || mockReason.value === 'invalid_key' || !mockReason.value
)
const hasScore = computed(() => report.value?.total_score !== null && report.value?.total_score !== undefined)
// 本轮目标达成：老报告没有 plan 字段，整块不显示
const reportPlan = computed(() => report.value?.plan || {})
const reportGoals = computed(() => reportPlan.value.goals || [])
const reportAchieved = computed(() => reportPlan.value.achieved || [])

// ---- 评分量表切换（hero 卡内；总分换考试读法，维度始终只给雅思 + CEFR）----
const SCALE_OPTIONS = [
  { id: 'ielts', label: '雅思' },
  { id: 'cefr', label: 'CEFR' },
  { id: 'toefl', label: '托福' },
  { id: 'duolingo', label: '多邻国' },
  { id: 'cet', label: '四六级' },
]
const scaleEls = []
const ghostLayer = ref(null)
const pillBoxEl = ref(null)
const pillHidden = ref(false)
const scaleInfoOpen = ref(false)
const scaleInfoEl = ref(null)
const ghostEls = []
let switchToken = 0

const scaleItems = computed(() => report.value?.scales?.items || null)
const hasScales = computed(() => !!scaleItems.value)
const activeScale = computed(() => settings.reportScale)
const scaleVersion = computed(() => report.value?.scales?.version || '2026-11')
// scales 缺失（老后端）时回退到 band / cefr
const legacyScales = computed(
  () => !hasScales.value && report.value?.band !== null && report.value?.band !== undefined
)

// 四六级通过线从 band 4.0（B1）起算，与后端换算表里的 425 分线一致
const cetPassed = computed(() => typeof report.value?.band === 'number' && report.value.band >= 4.0)
const cetRangeText = computed(() => {
  const cet = scaleItems.value?.cet
  if (!cet) return '—'
  return `CET-4 ${cet.cet4 || '—'} · CET-6 ${cet.cet6 || '—'}`
})
const cetPassPills = computed(() => [
  { id: 'cet4', label: `CET-4 ${cetPassed.value ? '已通过' : '未通过'}`, passed: cetPassed.value },
  { id: 'cet6', label: `CET-6 ${cetPassed.value ? '已通过' : '未通过'}`, passed: cetPassed.value },
])

// 药丸四种读法 + 两种兜底：雅思单点（衬线）/ 字母 / 区间 / 四六级（两档或两枚通过水平）
const pillKind = computed(() => {
  if (legacyScales.value) return 'legacy'
  if (!hasScales.value) return 'below'
  const one = activeScale.value
  if (one === 'cet') return settings.cetPassOnly ? 'cet-pass' : 'cet'
  return one
})
const pillValue = computed(() => {
  const items = scaleItems.value
  if (!items) return ''
  if (activeScale.value === 'cet') return cetRangeText.value
  return items[activeScale.value]?.display || ''
})
// ghost 用的一行文本（与药丸内容一致，四六级通过水平合并成一行）
const pillFlatText = computed(() => {
  if (pillKind.value === 'below') return '低于 A2 · 暂不评级'
  if (pillKind.value === 'cet-pass') return cetPassPills.value.map((p) => p.label).join(' · ')
  if (pillKind.value === 'legacy') {
    if (activeScale.value === 'ielts') return `雅思 ${report.value?.band}`
    if (activeScale.value === 'cefr') return `CEFR ${report.value?.cefr}`
    return '—'
  }
  const name = SCALE_OPTIONS.find((s) => s.id === activeScale.value)?.label || ''
  return `${name} ${pillValue.value}`.trim()
})
const scaleRows = computed(() => {
  const items = scaleItems.value
  if (!items) return []
  return [
    { id: 'ielts', label: '雅思', value: items.ielts?.display || '—', reference: false },
    { id: 'cefr', label: 'CEFR', value: items.cefr?.display || '—', reference: false },
    { id: 'toefl', label: '托福', value: items.toefl?.display || '—', reference: false },
    { id: 'duolingo', label: '多邻国', value: items.duolingo?.display || '—', reference: false },
    { id: 'cet', label: '四六级', value: cetRangeText.value, reference: true },
  ]
})

function dimBand(name) {
  const fromScales = report.value?.scales?.dimensions?.[name]?.ielts
  if (typeof fromScales === 'number') return fromScales.toFixed(1)
  const b = report.value?.bands?.[name]
  if (b === null || b === undefined) return ''
  return typeof b === 'number' ? b.toFixed(1) : b
}

function dimCefr(name) {
  return report.value?.scales?.dimensions?.[name]?.cefr || ''
}

function clearGhosts() {
  ghostEls.splice(0).forEach((el) => el.remove())
}

function pillTextStyle() {
  const el = pillBoxEl.value?.querySelector('[data-pill-text]')
  if (!el) return null
  const cs = getComputedStyle(el)
  return {
    fontFamily: cs.fontFamily,
    fontSize: cs.fontSize,
    fontWeight: cs.fontWeight,
    color: cs.color,
    lineHeight: cs.lineHeight,
  }
}

// 角标/飞行副本：固定层里按视口坐标摆，字体与药丸一致
function makeGhost(text, style) {
  const layer = ghostLayer.value
  if (!layer || !style) return null
  const el = document.createElement('span')
  el.textContent = text
  el.style.cssText =
    'position:absolute;pointer-events:none;white-space:nowrap;' +
    `font-family:${style.fontFamily};font-size:${style.fontSize};font-weight:${style.fontWeight};` +
    `color:${style.color};line-height:${style.lineHeight};`
  layer.appendChild(el)
  ghostEls.push(el)
  return el
}

function placeGhost(el, centerX, centerY) {
  const rect = el.getBoundingClientRect()
  el.style.left = `${centerX - rect.width / 2}px`
  el.style.top = `${centerY - rect.height / 2}px`
}

async function persistScale(id) {
  try {
    await api.patch('/me/settings', { report_scale: id })
  } catch {
    // 静默：本次展示已生效，下次进来回到服务端值
  }
}

async function pickScale(id, event) {
  if (id === activeScale.value || !hasScales.value) return
  const token = ++switchToken
  clearGhosts()
  const from = SCALE_OPTIONS.findIndex((s) => s.id === activeScale.value)
  const to = SCALE_OPTIONS.findIndex((s) => s.id === id)
  const dir = to > from ? 1 : -1
  const chip = event?.currentTarget || scaleEls[to]
  const chipRect = chip?.getBoundingClientRect()
  const oldText = pillFlatText.value
  const oldStyle = pillTextStyle()
  const oldTextEl = pillBoxEl.value?.querySelector('[data-pill-text]')
  const oldRect = oldTextEl?.getBoundingClientRect()

  // 立即换数据：药丸宽度一次性到位，不做宽度动画
  settings.setReportScale(id)
  persistScale(id)
  pillHidden.value = true

  if (reducedMotion()) {
    // 无 ghost、无位移，只做 120ms 透明度交叉
    await nextTick()
    pillHidden.value = false
    pillBoxEl.value?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120, easing: 'ease-out' })
    return
  }

  // 1) 旧值退场：120ms，按新 chip 的相对方向轻推 ∓6px
  if (oldRect && oldStyle) {
    const exit = makeGhost(oldText, oldStyle)
    if (exit) {
      placeGhost(exit, oldRect.left + oldRect.width / 2, oldRect.top + oldRect.height / 2)
      exit
        .animate(
          [
            { opacity: 1, transform: 'translateX(0px)' },
            { opacity: 0, transform: `translateX(${-dir * 6}px)` },
          ],
          { duration: 120, easing: 'ease-out', fill: 'forwards' }
        )
        .finished.then(() => exit.remove(), () => exit.remove())
    }
  }

  // 2) 新值 ghost：从被点 chip 中心飞进药丸中心（200ms，延迟 60ms）
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 60))
  if (token !== switchToken) return
  const box = pillBoxEl.value
  const style = pillTextStyle() || oldStyle
  const target = (box?.querySelector('[data-pill-text]') || box)?.getBoundingClientRect()
  if (!box || !chipRect || !target || !style) {
    pillHidden.value = false
    return
  }
  const ghost = makeGhost(pillFlatText.value, style)
  if (!ghost) {
    pillHidden.value = false
    return
  }
  const startX = chipRect.left + chipRect.width / 2
  const startY = chipRect.top + chipRect.height / 2
  placeGhost(ghost, startX, startY)
  const dx = target.left + target.width / 2 - startX
  const dy = target.top + target.height / 2 - startY
  ghost
    .animate(
      [
        { transform: 'translate(0px, 0px) scale(0.86)' },
        { transform: `translate(${dx}px, ${dy}px) scale(1)` },
      ],
      { duration: 200, easing: 'cubic-bezier(0.3,0.9,0.25,1)' }
    )
    .finished.then(
      () => {
        ghost.remove()
        if (token !== switchToken) return
        // 3) 到达后真药丸 100ms 淡入
        pillHidden.value = false
        nextTick(() => box.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 100, easing: 'ease-out' }))
      },
      () => ghost.remove()
    )
}

function onScaleKeydown(event, i) {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
  event.preventDefault()
  const delta = event.key === 'ArrowRight' ? 1 : -1
  const next = (i + delta + SCALE_OPTIONS.length) % SCALE_OPTIONS.length
  pickScale(SCALE_OPTIONS[next].id)
  nextTick(() => scaleEls[next]?.focus())
}

// 换算说明：桌面居中卡 / 窄屏底部 sheet
async function openScaleInfo() {
  scaleInfoOpen.value = true
  await nextTick()
  const el = scaleInfoEl.value
  if (!el || reducedMotion()) return
  const narrow = window.matchMedia('(max-width: 639px)').matches
  el.animate(
    narrow
      ? [
          { transform: 'translateY(24px)', opacity: 0 },
          { transform: 'translateY(0)', opacity: 1 },
        ]
      : [
          { transform: 'scale(0.98)', opacity: 0 },
          { transform: 'scale(1)', opacity: 1 },
        ],
    { duration: narrow ? 260 : 200, easing: 'cubic-bezier(0.2,0.7,0.2,1)' }
  )
}

async function closeScaleInfo() {
  const el = scaleInfoEl.value
  if (el && !reducedMotion()) {
    const narrow = window.matchMedia('(max-width: 639px)').matches
    const anim = el.animate(
      narrow
        ? [
            { transform: 'translateY(0)', opacity: 1 },
            { transform: 'translateY(24px)', opacity: 0 },
          ]
        : [
            { transform: 'scale(1)', opacity: 1 },
            { transform: 'scale(0.98)', opacity: 0 },
          ],
      { duration: 180, easing: 'ease-out', fill: 'forwards' }
    )
    await anim.finished.catch(() => {})
  }
  scaleInfoOpen.value = false
}

function onScaleInfoKeydown(event) {
  if (event.key === 'Escape' && scaleInfoOpen.value) closeScaleInfo()
}

const displayFeatures = computed(() => {
  const src = report.value?.features || {}
  const wordCount = Number(src.word_count ?? 0)
  const out = {}
  for (const [k, v] of Object.entries(src)) {
    if (v === null || v === undefined) continue
    // 没有中文标签的字段一律不渲染，后端以后新增字段也不会漏出英文键
    if (!featureLabels[k]) continue
    // 打字作答没有录音，填充词这类口语指标没意义
    if (typedOnly.value && (k === 'filler_count' || k === 'filler_rate')) continue
    // 词数太少时 TTR / MTLD 必然接近满分，会骗人
    if ((k === 'ttr' || k === 'mtld' || k === 'diversity' || k === 'diversity_metric') && wordCount < 20) continue
    let val = typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v
    if (k === 'diversity_metric' && typeof val === 'string') val = val.toUpperCase()
    out[k] = val
  }
  return out
})

// ---- 页签：概览 / 逐句纠错 / 指标（规格 2.1–2.3）----
const TABS = computed(() => [
  { key: 'overview', label: '概览', count: 0 },
  { key: 'fixes', label: '逐句纠错', count: report.value?.sentence_fixes?.length || 0 },
  { key: 'metrics', label: '指标', count: Object.keys(displayFeatures.value).length },
])
const tab = ref('overview')
// 1 = 向后（索引变大），-1 = 向前；进出场位移方向用它
const tabDir = ref(1)
const tabEls = []
const railEl = ref(null)
const railNatural = ref(0)
const tabInd = reactive({ x: 0, w: 0, show: false })
const tabAnimating = ref(false)

function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function measureTab(key) {
  const i = TABS.value.findIndex((t) => t.key === key)
  const el = tabEls[i]
  if (!el || !el.offsetWidth) return null
  return { x: el.offsetLeft, w: el.offsetWidth }
}

function placeIndicator(key, withAnim) {
  const m = measureTab(key)
  if (!m) {
    tabInd.show = false
    return
  }
  tabAnimating.value = withAnim
  tabInd.x = m.x
  tabInd.w = m.w
  tabInd.show = true
}

// 切换前若已滚过页签条，先把窗口立即滚回它的吸顶位置（无动画）
function alignRail() {
  const target = Math.max(0, railNatural.value - 64)
  if (window.scrollY > target) window.scrollTo({ top: target })
}

function setTab(next) {
  if (next === tab.value) return
  const from = TABS.value.findIndex((t) => t.key === tab.value)
  const to = TABS.value.findIndex((t) => t.key === next)
  if (to < 0) return
  tabDir.value = to > from ? 1 : -1
  alignRail()
  placeIndicator(next, true)
  tab.value = next
}

function onTabKeydown(event, i) {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
  event.preventDefault()
  const delta = event.key === 'ArrowRight' ? 1 : -1
  const next = (i + delta + TABS.value.length) % TABS.value.length
  setTab(TABS.value[next].key)
  nextTick(() => tabEls[next]?.focus())
}

// mode="out-in"：旧页先退（160ms），新页再进（240ms，延迟 80ms）
function tabEnter(el, done) {
  if (reducedMotion()) {
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120, easing: 'ease-out' }).finished.then(done, done)
    return
  }
  el.animate(
    [
      { opacity: 0, transform: `translateX(${tabDir.value * 16}px)` },
      { opacity: 1, transform: 'translateX(0)' },
    ],
    { duration: 240, delay: 80, easing: 'cubic-bezier(0.2,0.7,0.2,1)', fill: 'backwards' }
  ).finished.then(done, done)
}

function tabLeave(el, done) {
  if (reducedMotion()) {
    el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120, easing: 'ease-out' }).finished.then(done, done)
    return
  }
  el.animate(
    [
      { opacity: 1, transform: 'translateX(0)' },
      { opacity: 0, transform: `translateX(${-tabDir.value * 16}px)` },
    ],
    { duration: 160, easing: 'ease-out' }
  ).finished.then(done, done)
}

function onResize() {
  placeIndicator(tab.value, false)
}

onMounted(async () => {
  try {
    const { data } = await api.get(`/sessions/${route.params.id}/report`)
    report.value = data
    loadDrills()
  } catch (e) {
    if (e?.response?.status === 404) {
      // 从历史点进来的会话还没生成报告（中途退出/刷新丢态），别甩英文错误
      missing.value = true
      return
    }
    error.value = '加载报告失败：' + (e?.response?.data?.detail || e.message)
  }
  // 量表偏好跟账号走；读不到就用 localStorage 里上次的（规格 B7）
  try {
    const { data } = await api.get('/me/settings')
    if (data?.report_scale) settings.setReportScale(data.report_scale)
  } catch {
    // 未登录 / 接口不可用时保持本地值
  }
  await nextTick()
  if (railEl.value) railNatural.value = railEl.value.getBoundingClientRect().top + window.scrollY
  placeIndicator(tab.value, false)
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', onScaleInfoKeydown)
  try {
    const { data } = await api.get(`/sessions/${route.params.id}`)
    meta.value = data
  } catch {
    meta.value = null
  }
  const blobs = await loadRecordings(Number(route.params.id))
  for (const k of Object.keys(blobs)) blobs[k] = markRaw(blobs[k])
  recordings.value = blobs
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', onScaleInfoKeydown)
  clearGhosts()
  stopRecording()
})

// 本地录音（只在录这次练习的浏览器里有）：{ 第几句用户发言: Blob }
const recordings = ref({})
const playingFix = ref(-1)

function normText(text) {
  return String(text || '').toLowerCase().replace(/[^a-z0-9']+/g, ' ').trim()
}

// 每条纠错的原句是用户某一轮里的一句话：按文本包含关系找回那一轮的录音
const fixRecordings = computed(() => {
  const fixes = report.value?.sentence_fixes || []
  const turns = (meta.value?.turns || []).filter((t) => t.role === 'user')
  if (!fixes.length || !turns.length || !Object.keys(recordings.value).length) return []
  return fixes.map((f) => {
    const target = normText(f.original)
    if (!target) return null
    const idx = turns.findIndex((t) => t.input_mode === 'voice' && normText(t.content).includes(target))
    return idx >= 0 ? recordings.value[idx + 1] || null : null
  })
})

async function toggleFixPlayback(i) {
  if (playingFix.value === i) {
    stopRecording()
    playingFix.value = -1
    return
  }
  stopSpeaking()
  playingFix.value = i
  await playRecording(fixRecordings.value[i], () => {
    if (playingFix.value === i) playingFix.value = -1
  })
}

// 下一练：按推荐难度直接开一场，不用回首页重新选
async function nextPractice() {
  try {
    const rec = await api.get('/me/recommendation')
    const sceneId = rec?.data?.last_scene_id || meta.value?.scene_id
    const difficulty = settings.prefDifficulty || rec?.data?.recommended_difficulty || 'medium'
    if (!sceneId) {
      router.push('/')
      return
    }
    const { data } = await api.post('/sessions', { scene_id: sceneId })
    let usedDiff = difficulty
    try {
      const detail = await api.get(`/sessions/${data.session_id}`)
      usedDiff = detail?.data?.difficulty || usedDiff
    } catch {
      // 读不到就用本地偏好兜底
    }
    session.start(
      data.session_id,
      { id: sceneId, name: meta.value?.scene_name || '练习' },
      usedDiff,
      data.opening_question,
      data.plan
    )
    router.push(`/practice/${data.session_id}`)
  } catch (e) {
    error.value = '开始下一练失败：' + (e?.response?.data?.detail || e.message)
  }
}

// ---- 跟读重说：把报告的「改写句」做成练-错-立刻改的闭环 ----
const drills = ref({ items: [], pass_threshold: 0.85 })
const drillOpen = ref(null)
const drillListening = ref(false)
const drillText = ref('')
const drillResult = ref(null)
const drillBusy = ref(false)
let drillRecognizer = null

// ---- 加入学习清单：语法/啰嗦两类后端不会自动建卡，要用户自己挑 ----
const ERROR_LABELS = {
  spelling: '拼写',
  grammar: '语法',
  stiffness: '表达僵硬',
  wordiness: '啰嗦',
}
const addedMap = ref({})
const addBusy = ref(null)
const addError = ref({})

function errorLabel(type) {
  return ERROR_LABELS[type] || '表达'
}

async function addToStudy(fix, i) {
  if (addedMap.value[i] || addBusy.value === i) return
  addBusy.value = i
  addError.value = { ...addError.value, [i]: '' }
  try {
    const kind = fix.error_type === 'spelling' ? 'spelling' : 'phrase'
    const reason = fix.reason || ''
    // 拼写卡的题干不能出现纠错原因（原因常直接写出正确拼写），原因放到 related.reason，
    // 等判完之后在卡片反馈里显示
    const related = { ...(fix.related || {}) }
    if (kind === 'spelling' && reason) related.reason = reason
    await api.post('/study/items', {
      kind,
      term: fix.word || fix.better || fix.original,
      context: fix.original,
      meaning_zh: kind === 'spelling' ? '' : reason,
      example: fix.better || '',
      related,
      source_session_id: Number(route.params.id) || null,
    })
    addedMap.value = { ...addedMap.value, [i]: true }
  } catch (e) {
    addError.value = { ...addError.value, [i]: '加入失败：' + (e?.response?.data?.detail || e.message) }
  } finally {
    addBusy.value = null
  }
}

async function loadDrills() {
  try {
    const { data } = await api.get(`/sessions/${route.params.id}/drills`)
    drills.value = { items: data?.items || [], pass_threshold: data?.pass_threshold ?? 0.85 }
  } catch {
    // 降级报告没有改写句，接口会给空数组；拿不到就整块隐藏
    drills.value = { items: [], pass_threshold: 0.85 }
  }
}

const topFixes = computed(() => (drills.value.items || []).slice(0, 3).filter((it) => it.target))
const passedCount = computed(() => topFixes.value.filter((it) => it.passed).length)
const drillByIndex = computed(() =>
  Object.fromEntries((drills.value.items || []).map((it) => [it.index, it]))
)

function stopDrillListen() {
  if (drillRecognizer) {
    drillRecognizer.abort?.()
    drillRecognizer = null
  }
  drillListening.value = false
}

function openDrill(item) {
  stopDrillListen()
  drillError.value = ''
  drillOpen.value = item.index
  drillText.value = ''
  drillResult.value = null
}

function closeDrill() {
  stopDrillListen()
  drillError.value = ''
  drillOpen.value = null
  drillResult.value = null
  drillText.value = ''
}

function toggleDrillListen(item) {
  if (drillListening.value) {
    stopDrillListen()
    return
  }
  drillText.value = ''
  drillResult.value = null
  drillError.value = ''
  drillRecognizer = createRecognizer(
    (text) => {
      drillText.value = text
    },
    () => {
      drillListening.value = false
      if (drillText.value.trim()) submitDrill(item)
    },
    (event) => {
      drillListening.value = false
      const map = {
        'not-allowed': '麦克风权限被拒绝了。请在地址栏左侧允许，或先听一遍原句。',
        'no-speech': '没听到声音，再点一次麦克风试试。',
        'audio-capture': '没找到麦克风，检查一下设备。',
      }
      const msg = map[event?.error]
      if (msg) drillError.value = msg
    }
  )
  if (!drillRecognizer) {
    drillError.value = '当前浏览器不支持语音识别，请换 Chrome 再跟读。'
    return
  }
  drillListening.value = true
  drillRecognizer.start()
}

async function submitDrill(item) {
  const text = drillText.value.trim()
  if (!text || drillBusy.value) return
  drillBusy.value = true
  try {
    const { data } = await api.post(`/sessions/${route.params.id}/drills/${item.index}/attempt`, {
      transcript: text,
    })
    drillResult.value = data
    item.attempts = data.attempts
    item.best_similarity = data.best_similarity
    item.passed = data.passed
  } catch (e) {
    drillError.value = '评定失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    drillBusy.value = false
  }
}

function again() {
  session.clear()
  router.push('/')
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <AppHeader title="复盘报告" :subtitle="metaLine" back="/history" />

    <main class="sp-shell pb-16 pt-10">
      <p v-if="error" class="sp-alert-error">{{ error }}</p>

      <div v-if="missing" class="sp-card">
        <EmptyState icon="report" title="这次练习还没有报告" text="它可能是中途退出或刷新时丢掉的对话，还没走到生成报告这一步。重新练一次，说几句再点「结束并出报告」。">
          <button class="sp-btn-primary" @click="again">重新练一次</button>
          <button class="sp-btn-ghost" @click="router.push('/history')">回历史</button>
        </EmptyState>
      </div>

      <div v-if="!report && !missing && !error" class="sp-grid items-start" aria-label="正在加载报告">
        <aside class="lg:col-span-4 lg:col-start-9">
          <div class="rounded-card bg-white p-6 ring-1 ring-line/80">
            <div class="sp-skeleton h-3 w-16"></div>
            <div class="sp-skeleton mt-4 h-14 w-32"></div>
            <div class="sp-skeleton mt-4 h-9 w-full"></div>
          </div>
        </aside>
      </div>

      <div v-if="report">
        <div
          v-if="isMock"
          class="sp-alert-warn mb-4"
        >
          示例报告，本次不计分：{{ mockHint }}
          <router-link v-if="showMockSettingsLink" to="/settings" class="ml-1 font-medium underline">去设置</router-link>
        </div>

        <div
          v-if="showTypedBanner"
          class="mb-4 rounded-xl bg-brand-50 px-3.5 py-2.5 text-sm leading-6 text-brand-700 ring-1 ring-brand-100"
        >
          本次为打字作答，发音 / 流利度未计入综合分。想练发音就点麦克风说几句，再练一次。
        </div>
        <div
          v-else-if="showMixedBanner"
          class="mb-4 rounded-xl bg-canvas px-3.5 py-2.5 text-sm leading-6 text-ink-soft ring-1 ring-line"
        >
          这次录音和打字都有：发音、流利度只统计录音的句子，「文字表达」只统计打字的句子。
        </div>

        <div ref="railEl" class="sp-tab-rail border-b border-line/60">
          <div class="sp-shell flex h-full items-center">
            <div class="sp-segment relative" role="tablist" aria-label="报告分页">
              <span
                class="pointer-events-none absolute inset-y-1 left-0 rounded-full bg-white shadow-soft ring-1 ring-line/80"
                :class="tabAnimating ? 'transition-[transform,width] duration-[320ms] ease-[cubic-bezier(0.3,0.9,0.25,1)]' : ''"
                :style="{ width: `${tabInd.w}px`, transform: `translateX(${tabInd.x}px)`, opacity: tabInd.show ? 1 : 0 }"
                aria-hidden="true"
              ></span>
              <button
                v-for="(t, i) in TABS"
                :key="t.key"
                :ref="(el) => (tabEls[i] = el)"
                role="tab"
                :aria-selected="tab === t.key"
                :tabindex="tab === t.key ? 0 : -1"
                class="sp-segment-item relative z-10"
                @click="setTab(t.key)"
                @keydown="onTabKeydown($event, i)"
              >
                {{ t.label }}
                <span v-if="t.count" class="sp-num text-[12px] font-normal text-ink-mute">{{ t.count }}</span>
              </button>
            </div>
          </div>
        </div>

        <Transition :css="false" mode="out-in" @enter="tabEnter" @leave="tabLeave">
        <div :key="tab" class="pt-5">
        <div v-if="tab === 'overview'" class="sp-grid items-start">
          <aside class="space-y-5 lg:sticky lg:top-24 lg:col-span-4 lg:col-start-9 lg:row-start-1">
        <div
          v-if="hasScore"
          class="relative overflow-hidden rounded-card bg-ink p-6 text-white shadow-lift sm:p-7"
        >
          <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-brand-500/40 blur-2xl"></div>
          <div class="pointer-events-none absolute -bottom-16 -left-10 h-40 w-40 rounded-full bg-coral-500/25 blur-2xl"></div>
          <div class="relative">
            <div class="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/60">综合得分</div>
            <div class="mt-2 flex items-end gap-2">
              <span class="sp-num text-[64px] font-semibold leading-none">{{ report.total_score }}</span>
              <span class="mb-2 text-sm text-white/50">/ 100</span>
            </div>
            <!-- 等级药丸：随量表换读法（雅思衬线单点 / 字母 / 区间 / 四六级两档或两枚通过水平） -->
            <div ref="pillBoxEl" class="mt-4 flex flex-wrap items-center gap-1.5">
              <span v-if="pillKind === 'below'" class="text-[11px] text-white/50">低于 A2 · 暂不评级</span>
              <template v-else-if="pillKind === 'cet-pass'">
                <span
                  v-for="cet in cetPassPills"
                  :key="cet.id"
                  class="inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-full bg-white/10 px-2.5 py-1.5 text-[12px] font-medium text-white ring-1 ring-white/15"
                >
                  <span
                    class="h-[5px] w-[5px] shrink-0 rounded-full"
                    :class="cet.passed ? 'bg-brand-200' : 'bg-white/30'"
                  ></span>
                  {{ cet.label }}
                </span>
              </template>
              <span
                v-else
                :style="pillHidden ? { opacity: 0 } : undefined"
                class="inline-flex max-w-full items-center gap-1.5 rounded-full bg-white/10 px-3.5 py-1.5 text-[13px] font-medium text-white ring-1 ring-white/15"
              >
                <span data-pill-text class="inline-flex min-w-0 items-center gap-1.5">
                  <template v-if="pillKind === 'ielts'">
                    <span class="text-[13px]">雅思</span>
                    <span class="sp-num text-[15px] font-semibold">{{ scaleItems?.ielts?.display }}</span>
                  </template>
                  <template v-else-if="pillKind === 'cefr'">
                    <span class="text-[13px]">CEFR</span>
                    <span class="font-semibold">{{ scaleItems?.cefr?.display }}</span>
                  </template>
                  <template v-else-if="pillKind === 'toefl'">
                    <span class="text-[13px]">托福</span>
                    <span class="font-semibold">{{ scaleItems?.toefl?.display }}</span>
                  </template>
                  <template v-else-if="pillKind === 'duolingo'">
                    <span class="text-[13px]">多邻国</span>
                    <span class="font-semibold">{{ scaleItems?.duolingo?.display }}</span>
                  </template>
                  <template v-else-if="pillKind === 'cet'">
                    <span class="truncate font-semibold">{{ cetRangeText }}</span>
                  </template>
                  <template v-else>
                    <span class="truncate font-semibold">{{ pillFlatText }}</span>
                  </template>
                </span>
                <button
                  v-if="pillKind === 'cet'"
                  class="inline-flex h-[18px] shrink-0 items-center rounded-full bg-coral-500/15 px-1.5 text-[10px] font-medium text-coral-300 ring-1 ring-coral-500/30"
                  aria-label="四六级为参考换算，点开换算说明"
                  @click.stop="openScaleInfo"
                >
                  参考
                </button>
              </span>
            </div>

            <!-- 切换器 + 换算说明入口 -->
            <div class="mt-4 flex flex-wrap items-center gap-1.5 border-t border-white/10 pt-4">
              <div class="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="评分量表">
                <button
                  v-for="(s, si) in SCALE_OPTIONS"
                  :key="s.id"
                  :ref="(el) => (scaleEls[si] = el)"
                  role="radio"
                  :aria-checked="activeScale === s.id"
                  :aria-disabled="!hasScales"
                  :tabindex="activeScale === s.id ? 0 : -1"
                  class="h-7 rounded-full px-2.5 text-[11px] font-medium transition duration-[180ms] ease-out"
                  :class="[
                    activeScale === s.id
                      ? 'bg-white/15 text-white ring-1 ring-white/25'
                      : 'text-white/50 hover:bg-white/5 hover:text-white/80',
                    hasScales ? '' : 'pointer-events-none opacity-40',
                  ]"
                  @click="pickScale(s.id, $event)"
                  @keydown="onScaleKeydown($event, si)"
                >
                  {{ s.label }}
                </button>
              </div>
              <button
                class="ml-auto inline-flex items-center gap-1 text-[11px] text-white/45 transition hover:text-white/70"
                @click="openScaleInfo"
              >
                换算说明
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 11v5M12 8.2v.2" stroke-linecap="round" />
                </svg>
              </button>
            </div>
          </div>
        </div>
        <div
          v-if="Object.keys(report.dimensions || {}).length"
          class="sp-card p-6"
        >
          <div class="flex items-baseline justify-between">
            <div class="font-semibold text-ink">{{ Object.keys(report.dimensions).length }} 个维度</div>
            <span class="text-[11px] text-ink-mute">雅思 · CEFR</span>
          </div>
          <div v-for="(v, k) in report.dimensions" :key="k" class="mb-4 mt-4 last:mb-0">
            <div class="flex items-baseline justify-between text-sm">
              <span class="text-ink-soft">{{ dimLabels[k] || k }}</span>
              <span class="flex items-baseline gap-2">
                <span class="sp-num text-base font-semibold text-ink">{{ v }}</span>
                <span v-if="dimBand(k)" class="text-xs font-normal text-ink-mute">
                  雅思 {{ dimBand(k) }}<template v-if="dimCefr(k)"> · {{ dimCefr(k) }}</template>
                </span>
              </span>
            </div>
            <div class="sp-bar mt-2">
              <div class="sp-bar-fill" :style="{ width: v + '%' }"></div>
            </div>
          </div>
        </div>

        <div v-if="report.comment" class="sp-card-soft p-5">
          <div class="sp-eyebrow">点评</div>
          <p class="mt-2 text-sm leading-7 text-ink-soft">{{ report.comment }}</p>
        </div>
          </aside>

          <div class="min-w-0 space-y-5 lg:col-span-8 lg:col-start-1 lg:row-start-1">
        <div v-if="reportGoals.length" class="sp-card p-6">
          <div class="flex items-baseline justify-between gap-2">
            <div class="sp-section-title">本轮目标达成</div>
            <div class="flex items-center gap-2">
              <span v-if="reportPlan.review === 'rule'" class="sp-chip-line !py-0.5 !text-[11px]">规则判定</span>
              <span class="text-xs text-ink-mute">{{ reportAchieved.length }}/{{ reportGoals.length }}</span>
            </div>
          </div>
          <ul class="mt-3 flex flex-wrap gap-1.5">
            <li
              v-for="g in reportGoals"
              :key="g"
              class="sp-chip-line"
              :class="reportAchieved.includes(g) ? 'text-brand-700' : 'text-ink-mute'"
            >
              {{ reportAchieved.includes(g) ? '✓' : '○' }} {{ g }}
            </li>
          </ul>
          <p v-if="reportPlan.comment" class="mt-2 text-xs leading-5 text-ink-soft">{{ reportPlan.comment }}</p>
        </div>

        <button
          v-if="report.sentence_fixes.length"
          class="sp-card flex w-full items-center justify-between gap-3 p-5 text-left transition duration-200 hover:ring-brand-200"
          @click="setTab('fixes')"
        >
          <div class="flex min-w-0 flex-wrap items-baseline gap-x-2">
            <span class="font-semibold text-ink">{{ report.sentence_fixes.length }} 句可以改</span>
            <span v-if="topFixes.length" class="text-xs text-ink-mute">已通过 {{ passedCount }}/{{ topFixes.length }}</span>
          </div>
          <span class="shrink-0 text-sm font-medium text-brand-700">去看</span>
        </button>

        <div class="flex flex-col gap-2.5">
          <button class="sp-btn-primary w-full py-3" @click="nextPractice">按推荐再练一次</button>
          <div class="grid grid-cols-2 gap-2.5">
            <button class="sp-btn-secondary" @click="again">再来一次</button>
            <button class="sp-btn-secondary" @click="router.push('/history')">看历史</button>
          </div>
        </div>
          </div>
        </div>

        <div v-else-if="tab === 'fixes'" class="mx-auto w-full max-w-3xl space-y-5">
        <div v-if="topFixes.length" class="sp-card flex flex-wrap items-center justify-between gap-3 p-5">
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="sp-chip-brand">已通过 {{ passedCount }}/{{ topFixes.length }}</span>
            <router-link to="/pronunciation" class="font-medium text-brand-700 underline-offset-2 hover:underline">
              练 ship / sheep
            </router-link>
          </div>
        </div>

        <div class="sp-card p-6">
          <EmptyState
            v-if="!report.sentence_fixes.length"
            compact
            icon="done"
            title="没有需要改的句子"
            text="这次说的话里没有挑出要改写的句子。换个难一点的场景，或多说几句再看看。"
          />
          <div
            v-for="(f, i) in report.sentence_fixes"
            :key="i"
            :style="{ '--i': Math.min(i, 10) }"
            class="sp-reveal mt-3 rounded-2xl bg-paper p-4 text-sm ring-1 ring-line/70 transition duration-200 hover:ring-brand-200"
          >
            <div class="flex items-start gap-2">
              <span class="mt-0.5 text-[11px] font-medium text-ink-mute">原句</span>
              <div :class="f.better ? 'text-rose-500 line-through decoration-rose-300' : 'text-ink-soft'" class="leading-6">
                {{ f.original }}
              </div>
            </div>
            <div v-if="f.better" class="mt-1.5 flex items-start gap-2">
              <span class="mt-0.5 text-[11px] font-medium text-brand-700">改写</span>
              <div class="leading-6 text-brand-700">{{ f.better }}</div>
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <span class="sp-chip-line">{{ errorLabel(f.error_type) }}</span>
              <span v-if="f.natural" class="text-xs leading-5 text-ink-soft">更自然：{{ f.natural }}</span>
            </div>
            <div class="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-line/70 pt-2">
              <div class="min-w-0 text-xs leading-5 text-ink-soft">{{ f.reason }}</div>
              <div class="flex shrink-0 items-center gap-2">
                <button
                  v-if="fixRecordings[i]"
                  class="sp-btn-ghost !px-3 !py-1 text-xs"
                  :aria-label="playingFix === i ? '停止回放' : '听我当时怎么说的'"
                  @click="toggleFixPlayback(i)"
                >
                  {{ playingFix === i ? '停止' : '听我的录音' }}
                </button>
                <button
                  v-if="drillByIndex[i]"
                  class="sp-btn-secondary !px-3 !py-1 text-xs"
                  @click="openDrill(drillByIndex[i])"
                >
                  {{ drillByIndex[i].passed ? '已通过 · 再练' : '重说这句' }}
                </button>
                <button
                  class="sp-btn-ghost !px-3 !py-1 text-xs"
                  :disabled="addedMap[i] || addBusy === i"
                  @click="addToStudy(f, i)"
                >
                  {{ addedMap[i] ? '已加入清单' : '加入学习清单' }}
                </button>
              </div>
            </div>
            <p v-if="addError[i]" class="mt-1 text-[11px] leading-5 text-danger">{{ addError[i] }}</p>

            <div
              v-if="drillByIndex[i] && drillOpen === i"
              class="mt-2 rounded-xl bg-white p-3 ring-1 ring-brand-100"
            >
              <p class="text-[11px] leading-5 text-ink-mute">
                目标句：<span class="font-medium text-brand-700">{{ drillByIndex[i].target }}</span>
              </p>
              <div class="mt-2 flex flex-wrap items-center gap-2">
                <button class="sp-btn-ghost !px-2 !py-1 text-xs" @click="speakSmart(drillByIndex[i].target, { rate: 0.9 })">
                  先听一遍
                </button>
                <button
                  class="sp-btn-primary !px-3 !py-1.5 text-xs"
                  :disabled="drillBusy"
                  @click="toggleDrillListen(drillByIndex[i])"
                >
                  {{ drillListening ? '正在听…点一下停' : '点一下说' }}
                </button>
                <button class="sp-btn-ghost !px-2 !py-1 text-xs" @click="closeDrill">收起</button>
              </div>
              <p v-if="drillText" class="mt-2 text-xs leading-5 text-ink-soft">听到：{{ drillText }}</p>
              <p v-if="drillError" class="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 ring-1 ring-amber-100">
                {{ drillError }}
              </p>
              <div
                v-if="drillResult"
                class="mt-2 rounded-lg px-3 py-2 text-xs leading-5"
                :class="drillResult.passed ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100' : 'bg-amber-50 text-amber-800 ring-1 ring-amber-100'"
              >
                <div class="font-medium">
                  {{ drillResult.passed ? '过了！' : '还不够接近' }} · 相似度
                  {{ Math.round(drillResult.similarity * 100) }}% · 第 {{ drillResult.attempts }} 次
                </div>
                <div class="mt-0.5">{{ drillResult.feedback }}</div>
              </div>
            </div>
          </div>
        </div>
        </div>

        <div v-else class="mx-auto w-full max-w-3xl space-y-5">
        <div v-if="Object.keys(displayFeatures).length" class="sp-card p-6">
          <div class="font-semibold text-ink">{{ typedOnly ? '文字表达指标' : '流利度与表达指标' }}</div>
          <div class="mt-3.5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div v-for="(v, k) in displayFeatures" :key="k" class="rounded-xl bg-canvas px-3.5 py-3 ring-1 ring-line/60">
              <div class="text-[11px] text-ink-mute">{{ featureLabels[k] }}</div>
              <div class="sp-num mt-1 text-[15px] font-semibold text-ink">{{ v }}</div>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          compact
          icon="chart"
          title="这次没有可测指标"
          text="录音或打字多聊几轮，词数、语速这些数字就会出现。"
        />
        </div>
        </div>
        </Transition>
      </div>
    </main>

    <!-- 换算说明：桌面居中卡 / 窄屏底部 sheet -->
    <Transition
      enter-active-class="transition-opacity duration-[160ms] ease-out"
      leave-active-class="transition-opacity duration-[180ms] ease-out"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div
        v-if="scaleInfoOpen"
        class="fixed inset-0 z-40 flex items-end justify-center bg-ink/40 backdrop-blur-sm sm:items-center sm:px-4"
        @click.self="closeScaleInfo"
      >
        <div
          ref="scaleInfoEl"
          role="dialog"
          aria-modal="true"
          aria-label="换算说明"
          class="max-h-[80vh] w-full max-w-md overflow-y-auto rounded-t-card bg-white p-6 shadow-lift ring-1 ring-line/80 sm:rounded-card"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="sp-section-title">换算说明</div>
            <button class="sp-btn-ghost !p-1.5 text-lg leading-none" aria-label="关闭换算说明" @click="closeScaleInfo">×</button>
          </div>
          <table class="mt-4 w-full text-sm">
            <thead>
              <tr class="text-[11px] text-ink-mute">
                <th class="pb-2 text-left font-medium">量表</th>
                <th class="pb-2 text-right font-medium">本次</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in scaleRows"
                :key="row.id"
                class="rounded-xl"
                :class="row.id === activeScale ? 'bg-brand-50 ring-1 ring-brand-100' : ''"
              >
                <td class="px-2.5 py-2 text-ink-soft">{{ row.label }}</td>
                <td class="px-2.5 py-2 text-right">
                  <span class="sp-num text-ink">{{ row.value }}</span>
                  <span
                    v-if="row.reference"
                    class="ml-1 inline-flex h-[18px] items-center rounded-full bg-coral-50 px-1.5 text-[10px] font-medium text-coral-700 ring-1 ring-coral-100"
                  >参考</span>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="mt-4 space-y-1 text-[11px] leading-5 text-ink-mute">
            <p>雅思↔CEFR：IELTS 官方对照</p>
            <p>托福、多邻国：ETS、DET 官方 CEFR 对照</p>
            <p>四六级：无官方换算，按 425 通过线做水平段</p>
          </div>
          <p class="mt-3 text-right text-[11px] text-ink-mute">换算表版本 {{ scaleVersion }}</p>
        </div>
      </div>
    </Transition>

    <!-- 量表切换的飞行副本落点层：固定覆盖视口，脱离 hero 的层级 -->
    <div ref="ghostLayer" class="pointer-events-none fixed inset-0 z-50" aria-hidden="true"></div>
  </div>
</template>

