<script setup>
import { computed } from 'vue'

import AiStatusBadge from './AiStatusBadge.vue'
import BrandLogo from './BrandLogo.vue'
import ThinkingDots from './ThinkingDots.vue'

const props = defineProps({
  turn: { type: Object, required: true },
  index: { type: Number, required: true },
  // 正在回放的那条用户发言（同一时间只放一句）
  playingIndex: { type: Number, default: -1 },
  speechRate: { type: Number, default: 1 },
  // 思考态已等待的毫秒数（>4s 才显示长等待文案）
  thinkingMs: { type: Number, default: 0 },
})

const emit = defineEmits(['toggle-playback', 'speak', 'retry'])

// 输出侧终态：一次回复只有一个（已替换 > 已中断 > 降级 > 已停止已写在 aiStatus 里）
const outputStatus = computed(() => props.turn.aiStatus || '')
// 已停止 / 已中断的内容不完整，不提供朗读
const canSpeak = computed(
  () => props.turn.role === 'ai' && !props.turn.streaming && !props.turn.pending && props.turn.aiStatus !== 'stopped' && props.turn.aiStatus !== 'interrupted'
)
const hasBadgeRow = computed(() => !!outputStatus.value || !!props.turn.flagged || !!props.turn.retryable)
</script>

<template>
  <div
    :class="props.turn.role === 'ai' ? 'flex items-end justify-start gap-2.5' : 'flex justify-end'"
    class="animate-rise"
    :data-turn="props.index"
  >
    <span v-if="props.turn.role === 'ai'" class="mb-0.5 hidden shrink-0 sm:inline-flex" aria-hidden="true"><BrandLogo :size="28" /></span>
    <div class="flex min-w-0 max-w-[82%] flex-col" :class="props.turn.role === 'ai' ? 'items-start' : 'items-end'">
    <div
      :data-role="props.turn.role"
      :class="
        props.turn.role === 'ai'
          ? 'rounded-[1.25rem] rounded-bl-md bg-white text-ink ring-1 ring-line/80'
          : 'rounded-[1.25rem] rounded-br-md bg-brand-600 text-white'
      "
      :style="props.turn.pending && props.turn.minHeight ? { minHeight: `${props.turn.minHeight}px` } : undefined"
      class="max-w-full px-4 py-3 text-[15px] leading-7 shadow-soft"
    >
      <span
        v-if="props.turn.role === 'user'"
        class="mb-1 inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-white/90"
      >
        <svg v-if="props.turn.mode === 'voice'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
          <rect x="9" y="2.8" width="6" height="11" rx="3" />
          <path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0" />
          <path d="M12 17.8v3.4" />
        </svg>
        <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
          <path d="M4 6h16M4 12h16M4 18h10" />
        </svg>
        {{ props.turn.mode === 'voice' ? '录音' : '打字' }}
      </span>
      <AiStatusBadge
        v-if="props.turn.role === 'user' && props.turn.asrSource"
        class="mb-1 ml-1.5"
        :status="props.turn.asrSource"
        surface="bubble"
      />
      <button
        v-if="props.turn.role === 'user' && props.turn.blob"
        class="mb-1 ml-1 inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-white/90 transition hover:bg-white/25"
        :aria-label="props.playingIndex === props.index ? '停止回放' : '回放我的录音'"
        @click="emit('toggle-playback', props.turn, props.index)"
      >
        <svg v-if="props.playingIndex === props.index" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <rect x="6" y="6" width="12" height="12" rx="1.5" />
        </svg>
        <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M8 5.5v13l10.5-6.5L8 5.5Z" />
        </svg>
        {{ props.playingIndex === props.index ? '停止' : '回放' }}
      </button>
      <!-- 思考态与首字：同一个行盒原地替换（行高 28px），元素不换、位置不变 -->
      <ThinkingDots v-if="props.turn.pending" :elapsed-ms="props.thinkingMs" />
      <span
        v-else
        :class="props.turn.fading ? 'opacity-0' : 'opacity-100 transition-opacity duration-[120ms] ease-out'"
      >{{ props.turn.content }}</span>
      <span
        v-if="props.turn.streaming"
        class="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-brand-300"
        aria-hidden="true"
      ></span>
      <button
        v-if="canSpeak"
        class="ml-1.5 inline-flex h-6 w-6 items-center justify-center rounded-md text-brand-600 transition hover:bg-brand-50"
        aria-label="朗读这句"
        @click="emit('speak', props.turn)"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 9.5h3.2L12 5.6v12.8L7.2 14.5H4a.8.8 0 0 1-.8-.8v-3.4a.8.8 0 0 1 .8-.8Z" />
          <path d="M16 9.2a4 4 0 0 1 0 5.6" />
        </svg>
      </button>
    </div>
    <!-- 徽标行：输出侧在左，重试在右；最多两枚徽标 -->
    <div v-if="props.turn.role === 'ai' && hasBadgeRow" class="sp-badge-row">
      <AiStatusBadge v-if="outputStatus" :status="outputStatus" surface="page" />
      <span class="ml-auto flex items-center gap-2">
        <AiStatusBadge v-if="props.turn.flagged" status="flagged" surface="page" />
        <button
          v-if="props.turn.retryable"
          class="inline-flex h-6 items-center gap-1 px-1.5 text-[11px] font-medium text-brand-700 underline-offset-2 hover:underline"
          aria-label="重发这一句"
          @click="emit('retry', props.turn)"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M20 11a8 8 0 1 0-2.3 5.7" />
            <path d="M20 5v6h-6" />
          </svg>
          重试
        </button>
      </span>
    </div>
    </div>
  </div>
</template>
