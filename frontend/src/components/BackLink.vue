<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  // 直接打开这个页面（没有历史栈）时回到哪
  fallback: { type: String, default: '/' },
})

const router = useRouter()
const hasHistory = computed(() => window.history.length > 1)

// 统一口径：有历史栈就回上一级，直接打开就回父页面；四个二级页都用这一套
function goBack() {
  if (hasHistory.value) router.back()
  else router.push(props.fallback)
}
</script>

<template>
  <button class="sp-btn-ghost !px-2" aria-label="返回" @click="goBack">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M14.5 6 8.5 12l6 6" />
    </svg>
    返回
  </button>
</template>
