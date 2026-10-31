<script setup>
import { computed, onMounted, ref } from 'vue'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import TabBar from '../components/TabBar.vue'
import { speakSmart } from '../utils/speech'

const loading = ref(true)
const error = ref('')
const items = ref([])
const index = ref(0)
const revealed = ref(false)
const busy = ref(false)
const answer = ref('')
const judged = ref(null)

const KIND_LABELS = { word: '单词', phrase: '短语', spelling: '拼写' }

const current = computed(() => items.value[index.value] || null)
const isSpelling = computed(() => (current.value?.kind || '') === 'spelling')
const done = computed(() => !loading.value && !current.value)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/study/due')
    items.value = Array.isArray(data) ? data : data?.items || []
    index.value = 0
    resetCard()
  } catch (e) {
    if (e?.response?.status === 404) {
      items.value = []
    } else {
      error.value = '加载复习清单失败：' + (e?.response?.data?.detail || e.message)
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)

function resetCard() {
  revealed.value = false
  answer.value = ''
  judged.value = null
}

function reveal() {
  if (isSpelling.value) return
  revealed.value = true
}

function speakTerm() {
  const term = current.value?.term
  if (term) speakSmart(term, { rate: 0.95 })
}

// 拼写卡：默写，按编辑距离判档（全对 good、差 1–2 个字母 hard、其余 again）
function distance(a, b) {
  const s = (a || '').toLowerCase().trim()
  const t = (b || '').toLowerCase().trim()
  const dp = Array.from({ length: s.length + 1 }, (_, i) => [i, ...Array(t.length).fill(0)])
  for (let j = 0; j <= t.length; j += 1) dp[0][j] = j
  for (let i = 1; i <= s.length; i += 1) {
    for (let j = 1; j <= t.length; j += 1) {
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + (s[i - 1] === t[j - 1] ? 0 : 1)
      )
    }
  }
  return dp[s.length][t.length]
}

function gradeForSpelling() {
  const term = current.value?.term || ''
  const d = distance(answer.value, term)
  if (d === 0) return { grade: 'good', text: '拼对了' }
  if (d <= 2) return { grade: 'hard', text: `差 ${d} 个字母` }
  return { grade: 'again', text: '再看一眼正确写法' }
}

async function submitSpelling() {
  if (!answer.value.trim() || busy.value) return
  const { grade, text } = gradeForSpelling()
  judged.value = { grade, text }
  revealed.value = true
  await sendReview(grade)
}

async function gradeSelf(g) {
  if (busy.value) return
  await sendReview(g)
}

async function sendReview(grade) {
  const item = current.value
  if (!item) return
  busy.value = true
  try {
    await api.post(`/study/items/${item.id}/review`, { grade })
    index.value += 1
    resetCard()
  } catch (e) {
    error.value = '提交复习结果失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-16 sm:pb-0">
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-3">
        <div class="flex items-center gap-3">
          <router-link to="/" aria-label="返回首页">
            <BrandLogo :size="30" />
          </router-link>
          <span class="h-4 w-px bg-line"></span>
          <div class="font-semibold text-ink">复习</div>
        </div>
        <div class="flex items-center gap-1">
          <router-link to="/history" class="sp-btn-ghost">历史</router-link>
        </div>
      </div>
    </header>

    <main class="sp-shell flex min-h-[70vh] flex-col justify-center py-10">
      <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

      <p v-if="loading" class="text-center text-sm text-ink-mute">正在加载…</p>

      <div v-else-if="done" class="flex flex-col items-center text-center">
        <div class="sp-icon-tile h-14 w-14 text-brand-700">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </div>
        <div class="mt-4 text-lg font-semibold text-ink">这一轮复习完了</div>
        <p class="mt-1 max-w-xs text-sm leading-6 text-ink-soft">明天还会有到期的词，先记住今天这几个就够。</p>
        <div class="mt-6 flex gap-2">
          <router-link to="/notes" class="sp-btn-secondary">看笔记</router-link>
          <router-link to="/" class="sp-btn-primary">去练一次</router-link>
        </div>
      </div>

      <div v-else-if="current" class="mx-auto w-full max-w-xl">
        <div class="mb-3 flex items-baseline justify-between text-xs text-ink-mute">
          <span>{{ index + 1 }} / {{ items.length }}</span>
          <span class="sp-chip-line">{{ KIND_LABELS[current.kind] || current.kind }}</span>
        </div>

        <div v-if="isSpelling" class="sp-card p-8">
          <div class="text-center">
            <div class="text-xs text-ink-mute">按释义写出单词</div>
            <div class="mt-2 text-lg font-medium leading-7 text-ink">{{ current.meaning_zh || '看语境，写出对应的那个词' }}</div>
            <p v-if="current.context" class="mt-3 text-sm leading-6 text-ink-soft">{{ current.context }}</p>
          </div>

          <div class="mt-6 flex items-center gap-2">
            <input
              v-model="answer"
              class="sp-input text-center font-mono text-lg"
              placeholder="拼写"
              :disabled="!!judged"
              @keyup.enter="submitSpelling"
            />
            <button class="sp-btn-primary shrink-0" :disabled="!answer.trim() || busy || !!judged" @click="submitSpelling">
              提交
            </button>
          </div>

          <div v-if="judged" class="mt-4 rounded-xl px-4 py-3 text-sm"
               :class="judged.grade === 'good' ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100' : 'bg-amber-50 text-amber-800 ring-1 ring-amber-100'">
            <div class="flex items-center justify-between gap-2">
              <span class="font-medium">{{ judged.text }}</span>
              <button class="sp-btn-ghost !px-2 !py-1 text-xs" @click="speakTerm">听一遍</button>
            </div>
            <div class="mt-1">正确写法：<span class="font-mono font-medium">{{ current.term }}</span></div>
          </div>
        </div>

        <div
          v-else
          class="sp-card cursor-pointer select-none p-8 text-center transition duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lift active:translate-y-0"
          @click="reveal"
        >
          <div class="flex items-center justify-center gap-2">
            <span class="sp-num text-[34px] font-semibold leading-tight text-ink">{{ current.term }}</span>
            <button class="sp-btn-ghost !p-1.5" aria-label="朗读" @click.stop="speakTerm">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M4 9.5h3.2L12 5.6v12.8L7.2 14.5H4a.8.8 0 0 1-.8-.8v-3.4a.8.8 0 0 1 .8-.8Z" />
                <path d="M16 9.2a4 4 0 0 1 0 5.6" />
              </svg>
            </button>
          </div>
          <p v-if="current.context" class="mt-3 text-sm leading-6 text-ink-soft">{{ current.context }}</p>

          <div v-if="revealed" class="mt-6 space-y-2 text-left">
            <p v-if="current.meaning_zh" class="text-sm leading-6 text-ink">{{ current.meaning_zh }}</p>
            <p v-if="current.example" class="rounded-xl bg-canvas px-3 py-2 text-sm leading-6 text-ink-soft">
              {{ current.example }}
            </p>
          </div>
        </div>

        <div v-if="revealed && !isSpelling" class="mt-5 grid grid-cols-3 gap-2.5">
          <button class="sp-btn-secondary !py-2.5" :disabled="busy" @click="gradeSelf('again')">忘了</button>
          <button class="sp-btn-secondary !py-2.5" :disabled="busy" @click="gradeSelf('hard')">模糊</button>
          <button class="sp-btn-primary !py-2.5" :disabled="busy" @click="gradeSelf('good')">认识</button>
        </div>
      </div>
    </main>

    <TabBar />
  </div>
</template>
