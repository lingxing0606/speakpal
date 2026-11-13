<script setup>
import { computed, onMounted, ref } from 'vue'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import TabBar from '../components/TabBar.vue'
import { speakSmart } from '../utils/speech'

const KIND_LABELS = { word: '单词', spelling: '拼写', grammar: '语法', phrase: '短语' }

const loading = ref(true)
const error = ref('')
const groups = ref([])
const index = ref(0)
const revealed = ref(false)
const busy = ref(false)
const answer = ref('')
const judged = ref(null)

const queue = computed(() => groups.value.flatMap((g) => g.items || []))
const current = computed(() => queue.value[index.value] || null)
const isSpelling = computed(() => current.value?.kind === 'spelling')
const isGrammar = computed(() => current.value?.kind === 'grammar')
const isSpoken = computed(() => current.value?.kind === 'phrase' && current.value?.source === 'spoken')
const done = computed(() => !loading.value && !current.value)

const emptyState = computed(() => {
  if (!queue.value.length) {
    return { title: '今天没有要复习的', text: '练完一次，或学几个新词、加几张语法和口语卡，这里就会有内容。' }
  }
  return { title: '这一轮做完了', text: '做过的卡会按记忆间隔排到后面几天，先把今天这几张记住就够。' }
})

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

// 语法卡：term 语法点、meaning_zh 规则、context 错句、example 正确句，
// related.blank/answer 是服务端算好的挖空和答案
const grammarBlank = computed(() => String(current.value?.related?.blank || ''))
const grammarAnswerHint = computed(() => String(current.value?.related?.answer || ''))
// 拼写卡的纠错原因放在 related.reason，判完之后才显示，不能出现在题干上
const spellingReason = computed(() => String(current.value?.related?.reason || ''))

function cardLabel(item) {
  if (!item) return ''
  if (item.kind === 'phrase') return item.source === 'spoken' ? '口语' : '短语'
  return KIND_LABELS[item.kind] || item.kind
}

