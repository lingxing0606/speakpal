<script setup>
import { useRouter } from 'vue-router'

import BrandLogo from '../components/BrandLogo.vue'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const steps = [
  {
    n: '01',
    title: '选一个真实场景',
    desc: '咖啡店点单、酒店入住、机场值机、求职面试、雅思 Part 1、餐厅点餐，六选一。',
    icon: 'chat',
  },
  {
    n: '02',
    title: '开口说，说不出来就打字',
    desc: '麦克风录音会转写成文字；打字不计发音和流利度，只算文字表达，不会假装听了你的发音。',
    icon: 'mic',
  },
  {
    n: '03',
    title: '拿到评分和逐句纠错',
    desc: '按 CEFR、雅思量表给分，报告里有更地道的说法、中文原因和下一步练什么。',
    icon: 'chart',
  },
]

function begin() {
  // 这次浏览里已经看过介绍，登录/注册后就不再自动弹一遍
  try {
    sessionStorage.setItem('sp_intro_seen', '1')
  } catch {
    // 隐私模式下 sessionStorage 可能不可用，忽略
  }
  if (!auth.token) {
    router.push('/login')
    return
  }
  // 记「哪个账号看过」，而不是一个全局的 1：同一台机器换账号还能看到引导
  localStorage.setItem('sp_welcomed', auth.user?.username || '1')
  router.push('/')
}
</script>

<template>
  <div class="relative min-h-screen overflow-hidden bg-canvas">
    <div class="pointer-events-none absolute -right-32 -top-40 h-[28rem] w-[28rem] rounded-full bg-brand-100/70 blur-3xl"></div>
    <div class="pointer-events-none absolute -bottom-40 -left-32 h-[26rem] w-[26rem] rounded-full bg-coral-100/60 blur-3xl"></div>

    <div class="sp-shell relative flex min-h-screen flex-col py-8">
      <div class="flex items-center justify-between">
        <BrandLogo :size="32" wordmark />
        <button class="sp-btn-ghost" @click="begin">{{ auth.token ? '跳过' : '登录' }}</button>
      </div>

      <div class="flex flex-1 flex-col justify-center py-12">
        <div class="max-w-3xl">
          <div class="sp-eyebrow animate-rise">场景化 AI 英语口语陪练</div>
          <h1 class="mt-4 text-[40px] font-bold leading-[1.1] tracking-tight text-ink animate-rise [animation-delay:80ms] sm:text-[56px]">
            把英语说出口，<br /><span class="text-brand-700">再看清哪里能更好。</span>
          </h1>
          <p class="mt-6 max-w-xl text-[15px] leading-7 text-ink-soft animate-rise [animation-delay:160ms]">
            三步走完，第一次练习大概两分钟。说不出来的时候可以打字，系统不会替你编一个发音分。
          </p>
          <div class="mt-8 flex flex-wrap items-center gap-3 animate-rise [animation-delay:240ms]">
            <button class="sp-btn-primary px-6 py-3 text-[15px]" @click="begin">
              {{ auth.token ? '开始第一次练习' : '开始使用' }}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
            <span class="text-xs text-ink-mute">不用装任何东西，Chrome 打开就能说</span>
          </div>
        </div>

        <div class="mt-16 grid gap-5 sm:grid-cols-3">
          <div v-for="(s, i) in steps" :key="s.n" :style="{ '--i': i + 4 }" class="sp-reveal sp-hover sp-card flex flex-col p-6">
            <div class="flex items-center justify-between">
              <div class="sp-icon-tile text-brand-700">
                <svg v-if="s.icon === 'mic'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="9" y="2.8" width="6" height="11" rx="3" />
                  <path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0" />
                  <path d="M12 17.8v3.4" />
                </svg>
                <svg v-else-if="s.icon === 'chart'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M4 19h16" />
                  <path d="M7 19V9M12 19V5M17 19v-6" />
                </svg>
                <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M4 11.5A7 7 0 0 1 11 4.5h2a7 7 0 0 1 7 7v3a7 7 0 0 1-7 7h-1.6l-3.4 2.4v-3.1A7 7 0 0 1 4 14.5Z" />
                  <path d="M9 11h6M9 14h4" />
                </svg>
              </div>
              <span class="sp-num text-2xl font-semibold text-sand-300">{{ s.n }}</span>
            </div>
            <div class="mt-5 font-semibold text-ink">{{ s.title }}</div>
            <p class="mt-1.5 text-[13px] leading-6 text-ink-soft">{{ s.desc }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
