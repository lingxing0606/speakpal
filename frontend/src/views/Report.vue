<script setup>
import { computed, markRaw, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import CountUp from '../components/CountUp.vue'
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
const showDetail = ref(false)
const showFeatures = ref(false)
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
const scoringDims = computed(() => report.value?.scoring_detail?.dimensions || {})
const hasDetail = computed(() => Object.keys(scoringDims.value).length > 0)
// 本轮目标达成：老报告没有 plan 字段，整块不显示
const reportPlan = computed(() => report.value?.plan || {})
const reportGoals = computed(() => reportPlan.value.goals || [])
const reportAchieved = computed(() => reportPlan.value.achieved || [])

function evidenceText(d) {
  const inputs = d?.inputs
  if (!inputs || typeof inputs !== 'object') return ''
  const parts = []
  for (const [k, v] of Object.entries(inputs)) {
    if (v === null || v === undefined || v === '') continue
    const label = featureLabels[k] || k
    if (Array.isArray(v)) {
      if (v.length) parts.push(`${label}：${v.join('、')}`)
    } else if (typeof v === 'number') {
      parts.push(`${label}：${Number.isInteger(v) ? v : v.toFixed(2)}`)
    } else {
      parts.push(`${label}：${v}`)
    }
    if (parts.length >= 6) break
  }
  return parts.join(' · ')
}

const bandText = computed(() => {
  const r = report.value
  if (!r || r.band === null || r.band === undefined) return ''
  const band = typeof r.band === 'number' ? r.band.toFixed(1) : r.band
  return r.cefr ? `${r.cefr} · 雅思 ${band}` : `雅思 ${band}`
})

// 综合分怎么来的：有评分依据时说明是融合分，别再说「AI 估算」，否则和下方的融合说明互相打架
const scoreNote = computed(() => {
  const r = report.value
  if (!r) return ''
  if (hasDetail.value) return '综合分 = 模型分与可测规则分融合；有可测证据的维度同时给出规则分。'
  return r.note || ''
})

function dimBand(name) {
  const b = report.value?.bands?.[name]
  if (b === null || b === undefined) return ''
  return typeof b === 'number' ? b.toFixed(1) : b
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

onUnmounted(() => stopRecording())

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

        <div class="sp-grid items-start">
          <aside class="space-y-5 lg:sticky lg:top-24 lg:col-span-4 lg:col-start-9 lg:row-start-1">
        <div
          v-if="hasScore"
          class="relative overflow-hidden rounded-card bg-ink p-7 text-white shadow-lift"
        >
          <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-brand-500/40 blur-2xl"></div>
          <div class="pointer-events-none absolute -bottom-16 -left-10 h-40 w-40 rounded-full bg-coral-500/25 blur-2xl"></div>
          <div class="relative">
            <div class="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/60">综合得分</div>
            <div class="mt-2 flex items-end gap-2">
              <span class="sp-num text-[64px] font-semibold leading-none"><CountUp :value="report.total_score" /></span>
              <span class="mb-2 text-sm text-white/50">/ 100</span>
            </div>
            <div v-if="bandText" class="mt-4 inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3.5 py-1.5 text-sm font-medium text-white ring-1 ring-white/15">
              {{ bandText }}
            </div>
          </div>
        </div>
        <div
          v-if="Object.keys(report.dimensions || {}).length"
          class="sp-card p-6"
        >
          <div class="flex items-baseline justify-between">
            <div class="font-semibold text-ink">{{ Object.keys(report.dimensions).length }} 个维度</div>
            <div class="text-xs text-ink-mute">模型分与可测规则分融合</div>
          </div>
          <div v-for="(v, k) in report.dimensions" :key="k" class="mb-4 mt-4 last:mb-0">
            <div class="flex items-baseline justify-between text-sm">
              <span class="text-ink-soft">{{ dimLabels[k] || k }}</span>
              <span class="flex items-baseline gap-2">
                <span class="sp-num text-base font-semibold text-ink">{{ v }}</span>
                <span v-if="dimBand(k)" class="text-xs font-normal text-ink-mute">雅思 {{ dimBand(k) }}</span>
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
        <div class="flex flex-col gap-2.5">
          <button class="sp-btn-primary w-full py-3" @click="nextPractice">按推荐再练一次</button>
          <div class="grid grid-cols-2 gap-2.5">
            <button class="sp-btn-secondary" @click="again">再来一次</button>
            <button class="sp-btn-secondary" @click="router.push('/history')">看历史</button>
          </div>
        </div>
          </aside>

          <div class="min-w-0 space-y-5 lg:col-span-8 lg:col-start-1 lg:row-start-1">
        <div v-if="topFixes.length" class="sp-card flex flex-wrap items-center justify-between gap-3 p-5">
          <div class="min-w-0">
            <div class="font-semibold text-ink">最该改的 {{ topFixes.length }} 句</div>
            <p class="mt-0.5 text-xs leading-5 text-ink-mute">
              跟读相似度 ≥ {{ Math.round(drills.pass_threshold * 100) }}% 算过。
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="sp-chip-brand">已通过 {{ passedCount }}/{{ topFixes.length }}</span>
            <router-link to="/pronunciation" class="font-medium text-brand-700 underline-offset-2 hover:underline">
              练 ship / sheep
            </router-link>
          </div>
        </div>

        <div v-if="reportGoals.length" class="sp-card p-6">
          <div class="flex items-baseline justify-between">
            <div class="sp-section-title">本轮目标达成</div>
            <span class="text-xs text-ink-mute">{{ reportAchieved.length }}/{{ reportGoals.length }}</span>
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
          <p v-if="reportPlan.review === 'rule'" class="mt-1 text-[11px] leading-5 text-ink-mute">
            目标达成按关键词规则判定，模型这次没有参与复盘。
          </p>
        </div>

        <div class="sp-card p-6">
          <div class="flex items-baseline justify-between">
            <div class="sp-section-title">逐句纠错</div>
            <span v-if="report.sentence_fixes.length" class="text-xs text-ink-mute">{{ report.sentence_fixes.length }} 句</span>
          </div>
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

        <div v-if="Object.keys(displayFeatures).length" class="sp-card p-6">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-semibold text-ink">{{ typedOnly ? '文字表达指标' : '流利度与表达指标' }}</div>
              <div class="mt-0.5 text-xs text-ink-mute">词数、语速这些可测数字，想看再展开。</div>
            </div>
            <button class="sp-btn-ghost shrink-0 py-1.5" @click="showFeatures = !showFeatures">
              {{ showFeatures ? '收起' : '展开' }}
            </button>
          </div>
          <div v-if="showFeatures" class="mt-3.5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div v-for="(v, k) in displayFeatures" :key="k" class="rounded-xl bg-canvas px-3.5 py-3 ring-1 ring-line/60">
              <div class="text-[11px] text-ink-mute">{{ featureLabels[k] }}</div>
              <div class="sp-num mt-1 text-[15px] font-semibold text-ink">{{ v }}</div>
            </div>
          </div>
        </div>

        <div v-if="hasDetail" class="sp-card p-6">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-semibold text-ink">评分依据</div>
              <div class="mt-0.5 text-xs text-ink-mute">想核对分数怎么来的再展开，学习者只看分数和等级就行。</div>
            </div>
            <button class="sp-btn-ghost shrink-0 py-1.5" @click="showDetail = !showDetail">
              {{ showDetail ? '收起' : '展开' }}
            </button>
          </div>
          <div v-if="showDetail" class="mt-3">
            <p v-if="scoreNote" class="text-xs leading-5 text-ink-soft">{{ scoreNote }}</p>
            <p v-if="bandText" class="mt-1 text-xs leading-5 text-ink-mute">
              band 是本模式口径（按这次是录音还是打字换算）；历史曲线用的是跨模式可比口径。
            </p>
            <p class="mt-1 text-xs leading-5 text-ink-soft">
              每个维度先由模型打分，再用可测规则分（词数、语速、TTR 等）校准；「最终」才是算进综合分的那一列。
            </p>
            <div v-if="report.scoring_detail.note" class="mt-1 text-xs leading-5 text-ink-mute">
              {{ report.scoring_detail.note }}
            </div>
            <div v-for="(d, k) in scoringDims" :key="k" class="mt-3 rounded-xl bg-canvas p-3.5 text-sm ring-1 ring-line/60">
              <div class="flex flex-wrap items-baseline justify-between gap-1">
                <span class="font-medium text-ink-soft">{{ dimLabels[k] || k }}</span>
                <span class="text-[11px] text-ink-mute">
                  模型 {{ d.model_score ?? '—' }} · 规则 {{ d.rule_score ?? '—' }} · 最终 {{ d.final_score ?? '—' }}
                </span>
              </div>
              <div v-if="d.clamped" class="mt-1.5 text-xs text-warn">{{ d.clamp_reason }}</div>
              <div class="mt-1.5 text-xs leading-5 text-ink-soft">{{ d.note }}</div>
              <div v-if="evidenceText(d)" class="mt-1 text-[11px] leading-5 text-ink-mute">{{ evidenceText(d) }}</div>
            </div>

            <div class="mt-4 rounded-xl bg-canvas p-3.5 text-[11px] leading-5 text-ink-mute ring-1 ring-line/60">
              <div class="mb-1 font-medium text-ink-soft">综合分怎么算</div>
              <div>纯录音：发音 20 · 流利度 20 · 语法词汇（语言复杂度）30 · 任务完成度（语用得体性）30</div>
              <div>纯打字：文字表达 35 · 语法词汇（语言复杂度）35 · 任务完成度（语用得体性）30</div>
              <div>混合：发音 15 · 流利度 15 · 文字表达 20 · 语法词汇（语言复杂度）25 · 任务完成度（语用得体性）25</div>
              <div class="mt-1">缺的维度按剩余权重归一，不按 0 分算；跨模式只比「可比 band」（语法词汇 + 任务完成度）。</div>
            </div>
          </div>
        </div>


          </div>
        </div>
      </div>
    </main>
  </div>
</template>

