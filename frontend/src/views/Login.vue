<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const auth = useAuthStore()
const settings = useSettingsStore()

const mode = ref('login')
const username = ref('')
const password = ref('')
const nickname = ref('')
const error = ref('')
const loading = ref(false)

async function firstStop() {
  // 没配密钥且服务端也没有兜底密钥时才引导去设置页；接口不可用时放行，别挡住演示
  try {
    const { data } = await api.get('/config/llm')
    return data?.env_configured ? '/' : '/settings?onboarding=1'
  } catch {
    return '/'
  }
}

async function submit() {
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请填写账号和密码'
    return
  }
  loading.value = true
  try {
    const path = mode.value === 'login' ? '/auth/login' : '/auth/register'
    const body =
      mode.value === 'login'
        ? { username: username.value, password: password.value }
        : {
            username: username.value,
            password: password.value,
            nickname: nickname.value || username.value,
          }
    const { data } = await api.post(path, body)
    auth.setAuth(data.token, data.user)
    router.push(settings.configured ? '/' : await firstStop())
  } catch (e) {
    error.value = e?.response?.data?.detail || '请求失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 to-sky-100 px-4">
    <div class="w-full max-w-sm rounded-2xl bg-white p-8 shadow-xl">
      <h1 class="text-2xl font-bold text-slate-900">SpeakPal</h1>
      <p class="mt-1 text-sm text-slate-500">场景化 AI 英语口语陪练</p>

      <div class="mt-6 space-y-3">
        <input
          v-model="username"
          class="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-indigo-400"
          placeholder="账号"
        />
        <input
          v-model="password"
          type="password"
          class="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-indigo-400"
          placeholder="密码"
        />
        <input
          v-if="mode === 'register'"
          v-model="nickname"
          class="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-indigo-400"
          placeholder="昵称（可选）"
        />
      </div>

      <p v-if="error" class="mt-3 text-sm text-rose-500">{{ error }}</p>

      <button
        :disabled="loading"
        class="mt-5 w-full rounded-lg bg-indigo-600 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
        @click="submit"
      >
        {{ loading ? '请稍候…' : mode === 'login' ? '登录' : '注册' }}
      </button>

      <button
        class="mt-3 w-full text-sm text-indigo-600 hover:underline"
        @click="mode = mode === 'login' ? 'register' : 'login'"
      >
        {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
      </button>
    </div>
  </div>
</template>
