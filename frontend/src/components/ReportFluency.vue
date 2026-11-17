<script setup lang="ts">
import type { PropType } from 'vue'

import EmptyState from './EmptyState.vue'

const props = defineProps({
  // 已按中文标签筛好的指标（Report.vue 里算，页签计数也用同一份）
  items: { type: Object as PropType<Record<string, unknown>>, default: () => ({}) },
  // 字段中文名：筛选与展示共用同一份表，避免两处漂移
  labels: { type: Object as PropType<Record<string, string>>, default: () => ({}) },
  typedOnly: { type: Boolean, default: false },
})
</script>

<template>
  <div v-if="Object.keys(props.items).length" class="sp-card p-6">
    <div class="font-semibold text-ink">{{ props.typedOnly ? '文字表达指标' : '流利度与表达指标' }}</div>
    <div class="mt-3.5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
      <div v-for="(v, k) in props.items" :key="k" class="rounded-xl bg-canvas px-3.5 py-3 ring-1 ring-line/60">
        <div class="text-[11px] text-ink-mute">{{ props.labels[k] }}</div>
        <div class="sp-num mt-1 text-[15px] font-semibold text-ink">{{ v }}</div>
      </div>
    </div>
  </div>
  <EmptyState
    v-else
    compact
    icon="chart"
    title="这次没有可测指标"
    text="录音或打字多聊几轮，词数、语速这些数字就会出现。"
  />
</template>
