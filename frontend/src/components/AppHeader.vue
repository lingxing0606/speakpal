<script setup>
// 全站统一页头：左侧返回 / 标志 / 页面名，桌面端右侧主导航，插槽放页面自己的操作。
// 移动端主导航交给底部 TabBar（同一个 sm 断点切换，避免两套导航同时出现或同时消失）。
import { useRoute } from 'vue-router'

import BackLink from './BackLink.vue'
import BrandLogo from './BrandLogo.vue'

defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  // 传了就显示「返回」，值是直接打开页面时的回退地址
  back: { type: String, default: '' },
  nav: { type: Boolean, default: true },
  narrow: { type: Boolean, default: false },
})

const route = useRoute()

const LINKS = [
  { to: '/', label: '首页' },
  { to: '/study', label: '学习' },
  { to: '/notes', label: '笔记' },
  { to: '/history', label: '历史' },
  { to: '/settings', label: '设置' },
]

function active(to) {
  return to === '/' ? route.path === '/' : route.path.startsWith(to)
}
</script>

<template>
  <header class="sp-header">
    <div :class="narrow ? 'sp-shell-narrow' : 'sp-shell'" class="flex h-16 items-center justify-between gap-4">
      <div class="flex min-w-0 items-center gap-2.5">
        <BackLink v-if="back" :fallback="back" />
        <span v-if="back" class="h-4 w-px bg-line"></span>
        <router-link to="/" aria-label="首页" class="shrink-0 rounded-lg transition hover:opacity-80">
          <span v-if="!title" class="hidden sm:inline-flex"><BrandLogo :size="30" wordmark /></span>
          <span :class="title ? 'inline-flex' : 'inline-flex sm:hidden'"><BrandLogo :size="30" /></span>
        </router-link>
        <template v-if="title">
          <span class="h-4 w-px bg-line"></span>
          <div class="min-w-0">
            <div class="truncate text-sm font-semibold text-ink">{{ title }}</div>
            <div v-if="subtitle" class="truncate text-[11px] text-ink-mute">{{ subtitle }}</div>
          </div>
        </template>
        <slot name="left" />
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <slot />
        <nav v-if="nav" class="ml-1 hidden items-center gap-0.5 rounded-full bg-white/70 p-1 ring-1 ring-line/80 sm:flex" aria-label="主导航">
          <router-link
            v-for="l in LINKS"
            :key="l.to"
            :to="l.to"
            class="rounded-full px-3 py-1.5 text-[13px] font-medium transition duration-200"
            :class="active(l.to) ? 'bg-ink text-white' : 'text-ink-soft hover:bg-sand-50 hover:text-ink'"
            :aria-current="active(l.to) ? 'page' : undefined"
          >
            {{ l.label }}
          </router-link>
        </nav>
      </div>
    </div>
  </header>
</template>
