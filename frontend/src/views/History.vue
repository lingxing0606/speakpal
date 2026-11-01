<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import StudyDashboard from '../components/StudyDashboard.vue'
import TabBar from '../components/TabBar.vue'
import { useSessionStore } from '../stores/session'
import { useSettingsStore } from '../stores/settings'
import { KEY_REQUIRED_MESSAGE, llmReady } from '../utils/llmGate'

const router = useRouter()
const session = useSessionStore()
const settings = useSettingsStore()
const items = ref([])
const error = ref('')
const rec = ref(null)
const needKey = ref(false)
const pendingItem = ref(null)
// 列表还没回来时显示骨架，不能先闪一下「还没有练习记录」
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/sessions')
    items.value = data
  } catch (e) {
    error.value = '加载失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
  try {
    const { data } = await api.get('/me/recommendation')
    rec.value = data
  } catch {
    rec.value = null
  }
})

function askKey(item) {
  pendingItem.value = item
  needKey.value = true
}

// 继续练 / 再练一次都要先确认有密钥，别让人听完开场白、录完一句才被拒
async function resume(item) {
  const gate = await llmReady()
  if (!gate.ok) {
    askKey(item)
    return
  }
  router.push(`/practice/${item.id}`)
}

async function replay(item) {
  const gate = await llmReady()
  if (!gate.ok) {
    askKey(item)
    return
  }
  try {
    const { data } = await api.post('/sessions', { scene_id: item.scene_id })
    let diff = settings.prefDifficulty || rec.value?.recommended_difficulty || 'medium'
    try {
      const detail = await api.get(`/sessions/${data.session_id}`)
      diff = detail?.data?.difficulty || diff
    } catch {
      // 读不到就用本地偏好兜底
    }
    session.start(
      data.session_id,
      { id: item.scene_id, name: item.scene_name },
      diff,
      data.opening_question
    )
    router.push(`/practice/${data.session_id}`)
  } catch (e) {
    error.value = '开始失败：' + (e?.response?.data?.detail || e.message)
  }
}

// 成长曲线用可比 band（语言复杂度 + 语用得体性），打字和录音都能进同一条线；
// total_score 只在同模式内可比，不拿来跨模式连线
const curveSessions = computed(() =>
  items.value
    .filter((it) => {
      if (it.status !== 'finished') return false
      const v = it.comparable_band ?? it.band
      return v !== null && v !== undefined
    })
    .slice()
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
)

const MODE_LABELS = { voice: '录音', typed: '打字', mixed: '混合' }

// 纵轴固定成雅思全量程 3–9，不按数据动态缩放：
// 动态量程会把 5.0→5.5 的 0.5 档画成贯穿全高的陡坡，看起来像“巨大进步”，这是误导。
const BAND_LO = 3
const BAND_HI = 9

const curve = computed(() => {
  const rows = curveSessions.value
  if (rows.length < 2) return null
  const w = 320
  const h = 80
  const pad = 6
  const vals = rows.map((r) => Number(r.comparable_band ?? r.band))
  const span = BAND_HI - BAND_LO
  const yOf = (v) => {
    const band = Math.min(BAND_HI, Math.max(BAND_LO, v))
    return h - pad - ((band - BAND_LO) / span) * (h - pad * 2)
  }
  const points = rows.map((r, i) => {
    const x = pad + (i * (w - pad * 2)) / (rows.length - 1)
    const v = Number(r.comparable_band ?? r.band)
    const y = yOf(v)
    return {
      x: Number(x.toFixed(1)),
      y: Number(y.toFixed(1)),
      band: v,
      mode: r.answer_mode || '',
      label: v.toFixed(1),
      labelY: Number(Math.max(9, y - 6).toFixed(1)),
    }
  })
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ')
  // 整数档网格线（4–8），让“平缓的进步”和“真实的跃升”能区分开
  const grid = [4, 5, 6, 7, 8].map((v) => Number(yOf(v).toFixed(1)))
  return {
    points,
    path,
    grid,
    w,
    h,
    first: vals[0],
    last: vals[vals.length - 1],
    count: rows.length,
    showLabels: rows.length <= 8,
  }
})

