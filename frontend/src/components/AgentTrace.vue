<script setup lang="ts">
import { ref, type PropType } from 'vue'

import type { AgentTraceStep } from '../types/api'

defineProps({
  trace: { type: Array as PropType<AgentTraceStep[]>, default: () => [] },
  open: { type: Boolean, default: false },
})

const argsOpen = ref<Record<number, boolean>>({})
const resultOpen = ref<Record<number, boolean>>({})

function argsText(entry: AgentTraceStep) {
  try {
    return JSON.stringify(entry.args || {})
  } catch {
    return '{}'
  }
}

function prettyArgs(entry: AgentTraceStep) {
  try {
    return JSON.stringify(entry.args || {}, null, 2)
  } catch {
    return '{}'
  }
}

function toggleArgs(index: number) {
  argsOpen.value = { ...argsOpen.value, [index]: !argsOpen.value[index] }
}

function toggleResult(index: number) {
  resultOpen.value = { ...resultOpen.value, [index]: !resultOpen.value[index] }
}
</script>

<template>
  <div
    class="grid transition-[grid-template-rows] duration-[320ms] ease-out motion-reduce:transition-none"
    :class="open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
  >
    <div class="overflow-hidden">
      <ol class="sp-timeline mt-3 max-h-[320px] overflow-y-auto overscroll-contain pr-1 max-sm:max-h-[50vh]">
        <li v-for="(entry, index) in trace" :key="`${entry.step}-${entry.tool}-${index}`" class="relative pl-7">
          <div class="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            <span
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] ring-1"
              :class="
                entry.ok
                  ? index === trace.length - 1
                    ? 'bg-brand-50 text-brand-700 ring-brand-100'
                    : 'bg-canvas text-ink-mute ring-line'
                  : 'bg-amber-50 text-amber-800 ring-amber-100'
              "
            >
              {{ entry.step }}
            </span>
            <span class="sp-chip-line !py-0.5 font-mono text-[11px]">{{ entry.tool }}</span>
            <span v-if="!entry.ok" class="text-[11px] text-amber-800">失败</span>
            <span
              class="ml-auto text-[11px]"
              :class="entry.ms > 1500 ? 'text-warn' : 'text-ink-mute'"
            >{{ entry.ms }}ms</span>
          </div>
          <button
            class="mt-1 block w-full truncate text-left font-mono text-[11px] text-ink-mute transition hover:text-ink-soft"
            :aria-expanded="!!argsOpen[index]"
            @click="toggleArgs(index)"
          >
            参数 {{ argsText(entry) }}
          </button>
          <pre
            v-if="argsOpen[index]"
            class="mt-1 max-h-40 overflow-y-auto rounded-lg bg-paper p-2 font-mono text-[11px] leading-5 text-ink-soft"
          >{{ prettyArgs(entry) }}</pre>
          <p class="mt-1 text-[12px] leading-5 text-ink-soft line-clamp-2">{{ entry.summary }}</p>
          <button
            class="mt-0.5 text-[11px] text-brand-700 underline-offset-2 hover:underline"
            :aria-expanded="!!resultOpen[index]"
            @click="toggleResult(index)"
          >
            {{ resultOpen[index] ? '收起原文' : '看原文' }}
          </button>
          <pre
            v-if="resultOpen[index]"
            class="mt-1 max-h-64 overflow-y-auto rounded-lg bg-paper p-2 font-mono text-[12px] leading-5 text-ink-soft"
          >{{ entry.result }}</pre>
        </li>
      </ol>
    </div>
  </div>
</template>
