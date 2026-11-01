<script setup>
// 统一空状态：插画（叠层圆 + 浮动点 + 图标）+ 一句话说明 + 行动按钮（默认插槽）。
// icon：practice | cards | notes | chart | done | search | report | key
defineProps({
  icon: { type: String, default: 'practice' },
  title: { type: String, required: true },
  text: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const PATHS = {
  practice: ['M12 3.5a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0v-5a3 3 0 0 1 3-3Z', 'M5.6 11.4a6.4 6.4 0 0 0 12.8 0', 'M12 17.8v3'],
  cards: ['M4 6.5h11a1.5 1.5 0 0 1 1.5 1.5v10A1.5 1.5 0 0 1 15 19.5H4A1.5 1.5 0 0 1 2.5 18V8A1.5 1.5 0 0 1 4 6.5Z', 'M7 4.5h12A1.5 1.5 0 0 1 20.5 6v10'],
  notes: ['M6 3.5h9l4 4v13H6z', 'M15 3.5v4h4', 'M9 12h7M9 16h5'],
  chart: ['M4 19.5h16', 'M7 19.5v-6M12 19.5V7M17 19.5v-9'],
  done: ['M5 12.5l4.5 4.5L19 7.5'],
  search: ['M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Z', 'm15.5 15.5 4.5 4.5'],
  report: ['M6 3.5h12v17H6z', 'M9 8h6M9 12h6M9 16h3'],
  key: ['M8 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M11.5 12h9M17.5 12v3M20.5 12v2'],
}
</script>

<template>
  <div class="flex flex-col items-center text-center" :class="compact ? 'py-6' : 'py-12 sm:py-16'">
    <div class="relative" :class="compact ? 'h-20 w-20' : 'h-28 w-28'" aria-hidden="true">
      <div class="absolute inset-0 rounded-full bg-sand-50"></div>
      <div class="absolute inset-[14%] rounded-full bg-brand-50 ring-1 ring-brand-100"></div>
      <span class="absolute right-[6%] top-[10%] h-2.5 w-2.5 animate-float rounded-full bg-coral-300"></span>
      <span class="absolute bottom-[14%] left-[4%] h-2 w-2 animate-float rounded-full bg-brand-300 [animation-delay:-1.6s]"></span>
      <div class="absolute inset-0 flex items-center justify-center text-brand-700">
        <svg :width="compact ? 26 : 34" :height="compact ? 26 : 34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path v-for="(d, i) in PATHS[icon] || PATHS.practice" :key="i" :d="d" />
        </svg>
      </div>
    </div>
    <div class="font-semibold tracking-tight text-ink" :class="compact ? 'mt-3 text-[15px]' : 'mt-5 text-lg'">{{ title }}</div>
    <p v-if="text" class="mt-1.5 max-w-sm text-sm leading-6 text-ink-soft">{{ text }}</p>
    <div v-if="$slots.default" class="flex flex-wrap justify-center gap-2" :class="compact ? 'mt-4' : 'mt-6'">
      <slot />
    </div>
  </div>
</template>
