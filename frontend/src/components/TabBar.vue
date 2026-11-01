<script setup>
// 移动端底部导航：桌面不显示（与 AppHeader 的主导航同一个 sm 断点切换）
import { useRoute } from 'vue-router'

const route = useRoute()

const tabs = [
  { to: '/', label: '首页', icon: ['M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z'] },
  {
    to: '/study',
    label: '学习',
    icon: ['M4 5.5h7a2 2 0 0 1 2 2V20a1.8 1.8 0 0 0-1.8-1.8H4z', 'M20 5.5h-5a2 2 0 0 0-2 2V20a1.8 1.8 0 0 1 1.8-1.8H20z'],
  },
  { to: '/notes', label: '笔记', icon: ['M6 3.5h9l4 4v13H6z', 'M15 3.5v4h4', 'M9 12h7M9 16h5'] },
  { to: '/history', label: '历史', icon: ['M12 20.5a8.5 8.5 0 1 0-8.5-8.5', 'M3.5 7v5h5', 'M12 7.5V12l3 2'] },
  {
    to: '/settings',
    label: '设置',
    icon: [
      'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4z',
      'M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.2A1.6 1.6 0 0 0 7.5 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 13.5H3a2 2 0 1 1 0-4h.2A1.6 1.6 0 0 0 4.7 7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.2V3a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.4 1.2z',
    ],
  },
]

function active(to) {
  return to === '/' ? route.path === '/' : route.path.startsWith(to)
}
</script>

<template>
  <nav
    class="fixed inset-x-0 bottom-0 z-30 border-t border-line/80 bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md sm:hidden"
    aria-label="底部导航"
  >
    <div class="flex h-16 items-stretch">
      <router-link
        v-for="t in tabs"
        :key="t.to"
        :to="t.to"
        class="flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition active:scale-95"
        :class="active(t.to) ? 'text-brand-700' : 'text-ink-mute'"
        :aria-current="active(t.to) ? 'page' : undefined"
      >
        <span
          class="flex h-7 w-12 items-center justify-center rounded-full transition duration-200"
          :class="active(t.to) ? 'bg-brand-50 ring-1 ring-brand-100' : ''"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path v-for="(d, i) in t.icon" :key="i" :d="d" />
          </svg>
        </span>
        {{ t.label }}
      </router-link>
    </div>
  </nav>
</template>
