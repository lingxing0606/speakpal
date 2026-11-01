<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import TabBar from '../components/TabBar.vue'
import { speakSmart } from '../utils/speech'

const route = useRoute()
const router = useRouter()

// 四个板块：复习（今天到期的全部卡，按类型分组）、新词、语法、口语
const TABS = [
  { id: 'review', label: '复习' },
  { id: 'new', label: '新词' },
  { id: 'grammar', label: '语法' },
  { id: 'phrase', label: '口语' },
]

const KIND_LABELS = { word: '单词', spelling: '拼写', grammar: '语法', phrase: '短语' }

function tabFromQuery(v) {
  return TABS.some((t) => t.id === v) ? v : ''
}

const tab = ref(tabFromQuery(route.query.tab) || 'review')
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
const done = computed(() => !loading.value && tab.value === 'review' && !current.value)

const dueByKey = computed(() => {
  const out = {}
  for (const g of groups.value) out[g.key] = g.count
  return out
})
const counts = computed(() => ({
  review: queue.value.length,
  new: null,
  grammar: dueByKey.value.grammar || 0,
  phrase: dueByKey.value.spoken || 0,
}))

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
      error.value = '加载学习清单失败：' + (e?.response?.data?.detail || e.message)
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadToday()
  if (tab.value === 'new') await fetchVocab('')
  if (tab.value === 'grammar') await loadGrammar()
  if (tab.value === 'phrase') await loadSpoken()
})

watch(
  () => route.query.tab,
  (v) => {
    const next = tabFromQuery(v)
    if (next) tab.value = next
  }
)

watch(tab, (id) => {
  index.value = 0
  resetCard()
  if (id === 'new' && !bankData.value && !bankLoading.value) fetchVocab('')
  if (id === 'grammar' && !grammarLib.value && !grammarLoading.value) loadGrammar()
  if (id === 'phrase' && !spokenLib.value && !spokenLoading.value) loadSpoken()
})

function switchTab(id) {
  // tab 之间切换不算「返回」：用 replace，返回键仍然回首页
  if (id === tab.value) return
  tab.value = id
  router.replace({ path: '/study', query: { tab: id } })
}

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

// ---- 学新单词 ----
const bankLoading = ref(false)
const bankData = ref(null)
const bankBusy = ref(false)
const bankTip = ref('')
const bankTipBad = ref(false)

// 每次取几个：10 / 20 / 30 / 全部（后端一次最多 200）
const PULL_OPTIONS = [
  { value: 10, label: '10' },
  { value: 20, label: '20' },
  { value: 30, label: '30' },
  { value: 200, label: '全部' },
]
const pullCount = ref(10)

const bankWords = computed(() => bankData.value?.items || [])
const bankScopes = computed(() => bankData.value?.scopes || [])

async function fetchVocab(scope) {
  bankLoading.value = true
  bankTip.value = ''
  bankTipBad.value = false
  try {
    const { data } = await api.get('/study/vocab', {
      params: scope ? { scope, limit: pullCount.value } : { limit: pullCount.value },
    })
    bankData.value = data
  } catch (e) {
    bankTip.value = '暂时取不到词库：' + (e?.response?.data?.detail || e.message)
    bankTipBad.value = true
  } finally {
    bankLoading.value = false
  }
}

async function setPullCount(n) {
  if (pullCount.value === n) return
  pullCount.value = n
  await fetchVocab(bankData.value?.scope)
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
  bankTipBad.value = false
  try {
    const terms = bankWords.value.map((w) => w.term)
    const { data } = await api.post('/study/vocab/add', {
      scope: bankData.value?.scope,
      terms,
    })
    const added = Number(data.added || 0)
    const skipped = Number(data.skipped || 0)
    let text = '没有加入新词'
    if (added && skipped) text = `已加入 ${added} 个，${skipped} 个之前学过`
    else if (added) text = `已加入 ${added} 个`
    else if (skipped) text = `这 ${skipped} 个之前都学过`
    // 先刷新列表再写提示：fetchVocab 会清空旧提示，顺序反了就等于什么都没显示
    await fetchVocab(bankData.value?.scope)
    await loadToday()
    bankTip.value = text
  } catch (e) {
    bankTip.value = '加入失败：' + (e?.response?.data?.detail || e.message)
    bankTipBad.value = true
  } finally {
    bankBusy.value = false
  }
}

