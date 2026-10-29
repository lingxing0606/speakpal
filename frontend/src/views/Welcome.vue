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
    desc: '按 CEFR（欧洲语言共同参考框架）和雅思量表给分，报告里有更地道的说法、中文原因和下一步练什么。',
    icon: 'chart',
  },
]

function begin() {
  // 记「哪个账号看过」，而不是一个全局的 1：同一台机器换账号还能看到引导
  localStorage.setItem('sp_welcomed', auth.user?.username || '1')
  router.push('/')
}
</script>

<template>
  <div class="relative min-h-screen overflow-hidden bg-canvas">
    <div class="pointer-events-none absolute -left-24 -top-32 h-80 w-80 rounded-full bg-brand-200/45 blur-3xl"></div>
    <div class="pointer-events-none absolute -bottom-32 -right-24 h-80 w-80 rounded-full bg-coral-300/30 blur-3xl"></div>

    <div class="relative mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-12">
      <div class="flex flex-col items-center text-center">
        <BrandLogo :size="64" wordmark layout="stacked" subtitle="场景化 AI 英语口语陪练" />
        <p class="mt-5 max-w-md text-sm leading-6 text-ink-soft">
          三步走完，第一次练习大概两分钟。说不出来的时候可以打字，系统不会替你编一个发音分。
        </p>
      </div>

      <div class="mt-8 grid gap-3 sm:grid-cols-3">
        <div v-for="s in steps" :key="s.n" class="sp-card flex flex-col p-5">
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
            <span class="sp-num text-sm font-semibold text-brand-300">{{ s.n }}</span>
          </div>
          <div class="mt-3.5 font-semibold text-ink">{{ s.title }}</div>
          <p class="mt-1 text-xs leading-5 text-ink-soft">{{ s.desc }}</p>
        </div>
      </div>

      <div class="mt-8 flex flex-col items-center gap-3">
        <button class="sp-btn-primary w-full max-w-xs py-3" @click="begin">开始第一次练习</button>
        <p class="text-xs text-ink-mute">这段引导只出现这一次，之后登录直接进首页。</p>
      </div>
    </div>
  </div>
</template>
