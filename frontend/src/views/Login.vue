<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const settings = useSettingsStore()

// 401 拦截器带过来的原因和原地址：登录过期被踢回来时给一句人话，登录后回到原来那一页
const expired = route.query.expired === '1'
const nextPath = (() => {
  const raw = route.query.next
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string') return ''
  if (!value.startsWith('/') || value.startsWith('//')) return ''
  if (value.startsWith('/login')) return ''
  return value
})()

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
    if (nextPath) {
      router.push(nextPath)
      return
    }
    router.push(settings.configured ? '/' : await firstStop())
  } catch (e) {
    error.value = e?.response?.data?.detail || '请求失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="relative min-h-screen overflow-hidden bg-canvas">
    <div class="pointer-events-none absolute -left-24 -top-32 h-80 w-80 rounded-full bg-brand-200/45 blur-3xl"></div>
    <div class="pointer-events-none absolute -bottom-32 -right-24 h-80 w-80 rounded-full bg-coral-300/30 blur-3xl"></div>

    <div class="relative flex min-h-screen items-center justify-center px-4 py-10">
      <div class="w-full max-w-[400px]">
        <div class="mb-6 flex flex-col items-center text-center">
          <BrandLogo :size="46" />
          <h1 class="mt-3.5 text-2xl font-bold tracking-tight text-ink">SpeakPal</h1>
          <p class="mt-1 text-sm text-ink-soft">场景化 AI 英语口语陪练</p>
        </div>

        <div class="sp-card p-6 sm:p-7">
          <div class="mb-5">
            <div class="text-[15px] font-semibold text-ink">
              {{ mode === 'login' ? '欢迎回来' : '创建账号' }}
            </div>
            <div class="mt-0.5 text-xs text-ink-mute">
              {{ mode === 'login' ? '登录后继续你的口语练习' : '注册后即可开始练习，记录只属于你' }}
            </div>
          </div>

          <div class="space-y-3">
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-ink-soft">账号</span>
              <input v-model="username" class="sp-input" placeholder="账号" autocomplete="username" />
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-ink-soft">密码</span>
              <input
                v-model="password"
                type="password"
                class="sp-input"
                placeholder="密码"
                autocomplete="current-password"
                @keyup.enter="submit"
              />
            </label>
            <label v-if="mode === 'register'" class="block">
              <span class="mb-1.5 block text-xs font-medium text-ink-soft">昵称</span>
              <input
                v-model="nickname"
                class="sp-input"
                placeholder="昵称（可选）"
                @keyup.enter="submit"
              />
            </label>
          </div>

          <p v-if="expired" class="sp-alert-warn mt-4">登录状态已过期，重新登录就能接着练（练习记录还在）。</p>

          <p v-if="error" class="sp-alert-error mt-4">{{ error }}</p>

          <button
            :disabled="loading"
            class="sp-btn-primary mt-5 w-full py-2.5"
            @click="submit"
          >
            {{ loading ? '请稍候…' : mode === 'login' ? '登录' : '注册' }}
          </button>

          <div class="mt-4 text-center">
            <button class="sp-link" @click="mode = mode === 'login' ? 'register' : 'login'">
              {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
            </button>
          </div>
        </div>

        <p class="mt-5 text-center text-xs text-ink-mute">
          练习记录按账号独立保存，密钥只留在你自己的浏览器里
        </p>
      </div>
    </div>
  </div>
</template>
