<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import TabBar from '../components/TabBar.vue'
import SceneIcon from '../components/SceneIcon.vue'
import { useAuthStore } from '../stores/auth'
import { useSessionStore } from '../stores/session'
import { useSettingsStore } from '../stores/settings'

const router = useRouter()
const auth = useAuthStore()
const session = useSessionStore()
const settings = useSettingsStore()

const scenes = ref([])
const difficulty = ref('medium')
const loading = ref(false)
const error = ref('')
const needKey = ref(false)
const envFallback = ref(false)
const pendingScene = ref(null)
const rec = ref(null)
const pickedDifficulty = ref(false)
const dueCount = ref(0)
const notesCount = ref(0)
const summaryError = ref(false)

const DIFF_LABELS = { easy: '简单', medium: '中等', hard: '困难' }

onMounted(async () => {
  try {
    const { data } = await api.get('/scenes')
    scenes.value = data
  } catch (e) {
    error.value = '加载场景失败：' + (e?.response?.data?.detail || e.message)
  }
  // 按上次成绩推荐难度：没出过分就是中等，用户自己改过就不覆盖
  try {
    const { data } = await api.get('/me/recommendation')
    rec.value = data
    if (!pickedDifficulty.value && data?.recommended_difficulty) {
      difficulty.value = data.recommended_difficulty
    }
  } catch {
    rec.value = null
  }
  // 首页两张卡一次拿全：/study/summary 是聚合接口，口径与 /study/due 的条数一致
  try {
    const { data } = await api.get('/study/summary')
    // due_count / notes_count 是定稿字段；due / notes 是过渡期旧字段，后端改完可删
    dueCount.value = Number(data?.due_count ?? data?.due ?? 0)
    notesCount.value = Number(data?.notes_count ?? data?.notes ?? 0)
    summaryError.value = false
  } catch {
    // 不静默归零：取不到就明说，别让用户以为今天没有复习内容
    summaryError.value = true
  }
})

function pickRecommended() {
  if (!rec.value?.recommended_difficulty) return
  difficulty.value = rec.value.recommended_difficulty
  pickedDifficulty.value = true
}

async function begin(scene) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/sessions', {
      scene_id: scene.id,
      difficulty: difficulty.value,
    })
    session.start(data.session_id, scene, difficulty.value, data.opening_question)
    router.push(`/practice/${data.session_id}`)
  } catch (e) {
    error.value = '开始失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function start(scene) {
  // 用户要求：点场景开练就要先有密钥。本浏览器没填时，先停下来问清楚，
  // 而不是拿服务端兜底 key 悄悄放行
  if (!settings.configured) {
    pendingScene.value = scene
    needKey.value = true
    try {
      const { data } = await api.get('/config/llm')
      envFallback.value = !!data?.env_configured
    } catch {
      envFallback.value = false
    }
    return
  }
  await begin(scene)
}

