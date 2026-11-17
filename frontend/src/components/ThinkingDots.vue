<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 从发送到现在的毫秒数：>4s 才开始写「对方正在思考…」，>10s 再补「已 10s」
  elapsedMs: { type: Number, default: 0 },
})

const slow = computed(() => props.elapsedMs >= 4000)
const seconds = computed(() => Math.floor(props.elapsedMs / 1000))
</script>

<template>
  <!-- 行高固定 28px：三点与文字在同一个行盒里原地替换，气泡高度不变 -->
  <span
    class="sp-thinking flex h-7 items-center gap-2"
    role="status"
    aria-label="对方正在思考"
  >
    <span class="sp-thinking-dots" aria-hidden="true">
      <span class="sp-thinking-dot"></span>
      <span class="sp-thinking-dot"></span>
      <span class="sp-thinking-dot"></span>
    </span>
    <span v-if="slow" class="whitespace-nowrap text-[11px] text-ink-mute">
      对方正在思考…<template v-if="seconds >= 10"> 已 {{ seconds }}s</template>
    </span>
  </span>
</template>
