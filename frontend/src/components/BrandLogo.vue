<script setup>
import { computed } from 'vue'

// SpeakPal 品牌标：气泡（你在说）+ 三根递增高声波柱（口语 / 进步 / 评分）+ 星标（陪练回应）
// 几何与 frontend/public/logo.svg、logo-mark.svg 完全一致；内联是为了不发额外请求、并支持深色底反白。
// 色值只取 docs/ui-visual.md 的色板：brand-600 #14806F、白、星标 #38BDF8。不引入第四色。
const props = defineProps({
  size: { type: Number, default: 32 },
  tone: { type: String, default: 'color' }, // color | inverse
  badge: { type: Boolean, default: true }, // 星标；< 32px 自动隐藏（会和气泡糊成一团）
  wordmark: { type: Boolean, default: false },
  subtitle: { type: String, default: '' },
})

const bubble = computed(() => (props.tone === 'inverse' ? '#FFFFFF' : '#14806F'))
const bar = computed(() => (props.tone === 'inverse' ? '#14806F' : '#FFFFFF'))
const wordTone = computed(() => (props.tone === 'inverse' ? 'text-white' : 'text-ink'))
const palTone = computed(() => (props.tone === 'inverse' ? 'text-brand-300' : 'text-brand-600'))
const subtitleTone = computed(() => (props.tone === 'inverse' ? 'text-slate-400' : 'text-ink-mute'))
const fontSize = computed(() => `${Math.round(props.size * 0.62)}px`)
const showBadge = computed(() => props.badge && props.size >= 32)
</script>

<template>
  <span class="inline-flex items-center gap-2.5 align-middle">
    <svg
      :width="size"
      :height="size"
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      class="shrink-0"
      :role="wordmark ? 'presentation' : 'img'"
      :aria-label="wordmark ? undefined : 'SpeakPal'"
    >
      <title v-if="!wordmark">SpeakPal</title>
      <g :fill="bubble">
        <rect x="2" y="14" width="40" height="30" rx="10" />
        <path d="M12 43 C10.4 46.8 8.4 51.4 7.4 54.2 C6.7 56.4 8.3 57.4 10.2 56.2 L28 43.5 Z" />
      </g>
      <g :fill="bar">
        <rect x="10" y="25" width="5" height="8" rx="2.5" />
        <rect x="19.5" y="22" width="5" height="14" rx="2.5" />
        <rect x="29" y="19" width="5" height="20" rx="2.5" />
      </g>
      <g v-if="showBadge">
        <circle cx="53" cy="11" r="10" fill="#38BDF8" />
        <path
          d="M53 4.8 Q54.1 9.9 59.2 11 Q54.1 12.1 53 17.2 Q51.9 12.1 46.8 11 Q51.9 9.9 53 4.8 Z"
          fill="#FFFFFF"
        />
      </g>
    </svg>

    <span v-if="wordmark" class="flex flex-col leading-tight">
      <span class="font-bold tracking-tight" :class="wordTone" :style="{ fontSize }">
        Speak<span :class="palTone">Pal</span>
      </span>
      <span v-if="subtitle" class="mt-[2px] text-[11px]" :class="subtitleTone">{{ subtitle }}</span>
    </span>
  </span>
</template>
