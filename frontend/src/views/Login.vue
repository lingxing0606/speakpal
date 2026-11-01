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

// 401 拦截器带过来的原因和原地址：按原因给不同提示，登录后回到原来那一页
const kickReason = (() => {
  const raw = route.query.reason
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value === 'string' && value) return value
  return route.query.expired === '1' ? 'expired' : ''
})()
const kicked = !!kickReason
const KICK_TEXTS = {
  password_changed: '密码已修改，请用新密码重新登录。',
  user_gone: '这个账号已注销，重新注册一个就能继续练。',
  token_invalid: '登录凭证已失效，重新登录即可。',
  unauthenticated: '请先登录。',
}
const kickText =
  KICK_TEXTS[kickReason] || '登录状态已过期，重新登录即可继续。'
const nextPath = (() => {
  const raw = route.query.next
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string') return ''
  if (!value.startsWith('/') || value.startsWith('//')) return ''
  if (value.startsWith('/login')) return ''
  // 欢迎页已删除，旧的 next=/welcome 不再当跳转目标
  if (value.startsWith('/welcome')) return ''
  return value
})()

const mode = ref('login')
const showPwd = ref(false)
const username = ref('')
const password = ref('')
const nickname = ref('')
const error = ref('')
const loading = ref(false)

async function firstStop() {
  // 服务端不再提供密钥：本浏览器填过就直接进首页，没填就去设置页
  return settings.configured ? '/' : '/settings?onboarding=1'
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
    // 登录/注册后直接进首页；本浏览器没 key 才去设置页填
    router.push(await firstStop())
  } catch (e) {
    error.value = e?.response?.data?.detail || '请求失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-canvas lg:grid lg:grid-cols-2">
    <!-- 品牌面板（桌面） -->
    <aside class="relative hidden overflow-hidden bg-ink p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div class="pointer-events-none absolute -left-20 -top-24 h-96 w-96 rounded-full bg-brand-500/35 blur-3xl"></div>
      <div class="pointer-events-none absolute -bottom-32 right-0 h-96 w-96 rounded-full bg-coral-500/20 blur-3xl"></div>
      <div class="relative"><BrandLogo :size="40" tone="inverse" wordmark /></div>
      <div class="relative max-w-md">
        <div class="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/50">Speak · Review · Remember</div>
        <p class="mt-5 text-[34px] font-bold leading-[1.2] tracking-tight">在真实场景里开口，<br />拿到看得懂的反馈。</p>
        <div class="mt-10 space-y-3">
          <div class="max-w-xs rounded-[1.25rem] rounded-bl-md bg-white/10 px-4 py-3 text-sm leading-6 ring-1 ring-white/10 animate-rise">
            Could you tell me a bit about yourself?
          </div>
          <div class="ml-auto max-w-xs rounded-[1.25rem] rounded-br-md bg-brand-500 px-4 py-3 text-sm leading-6 animate-rise [animation-delay:150ms]">
            I'm a student and I love building web apps.
          </div>
          <div class="max-w-xs rounded-2xl bg-white px-4 py-3 text-ink shadow-lift animate-rise [animation-delay:300ms]">
            <div class="flex items-baseline justify-between"><span class="text-xs text-ink-mute">综合得分</span><span class="sp-num text-2xl font-semibold">78</span></div>
            <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-brand-50"><div class="h-full w-[78%] rounded-full bg-brand-500"></div></div>
          </div>
        </div>
      </div>
      <p class="relative text-xs text-white/40">练习记录按账号独立保存，密钥只留在你自己的浏览器里</p>
    </aside>

    <div class="relative flex min-h-screen items-center justify-center px-5 py-10">
      <div class="w-full max-w-[400px]">
        <div class="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
          <span class="lg:hidden"><BrandLogo :size="46" /></span>
          <div class="sp-eyebrow mt-4 lg:mt-0">SpeakPal</div>
          <h1 class="mt-2 text-[28px] font-bold tracking-tight text-ink">{{ mode === 'login' ? '欢迎回来' : '创建账号' }}</h1>
          <p class="mt-1.5 text-sm text-ink-soft">{{ mode === 'login' ? '登录后继续你的口语练习' : '注册后即可开始练习，记录只属于你' }}</p>
        </div>

        <div class="sp-card p-6 sm:p-7">
          <div class="space-y-3">
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-ink-soft">账号</span>
              <input
                v-model="username"
                class="sp-input"
                placeholder="登录用户名"
                autocomplete="username"
              />
            </label>
            <div class="block">
              <label class="mb-1.5 block text-xs font-medium text-ink-soft" for="sp-password">密码</label>
              <div class="relative">
                <input
                  id="sp-password"
                  v-model="password"
                  :type="showPwd ? 'text' : 'password'"
                  class="sp-input pr-11"
                  placeholder="至少 6 位"
                  autocomplete="current-password"
                  @keyup.enter="submit"
                />
                <button
                  type="button"
                  class="absolute inset-y-0 right-1 my-auto flex h-8 w-8 items-center justify-center rounded-lg text-ink-mute transition hover:bg-canvas hover:text-ink-soft"
                  :aria-label="showPwd ? '隐藏密码' : '显示密码'"
                  :aria-pressed="showPwd"
                  @click="showPwd = !showPwd"
                >
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
                    <circle cx="12" cy="12" r="3" />
                    <path v-if="showPwd" d="M4 20 20 4" />
                  </svg>
                </button>
              </div>
              <p v-if="mode === 'login'" class="mt-1 text-[11px] text-ink-mute">
                忘记密码？可以让管理员在后台重置。
              </p>
            </div>
            <label v-if="mode === 'register'" class="block">
              <span class="mb-1.5 block text-xs font-medium text-ink-soft">昵称</span>
              <input
                v-model="nickname"
                class="sp-input"
                placeholder="昵称"
                @keyup.enter="submit"
              />
            </label>
          </div>

          <p v-if="kicked" class="mt-4 rounded-xl bg-brand-50 px-3.5 py-2.5 text-sm leading-6 text-brand-700 ring-1 ring-brand-100">
            {{ kickText }}
          </p>

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

        <p class="mt-6 text-center text-xs text-ink-mute lg:hidden">
          练习记录按账号独立保存，密钥只留在你自己的浏览器里
        </p>
      </div>
    </div>
  </div>
</template>
