<script setup>
import { computed, onMounted, ref } from 'vue'

import api from '../api/client'
import BackLink from '../components/BackLink.vue'
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

function words(arr) {
  return (arr || [])
    .map((x) => (typeof x === 'string' ? x : x?.term || x?.word || ''))
    .filter(Boolean)
}

const relatedRows = computed(() => {
  const rel = current.value?.related || {}
  return [
    { label: '近义', items: words(rel.synonyms) },
    { label: '反义', items: words(rel.antonyms) },
    { label: '同类', items: words(rel.similar) },
  ].filter((r) => r.items.length)
})
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

// ---- 学新单词：范围（高考/四级/六级…）→ 取未学过的词 → 批量加入 ----
const bankOpen = ref(false)
const bankLoading = ref(false)
const bankData = ref(null)
const bankBusy = ref(false)
const bankTip = ref('')

const bankWords = computed(() => bankData.value?.items || [])
const bankScopes = computed(() => bankData.value?.scopes || [])

async function fetchVocab(scope) {
  bankLoading.value = true
  bankTip.value = ''
  try {
    const { data } = await api.get('/study/vocab', { params: scope ? { scope, limit: 10 } : { limit: 10 } })
    bankData.value = data
  } catch (e) {
    bankTip.value = '暂时取不到词库：' + (e?.response?.data?.detail || e.message)
  } finally {
    bankLoading.value = false
  }
}

async function openBank() {
  bankOpen.value = !bankOpen.value
  if (bankOpen.value && !bankData.value) await fetchVocab('')
}

async function pickScope(id) {
  if (bankData.value?.scope === id) return
  await fetchVocab(id)
  // 选过的范围记到服务端，换设备也跟着走
  try {
    await api.patch('/me/settings', { word_scope: id })
  } catch {
    // 记不上不影响本次学习
  }
}

async function addBankWords() {
  if (bankBusy.value || !bankWords.value.length) return
  bankBusy.value = true
  bankTip.value = ''
  try {
    const terms = bankWords.value.map((w) => w.term)
    const { data } = await api.post('/study/vocab/add', {
      scope: bankData.value?.scope,
      terms,
    })
    const parts = []
    if (data.added) parts.push(`加入 ${data.added} 个`)
    if (data.skipped) parts.push(`${data.skipped} 个已在清单里`)
    if (data.limited) parts.push(`${data.limited} 个超过今天的新词上限`)
    bankTip.value = parts.length ? parts.join('，') : '没有加入新词'
    await fetchVocab(bankData.value?.scope)
    await load()
  } catch (e) {
    bankTip.value = '加入失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    bankBusy.value = false
  }
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
          <BackLink :desktop-only="true" />
          <span class="h-4 w-px bg-line"></span>
          <router-link to="/" aria-label="首页">
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

    <main class="sp-shell py-8">
      <div class="sp-card p-5">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="font-semibold text-ink">学新单词</div>
            <p class="mt-0.5 text-xs leading-5 text-ink-mute">
              {{ bankData ? `${bankData.name} · 精选 ${bankData.total} 词 · 已学 ${bankData.learned} 个 · 今天还能学 ${bankData.remaining_today} 个` : '按备考范围挑一批新词' }}
            </p>
          </div>
          <button class="sp-btn-secondary !px-3 !py-1.5 text-xs" @click="openBank">
            {{ bankOpen ? '收起' : '选词库' }}
          </button>
        </div>

        <div v-if="bankOpen" class="mt-4">
          <div class="grid gap-2 sm:grid-cols-3">
            <button
              v-for="sc in bankScopes"
              :key="sc.id"
              class="rounded-xl bg-canvas px-4 py-3 text-left ring-1 transition"
              :class="bankData?.scope === sc.id ? 'ring-brand-300' : 'ring-line/60 hover:ring-brand-200'"
              @click="pickScope(sc.id)"
            >
              <div class="text-sm font-medium text-ink">{{ sc.name }}</div>
              <div class="mt-1 text-[11px] text-ink-mute">已学 {{ sc.learned }} / 精选 {{ sc.total }} 词</div>
            </button>
          </div>

          <p v-if="bankLoading" class="mt-3 text-xs text-ink-mute">正在取词…</p>

          <div v-else-if="bankWords.length" class="mt-3">
            <div class="grid gap-2 sm:grid-cols-2">
              <div v-for="w in bankWords" :key="w.term" class="rounded-xl bg-canvas px-3 py-2 ring-1 ring-line/60">
                <div class="flex items-baseline gap-2">
                  <span class="font-medium text-ink">{{ w.term }}</span>
                  <span v-if="w.phonetic" class="text-[11px] text-ink-mute">{{ w.phonetic }}</span>
                </div>
                <div class="mt-0.5 text-xs leading-5 text-ink-soft">{{ w.pos }} {{ w.meaning_zh }}</div>
              </div>
            </div>
            <p v-if="bankData?.remaining_today === 0" class="mt-3 text-xs leading-5 text-ink-mute">今天的新词学满了，明天再来。</p>
            <button
              class="sp-btn-primary mt-3"
              :disabled="bankBusy || bankData?.remaining_today === 0"
              @click="addBankWords"
            >
              {{ bankBusy ? '加入中…' : `加入这 ${bankWords.length} 个` }}
            </button>
          </div>

          <p v-else-if="!bankLoading" class="mt-3 text-xs text-ink-mute">这一档的词都学过了，换一档看看</p>
          <p v-if="bankTip" class="mt-2 text-xs leading-5 text-ink-soft">{{ bankTip }}</p>
        </div>
      </div>

      <div class="mt-6"></div>

    </main>

    <main class="sp-shell flex min-h-[70vh] flex-col justify-center py-8">
      <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

      <p v-if="loading" class="text-center text-sm text-ink-mute">正在加载…</p>

      <div v-else-if="done" class="flex flex-col items-center text-center">
        <div class="sp-icon-tile h-14 w-14 text-brand-700">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </div>
        <div class="mt-4 text-lg font-semibold text-ink">这一轮复习完了</div>
        <p class="mt-1 max-w-xs text-sm leading-6 text-ink-soft">复习过的词会按记忆间隔排到后面几天，先把今天这几个记住就够。</p>
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
            <div class="mt-2 text-lg font-medium leading-7 text-ink">{{ current.meaning_zh || '按提示写出这个词' }}</div>
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
            <div v-if="relatedRows.length" class="mt-2 space-y-0.5 text-xs leading-5">
              <div v-for="r in relatedRows" :key="r.label">
                <span class="text-ink-mute">{{ r.label }}</span>
                <span class="ml-1 text-ink-soft">{{ r.items.join('、') }}</span>
              </div>
            </div>
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
            <div v-if="relatedRows.length" class="rounded-xl bg-canvas px-3 py-2 text-xs leading-6">
              <div v-for="r in relatedRows" :key="r.label">
                <span class="text-ink-mute">{{ r.label }}</span>
                <span class="ml-1 text-ink-soft">{{ r.items.join('、') }}</span>
              </div>
            </div>
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
