<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'ok' },
  // bubble：气泡里的小标签（白字半透明底）；page：页面上（浅底 + ring）
  surface: { type: String, default: 'bubble' },
})

const LABELS = {
  ok: '未触发',
  degraded: '降级',
  replaced: '已替换',
  interrupted: '已中断',
  stopped: '已停止',
  flagged: '已标记',
  cloud: '云端转写',
  browser: '浏览器识别',
  mock: '示例报告',
}

const BUBBLE = {
  ok: 'bg-white/15 text-white/90',
  degraded: 'bg-white/15 text-white/90',
  replaced: 'bg-white/15 text-white/90',
  interrupted: 'bg-white/15 text-white/90',
  stopped: 'bg-white/15 text-white/90',
  flagged: 'bg-white/15 text-white/90',
  cloud: 'bg-white/15 text-white/90',
  browser: 'bg-white/10 text-white/85',
  mock: 'bg-white/15 text-white/90',
}

const PAGE = {
  ok: 'bg-brand-50 text-brand-700',
  degraded: 'bg-amber-50 text-amber-800 ring-1 ring-amber-100',
  replaced: 'bg-amber-50 text-amber-800 ring-1 ring-amber-100',
  // 真实错误用 rose（不并入琥珀降级语汇）
  interrupted: 'bg-rose-50 text-danger ring-1 ring-rose-100',
  stopped: 'bg-canvas text-ink-mute ring-1 ring-line',
  flagged: 'bg-canvas text-ink-mute ring-1 ring-line',
  cloud: 'bg-brand-50 text-brand-700 ring-1 ring-brand-100',
  browser: 'bg-canvas text-ink-mute ring-1 ring-line',
  mock: 'bg-amber-50 text-amber-800 ring-1 ring-amber-100',
}

const label = computed(() => LABELS[props.status] || '')
const tone = computed(() => {
  const palette = props.surface === 'page' ? PAGE : BUBBLE
  return palette[props.status] || (props.surface === 'page' ? PAGE.ok : BUBBLE.ok)
})
// ok 不占位、不占高度：调用方可以无脑传
const visible = computed(() => props.status !== 'ok' && !!LABELS[props.status])
</script>

<template>
  <span v-if="visible" class="sp-ai-badge shrink-0" :class="tone">
    <svg v-if="status === 'cloud'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M7 18h10a4 4 0 0 0 .6-8A6 6 0 0 0 5.9 11a3.5 3.5 0 0 0 1.1 7Z" />
    </svg>
    <svg v-else-if="status === 'browser'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.6 2.5 15.4 0 18M12 3c-2.5 2.6-2.5 15.4 0 18" />
    </svg>
    <svg v-else-if="status === 'replaced'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 3 5 6v5c0 4.4 2.9 8.3 7 9.5 4.1-1.2 7-5.1 7-9.5V6l-7-3Z" />
      <path d="M9 12h6" />
    </svg>
    <svg v-else-if="status === 'interrupted'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
      <path d="M12 3v9M12 16v.2" />
      <circle cx="12" cy="12" r="9" />
    </svg>
    <svg v-else-if="status === 'stopped'" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="1.5" />
    </svg>
    <svg v-else-if="status === 'degraded'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 3 2.8 20h18.4L12 3Z" />
      <path d="M12 9v5M12 17v.2" />
    </svg>
    <svg v-else-if="status === 'flagged'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M6 21V4M6 4h11l-2 4 2 4H6" />
    </svg>
    <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="m5 12 4 4L19 6" />
    </svg>
    {{ label }}
  </span>
</template>
