<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps({
  // crash：页面渲染崩了；stale：旧 chunk 失效且 5 分钟内已重载过一次
  reason: { type: String, default: 'crash' },
})

const router = useRouter()

function reload() {
  window.location.reload()
}
</script>

<template>
  <div class="min-h-screen bg-canvas grid place-items-center px-5">
    <div class="sp-card w-full max-w-sm p-8 text-center">
      <div class="sp-icon-tile mx-auto text-ink-soft" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3 2.8 20h18.4L12 3Z" />
          <path d="M12 9v5M12 17v.2" />
        </svg>
      </div>
      <h1 class="mt-4 text-[20px] font-semibold text-ink">
        {{ props.reason === 'stale' ? '页面需要更新' : '页面出错了' }}
      </h1>
      <p class="mt-1.5 text-[12px] leading-5 text-ink-mute">
        {{ props.reason === 'stale' ? '刷新一次就好。' : '刚输入的内容可能没保存' }}
      </p>
      <div class="mt-5 flex flex-col gap-2">
        <button class="sp-btn-primary w-full" @click="reload">
          {{ props.reason === 'stale' ? '刷新一次' : '刷新页面' }}
        </button>
        <button class="sp-btn-ghost w-full" @click="router.push('/')">回首页</button>
      </div>
    </div>
  </div>
</template>