function useServerKey() {
  const scene = pendingScene.value
  needKey.value = false
  if (scene) begin(scene)
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-16 sm:pb-0">
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-3">
        <div class="flex items-center gap-3">
          <span class="hidden sm:inline-flex">
            <BrandLogo :size="30" wordmark />
          </span>
          <span class="inline-flex sm:hidden">
            <BrandLogo :size="30" />
          </span>
          <span class="hidden h-4 w-px bg-line sm:block"></span>
          <span class="hidden text-xs text-ink-mute sm:block">
            你好，{{ auth.user?.nickname || auth.user?.username }}
          </span>
        </div>
        <div class="hidden items-center gap-1 sm:flex">
          <router-link to="/study" class="sp-btn-ghost">学习</router-link>
          <router-link to="/notes" class="sp-btn-ghost">笔记</router-link>
          <router-link to="/history" class="sp-btn-ghost">历史</router-link>
          <router-link to="/settings" class="sp-btn-ghost">设置</router-link>
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

        <div class="flex flex-col gap-1.5">
          <label class="flex items-center gap-2 text-sm text-ink-soft">
            <span class="text-xs font-medium text-ink-mute">难度</span>
            <select v-model="difficulty" class="sp-select" @change="pickedDifficulty = true">
              <option value="easy">简单</option>
              <option value="medium">中等</option>
              <option value="hard">困难</option>
            </select>
          </label>
          <p v-if="rec" class="text-[11px] leading-5 text-ink-mute sm:text-right">
            推荐 {{ DIFF_LABELS[rec.recommended_difficulty] || rec.recommended_difficulty }} · {{ rec.reason }}
            <button
              v-if="difficulty !== rec.recommended_difficulty"
              class="ml-1 font-medium text-brand-700 underline-offset-2 hover:underline"
              @click="pickRecommended"
            >
              用推荐
            </button>
          </p>
        </div>
      </div>

      <p v-if="error" class="sp-alert-error mt-5">{{ error }}</p>

      <div class="mt-8 grid gap-3 sm:grid-cols-2">
        <router-link
          to="/study"
          class="sp-card group flex items-center justify-between gap-4 p-5 transition duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift active:translate-y-0"
        >
          <div class="min-w-0">
            <div class="text-xs text-ink-mute">今天要复习</div>
            <div class="mt-1.5 flex items-baseline gap-1.5">
              <span v-if="!summaryError" class="sp-num text-[26px] font-semibold leading-none text-ink">{{ dueCount }}</span>
              <span v-else class="text-sm font-medium text-ink-mute">暂时取不到</span>
              <span v-if="!summaryError" class="text-sm text-ink-soft">个词</span>
            </div>
            <p class="mt-1.5 text-xs leading-5 text-ink-mute">
              {{ summaryError ? '过一会儿再刷一次' : dueCount ? '之前错过的，今天再来一遍' : '练完一次，报告里的错词会进来' }}
            </p>
          </div>
          <span class="sp-icon-tile shrink-0 text-brand-700">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 5.5h7a2 2 0 0 1 2 2V20a1.8 1.8 0 0 0-1.8-1.8H4z" />
              <path d="M20 5.5h-5a2 2 0 0 0-2 2V20a1.8 1.8 0 0 1 1.8-1.8H20z" />
            </svg>
          </span>
        </router-link>

        <router-link
          to="/notes"
          class="sp-card group flex items-center justify-between gap-4 p-5 transition duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift active:translate-y-0"
        >
          <div class="min-w-0">
            <div class="text-xs text-ink-mute">笔记</div>
            <div class="mt-1.5 flex items-baseline gap-1.5">
              <span v-if="!summaryError" class="sp-num text-[26px] font-semibold leading-none text-ink">{{ notesCount }}</span>
              <span v-else class="text-sm font-medium text-ink-mute">暂时取不到</span>
              <span v-if="!summaryError" class="text-sm text-ink-soft">条</span>
            </div>
            <p class="mt-1.5 text-xs leading-5 text-ink-mute">
              {{ notesCount ? '上次记到的东西' : '把想记住的说法写下来' }}
            </p>
          </div>
          <span class="sp-icon-tile shrink-0 text-brand-700">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M6 3.5h9l4 4v13H6z" />
              <path d="M15 3.5v4h4" />
              <path d="M9 12h7M9 16h5" />
            </svg>
          </span>
        </router-link>
      </div>

      <div v-if="needKey" class="sp-card mt-5 p-5 ring-brand-100">
        <div class="flex items-start gap-3">
          <div class="sp-icon-tile shrink-0 text-brand-700">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="8" cy="12" r="4" />
              <path d="M12 12h9M17.5 12v3.2M20.5 12v2.2" />
            </svg>
          </div>
          <div class="min-w-0 flex-1">
            <div class="font-semibold text-ink">先接入一个模型密钥</div>
            <p class="mt-1 text-xs leading-5 text-ink-soft">
              练习要靠模型陪聊和评分。密钥只存在你自己的浏览器里，不上传、不写数据库。
              <template v-if="!envFallback">服务端目前也没有兜底密钥，所以必须自己填。</template>
            </p>
            <div class="mt-3 flex flex-wrap items-center gap-2">
              <button class="sp-btn-primary" @click="router.push('/settings?onboarding=1')">去设置填密钥</button>
              <button v-if="envFallback" class="sp-btn-secondary" @click="useServerKey">用服务端密钥继续</button>
              <button class="sp-btn-ghost" @click="needKey = false">取消</button>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-6 grid gap-4 sm:grid-cols-3">
        <button
          v-for="s in scenes"
          :key="s.id"
          :disabled="loading"
          class="group sp-card flex flex-col p-5 text-left transition duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift hover:ring-brand-200 disabled:translate-y-0 disabled:opacity-60"
          @click="start(s)"
        >
          <div class="flex items-center justify-between">
            <div class="sp-icon-tile text-brand-700">
              <SceneIcon :name="s.icon" :size="22" />
            </div>
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

    <TabBar />
  </div>
</template>
