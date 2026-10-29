<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import { useAuthStore } from '../stores/auth'
import { useSessionStore } from '../stores/session'
import { KEY_REQUIRED_MESSAGE, llmReady } from '../utils/llmGate'

const router = useRouter()
const auth = useAuthStore()
const session = useSessionStore()

const scenes = ref([])
const difficulty = ref('medium')
const loading = ref(false)
const error = ref('')

const icons = { briefcase: '💼', coffee: '☕', book: '📘' }

onMounted(async () => {
  try {
    const { data } = await api.get('/scenes')
    scenes.value = data
  } catch (e) {
    error.value = '加载场景失败：' + (e?.response?.data?.detail || e.message)
  }
})

async function start(scene) {
  loading.value = true
  error.value = ''
  try {
    const gate = await llmReady()
    if (!gate.ok) {
      error.value = KEY_REQUIRED_MESSAGE
      router.push('/settings?onboarding=1')
      return
    }
    const { data } = await api.post('/sessions', {
      scene_id: scene.id,
      difficulty: difficulty.value,
    })
    session.start(data.session_id, scene, difficulty.value, data.opening_question)
    router.push('/practice')
  } catch (e) {
    error.value = '开始失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-3">
        <div class="flex items-center gap-3">
          <BrandLogo :size="30" wordmark />
          <span class="hidden h-4 w-px bg-line sm:block"></span>
          <span class="hidden text-xs text-ink-mute sm:block">
            你好，{{ auth.user?.nickname || auth.user?.username }}
          </span>
        </div>
        <div class="flex items-center gap-1">
          <router-link to="/history" class="sp-btn-ghost">历史记录</router-link>
          <router-link to="/settings" class="sp-btn-ghost">设置</router-link>
          <button class="sp-btn-ghost" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <main class="sp-shell py-9">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 class="text-[26px] font-bold leading-tight tracking-tight text-ink">
            选一个场景，开始说英语
          </h1>
          <p class="mt-1.5 text-sm text-ink-soft">和 AI 角色多轮对话，结束后拿到评分和逐句纠错。</p>
          <p class="mt-1 text-xs text-ink-mute sm:hidden">
            你好，{{ auth.user?.nickname || auth.user?.username }}
          </p>
        </div>

        <label class="flex items-center gap-2 text-sm text-ink-soft">
          <span class="text-xs font-medium text-ink-mute">难度</span>
          <select v-model="difficulty" class="sp-select">
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
        </label>
      </div>

      <p v-if="error" class="sp-alert-error mt-5">{{ error }}</p>

      <div class="mt-6 grid gap-4 sm:grid-cols-3">
        <button
          v-for="s in scenes"
          :key="s.id"
          :disabled="loading"
          class="group sp-card flex flex-col p-5 text-left transition duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift hover:ring-brand-200 disabled:translate-y-0 disabled:opacity-60"
          @click="start(s)"
        >
          <div class="flex items-center justify-between">
            <div class="sp-icon-tile">{{ icons[s.icon] || '🎯' }}</div>
            <span class="text-lg text-line transition group-hover:text-brand-400">→</span>
          </div>
          <div class="mt-3.5 font-semibold text-ink">{{ s.name }}</div>
          <div class="mt-1 text-xs leading-5 text-ink-soft">{{ s.desc }}</div>
          <div class="mt-4 text-xs font-medium text-brand-700 opacity-0 transition group-hover:opacity-100">
            开始练习
          </div>
        </button>
      </div>

      <div v-if="!scenes.length && !error" class="mt-6 grid gap-4 sm:grid-cols-3">
        <div v-for="i in 3" :key="i" class="sp-card-flat animate-pulse p-5">
          <div class="h-11 w-11 rounded-2xl bg-brand-50"></div>
          <div class="mt-4 h-3.5 w-2/3 rounded bg-slate-100"></div>
          <div class="mt-2 h-3 w-full rounded bg-slate-100"></div>
        </div>
      </div>

      <p class="mt-8 text-center text-xs text-ink-mute">
        每一轮都由 AI 角色追问，结束后按 CEFR / 雅思量表出分
      </p>
    </main>
  </div>
</template>