// ---- 语法卡库：四组各 15 张，整组加入后进「复习」 ----
const grammarLib = ref(null)
const grammarLoading = ref(false)
const grammarBusy = ref('')
const grammarTip = ref('')

async function loadGrammar() {
  grammarLoading.value = true
  grammarTip.value = ''
  try {
    const { data } = await api.get('/study/grammar')
    grammarLib.value = data
  } catch (e) {
    grammarTip.value = '暂时取不到语法卡：' + (e?.response?.data?.detail || e.message)
  } finally {
    grammarLoading.value = false
  }
}

async function addGrammarGroup(group) {
  if (grammarBusy.value) return
  grammarBusy.value = group
  grammarTip.value = ''
  try {
    const { data } = await api.post('/study/grammar/add', { group })
    grammarTip.value = data.added ? `加入了 ${data.added} 张，去「复习」里做` : '这一组已经都在清单里了'
    await Promise.all([loadGrammar(), loadToday()])
  } catch (e) {
    grammarTip.value = '加入失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    grammarBusy.value = ''
  }
}

// ---- 口语卡库：60 张，一次加 10 张 ----
const spokenLib = ref(null)
const spokenLoading = ref(false)
const spokenBusy = ref(false)
const spokenTip = ref('')

async function loadSpoken() {
  spokenLoading.value = true
  spokenTip.value = ''
  try {
    const { data } = await api.get('/study/spoken')
    spokenLib.value = data
  } catch (e) {
    spokenTip.value = '暂时取不到口语卡：' + (e?.response?.data?.detail || e.message)
  } finally {
    spokenLoading.value = false
  }
}

