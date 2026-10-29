<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'

const router = useRouter()
const items = ref([])
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/sessions')
    items.value = data
  } catch (e) {
    error.value = '加载失败：' + (e?.response?.data?.detail || e.message)
  }
})

function open(item) {
  if (item.total_score !== null) {
    router.push(`/report/${item.id}`)
  }
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-3">
        <div class="flex items-center gap-3">
          <router-link to="/" aria-label="返回首页">
            <BrandLogo :size="30" />
          </router-link>
          <span class="h-4 w-px bg-line"></span>
          <div class="font-semibold text-ink">历史记录</div>
        </div>
        <div class="flex items-center gap-1">
          <router-link to="/settings" class="sp-btn-ghost">设置</router-link>
          <button class="sp-btn-ghost" @click="router.push('/')">返回首页</button>
        </div>
      </div>
    </header>

    <main class="sp-shell py-8">
      <p v-if="error" class="sp-alert-error">{{ error }}</p>

      <div class="mb-4 flex items-baseline justify-between">
        <h1 class="text-xl font-bold tracking-tight text-ink">我的练习</h1>
        <span class="text-xs text-ink-mute">{{ items.length }} 次</span>
      </div>

      <div v-if="items.length === 0 && !error" class="sp-card flex flex-col items-center px-6 py-14 text-center">
        <div class="flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-2xl ring-1 ring-brand-100">
          🎤
        </div>
        <div class="mt-4 font-semibold text-ink">还没有练习记录。</div>
        <p class="mt-1 max-w-xs text-sm leading-6 text-ink-soft">
          选一个场景说上几句，结束后就能在这里看到每次的分数和纠错。
        </p>
        <button class="sp-btn-primary mt-5" @click="router.push('/')">去练一次</button>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="it in items"
          :key="it.id"
          :class="it.total_score !== null ? 'cursor-pointer hover:-translate-y-0.5 hover:shadow-lift hover:ring-brand-200' : ''"
          class="sp-card-flat flex items-center justify-between gap-4 p-4 transition duration-200 ease-out"
          @click="open(it)"
        >
          <div class="min-w-0">
            <div class="truncate font-medium text-ink">{{ it.scene_name }}</div>
            <div class="mt-1 text-xs text-ink-mute">{{ it.created_at }}</div>
          </div>
          <div class="flex shrink-0 items-center gap-3">
            <div v-if="it.total_score !== null" class="text-right">
              <div class="sp-num text-2xl font-semibold leading-none text-ink">{{ it.total_score }}</div>
              <div class="mt-1 text-[11px] text-ink-mute">综合分</div>
            </div>
            <div
              v-else
              class="sp-chip-line"
            >
              未出分
            </div>
            <span
              class="text-line transition"
              :class="it.total_score !== null ? 'group-hover:text-brand-400' : 'opacity-0'"
            >→</span>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
