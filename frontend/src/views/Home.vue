<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import CountUp from '../components/CountUp.vue'
import EmptyState from '../components/EmptyState.vue'
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
const loading = ref(false)
const error = ref('')
const needKey = ref(false)
const pendingScene = ref(null)
const rec = ref(null)
const dueCount = ref(0)
const notesCount = ref(0)
const summaryError = ref(false)
const scenesLoading = ref(true)
const dash = ref(null)

// 场景卡的色块轮换：同一套暖色系里取，不和品牌青抢
const TINTS = [
  { band: 'bg-brand-50', dot: 'bg-brand-200', icon: 'text-brand-700' },
  { band: 'bg-coral-50', dot: 'bg-coral-100', icon: 'text-coral-700' },
  { band: 'bg-sand-50', dot: 'bg-sand-200', icon: 'text-ink-soft' },
  { band: 'bg-sky-50', dot: 'bg-sky-100', icon: 'text-sky-800' },
  { band: 'bg-amber-50', dot: 'bg-amber-100', icon: 'text-amber-800' },
  { band: 'bg-violet-50', dot: 'bg-violet-100', icon: 'text-violet-800' },
]

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})

// 最近 7 天每天练了几轮（首页小柱状条）
const week = computed(() => {
  const days = dash.value?.heatmap || []
  const last = days.slice(-7)
  const max = Math.max(1, ...last.map((d) => d.count))
  const names = ['日', '一', '二', '三', '四', '五', '六']
  return last.map((d) => ({
    ...d,
    h: d.count ? 18 + (d.count / max) * 82 : 8,
    label: names[new Date(`${d.date}T00:00:00`).getDay()],
  }))
})

const DIFF_LABELS = { easy: '简单', medium: '中等', hard: '困难' }
// 本次会用的难度：设置里的偏好 > 上次成绩推荐 > 中等
const usedDifficulty = computed(() => settings.prefDifficulty || rec.value?.recommended_difficulty || 'medium')