function inputTag(it) {
  if (it.answer_mode) return MODE_LABELS[it.answer_mode] || ''
  if (!it.typed_turns && !it.voice_turns) return ''
  if (!it.typed_turns) return '录音'
  if (!it.voice_turns) return '打字'
  return '混合'
}

// 行内等级与曲线同一口径（可比 band），否则同一次练习会出现两个不同等级
function rowBand(it) {
  const v = it.comparable_band ?? it.band
  return v === null || v === undefined ? null : Number(v)
}

// 后端给的是不带时区的 UTC 串，先补 Z 再解析，否则会当成本地时间差 8 小时
function when(iso) {
  if (!iso) return ''
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function open(item) {
  // 按后端列表字段直接分支，不做「先跳报告页、404 再退回」的试探
  if (item.report_id) return router.push(`/report/${item.id}`)
  if (item.status && item.status !== 'finished') return resume(item)
  // finished 却没有报告（生成失败等罕见情况）：报告页会给「还没有报告」的说明
  return router.push(`/report/${item.id}`)
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="历史记录" back="/" />

    <main class="sp-shell pb-16 pt-10">
      <p v-if="error" class="sp-alert-error">{{ error }}</p>

      <div v-if="needKey" class="sp-card mb-4 p-5 ring-brand-100">
        <div class="font-semibold text-ink">先接入一个模型密钥</div>
        <p class="mt-1 text-xs leading-5 text-ink-soft">
          继续练习会调用模型陪聊和评分。密钥只存在你自己的浏览器里，不上传、不写数据库。
        </p>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <button class="sp-btn-primary" @click="router.push('/settings?onboarding=1')">去设置填密钥</button>
          <button class="sp-btn-ghost" @click="needKey = false">取消</button>
        </div>
      </div>

      <div class="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div class="sp-eyebrow">历史</div>
          <h1 class="sp-title mt-2">我的练习</h1>
          <p class="sp-lede">每一次对话、分数和纠错都在这里。成长曲线用跨模式可比的档位，打字和录音可以放在一起看。</p>
        </div>
        <span v-if="!loading" class="sp-chip bg-white text-ink-soft ring-1 ring-line">{{ items.length }} 次练习</span>
      </div>

      <div v-if="loading" class="sp-grid">
        <div class="space-y-4 lg:col-span-5">
          <div class="sp-card-flat space-y-3 p-5">
            <div class="sp-skeleton h-4 w-1/3"></div>
            <div class="grid grid-cols-3 gap-2"><div v-for="i in 3" :key="i" class="sp-skeleton h-16"></div></div>
            <div class="sp-skeleton h-24"></div>
          </div>
        </div>
        <div class="space-y-3 lg:col-span-7">
          <div v-for="i in 4" :key="i" class="sp-card-flat flex items-center justify-between p-5">
            <div class="w-1/2 space-y-2"><div class="sp-skeleton h-4 w-2/3"></div><div class="sp-skeleton h-3 w-full"></div></div>
            <div class="sp-skeleton h-8 w-12"></div>
          </div>
        </div>
      </div>

      <div v-else-if="items.length === 0 && !error" class="sp-card">
        <EmptyState icon="practice" title="还没有练习记录" text="选一个场景说上几句，结束后这里会出现分数、纠错和你的成长曲线。">
          <button class="sp-btn-primary" @click="router.push('/')">去练第一次</button>
        </EmptyState>
      </div>

      <div v-else-if="items.length" class="sp-grid items-start">
        <aside class="space-y-5 lg:sticky lg:top-24 lg:col-span-5">
        <StudyDashboard />
        <div v-if="curve" class="sp-card p-5">
          <div class="flex items-baseline justify-between">
            <div class="font-semibold text-ink">成长曲线</div>
            <div class="text-xs text-ink-mute">{{ curve.count }} 次</div>
          </div>
          <p class="mt-0.5 text-[11px] leading-5 text-ink-mute">
            打字和录音用同一套标准计分，可以直接比。
          </p>
          <svg :viewBox="`0 0 ${curve.w} ${curve.h}`" class="mt-3 h-24 w-full" role="img" aria-label="可比 band 成长曲线，纵轴固定雅思 3 到 9">
            <line
              v-for="(gy, i) in curve.grid"
              :key="`g${i}`"
              x1="0"
              :x2="curve.w"
              :y1="gy"
              :y2="gy"
              stroke="#E3EAE9"
              stroke-width="1"
            />
            <path :d="curve.path" fill="none" stroke="#1F9C89" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <circle
              v-for="(p, i) in curve.points"
              :key="i"
              :cx="p.x"
              :cy="p.y"
              r="3"
              :fill="p.mode === 'typed' ? '#fff' : '#14806F'"
              :stroke="p.mode === 'typed' ? '#1F9C89' : '#fff'"
              stroke-width="1.6"
            />
            <g v-if="curve.showLabels" fill="#475467" font-size="8" text-anchor="middle">
              <text v-for="(p, i) in curve.points" :key="`t${i}`" :x="p.x" :y="p.labelY">{{ p.label }}</text>
            </g>
          </svg>
          <div class="mt-1 flex items-center justify-between text-[11px] text-ink-mute">
            <span>从 雅思 {{ curve.first.toFixed(1) }} 到现在</span>
            <span class="font-medium text-brand-700">雅思 {{ curve.last.toFixed(1) }}</span>
          </div>
          <div class="mt-1 flex items-center gap-3 text-[10px] text-ink-mute">
            <span class="inline-flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-brand-600"></span>录音/混合</span>
            <span class="inline-flex items-center gap-1"><span class="h-2 w-2 rounded-full border border-brand-500 bg-white"></span>打字</span>
          </div>
        </div>
        </aside>

        <section class="space-y-3 lg:col-span-7" aria-label="练习列表">
        <div
          v-for="(it, idx) in items"
          :key="it.id"
          :style="{ '--i': Math.min(idx, 12) }"
          class="sp-reveal sp-hover group flex cursor-pointer flex-wrap items-center justify-between gap-4 rounded-2xl bg-white p-5 ring-1 ring-line/80"
          @click="open(it)"
        >
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <div class="truncate font-medium text-ink">{{ it.scene_name }}</div>
              <span v-if="inputTag(it)" class="sp-chip-line shrink-0 !px-1.5 !py-0.5 !text-[10px]">{{ inputTag(it) }}</span>
            </div>
            <div class="mt-1 text-xs text-ink-mute">
              {{ when(it.created_at) }}
              <span v-if="rowBand(it) !== null"> · 可比 雅思 {{ rowBand(it).toFixed(1) }}</span>
            </div>
          </div>
          <div class="flex shrink-0 items-center gap-3">
            <div v-if="it.total_score !== null" class="text-right">
              <div class="sp-num text-2xl font-semibold leading-none text-ink">{{ it.total_score }}</div>
              <div class="mt-1 text-[11px] text-ink-mute">综合分</div>
            </div>
            <div v-else-if="it.status && it.status !== 'finished'" class="sp-chip-brand">进行中</div>
            <div v-else class="sp-chip-line">未出分</div>
            <button
              class="sp-chip-line text-brand-700 ring-brand-200 transition hover:bg-brand-50"
              @click.stop="replay(it)"
            >
              再练一次
            </button>
            <span class="hidden text-[11px] text-ink-mute sm:inline">{{ it.report_id ? '看报告' : '继续练习' }}</span>
            <span class="sp-arrow" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </span>
          </div>
        </div>
        </section>
      </div>
    </main>

    <TabBar />
  </div>
</template>
