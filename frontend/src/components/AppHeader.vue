<script>
// 每个页面各自渲染页头，切页时页头会重新挂载；
// 这里（模块作用域，不随组件销毁）记住上一次黑块的位置，新页头从那里滑到当前项。
let lastIndicator = null
</script>

<script setup>
// 全站统一页头：左侧返回 / 标志 / 页面名，桌面端右侧主导航，插槽放页面自己的操作。
// 移动端主导航交给底部 TabBar（同一个 sm 断点切换，避免两套导航同时出现或同时消失）。
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
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
  { to: '/review', label: '复习' },
  { to: '/study', label: '学习' },
  { to: '/notes', label: '笔记' },
  { to: '/history', label: '历史' },
  { to: '/settings', label: '设置' },
]

function active(to) {
  return to === '/' ? route.path === '/' : route.path.startsWith(to)
}

// ---------------------------------------------------------------- 滑动黑块
const navEl = ref(null)
const linkEls = []
const activeIndex = LINKS.findIndex((l) => active(l.to))
const fromIndicator = activeIndex >= 0 && lastIndicator && lastIndicator.index !== activeIndex ? lastIndicator : null
// 白字跟着黑块走：滑动开始前先停在上一页的那一项，免得白字落在浅底上
const highlight = ref(fromIndicator ? fromIndicator.index : activeIndex)
const ind = reactive({ x: 0, w: 0, show: false })
const animate = ref(false)

function measure(i) {
  const comp = linkEls[i]
  const el = comp?.$el ?? comp
  if (!el || !el.offsetWidth) return null
  return { x: el.offsetLeft, w: el.offsetWidth }
}

function save() {
  const m = measure(activeIndex)
  if (m) lastIndicator = { index: activeIndex, ...m }
}

function place(withAnim) {
  const m = measure(activeIndex)
  if (!m) {
    ind.show = false
    return
  }
  animate.value = withAnim
  ind.x = m.x
  ind.w = m.w
  ind.show = true
  highlight.value = activeIndex
  save()
}

function onResize() {
  if (activeIndex >= 0) place(false)
}

onMounted(async () => {
  await nextTick()
  if (activeIndex < 0) {
    // 报告页等不在主导航里的页面：下次进主导航页时黑块直接出现，不从奇怪的位置滑过来
    lastIndicator = null
    return
  }
  if (fromIndicator) {
    animate.value = false
    ind.x = fromIndicator.x
    ind.w = fromIndicator.w
    ind.show = true
    // 等浏览器先画出起点，再开过渡滑到终点
    requestAnimationFrame(() => requestAnimationFrame(() => place(true)))
  } else {
    place(false)
  }
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => window.removeEventListener('resize', onResize))
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
        <nav v-if="nav" ref="navEl" class="relative ml-1 hidden items-center gap-0.5 rounded-full bg-white/70 p-1 ring-1 ring-line/80 sm:flex" aria-label="主导航">
          <span
            class="pointer-events-none absolute inset-y-1 left-0 rounded-full bg-ink shadow-soft"
            :class="animate ? 'transition-[transform,width] duration-[380ms] ease-[cubic-bezier(0.3,0.9,0.25,1)]' : ''"
            :style="{ width: `${ind.w}px`, transform: `translateX(${ind.x}px)`, opacity: ind.show ? 1 : 0 }"
            aria-hidden="true"
          ></span>
          <router-link
            v-for="(l, i) in LINKS"
            :key="l.to"
            :ref="(el) => (linkEls[i] = el)"
            :to="l.to"
            class="relative z-10 rounded-full px-3 py-1.5 text-[13px] font-medium transition-colors duration-300"
            :class="highlight === i && ind.show ? 'text-white' : 'text-ink-soft hover:bg-sand-50 hover:text-ink'"
            :aria-current="active(l.to) ? 'page' : undefined"
          >
            {{ l.label }}
          </router-link>
        </nav>
      </div>
    </div>
  </header>
</template>
