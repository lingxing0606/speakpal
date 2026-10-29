<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const report = ref(null)
const error = ref('')
const missing = ref(false)
const showDetail = ref(false)

const dimLabels = {
  pronunciation: '发音清晰度',
  fluency: '流利度',
  grammar_vocab: '语法词汇',
  task_completion: '任务完成度',
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
}

const isMock = computed(() => report.value?.source === 'mock')
const mockReason = computed(() => report.value?.mock_reason || '')
const mockHint = computed(() => {
  switch (mockReason.value) {
    case 'not_configured':
      return '这次练习没有可用的模型密钥，所以没出分。去「设置」里填一个密钥，再练一次就能拿到完整评分。'
    case 'invalid_key':
      return '服务端配置的兜底密钥失效了，这是部署侧的问题，不是你操作错了。可以先自己配一个密钥，或者等运维修好。'
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

function dimBand(name) {
  const b = report.value?.bands?.[name]
  if (b === null || b === undefined) return ''
  return typeof b === 'number' ? b.toFixed(1) : b
}

const displayFeatures = computed(() => {
  const src = report.value?.features || {}
  const out = {}
  for (const [k, v] of Object.entries(src)) {
    if (v === null || v === undefined) continue
    out[k] = typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v
  }
  return out
})

onMounted(async () => {
  try {
    const { data } = await api.get(`/sessions/${route.params.id}/report`)
    report.value = data
  } catch (e) {
    if (e?.response?.status === 404) {
      // 从历史点进来的会话还没生成报告（中途退出/刷新丢态），别甩英文错误
      missing.value = true
      return
    }
    error.value = '加载报告失败：' + (e?.response?.data?.detail || e.message)
  }
})

function again() {
  session.clear()
  router.push('/')
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-3">
        <div class="flex items-center gap-3">
          <router-link to="/" aria-label="返回首页">
            <BrandLogo :size="30" />
          </router-link>
          <span class="h-4 w-px bg-line"></span>
          <div class="font-semibold text-ink">复盘报告</div>
        </div>
        <button class="sp-btn-ghost" @click="router.push('/')">返回首页</button>
      </div>
    </header>

    <main class="sp-shell py-8">
      <p v-if="error" class="sp-alert-error">{{ error }}</p>

      <div v-if="missing" class="sp-card flex flex-col items-center px-6 py-14 text-center">
        <div class="flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-2xl ring-1 ring-brand-100">📄</div>
        <div class="mt-4 font-semibold text-ink">这次练习还没有报告</div>
        <p class="mt-1 max-w-sm text-sm leading-6 text-ink-soft">
          它可能是中途退出或刷新时丢掉的对话，还没有走到生成报告这一步。重新练一次，说几句再点「结束并出报告」，就能看到分数和纠错。
        </p>
        <button class="sp-btn-primary mt-5" @click="again">重新练一次</button>
      </div>

      <div v-if="report">
        <div
          v-if="isMock"
          class="sp-alert-warn mb-4"
        >
          示例报告（本次不计分）：{{ mockHint }}
          <router-link v-if="showMockSettingsLink" to="/settings" class="ml-1 font-medium underline">去设置</router-link>
        </div>

        <div
          v-if="hasScore"
          class="relative overflow-hidden rounded-card bg-white p-7 text-center shadow-card ring-1 ring-line/70"
        >
          <div class="pointer-events-none absolute -right-10 -top-16 h-44 w-44 rounded-full bg-brand-100/60 blur-2xl"></div>
          <div class="relative">
            <div class="text-xs font-medium tracking-wide text-ink-mute">综合得分</div>
            <div class="sp-num mt-1 text-[56px] font-semibold leading-none text-ink">{{ report.total_score }}</div>
            <div v-if="bandText" class="mt-3 inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3.5 py-1.5 text-sm font-medium text-brand-700">
              {{ bandText }}
            </div>
            <div class="mt-2.5 text-xs leading-5 text-ink-mute">{{ report.note }}</div>
          </div>
        </div>

        <div
          v-if="Object.keys(report.dimensions || {}).length"
          class="sp-card mt-4 p-6"
        >
          <div class="flex items-baseline justify-between">
            <div class="font-semibold text-ink">四个维度</div>
            <div class="text-xs text-ink-mute">模型分与可测指标融合</div>
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

        <div
          v-if="Object.keys(displayFeatures).length"
          class="sp-card mt-4 p-6"
        >
          <div class="font-semibold text-ink">流利度与表达指标</div>
          <div class="mt-3.5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div v-for="(v, k) in displayFeatures" :key="k" class="rounded-xl bg-canvas px-3.5 py-3 ring-1 ring-line/60">
              <div class="text-[11px] text-ink-mute">{{ featureLabels[k] || k }}</div>
              <div class="sp-num mt-1 text-[15px] font-semibold text-ink">{{ v }}</div>
            </div>
          </div>
        </div>

        <div
          v-if="hasDetail"
          class="sp-card mt-4 p-6"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-semibold text-ink">评分依据（可复现）</div>
              <div class="mt-0.5 text-xs text-ink-mute">想核对分数怎么来的再展开，学习者只看分数和等级就行。</div>
            </div>
            <button class="sp-btn-ghost shrink-0 py-1.5" @click="showDetail = !showDetail">
              {{ showDetail ? '收起' : '展开' }}
            </button>
          </div>
          <div v-if="showDetail" class="mt-3">
            <p class="text-xs leading-5 text-ink-soft">
              每个维度先由模型打分，再用可测指标（词数、语速、TTR 等）校准；「最终」才是算进综合分的那一列。
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
          </div>
        </div>

        <div class="sp-card mt-4 p-6">
          <div class="font-semibold text-ink">逐句纠错</div>
          <p v-if="!report.sentence_fixes.length" class="mt-3 text-sm text-ink-mute">
            本次没有可展示的句子。
          </p>
          <div
            v-for="(f, i) in report.sentence_fixes"
            :key="i"
            class="mt-3 rounded-xl bg-canvas p-4 text-sm ring-1 ring-line/60"
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
            <div class="mt-2 border-t border-line/70 pt-2 text-xs leading-5 text-ink-soft">{{ f.reason }}</div>
          </div>
        </div>

        <div class="sp-card mt-4 p-6 text-sm leading-6 text-ink-soft">
          {{ report.comment }}
        </div>

        <div class="mt-6 flex gap-3">
          <button class="sp-btn-primary flex-1" @click="again">再来一次</button>
          <button class="sp-btn-secondary flex-1" @click="router.push('/history')">看历史</button>
        </div>
      </div>
    </main>
  </div>
</template>