onMounted(async () => {
  try {
    const { data } = await api.get('/scenes')
    scenes.value = data
  } catch (e) {
    error.value = '加载场景失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    scenesLoading.value = false
  }
  try {
    const { data } = await api.get('/me/dashboard', { params: { tz_offset: new Date().getTimezoneOffset() } })
    dash.value = data
  } catch {
    dash.value = null
  }
  // 按上次成绩推荐难度：没出过分就是中等，用户自己改过就不覆盖
  try {
    const { data } = await api.get('/me/recommendation')
    rec.value = data
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

async function begin(scene) {
  loading.value = true
  error.value = ''
  try {
    // 不传 difficulty：服务端会用「设置 → 练习偏好」里的值
    const { data } = await api.post('/sessions', { scene_id: scene.id })
    let diff = usedDifficulty.value
    let plan = data.plan || null
    try {
      const detail = await api.get(`/sessions/${data.session_id}`)
      diff = detail?.data?.difficulty || diff
      plan = detail?.data?.plan || plan
    } catch {
      // 读不到就用本地偏好兜底
    }
    session.start(data.session_id, scene, diff, data.opening_question, plan)
    router.push(`/practice/${data.session_id}`)
  } catch (e) {
    error.value = '开始失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function start(scene) {
  // 点场景开练必须先有密钥：服务端不提供，本浏览器没填就只给「去设置填密钥」这一条路
  if (!settings.configured) {
    pendingScene.value = scene
    needKey.value = true
    return
  }
  begin(scene)
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader />

    <main class="sp-shell pb-16 pt-10 sm:pt-14">
      <!-- 问候 + 今日 -->
      <section class="sp-grid items-end">
        <div class="lg:col-span-7">
          <div class="sp-eyebrow">{{ greeting }}，{{ auth.user?.nickname || auth.user?.username }}</div>
          <h1 class="sp-title mt-3">
            今天想在哪个场景里<br class="hidden sm:block" />
            <span class="text-brand-700">开口说英语？</span>
          </h1>
          <p class="sp-lede">
            选一个场景和 AI 对话几轮，结束后拿到分项评分和逐句改写。本次难度
            <router-link to="/settings#prefs" class="font-medium text-ink underline decoration-sand-300 underline-offset-4 hover:decoration-brand-400">{{ DIFF_LABELS[usedDifficulty] || '中等' }}</router-link>。
          </p>
        </div>

        <div class="lg:col-span-5">
          <div class="sp-card p-5 sm:p-6">
            <div class="flex items-center justify-between">
              <div class="sp-section-title">今天</div>
              <span class="sp-chip" :class="dash?.practiced_today ? 'bg-brand-50 text-brand-700' : 'bg-sand-50 text-ink-mute'">
                {{ dash?.practiced_today ? '已经练过' : '还没开练' }}
              </span>
            </div>
            <div class="mt-4 grid grid-cols-3 gap-2">
              <router-link to="/history" class="sp-stat group transition hover:ring-brand-200">
                <div class="sp-num text-2xl font-semibold text-ink"><CountUp :value="dash?.current_streak || 0" /></div>
                <div class="mt-0.5 text-[11px] text-ink-mute">连续天数</div>
              </router-link>
              <router-link to="/review" class="sp-stat group transition hover:ring-brand-200">
                <div class="sp-num text-2xl font-semibold text-ink">
                  <CountUp v-if="!summaryError" :value="dueCount" />
                  <span v-else class="text-base text-ink-mute">—</span>
                </div>
                <div class="mt-0.5 text-[11px] text-ink-mute">待复习卡</div>
              </router-link>
              <router-link to="/notes" class="sp-stat group transition hover:ring-brand-200">
                <div class="sp-num text-2xl font-semibold text-ink">
                  <CountUp v-if="!summaryError" :value="notesCount" />
                  <span v-else class="text-base text-ink-mute">—</span>
                </div>
                <div class="mt-0.5 text-[11px] text-ink-mute">笔记</div>
              </router-link>
            </div>
            <div v-if="week.length" class="mt-4 flex items-end justify-between gap-1.5" aria-label="最近 7 天每天的练习轮数">
              <div v-for="d in week" :key="d.date" class="flex flex-1 flex-col items-center gap-1" :title="`${d.date}：${d.count} 轮`">
                <div class="flex h-10 w-full items-end">
                  <div
                    class="w-full rounded-md transition-[height] duration-700 ease-out"
                    :class="d.count ? 'bg-brand-400' : 'bg-sand-100'"
                    :style="{ height: d.h + '%' }"
                  ></div>
                </div>
                <span class="text-[10px] text-ink-mute">{{ d.label }}</span>
              </div>
            </div>
            <p v-if="summaryError" class="mt-3 text-[11px] text-ink-mute">复习和笔记数暂时取不到，过一会儿再刷新。</p>
          </div>
        </div>
      </section>

      <p v-if="error" class="sp-alert-error mt-8">{{ error }}</p>

      <div v-if="needKey" class="sp-card mt-8 p-5 ring-brand-100">
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
            </p>
            <div class="mt-3 flex flex-wrap items-center gap-2">
              <button class="sp-btn-primary" @click="router.push('/settings?onboarding=1')">去设置填密钥</button>
              <button class="sp-btn-ghost" @click="needKey = false">取消</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 场景 -->
      <section class="mt-14">
        <div class="flex items-end justify-between gap-4">
          <div>
            <div class="sp-eyebrow">场景</div>
            <h2 class="mt-2 text-xl font-bold tracking-tight text-ink">选一个开始</h2>
          </div>
          <router-link to="/pronunciation" class="sp-link hidden text-[13px] sm:inline">先练 ship / sheep 发音 →</router-link>
        </div>

        <div v-if="scenesLoading" class="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="i in 6" :key="i" class="sp-card-flat overflow-hidden">
            <div class="sp-skeleton h-28 rounded-none"></div>
            <div class="space-y-2 p-5">
              <div class="sp-skeleton h-4 w-1/2"></div>
              <div class="sp-skeleton h-3 w-full"></div>
              <div class="sp-skeleton h-3 w-4/5"></div>
            </div>
          </div>
        </div>

        <div v-else-if="scenes.length" class="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <button
            v-for="(s, i) in scenes"
            :key="s.id"
            :disabled="loading"
            :style="{ '--i': i }"
            class="sp-reveal sp-hover group flex flex-col overflow-hidden rounded-card bg-white text-left shadow-card ring-1 ring-line/80 disabled:pointer-events-none disabled:opacity-60"
            @click="start(s)"
          >
            <div class="relative h-28 overflow-hidden" :class="TINTS[i % TINTS.length].band">
              <span class="absolute -right-6 -top-8 h-28 w-28 rounded-full transition duration-500 group-hover:scale-110" :class="TINTS[i % TINTS.length].dot"></span>
              <span class="absolute bottom-3 right-16 h-3 w-3 rounded-full bg-white/80"></span>
              <div class="absolute bottom-4 left-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-white shadow-soft transition duration-300 group-hover:-rotate-6" :class="TINTS[i % TINTS.length].icon">
                <SceneIcon :name="s.icon" :size="24" />
              </div>
            </div>
            <div class="flex flex-1 flex-col p-5">
              <div class="text-[15px] font-semibold text-ink">{{ s.name }}</div>
              <div class="mt-1.5 flex-1 text-xs leading-5 text-ink-soft">{{ s.desc }}</div>
              <div class="mt-5 flex items-center justify-between">
                <span class="text-xs font-medium text-ink-mute transition group-hover:text-brand-700">
                  {{ loading ? '正在进入…' : '开始对话' }}
                </span>
                <span class="sp-arrow" aria-hidden="true">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                </span>
              </div>
            </div>
          </button>
        </div>

        <div v-else class="sp-card mt-6">
          <EmptyState icon="search" title="场景没加载出来" text="可能是网络断了，点「刷新」再试一次。">
            <button class="sp-btn-primary" @click="$router.go(0)">刷新</button>
          </EmptyState>
        </div>
      </section>
    </main>

    <TabBar />
  </div>
</template>
