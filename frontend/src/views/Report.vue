<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const report = ref(null)
const error = ref('')

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
const hasScore = computed(() => report.value?.total_score !== null && report.value?.total_score !== undefined)

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
    error.value = '加载报告失败：' + (e?.response?.data?.detail || e.message)
  }
})

function again() {
  session.clear()
  router.push('/')
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <div class="font-semibold">复盘报告</div>
        <button class="text-sm text-slate-500 hover:text-slate-800" @click="router.push('/')">返回首页</button>
      </div>
    </header>

    <main class="mx-auto max-w-3xl px-4 py-8">
      <p v-if="error" class="text-rose-500">{{ error }}</p>

      <div v-if="report">
        <div
          v-if="isMock"
          class="mb-4 rounded-xl bg-amber-50 p-4 text-sm leading-6 text-amber-800 ring-1 ring-amber-200"
        >
          示例报告（模型不可用）：这次没有拿到评分结果，因此<b>不计分、不给等级</b>。下面列出的句子都是你真实说过的内容，不是示例句。
        </div>

        <div
          v-if="hasScore"
          class="rounded-2xl bg-white p-6 text-center shadow-sm ring-1 ring-slate-200"
        >
          <div class="text-sm text-slate-500">综合得分</div>
          <div class="text-5xl font-bold text-indigo-600">{{ report.total_score }}</div>
          <div v-if="bandText" class="mt-2 inline-flex rounded-full bg-indigo-50 px-3 py-1 text-sm font-medium text-indigo-700">
            {{ bandText }}
          </div>
          <div class="mt-2 text-xs text-slate-400">{{ report.note }}</div>
        </div>

        <div
          v-if="Object.keys(report.dimensions || {}).length"
          class="mt-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"
        >
          <div class="font-semibold">四个维度</div>
          <div v-for="(v, k) in report.dimensions" :key="k" class="mb-3 mt-3">
            <div class="flex justify-between text-sm">
              <span>{{ dimLabels[k] || k }}</span>
              <span class="font-medium">
                {{ v }}
                <span v-if="dimBand(k)" class="ml-1 text-xs font-normal text-slate-400">雅思 {{ dimBand(k) }}</span>
              </span>
            </div>
            <div class="mt-1 h-2 rounded bg-slate-100">
              <div class="h-2 rounded bg-indigo-500" :style="{ width: v + '%' }"></div>
            </div>
          </div>
        </div>

        <div
          v-if="Object.keys(displayFeatures).length"
          class="mt-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"
        >
          <div class="font-semibold">流利度与表达指标</div>
          <div class="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div v-for="(v, k) in displayFeatures" :key="k" class="rounded-xl bg-slate-50 p-3">
              <div class="text-xs text-slate-500">{{ featureLabels[k] || k }}</div>
              <div class="mt-1 font-medium">{{ v }}</div>
            </div>
          </div>
        </div>

        <div class="mt-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div class="font-semibold">逐句纠错</div>
          <p v-if="!report.sentence_fixes.length" class="mt-3 text-sm text-slate-400">
            本次没有可展示的句子。
          </p>
          <div
            v-for="(f, i) in report.sentence_fixes"
            :key="i"
            class="mt-3 rounded-xl bg-slate-50 p-3 text-sm"
          >
            <div :class="f.better ? 'text-rose-500 line-through' : 'text-slate-600'">{{ f.original }}</div>
            <div v-if="f.better" class="text-emerald-600">{{ f.better }}</div>
            <div class="mt-1 text-xs text-slate-500">{{ f.reason }}</div>
          </div>
        </div>

        <div class="mt-4 rounded-2xl bg-white p-6 text-sm leading-6 text-slate-600 shadow-sm ring-1 ring-slate-200">
          {{ report.comment }}
        </div>

        <div class="mt-6 flex gap-3">
          <button class="flex-1 rounded-lg bg-indigo-600 py-2 text-white" @click="again">再来一次</button>
          <button class="flex-1 rounded-lg border border-slate-200 py-2" @click="router.push('/history')">看历史</button>
        </div>
      </div>
    </main>
  </div>
</template>