async function loadToday() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/study/today')
    groups.value = data?.groups || []
    index.value = 0
    resetCard()
  } catch (e) {
    if (e?.response?.status === 404) {
      groups.value = []
    } else {
      error.value = '加载复习清单失败：' + (e?.response?.data?.detail || e.message)
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadToday)

function resetCard() {
  revealed.value = false
  answer.value = ''
  judged.value = null
}

function reveal() {
  if (isSpelling.value || isGrammar.value || isSpoken.value) return
  revealed.value = true
}

function speakTerm() {
  const term = current.value?.term
  if (term) speakSmart(term, { rate: 0.95 })
}

// 拼写卡：本地先算差值给一句人话，最终档位以服务端返回为准
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

async function submitSpelling() {
  if (!answer.value.trim() || busy.value) return
  const d = distance(answer.value, current.value?.term || '')
  judged.value = {
    grade: d === 0 ? 'good' : d <= 2 ? 'hard' : 'again',
    text: d === 0 ? '拼对了' : d <= 2 ? `差 ${d} 个字母` : '再看一眼正确写法',
  }
  revealed.value = true
  const res = await sendReview({ answer: answer.value }, { advance: false })
  if (res?.last_result && judged.value) judged.value.grade = res.last_result
}

async function submitGrammar() {
  if (!answer.value.trim() || busy.value) return
  const res = await sendReview({ answer: answer.value }, { advance: false })
  if (!res) return
  const grade = res.last_result || 'again'
  judged.value = {
    grade,
    text: grade === 'good' ? '改对了' : grade === 'hard' ? '差一点，对照一下正确写法' : '看看正确写法',
  }
  revealed.value = true
}

async function submitSpoken() {
  if (!answer.value.trim() || busy.value) return
  const res = await sendReview({ answer: answer.value }, { advance: false })
  if (!res) return
  const grade = res.last_result || 'again'
  judged.value = {
    grade,
    text: grade === 'good' ? '这一版够自然' : grade === 'hard' ? '快接近了，看看更自然的说法' : '看看更自然的说法',
  }
  revealed.value = true
}

async function gradeSelf(g) {
  if (busy.value) return
  await sendReview({ grade: g })
}

function nextCard() {
  index.value += 1
  resetCard()
}

async function sendReview(payload, { advance = true } = {}) {
  const item = current.value
  if (!item) return null
  busy.value = true
  try {
    const { data } = await api.post(`/study/items/${item.id}/review`, payload)
    if (advance) nextCard()
    return data
  } catch (e) {
    error.value = '提交复习结果失败：' + (e?.response?.data?.detail || e.message)
    return null
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="复习" />

    <main class="sp-shell pb-16 pt-8">
      <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

      <div v-if="loading" class="mx-auto max-w-xl" aria-label="正在加载"><div class="sp-skeleton h-72 rounded-card"></div><div class="mt-4 grid grid-cols-3 gap-2.5"><div v-for="i in 3" :key="i" class="sp-skeleton h-11"></div></div></div>

      <div v-else-if="done" class="sp-card mx-auto max-w-2xl">
        <EmptyState icon="done" :title="emptyState.title" :text="emptyState.text">
          <router-link to="/study?tab=new" class="sp-btn-secondary">学几个新词</router-link>
          <router-link to="/study?tab=grammar" class="sp-btn-secondary">看语法卡</router-link>
          <router-link to="/" class="sp-btn-primary">去练一次</router-link>
        </EmptyState>
      </div>

      <div v-else-if="current" class="mx-auto w-full max-w-xl">
        <div class="mb-3 flex items-baseline justify-between text-xs text-ink-mute">
          <span>{{ index + 1 }} / {{ queue.length }}</span>
          <span class="sp-chip-line">{{ cardLabel(current) }}</span>
        </div>

        <!-- 拼写 -->
        <div v-if="isSpelling" class="sp-card p-8 sm:p-10">
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
            <p v-if="spellingReason" class="mt-2 text-xs leading-5 text-ink-mute">为什么：{{ spellingReason }}</p>
          </div>
        </div>

        <!-- 语法：给错句，补空或整句改写 -->
        <div v-else-if="isGrammar" class="sp-card p-8 sm:p-10">
          <div class="text-xs text-ink-mute">{{ current.term }}</div>
          <p v-if="current.meaning_zh" class="mt-1.5 text-sm leading-6 text-ink-soft">{{ current.meaning_zh }}</p>

          <p class="mt-4 text-base leading-7 text-ink">
            <span class="text-rose-500 line-through decoration-rose-300">{{ current.context }}</span>
          </p>

          <p v-if="grammarBlank" class="mt-3 rounded-xl bg-canvas px-3 py-2 text-sm leading-6 text-ink">
            {{ grammarBlank }}
          </p>

          <div class="mt-4 flex items-center gap-2">
            <input
              v-model="answer"
              class="sp-input"
              :placeholder="grammarBlank ? '补上缺的部分' : '写出改写后的句子'"
              :disabled="!!judged"
              @keyup.enter="submitGrammar"
            />
            <button class="sp-btn-primary shrink-0" :disabled="!answer.trim() || busy || !!judged" @click="submitGrammar">
              提交
            </button>
          </div>

          <div v-if="judged" class="mt-4 rounded-xl bg-canvas px-4 py-3 text-sm">
            <div class="font-medium text-ink">{{ judged.text }}</div>
            <div class="mt-1.5 text-ink-soft">正确写法：<span class="text-brand-700">{{ current.example }}</span></div>
            <div v-if="grammarAnswerHint" class="mt-1 text-xs text-ink-mute">这个空是：{{ grammarAnswerHint }}</div>
          </div>
        </div>

        <!-- 口语：书面 → 更自然的口语 -->
        <div v-else-if="isSpoken" class="sp-card p-8 sm:p-10">
          <div class="text-xs text-ink-mute">换成更自然的口语说法</div>
          <p class="mt-2 text-base font-medium leading-7 text-ink">{{ current.term }}</p>

          <div class="mt-5 flex items-center gap-2">
            <input
              v-model="answer"
              class="sp-input"
              placeholder="用口语改写这句话"
              :disabled="!!judged"
              @keyup.enter="submitSpoken"
            />
            <button class="sp-btn-primary shrink-0" :disabled="!answer.trim() || busy || !!judged" @click="submitSpoken">
              提交
            </button>
          </div>

          <div v-if="judged" class="mt-4 rounded-xl bg-canvas px-4 py-3 text-sm">
            <div class="font-medium text-ink">{{ judged.text }}</div>
            <div class="mt-1.5 text-ink-soft">更自然的说法：<span class="text-brand-700">{{ current.example }}</span></div>
            <p v-if="current.meaning_zh" class="mt-1 text-xs leading-5 text-ink-mute">{{ current.meaning_zh }}</p>
          </div>
        </div>

        <!-- 单词与报告带来的句型卡：先回忆，再自评 -->
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

        <div v-if="revealed && !isSpelling && !isGrammar && !isSpoken" class="mt-5 grid grid-cols-3 gap-2.5">
          <button class="sp-btn-secondary !py-2.5" :disabled="busy" @click="gradeSelf('again')">忘了</button>
          <button class="sp-btn-secondary !py-2.5" :disabled="busy" @click="gradeSelf('hard')">模糊</button>
          <button class="sp-btn-primary !py-2.5" :disabled="busy" @click="gradeSelf('good')">认识</button>
        </div>

        <button v-if="judged" class="sp-btn-primary mt-4 w-full" @click="nextCard">下一张</button>
      </div>
    </main>

    <TabBar />
  </div>
</template>
