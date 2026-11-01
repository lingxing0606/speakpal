<script setup>
// 数字从 0 数到目标值（约 0.8 秒，缓出）。系统开了「减少动态效果」就直接显示终值。
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  decimals: { type: Number, default: 0 },
  duration: { type: Number, default: 800 },
})

const shown = ref(0)
let raf = 0

function run(to) {
  cancelAnimationFrame(raf)
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduce || !Number.isFinite(to)) {
    shown.value = to
    return
  }
  const from = 0
  const start = performance.now()
  const step = (now) => {
    const t = Math.min(1, (now - start) / props.duration)
    const eased = 1 - Math.pow(1 - t, 3)
    shown.value = from + (to - from) * eased
    if (t < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}

watch(() => props.value, run, { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <span>{{ Number(shown).toFixed(decimals) }}</span>
</template>
