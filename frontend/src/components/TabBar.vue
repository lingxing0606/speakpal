<script setup>
// 移动端底部导航：桌面不显示，避免和页头重复
const tabs = [
  {
    to: '/',
    label: '首页',
    icon: 'M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z',
  },
  {
    to: '/study',
    label: '学习',
    icon: 'M4 5.5h7a2 2 0 0 1 2 2V20a1.8 1.8 0 0 0-1.8-1.8H4zM20 5.5h-5a2 2 0 0 0-2 2V20a1.8 1.8 0 0 1 1.8-1.8H20z',
  },
  {
    to: '/notes',
    label: '笔记',
    icon: 'M6 3.5h9l4 4v13H6zM15 3.5v4h4M9 12h7M9 16h5',
  },
  {
    to: '/settings',
    label: '设置',
    icon: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.2A1.6 1.6 0 0 0 7.5 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 13.5H3a2 2 0 1 1 0-4h.2A1.6 1.6 0 0 0 4.7 7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.2V3a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.4 1.2z',
  },
]
</script>

<template>
  <nav
    class="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
    aria-label="底部导航"
  >
    <div class="flex h-14 items-stretch">
      <router-link
        v-for="t in tabs"
        :key="t.to"
        :to="t.to"
        class="flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] transition"
        :class="$route.path === t.to ? 'text-brand-700' : 'text-ink-mute'"
      >
        <span
          class="flex h-7 w-10 items-center justify-center rounded-full transition"
          :class="$route.path === t.to ? 'bg-brand-50' : ''"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path :d="t.icon" />
          </svg>
        </span>
        {{ t.label }}
      </router-link>
    </div>
  </nav>
</template>
