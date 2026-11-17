<script setup>
import { computed } from 'vue'

const props = defineProps({
  transparency: { type: Object, default: null },
})

const safety = computed(() => props.transparency?.safety || {})
const scores = computed(() => props.transparency?.scores || null)
const coach = computed(() => props.transparency?.coach || null)
const model = computed(() => String(props.transparency?.model || ''))
const flagged = computed(() => Number(safety.value.flagged_inputs || 0))
const replaced = computed(() => Number(safety.value.replaced_replies || 0))
const hasSafety = computed(() => flagged.value > 0 || replaced.value > 0)
const hasScores = computed(
  () => typeof scores.value?.model_ratio === 'number' && typeof scores.value?.rule_ratio === 'number'
)
const hasData = computed(
  () => !!model.value || hasSafety.value || hasScores.value || !!coach.value
)

const coachText = computed(() => {
  if (!coach.value) return '—'
  return `${coach.value.grounded ?? 0} / ${coach.value.total ?? 0} 条有证据`
})
</script>

<template>
  <section v-if="hasData" class="sp-card-soft p-5 max-sm:p-4">
    <div class="text-xs font-semibold text-ink">AI 透明度</div>
    <div class="mt-3 space-y-2 max-sm:grid max-sm:grid-cols-2 max-sm:gap-3 max-sm:space-y-0">
      <div class="flex items-baseline gap-2 max-sm:flex-col max-sm:gap-0.5">
        <span class="w-[72px] shrink-0 text-[11px] text-ink-mute max-sm:w-auto">模型</span>
        <span v-if="model" class="min-w-0 truncate text-xs text-ink" :title="model">{{ model }}</span>
        <span v-else class="text-xs text-ink-mute">—</span>
      </div>

      <div class="flex items-baseline gap-2 max-sm:flex-col max-sm:gap-0.5">
        <span class="w-[72px] shrink-0 text-[11px] text-ink-mute max-sm:w-auto">安全</span>
        <span v-if="!hasSafety" class="text-xs text-ink">未触发</span>
        <span v-else class="flex flex-wrap items-center gap-1">
          <span v-if="flagged" class="rounded-full bg-canvas px-1.5 py-0.5 text-[10px] font-medium text-ink-mute ring-1 ring-line">
            输入标记 <span class="sp-num">{{ flagged }}</span>
          </span>
          <span v-if="replaced" class="rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 ring-1 ring-amber-100">
            回复替换 <span class="sp-num">{{ replaced }}</span>
          </span>
        </span>
      </div>

      <div class="flex items-baseline gap-2 max-sm:flex-col max-sm:gap-0.5">
        <span class="w-[72px] shrink-0 text-[11px] text-ink-mute max-sm:w-auto">分数构成</span>
        <span v-if="hasScores" class="text-xs text-ink">
          模型 <span class="sp-num">{{ scores.model_ratio }}%</span> ·
          规则 <span class="sp-num">{{ scores.rule_ratio }}%</span>
        </span>
        <span v-else class="text-xs text-ink-mute">—</span>
      </div>

      <div class="flex items-baseline gap-2 max-sm:flex-col max-sm:gap-0.5">
        <span class="w-[72px] shrink-0 text-[11px] text-ink-mute max-sm:w-auto">教练证据</span>
        <span class="text-xs" :class="coach ? 'text-ink' : 'text-ink-mute'">{{ coachText }}</span>
      </div>
    </div>
  </section>
</template>
