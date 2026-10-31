<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  // 直接打开这个页面（没有历史栈）时回到哪
  fallback: { type: String, default: '/' },
  // 移动端底部 tab 的根页面不显示返回，避免点返回直接退出站点
  desktopOnly: { type: Boolean, default: false },
})

const router = useRouter()
const hasHistory = computed(() => window.history.length > 1)

function goBack() {
  if (hasHistory.value) router.back()
  else router.push(props.fallback)
}
</script>

<template>
  <button
    class="sp-btn-ghost !px-2"
    :class="desktopOnly ? 'hidden sm:inline-flex' : 'inline-flex'"
    aria-label="返回"
    @click="goBack"
  >
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M14.5 6 8.5 12l6 6" />
    </svg>
    返回
  </button>
</template>
