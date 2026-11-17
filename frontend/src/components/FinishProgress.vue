<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, type PropType } from 'vue'

import type { AgentTraceStep } from '../types/api'

const STAGES = [
  { key: 'scoring', label: '评分' },
  { key: 'critic', label: '复核' },
  { key: 'coach', label: '查资料' },
  { key: 'cards', label: '生成学习卡' },
]
const TOOL_LABELS: Record<string, string> = {
  lookup_word: '查词库',
  grammar_card: '查语法卡',
  recent_weakness: '查近期错因',
  get_frames: '查场景句型',
}

const props = defineProps({
  // 当前阶段：scoring / critic / coach / cards / done；空串表示还没收到任何事件
  stage: { type: String, default: '' },
  // 教练的工具调用 trace（只取最近一条展示）
  tools: { type: Array as PropType<AgentTraceStep[]>, default: () => [] as AgentTraceStep[] },
  startedAt: { type: Number, default: 0 },
  // 非空表示失败，块内显示错误与重试
  failed: { type: String, default: '' },
  // 后端没有流式接口，回落普通 finish：单行不确定态，不假装阶段推进
  fallback: { type: Boolean, default: false },
})
const emit = defineEmits(['retry'])

const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const seen = ref<string[]>([])
watch(
  () => props.stage,
  (value) => {
    if (value && value !== 'done' && !seen.value.includes(value)) seen.value = [...seen.value, value]
  },
  { immediate: true }
)

const done = computed(() => props.stage === 'done')
const elapsed = computed(() => {
  if (!props.startedAt) return 0
  return Math.max(0, Math.round((now.value - props.startedAt) / 1000))
})
const currentIndex = computed(() => STAGES.findIndex((stage) => stage.key === props.stage))
const completedCount = computed(() => {
  if (done.value) return STAGES.length
  return currentIndex.value < 0 ? 0 : currentIndex.value
})
// coach 被跳过：cards 已经来了但整轮没收到 coach 阶段
const coachSkipped = computed(
  () => currentIndex.value >= 3 && !seen.value.includes('coach') && !done.value
)
const stepNo = computed(() => (done.value ? STAGES.length : Math.min(STAGES.length, completedCount.value + 1)))
const progressPercent = computed(() => {
  if (done.value) return 100
  return Math.min(100, ((completedCount.value + 0.5) / STAGES.length) * 100)
})
const toolLine = computed(() => {
  const latest = props.tools[props.tools.length - 1]
  if (!latest) return ''
  return `${TOOL_LABELS[latest.tool] || latest.tool || '调用工具'} · ${latest.ms}ms`
})

function stateOf(index: number) {
  if (index === 2 && coachSkipped.value) return 'skipped'
  if (done.value) return 'complete'
  const current = currentIndex.value
  if (current < 0) return 'future'
  if (index < current) return 'complete'
  if (index > current) return 'future'
  return 'current'
}

function dotClass(index: number) {
  const state = stateOf(index)
  if (state === 'complete') return 'bg-brand-600 text-white ring-brand-600'
  if (state === 'skipped') return 'bg-canvas text-ink-mute ring-line'
  if (state === 'current') return 'bg-brand-50 text-brand-700 ring-brand-200 motion-safe:animate-pulse'
  return 'bg-canvas text-ink-mute ring-line'
}

function labelClass(index: number) {
  const state = stateOf(index)
  if (state === 'complete') return 'text-ink-soft'
  if (state === 'current') return 'font-medium text-brand-700'
  return 'text-ink-mute'
}
</script>

<template>
  <div class="rounded-xl bg-canvas p-3 ring-1 ring-line" aria-live="polite">
    <template v-if="failed">
      <div class="flex items-center justify-between">
        <span class="text-[13px] font-semibold text-ink">生成报告失败</span>
      </div>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <p class="sp-alert-error flex-1 !py-2 text-xs">{{ failed }}</p>
        <button class="sp-btn-secondary shrink-0 !px-3 !py-1.5 text-xs" @click="emit('retry')">再试一次</button>
      </div>
    </template>

    <template v-else-if="fallback">
      <div class="flex items-center justify-between">
        <span class="text-[13px] font-semibold text-ink">评分中…</span>
        <span class="text-[11px] text-ink-mute">旧服务，不显示阶段</span>
      </div>
      <div class="sp-skeleton mt-2 h-0.5 w-full" aria-hidden="true"></div>
    </template>

    <template v-else>
      <div class="flex items-center justify-between gap-2">
        <span class="text-[13px] font-semibold text-ink">{{ done ? '报告已生成' : '正在出报告' }}</span>
        <span class="shrink-0 text-[11px] text-ink-mute">{{ stepNo }}/{{ STAGES.length }} · 已 {{ elapsed }}s</span>
      </div>
      <div class="mt-2 h-0.5 overflow-hidden rounded-full bg-line/70" aria-hidden="true">
        <div
          class="h-full rounded-full bg-brand-500 transition-[width] duration-[240ms] ease-out motion-reduce:transition-none"
          :style="{ width: progressPercent + '%' }"
        ></div>
      </div>
      <div class="sp-stage mt-2.5">
        <template v-for="(step, index) in STAGES" :key="step.key">
          <span
            v-if="index"
            class="h-[2px] w-3 shrink-0 rounded-full transition-colors duration-200 motion-reduce:transition-none sm:w-5"
            :class="index <= completedCount ? 'bg-brand-500' : 'bg-line'"
            aria-hidden="true"
          ></span>
          <span
            class="inline-flex items-center gap-1"
            :aria-current="stateOf(index) === 'current' ? 'step' : undefined"
          >
            <span
              class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] ring-1 transition duration-200 motion-reduce:transition-none"
              :class="dotClass(index)"
            >
              {{ stateOf(index) === 'complete' ? '✓' : index + 1 }}
            </span>
            <span class="text-[11px]" :class="labelClass(index)">{{ step.label }}</span>
            <span v-if="stateOf(index) === 'skipped'" class="text-[10px] text-ink-mute">跳过</span>
            <span
              v-if="step.key === 'coach' && stateOf(index) === 'current' && elapsed > 3"
              class="text-[10px] text-ink-mute"
            >已 {{ elapsed }}s</span>
          </span>
        </template>
      </div>
      <p class="mt-1 h-4 truncate text-[11px] text-ink-mute">{{ toolLine || ' ' }}</p>
    </template>
  </div>
</template>
