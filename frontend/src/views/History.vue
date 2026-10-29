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

// 后端给的是不带时区的 UTC 串，先补 Z 再解析，否则会当成本地时间差 8 小时
function when(iso) {
  if (!iso) return ''
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function open(item) {
  // 按后端列表字段直接分支，不做「先跳报告页、404 再退回」的试探
  if (item.report_id) return router.push(`/report/${item.id}`)
  if (item.status && item.status !== 'finished') return router.push(`/practice/${item.id}`)
  // finished 却没有报告（生成失败等罕见情况）：报告页会给「还没有报告」的说明
  return router.push(`/report/${item.id}`)
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
        <div class="flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600 ring-1 ring-brand-100">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="9" y="2.8" width="6" height="11" rx="3" />
            <path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0" />
            <path d="M12 17.8v3.4" />
          </svg>
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
          class="sp-card-flat flex cursor-pointer items-center justify-between gap-4 p-4 transition duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift hover:ring-brand-200"
          @click="open(it)"
        >
          <div class="min-w-0">
            <div class="truncate font-medium text-ink">{{ it.scene_name }}</div>
            <div class="mt-1 text-xs text-ink-mute">{{ when(it.created_at) }}</div>
          </div>
          <div class="flex shrink-0 items-center gap-3">
            <div v-if="it.total_score !== null" class="text-right">
              <div class="sp-num text-2xl font-semibold leading-none text-ink">{{ it.total_score }}</div>
              <div class="mt-1 text-[11px] text-ink-mute">综合分</div>
            </div>
            <div v-else-if="it.status && it.status !== 'finished'" class="sp-chip-brand">进行中</div>
            <div v-else class="sp-chip-line">未出分</div>
            <span class="text-[11px] text-ink-mute">{{ it.report_id ? '看报告' : '继续练习' }}</span>
            <span class="text-line transition">→</span>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
