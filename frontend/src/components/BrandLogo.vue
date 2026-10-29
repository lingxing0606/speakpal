<script setup>
import { computed } from 'vue'

// SpeakPal 品牌标：气泡（你在说）+ 三根递增高声波柱（口语 / 进步 / 评分）+ 星标（陪练回应）
// 图形只有一份真源：frontend/public/*.svg。组件只负责挑版本、尺寸和字标，不再内联几何——
// 改色/改形只改 SVG，全站（页头、登录页、favicon）一起生效。
// 档位：≥32px 带星标（logo.svg / logo-inverse.svg）；<32px 用居中简化版（logo-mark*.svg）。
const props = defineProps({
  size: { type: Number, default: 32 },
  tone: { type: String, default: 'color' }, // color | inverse
  badge: { type: Boolean, default: true }, // 星标；< 32px 自动隐藏（会和气泡糊成一团）
  wordmark: { type: Boolean, default: false },
  subtitle: { type: String, default: '' },
  layout: { type: String, default: 'inline' }, // inline（页头）| stacked（欢迎页、答辩封面）
})

const showBadge = computed(() => props.badge && props.size >= 32)
const src = computed(() => {
  const inverse = props.tone === 'inverse'
  if (showBadge.value) return inverse ? '/logo-inverse.svg' : '/logo.svg'
  return inverse ? '/logo-mark-inverse.svg' : '/logo-mark.svg'
})
const wordTone = computed(() => (props.tone === 'inverse' ? 'text-white' : 'text-ink'))
const palTone = computed(() => (props.tone === 'inverse' ? 'text-brand-300' : 'text-brand-600'))
const subtitleTone = computed(() => (props.tone === 'inverse' ? 'text-slate-400' : 'text-ink-mute'))
const fontSize = computed(() => `${Math.round(props.size * 0.62)}px`)
const stacked = computed(() => props.layout === 'stacked')
// 横排：图标 + 字标同一基线（页头）。竖排：图标在上、字标居中在下（欢迎页首屏）。
const wrapClass = computed(() =>
  stacked.value
    ? 'inline-flex flex-col items-center gap-3 text-center'
    : 'inline-flex items-center gap-2.5 align-middle',
)
const wordClass = computed(() =>
  stacked.value ? 'flex flex-col items-center leading-tight' : 'flex flex-col leading-tight',
)
</script>

<template>
  <span :class="wrapClass">
    <img
      :src="src"
      :width="size"
      :height="size"
      :alt="wordmark ? '' : 'SpeakPal'"
      class="shrink-0"
      draggable="false"
    />

    <span v-if="wordmark" :class="wordClass">
      <span class="font-bold tracking-tight" :class="wordTone" :style="{ fontSize }">
        Speak<span :class="palTone">Pal</span>
      </span>
      <span v-if="subtitle" class="mt-[2px] text-[11px]" :class="subtitleTone">{{ subtitle }}</span>
    </span>
  </span>
</template>
