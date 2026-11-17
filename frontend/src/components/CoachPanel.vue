<script setup>
import { computed, ref } from 'vue'

import AgentTrace from './AgentTrace.vue'

const props = defineProps({
  coach: { type: Object, default: null },
})
const emit = defineEmits(['open-fix'])

const TOOL_LABELS = {
  lookup_word: '词库',
  grammar_card: '语法卡',
  recent_weakness: '近期错因',
  get_frames: '场景句型',
}

const priorities = computed(() => props.coach?.priorities || [])
const trace = computed(() => props.coach?.trace || [])
const skipped = computed(() => props.coach?.source === 'skipped')
const traceOpen = ref(false)
// `${priorityIndex}-${evidenceIndex}`：同一时间只展开一处证据原文
const activeEvidence = ref('')

function traceFor(evidence) {
  const ref = String(evidence?.ref || '')
  if (!ref) return null
  return trace.value.find((entry) => String(entry.result || '').includes(ref)) || null
}

function visibleEvidence(priority) {
  return (priority.evidence || []).filter((evidence) => traceFor(evidence))
}

function chipLabel(evidence) {
  const tool = TOOL_LABELS[evidence.tool] || evidence.tool || '工具'
  const ref = String(evidence.ref || '')
  const short = ref.length > 24 ? `${ref.slice(0, 24)}…` : ref
  return `${tool} · ${short}`
}

function toggleEvidence(priorityIndex, evidenceIndex) {
  const key = `${priorityIndex}-${evidenceIndex}`
  activeEvidence.value = activeEvidence.value === key ? '' : key
}

function activeEntry(priorityIndex, priority) {
  const index = visibleEvidence(priority).findIndex(
    (_evidence, evidenceIndex) => activeEvidence.value === `${priorityIndex}-${evidenceIndex}`
  )
  return index < 0 ? null : traceFor(visibleEvidence(priority)[index])
}

function argsText(entry) {
  try {
    return JSON.stringify(entry.args || {})
  } catch {
    return '{}'
  }
}
</script>

<template>
  <section class="sp-card p-6">
    <div class="flex min-h-[44px] items-start justify-between gap-3">
      <h2 class="text-base font-semibold text-ink">教练建议 · {{ priorities.length }} 条</h2>
      <button
        v-if="trace.length"
        class="sp-btn-ghost shrink-0 !px-2 !py-1 text-[11px] text-ink-mute"
        :aria-expanded="traceOpen"
        aria-controls="coach-trace"
        @click="traceOpen = !traceOpen"
      >
        AI 诊断过程 · {{ trace.length }} 步
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="transition-transform duration-200 motion-reduce:transition-none"
          :class="traceOpen ? 'rotate-180' : ''"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
    </div>

    <p v-if="coach.summary" class="mt-1 text-[13px] leading-6 text-ink-soft">{{ coach.summary }}</p>

    <p v-if="!priorities.length" class="mt-3 text-[11px] leading-5 text-ink-mute">
      {{ skipped ? '诊断未完成' : '这次没有需要优先改的' }}
    </p>

    <ol v-else class="m-0 list-none p-0">
      <li
        v-for="(priority, priorityIndex) in priorities"
        :key="priorityIndex"
        class="relative"
        :class="[
          priorityIndex ? 'mt-4 border-t border-line/60 pt-4' : 'mt-3',
          priority.grounded ? '' : 'border-l-2 border-dashed border-line pl-3',
        ]"
      >
        <div class="flex items-start gap-2">
          <span class="sp-num text-[20px] leading-6 text-ink-mute">{{ priorityIndex + 1 }}</span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="text-[15px] font-semibold leading-6 text-ink">{{ priority.title || '优先改这一点' }}</h3>
              <span
                v-if="!priority.grounded"
                class="rounded-full bg-canvas px-2 py-0.5 text-[11px] text-ink-mute ring-1 ring-line"
              >推断</span>
            </div>
            <p v-if="priority.why" class="mt-1 text-[13px] leading-6 text-ink-soft line-clamp-3">{{ priority.why }}</p>

            <div v-if="priority.grounded" class="mt-2 flex flex-wrap gap-1.5">
              <button
                v-for="(evidence, evidenceIndex) in visibleEvidence(priority)"
                :key="`${evidence.tool}-${evidence.ref}-${evidenceIndex}`"
                class="sp-chip-line transition duration-150 motion-reduce:transition-none"
                :class="activeEvidence === `${priorityIndex}-${evidenceIndex}` ? 'bg-brand-50 ring-brand-100' : ''"
                :aria-expanded="activeEvidence === `${priorityIndex}-${evidenceIndex}`"
                @click="toggleEvidence(priorityIndex, evidenceIndex)"
              >
                {{ chipLabel(evidence) }}
              </button>
            </div>

            <div
              v-if="priority.grounded && visibleEvidence(priority).length"
              class="sp-evidence motion-reduce:transition-none"
              :class="activeEntry(priorityIndex, priority) ? 'is-open' : ''"
            >
              <div class="p-3">
                <template v-if="activeEntry(priorityIndex, priority)">
                  <p class="truncate font-mono text-[11px] text-ink-mute">
                    参数 {{ argsText(activeEntry(priorityIndex, priority)) }}
                  </p>
                  <pre
                    class="mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-5 text-ink-soft"
                  >{{ activeEntry(priorityIndex, priority).result }}</pre>
                </template>
              </div>
            </div>

            <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p v-if="priority.next_step" class="min-w-0 text-[13px] leading-6 text-ink-soft">
                <span class="text-ink-mute">下一步：</span>{{ priority.next_step }}
              </p>
              <button
                v-if="Number.isInteger(priority.fix_index)"
                class="shrink-0 text-[12px] font-medium text-brand-700 underline-offset-2 hover:underline"
                @click="emit('open-fix', priority.fix_index)"
              >
                看这句
              </button>
            </div>
          </div>
        </div>
      </li>
    </ol>

    <AgentTrace v-if="trace.length" id="coach-trace" :trace="trace" :open="traceOpen" />
  </section>
</template>
