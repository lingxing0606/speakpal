<script setup>
// 输入区上沿的动态提示卡：头部（标题 / 来源徽标 / 换一批 / 收起）+ 条目 + 骨架。
// 只负责展示与本地小动效；取数、计数、填入都在 Practice.vue。
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  hints: { type: Array, default: () => [] },
  source: { type: String, default: 'frames' }, // llm | frames
  loading: { type: Boolean, default: false }, // 冷启动：条目区骨架
  busy: { type: Boolean, default: false }, // 已有条目的刷新中（换一批）
  canRefresh: { type: Boolean, default: true },
})

const emit = defineEmits(['pick', 'refresh', 'close'])

// 展示用副本：换一批时先让旧行淡出 140ms，再原地换新（规格四 C）
const display = ref([...(props.hints || [])])
const phase = ref('idle') // idle | out | in
const picked = ref(-1)
let phaseTimer = null
let pickTimer = null

watch(
  () => props.hints,
  (next) => {
    const fresh = next || []
    if (!display.value.length || !fresh.length) {
      display.value = fresh
      phase.value = 'idle'
      return
    }
    phase.value = 'out'
    clearTimeout(phaseTimer)
    phaseTimer = setTimeout(() => {
      display.value = fresh
      phase.value = 'in'
      phaseTimer = setTimeout(() => (phase.value = 'idle'), 260)
    }, 140)
  }
)

onBeforeUnmount(() => {
  clearTimeout(phaseTimer)
  clearTimeout(pickTimer)
})

const showSkeleton = computed(() => props.loading && !display.value.length)
const dimmed = computed(() => props.busy || props.loading)

function rowClass(hint, i) {
  return [
    'flex w-full items-start gap-2 px-3 py-2.5 text-left transition duration-[140ms] ease-out',
    phase.value === 'out' ? 'pointer-events-none -translate-y-1.5 opacity-0' : 'sp-hint-row-in',
    picked.value === i ? 'bg-brand-50' : 'hover:bg-canvas/70 active:scale-[0.995]',
    i ? 'border-t border-line/60' : '',
  ]
}

function rowStyle(i) {
  const style = { '--hi': i }
  if (phase.value === 'in') {
    style.animationDelay = '60ms'
    style.animationDuration = '180ms'
  }
  return style
}

function pick(hint, i, event) {
  if (dimmed.value) return
  picked.value = i
  clearTimeout(pickTimer)
  pickTimer = setTimeout(() => (picked.value = -1), 140)
  emit('pick', hint, event)
}
</script>

<template>
  <div class="sp-hint-card" role="dialog" aria-label="动态提示">
    <div class="flex h-11 items-center gap-1.5 border-b border-line/60 px-3">
      <span class="text-[12px] font-semibold text-ink">这样说更顺</span>
      <span
        v-if="!showSkeleton"
        class="inline-flex h-[18px] items-center rounded-full px-1.5 text-[10px] font-medium"
        :class="source === 'llm' ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100' : 'bg-white text-ink-mute ring-1 ring-line'"
      >
        {{ source === 'llm' ? 'AI 生成' : '通用句型' }}
      </span>
      <div class="ml-auto flex items-center gap-1">
        <button
          class="inline-flex h-7 min-w-[40px] items-center justify-center gap-1 rounded-lg px-1.5 text-[11px] text-ink-mute transition hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="!canRefresh || busy || loading"
          aria-label="换一批提示"
          @click="emit('refresh')"
        >
          <svg
            :class="busy || loading ? 'animate-spin' : ''"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M20 11a8 8 0 1 0-2.6 5.9" />
            <path d="M20 4.5V11h-6.2" />
          </svg>
          {{ busy ? '在想…' : '换一批' }}
        </button>
        <button
          class="inline-flex h-6 w-6 items-center justify-center rounded-md text-base leading-none text-ink-mute transition hover:bg-canvas"
          aria-label="收起提示"
          @click="emit('close')"
        >
          ×
        </button>
      </div>
    </div>

    <div
      class="max-h-[min(46vh,320px)] overflow-y-auto pb-1"
      :class="dimmed ? 'pointer-events-none opacity-45' : ''"
    >
      <div v-if="showSkeleton" class="space-y-2 p-3" aria-label="正在生成提示">
        <div class="sp-skeleton h-8"></div>
        <div class="sp-skeleton h-8"></div>
      </div>
      <template v-else>
        <button
          v-for="(hint, i) in display"
          :key="`${i}-${hint.en}`"
          :class="rowClass(hint, i)"
          :style="rowStyle(i)"
          @click="pick(hint, i, $event)"
        >
          <span class="min-w-0 flex-1">
            <span class="block text-[13px] font-medium leading-5 text-ink">{{ hint.en }}</span>
            <span class="mt-0.5 block text-[11px] leading-5 text-ink-mute">{{ hint.zh }}</span>
          </span>
          <span class="mt-0.5 inline-flex h-4 shrink-0 items-center rounded-full bg-canvas px-1.5 text-[10px] text-ink-mute ring-1 ring-line/70">
            {{ hint.tag }}
          </span>
        </button>
      </template>
    </div>
  </div>
</template>
