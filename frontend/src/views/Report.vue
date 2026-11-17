<script setup>
import { computed, markRaw, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import AiTransparency from '../components/AiTransparency.vue'
import AppHeader from '../components/AppHeader.vue'
import CoachPanel from '../components/CoachPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import ReportDimensions from '../components/ReportDimensions.vue'
import ReportFixes from '../components/ReportFixes.vue'
import ReportFluency from '../components/ReportFluency.vue'
import ReportScoreHeader from '../components/ReportScoreHeader.vue'
import { useSessionStore } from '../stores/session'
import { useSettingsStore } from '../stores/settings'
import { loadRecordings, stopRecording } from '../utils/recordings'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const settings = useSettingsStore()

const report = ref(null)
const error = ref('')
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

// 教练建议「看这句」：切到逐句纠错，并把目标句滚到视口中间、闪一次
const fixesRef = ref(null)
const highlightFix = ref(-1)

function openFix(index) {
  const target = Number(index)
  if (!Number.isInteger(target) || target < 0) return
  setTab('fixes')
  const scroll = () => {
    if (!fixesRef.value?.scrollTo(target)) return false
    highlightFix.value = target
    setTimeout(() => {
      if (highlightFix.value === target) highlightFix.value = -1
    }, 450)
    return true
  }
  if (scroll()) return
  // 页签 out-in 切换期间目标列表还没挂载：等它出现再滚
  let tries = 0
  const timer = setInterval(() => {
    tries += 1
    if (scroll() || tries > 20) clearInterval(timer)
  }, 60)
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
  if (railEl.value) railNatural.value = railEl.value.getBoundingClientRect().top + window.scrollY
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
  document.fonts?.ready.then(() => {
    if (railEl.value) railNatural.value = railEl.value.getBoundingClientRect().top + window.scrollY
  })
  placeIndicator(tab.value, false)
  window.addEventListener('resize', onResize)
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
  stopRecording()
})

// 本地录音（只在录这次练习的浏览器里有）：{ 第几句用户发言: Blob }
const recordings = ref({})

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
            <div class="sp-segment relative max-w-full overflow-x-auto" role="tablist" aria-label="报告分页">
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
          <aside class="space-y-5 lg:sticky lg:top-24 lg:col-span-4 lg:col-start-9 lg:row-start-1 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:overscroll-contain lg:[scrollbar-width:none] lg:[&::-webkit-scrollbar]:hidden">
        <ReportScoreHeader v-if="hasScore" :report="report" />
        <ReportDimensions v-if="Object.keys(report.dimensions || {}).length" :report="report" />

        <div v-if="report.comment" class="sp-card-soft p-5">
          <div class="sp-eyebrow">点评</div>
          <p class="mt-2 text-sm leading-7 text-ink-soft">{{ report.comment }}</p>
        </div>
          </aside>

          <div class="min-w-0 space-y-5 lg:col-span-8 lg:col-start-1 lg:row-start-1">
        <CoachPanel v-if="report.coach" :coach="report.coach" @open-fix="openFix" />
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
          v-if="(report.sentence_fixes || []).length"
          class="sp-card group flex w-full items-center justify-between gap-3 p-5 text-left transition duration-200 hover:ring-brand-200"
          @click="setTab('fixes')"
        >
          <div class="flex min-w-0 flex-wrap items-baseline gap-x-2">
            <span class="font-semibold text-ink">{{ (report.sentence_fixes || []).length }} 句可以改</span>
            <span v-if="topFixes.length" class="text-xs text-ink-mute">已通过 {{ passedCount }}/{{ (report.sentence_fixes || []).length }}</span>
          </div>
          <span class="flex shrink-0 items-center gap-2">
            <span class="text-sm font-medium text-brand-700">去看</span>
            <span class="sp-arrow" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </span>
          </span>
        </button>

        <AiTransparency v-if="report.transparency" :transparency="report.transparency" />

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
        <ReportFixes
          ref="fixesRef"
          :report="report"
          :drills="drills"
          :fix-recordings="fixRecordings"
          :highlight-fix="highlightFix"
        />
        </div>

        <div v-else class="mx-auto w-full max-w-3xl space-y-5">
        <ReportFluency :items="displayFeatures" :labels="featureLabels" :typed-only="typedOnly" />
        </div>
        </div>
        </Transition>
      </div>
    </main>

  </div>
</template>

