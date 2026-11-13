<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import TabBar from '../components/TabBar.vue'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const settings = useSettingsStore()

const scopes = ref([])
const lastScope = ref('')
const loading = ref(true)
const error = ref('')
const dueCount = ref(0)
const picking = ref('')
let pickTimer = null

async function loadScopes() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/study/vocab')
    scopes.value = data?.scopes || []
    lastScope.value = data?.scope || ''
    // 上次范围记在服务端；本地也存一份，旧链接重定向时直接用
    if (data?.scope) settings.setWordScope(data.scope)
  } catch (e) {
    error.value = '加载学习范围失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function loadDue() {
  try {
    const { data } = await api.get('/study/summary')
    dueCount.value = Number(data?.due_count || 0)
  } catch {
    // 取不到就不显示顶部条，不在范围页弹错误
    dueCount.value = 0
  }
}

onMounted(() => {
  loadScopes()
  loadDue()
})

onBeforeUnmount(() => clearTimeout(pickTimer))

function cardClass(sc) {
  if (picking.value) {
    if (picking.value === sc.id) return 'ring-brand-300 bg-brand-50/40 scale-[0.99]'
    return 'opacity-[0.55] scale-[0.98]'
  }
  return lastScope.value === sc.id ? 'ring-brand-300 bg-brand-50/40' : ''
}

function openScope(sc) {
  if (picking.value) return
  picking.value = sc.id
  lastScope.value = sc.id
  // 选过的范围记到服务端，换设备也跟着走；记不上不影响本次学习
  settings.setWordScope(sc.id)
  api.patch('/me/settings', { word_scope: sc.id }).catch(() => {})
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  pickTimer = setTimeout(() => router.push(`/study/${sc.id}`), reduce ? 0 : 240)
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="学习" />

    <!-- 今日复习：有到期卡才出现，和学习同级 -->
    <div v-if="dueCount" class="sticky top-16 z-10 border-b border-line/60 bg-canvas/[0.92] backdrop-blur-md">
      <div class="sp-shell flex h-11 items-center justify-between gap-4">
        <p class="text-xs text-ink-soft">
          今日复习 <span class="sp-num font-semibold text-ink">{{ dueCount }}</span> 张
        </p>
        <router-link to="/review" class="text-xs font-medium text-brand-700 hover:underline">开始 →</router-link>
      </div>
    </div>

    <main class="sp-shell pb-16 pt-10">
      <div class="sp-eyebrow">学习</div>
      <h1 class="sp-title mt-2">选备考范围</h1>

      <p v-if="error" class="sp-alert-error mt-6">{{ error }}</p>

      <div v-if="loading" class="mt-8 grid gap-4 sm:grid-cols-2" aria-label="正在加载学习范围">
        <div v-for="i in 4" :key="i" class="sp-skeleton h-28 rounded-card"></div>
      </div>

      <div v-else class="mt-8 grid gap-4 sm:grid-cols-2">
        <a
          v-for="sc in scopes"
          :key="sc.id"
          :href="`/study/${sc.id}`"
          class="sp-card sp-hover group flex items-start justify-between gap-4 p-5 transition duration-[160ms]"
          :class="cardClass(sc)"
          :aria-disabled="picking ? 'true' : undefined"
          @click.prevent="openScope(sc)"
        >
          <div class="min-w-0">
            <div class="text-[18px] font-semibold leading-7 text-ink">{{ sc.name }} {{ sc.total }} 词</div>
            <div class="mt-1 text-xs text-ink-mute">
              已学 <span class="sp-num">{{ sc.learned ?? 0 }}</span> /
              <span class="sp-num">{{ sc.total }}</span>
            </div>
          </div>
          <span class="sp-arrow h-6 w-6 shrink-0" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </span>
        </a>

        <!-- 自由扩充留到第二批：本批只占位，不做导入与 AI 补卡 -->
        <div class="sp-card-soft flex items-start justify-between gap-4 p-5" aria-disabled="true">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-[18px] font-semibold leading-7 text-ink">自由扩充</span>
              <span class="sp-chip-line">自建</span>
            </div>
            <div class="mt-1 text-xs text-ink-mute">手动添加 · 从报告取词</div>
          </div>
        </div>
      </div>
    </main>

    <TabBar />
  </div>
</template>