async function addSpoken() {
  if (spokenBusy.value) return
  const fresh = (spokenLib.value?.items || []).filter((i) => !i.learned).slice(0, 10)
  if (!fresh.length) return
  spokenBusy.value = true
  spokenTip.value = ''
  try {
    const { data } = await api.post('/study/spoken/add', { ids: fresh.map((i) => i.id) })
    spokenTip.value = data.added ? `加入了 ${data.added} 张，去「复习」里做` : '这些卡已经都在清单里了'
    await Promise.all([loadSpoken(), loadToday()])
  } catch (e) {
    spokenTip.value = '加入失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    spokenBusy.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="学习" back="/">
      <router-link to="/notes" class="sp-btn-ghost sm:hidden">笔记</router-link>
    </AppHeader>

    <main class="sp-shell pb-16 pt-10">
      <div class="flex flex-wrap items-end justify-between gap-5">
        <div>
          <div class="sp-eyebrow">学习</div>
          <h1 class="sp-title mt-2">把说错的，练成会的</h1>
          <p class="sp-lede">报告里的错句会变成卡片，按间隔重复回到这里；也可以从词库、语法和口语卡里挑新的学。</p>
        </div>
        <nav class="sp-segment max-w-full overflow-x-auto" aria-label="学习板块">
          <button
            v-for="t in TABS"
            :key="t.id"
            class="sp-segment-item"
            :class="tab === t.id ? 'sp-segment-item-active' : ''"
            :aria-pressed="tab === t.id"
            @click="switchTab(t.id)"
          >
            {{ t.label }}
            <span v-if="counts[t.id]" class="rounded-full bg-brand-50 px-1.5 text-[11px] font-semibold text-brand-700">{{ counts[t.id] }}</span>
          </button>
        </nav>
      </div>

      <!-- 新词 -->
      <div v-if="tab === 'new'" class="mx-auto mt-10 max-w-4xl">
        <div class="sp-card p-5">
          <div class="font-semibold text-ink">学新单词</div>
          <p class="mt-0.5 text-xs leading-5 text-ink-mute">
            {{ bankData ? `${bankData.name} · 精选 ${bankData.total} 词 · 已学 ${bankData.learned} 个` : '按备考范围挑一批新词，加进今天的学习清单。' }}
          </p>

          <div class="mt-4 grid gap-2 sm:grid-cols-3">
            <button
              v-for="sc in bankScopes"
              :key="sc.id"
              class="rounded-2xl bg-paper px-4 py-3.5 text-left ring-1 transition duration-200 hover:-translate-y-0.5 active:scale-[0.99]"
              :class="bankData?.scope === sc.id ? 'ring-brand-300' : 'ring-line/60 hover:ring-brand-200'"
              @click="pickScope(sc.id)"
            >
              <div class="text-sm font-medium text-ink">{{ sc.name }}</div>
              <div class="mt-1 text-[11px] text-ink-mute">已学 {{ sc.learned ?? 0 }} / 精选 {{ sc.total }} 词</div>
            </button>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <span class="text-ink-mute">每次取</span>
            <button
              v-for="opt in PULL_OPTIONS"
              :key="opt.value"
              class="rounded-lg px-2.5 py-1 transition"
              :class="pullCount === opt.value ? 'bg-brand-50 font-medium text-brand-700 ring-1 ring-brand-100' : 'text-ink-mute hover:bg-canvas hover:text-ink-soft'"
              @click="setPullCount(opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>

          <div v-if="bankLoading" class="mt-4 grid gap-2 sm:grid-cols-2" aria-label="正在取词"><div v-for="i in 6" :key="i" class="sp-skeleton h-14"></div></div>

          <div v-else-if="bankWords.length" class="mt-3">
            <div class="grid gap-2 sm:grid-cols-2">
              <div v-for="(w, wi) in bankWords" :key="w.term" :style="{ '--i': wi }" class="sp-reveal rounded-xl bg-paper px-3.5 py-2.5 ring-1 ring-line/70">
                <div class="flex items-baseline gap-2">
                  <span class="font-medium text-ink">{{ w.term }}</span>
                  <span v-if="w.phonetic" class="text-[11px] text-ink-mute">{{ w.phonetic }}</span>
                </div>
                <div class="mt-0.5 text-xs leading-5 text-ink-soft">{{ w.pos }} {{ w.meaning_zh }}</div>
              </div>
            </div>
            <button class="sp-btn-primary mt-3" :disabled="bankBusy" @click="addBankWords">
              {{ bankBusy ? '加入中…' : `加入这 ${bankWords.length} 个` }}
            </button>
          </div>

          <EmptyState v-else-if="!bankLoading" compact icon="done" title="这一档的词都学过了" text="换一档词库看看，或者去复习已经加进来的词。" />
          <p
            v-if="bankTip"
            class="mt-3 rounded-xl px-3 py-2 text-xs leading-5 ring-1"
            :class="bankTipBad ? 'bg-rose-50 text-danger ring-rose-100' : 'bg-brand-50 text-brand-700 ring-brand-100'"
          >
            {{ bankTip }}
          </p>
        </div>
        <p class="mt-3 text-center text-[11px] text-ink-mute">加进来的词会进「复习」，当天就能过一遍。</p>
      </div>

      <!-- 语法 -->
      <div v-else-if="tab === 'grammar'" class="mt-10">
        <div class="flex items-baseline justify-between gap-3">
          <div>
            <div class="text-sm font-medium text-ink">语法卡</div>
            <p class="mt-0.5 text-xs text-ink-mute">
              {{ grammarLib ? `${grammarLib.total} 张 · 已学 ${grammarLib.learned} 张` : '按语法点分组，一组一个知识点。' }}
            </p>
          </div>
          <button v-if="counts.grammar" class="text-xs font-medium text-brand-700 hover:underline" @click="switchTab('review')">
            今天 {{ counts.grammar }} 张在复习里
          </button>
        </div>

        <div v-if="grammarLoading" class="mt-6 grid gap-4 sm:grid-cols-2" aria-label="正在加载"><div v-for="i in 4" :key="i" class="sp-skeleton h-32"></div></div>

        <div v-else-if="grammarLib" class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="(g, gi) in grammarLib.groups" :key="g.id" :style="{ '--i': gi }" class="sp-reveal sp-hover sp-card p-5">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="font-medium text-ink">{{ g.name }}</div>
                <p class="mt-0.5 text-xs leading-5 text-ink-mute">{{ g.desc }}</p>
              </div>
              <span class="shrink-0 text-[11px] text-ink-mute">已学 {{ g.learned }} / {{ g.total }}</span>
            </div>
            <ul class="mt-3 space-y-1.5">
              <li v-for="c in g.items.slice(0, 3)" :key="c.id" class="text-xs leading-5 text-ink-soft">
                <span :class="c.learned ? 'text-brand-700' : 'text-ink-mute'">{{ c.learned ? '已学' : '待学' }}</span>
                · {{ c.point }}
              </li>
            </ul>
            <button
              class="sp-btn-secondary mt-3 !px-3 !py-1.5 text-xs"
              :disabled="grammarBusy === g.id || g.learned >= g.total"
              @click="addGrammarGroup(g.id)"
            >
              {{ g.learned >= g.total ? '这一组已学完' : grammarBusy === g.id ? '加入中…' : `加入这一组（${g.total} 张）` }}
            </button>
          </div>
        </div>

        <div v-if="grammarLib && !grammarLib.groups.length" class="sp-card mt-6">
          <EmptyState icon="cards" title="今天没有要练的语法" text="去练一次对话，报告里的语法点会回到这里。">
            <router-link to="/" class="sp-btn-primary">去练一次</router-link>
          </EmptyState>
        </div>

        <p v-if="grammarTip" class="mt-3 text-xs leading-5 text-ink-soft">{{ grammarTip }}</p>
        <p class="mt-4 text-center text-[11px] text-ink-mute">做题在「复习」里：给错句改对或补上空缺，由服务端判档。</p>
      </div>

      <!-- 口语 -->
      <div v-else-if="tab === 'phrase'" class="mx-auto mt-10 max-w-4xl">
        <div class="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <div class="text-sm font-medium text-ink">口语卡</div>
            <p class="mt-0.5 text-xs text-ink-mute">
              {{ spokenLib ? `${spokenLib.total} 张 · 已学 ${spokenLib.learned} 张` : '书面说法换成更自然的口语。' }}
            </p>
          </div>
          <button
            v-if="spokenLib && spokenLib.learned < spokenLib.total"
            class="sp-btn-secondary !px-3 !py-1.5 text-xs"
            :disabled="spokenBusy"
            @click="addSpoken"
          >
            {{ spokenBusy ? '加入中…' : '加 10 张' }}
          </button>
        </div>

        <div v-if="spokenLoading" class="mt-6 space-y-3" aria-label="正在加载"><div class="sp-skeleton h-24"></div><div class="sp-skeleton h-24"></div><div class="sp-skeleton h-24 w-2/3"></div></div>

        <div v-else-if="spokenLib" class="mt-6 space-y-2.5">
          <div
            v-for="c in spokenLib.items"
            :key="c.id"
            class="sp-card-flat flex items-start justify-between gap-4 p-4 transition duration-200 hover:ring-brand-200"
          >
            <div class="min-w-0">
              <div class="text-sm leading-6 text-ink"><span class="text-ink-mute">书面</span> {{ c.formal }}</div>
              <div class="mt-1 text-sm leading-6 text-brand-700"><span class="text-ink-mute">口语</span> {{ c.natural }}</div>
              <p class="mt-1 text-[11px] leading-5 text-ink-mute">{{ c.why }}</p>
            </div>
            <span class="sp-chip-line shrink-0">{{ c.learned ? '已学' : '待学' }}</span>
          </div>
        </div>

        <p v-if="spokenTip" class="mt-3 text-xs leading-5 text-ink-soft">{{ spokenTip }}</p>

        <div v-if="spokenLib && !spokenLib.items.length" class="sp-card mt-6">
          <EmptyState icon="practice" title="今天没有要练的口语" text="去练一次带口语的对话，报告里的说法会回到这里。">
            <router-link to="/" class="sp-btn-primary">去练一次</router-link>
          </EmptyState>
        </div>
      </div>

      <!-- 复习队列 -->
      <div v-else class="mt-10">
        <p v-if="error" class="sp-alert-error mb-4">{{ error }}</p>

        <div v-if="loading" class="mx-auto max-w-xl" aria-label="正在加载"><div class="sp-skeleton h-72 rounded-card"></div><div class="mt-4 grid grid-cols-3 gap-2.5"><div v-for="i in 3" :key="i" class="sp-skeleton h-11"></div></div></div>

        <div v-else-if="done" class="sp-card mx-auto max-w-2xl">
          <EmptyState icon="done" :title="emptyState.title" :text="emptyState.text">
            <button class="sp-btn-secondary" @click="switchTab('new')">学几个新词</button>
            <button class="sp-btn-secondary" @click="switchTab('grammar')">看语法卡</button>
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
      </div>
    </main>

    <TabBar />
  </div>
</template>
