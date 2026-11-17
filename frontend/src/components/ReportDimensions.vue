<script setup>
const props = defineProps({
  report: { type: Object, default: null },
})

const dimLabels = {
  pronunciation: '发音清晰度',
  fluency: '流利度',
  grammar_vocab: '语法词汇',
  task_completion: '任务完成度',
  written_expression: '文字表达',
}

function dimBand(name) {
  const fromScales = props.report?.scales?.dimensions?.[name]?.ielts
  if (typeof fromScales === 'number') return fromScales.toFixed(1)
  const b = props.report?.bands?.[name]
  if (b === null || b === undefined) return ''
  return typeof b === 'number' ? b.toFixed(1) : b
}

function dimCefr(name) {
  return props.report?.scales?.dimensions?.[name]?.cefr || ''
}
</script>

<template>
  <div class="sp-card p-6">
    <div class="flex items-baseline justify-between">
      <div class="font-semibold text-ink">{{ Object.keys(report.dimensions).length }} 个维度</div>
      <span class="text-[11px] text-ink-mute">雅思 · CEFR</span>
    </div>
    <div v-for="(v, k) in report.dimensions" :key="k" class="mb-4 mt-4 last:mb-0">
      <div class="flex items-baseline justify-between text-sm">
        <span class="text-ink-soft">{{ dimLabels[k] || k }}</span>
        <span class="flex items-baseline gap-2">
          <span class="sp-num text-base font-semibold text-ink">{{ v }}</span>
          <span v-if="dimBand(k)" class="text-xs font-normal text-ink-mute">
            雅思 {{ dimBand(k) }}<template v-if="dimCefr(k)"> · {{ dimCefr(k) }}</template>
          </span>
        </span>
      </div>
      <div class="sp-bar mt-2">
        <div class="sp-bar-fill" :style="{ width: v + '%' }"></div>
      </div>
    </div>
  </div>
</template>
