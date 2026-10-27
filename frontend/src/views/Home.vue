<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useSessionStore } from '../stores/session'

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
  <div class="min-h-screen bg-slate-50">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <div>
          <div class="text-lg font-bold">SpeakPal</div>
          <div class="text-xs text-slate-500">你好，{{ auth.user?.nickname || auth.user?.username }}</div>
        </div>
        <div class="flex items-center gap-3 text-sm">
          <router-link to="/history" class="text-indigo-600 hover:underline">历史记录</router-link>
          <button class="text-slate-500 hover:text-slate-800" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-3xl px-4 py-8">
      <h1 class="text-2xl font-bold text-slate-900">选一个场景，开始说英语</h1>
      <p class="mt-1 text-sm text-slate-500">和 AI 角色多轮对话，结束后拿到评分和逐句纠错。</p>

      <div class="mt-5 flex items-center gap-3 text-sm">
        <span class="text-slate-500">难度</span>
        <select v-model="difficulty" class="rounded-lg border border-slate-200 px-3 py-1.5">
          <option value="easy">简单</option>
          <option value="medium">中等</option>
          <option value="hard">困难</option>
        </select>
      </div>

      <p v-if="error" class="mt-4 text-sm text-rose-500">{{ error }}</p>

      <div class="mt-5 grid gap-4 sm:grid-cols-3">
        <button
          v-for="s in scenes"
          :key="s.id"
          :disabled="loading"
          class="rounded-2xl bg-white p-5 text-left shadow-sm ring-1 ring-slate-200 hover:ring-indigo-400 disabled:opacity-60"
          @click="start(s)"
        >
          <div class="text-3xl">{{ icons[s.icon] || '🎯' }}</div>
          <div class="mt-3 font-semibold text-slate-900">{{ s.name }}</div>
          <div class="mt-1 text-xs leading-5 text-slate-500">{{ s.desc }}</div>
        </button>
      </div>
    </main>
  </div>
</template>
