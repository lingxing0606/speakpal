<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import TabBar from '../components/TabBar.vue'

const route = useRoute()
const router = useRouter()

// 三个菜单：新词（随范围变）、语法 / 口语（通用内容，不随范围变）
const TABS = [
  { id: 'new', label: '新词' },
  { id: 'grammar', label: '语法' },
  { id: 'spoken', label: '口语' },
]

function tabFromQuery(v) {
  if (v === 'phrase') return 'spoken'
  return TABS.some((t) => t.id === v) ? v : ''
}

const tab = ref(tabFromQuery(route.query.tab) || 'new')
const scopeId = computed(() => String(route.params.scope || '').toLowerCase())

// 顶部页签条：滚动超过 8px 才出下沿线
const scrolled = ref(false)
function onScroll() {
  scrolled.value = window.scrollY > 8
}

// ---- 到期数（语法 / 口语 tab 上的药丸） ----
const dueCounts = ref({ grammar: 0, spoken: 0 })
const counts = computed(() => ({
  grammar: dueCounts.value.grammar || 0,
  spoken: dueCounts.value.spoken || 0,
}))

async function loadCounts() {
  try {
    const { data } = await api.get('/study/summary')
    dueCounts.value = {
      grammar: Number(data?.due_grammar_count || 0),
      spoken: Number(data?.due_spoken_count || 0),
    }
  } catch {
    // 取不到数字就不显示药丸，不影响下面加入卡片
  }
}

// ---- 学新单词（范围由路由决定） ----
const bankLoading = ref(false)
const bankData = ref(null)
const bankBusy = ref(false)
const bankTip = ref('')
const bankTipBad = ref(false)

// 每次取几个；后端一次最多 200
const PULL_OPTIONS = [10, 20, 30]
const pullCount = ref(10)

const bankWords = computed(() => bankData.value?.items || [])
const scopeSubtitle = computed(() =>
  bankData.value ? `${bankData.value.name} · 已学 ${bankData.value.learned} / ${bankData.value.total}` : ''
)

async function fetchVocab(scope) {
  const wanted = String(scope || scopeId.value || '').trim().toLowerCase()
  bankLoading.value = true
  bankTip.value = ''
  bankTipBad.value = false
  try {
    const { data } = await api.get('/study/vocab', {
      params: { scope: wanted, limit: pullCount.value },
    })
    bankData.value = data
  } catch (e) {
    if (e?.response?.status === 400) {
      // 不存在的范围（比如旧的自由扩充链接）回范围选择页
      router.replace('/study')
      return
    }
    bankTip.value = '暂时取不到词库：' + (e?.response?.data?.detail || e.message)
    bankTipBad.value = true
  } finally {
    bankLoading.value = false
  }
}

async function setPullCount(n) {
  if (pullCount.value === n) return
  pullCount.value = n
  await fetchVocab(scopeId.value)
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
    await Promise.all([fetchVocab(scopeId.value), loadCounts()])
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
    await Promise.all([loadGrammar(), loadCounts()])
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
    await Promise.all([loadSpoken(), loadCounts()])
  } catch (e) {
    spokenTip.value = '加入失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    spokenBusy.value = false
  }
}

onMounted(async () => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
  await Promise.all([fetchVocab(scopeId.value), loadCounts()])
  if (tab.value === 'grammar') await loadGrammar()
  if (tab.value === 'spoken') await loadSpoken()
})

onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))

watch(
  () => route.query.tab,
  (v) => {
    const next = tabFromQuery(v)
    if (next) tab.value = next
  }
)

watch(
  () => route.params.scope,
  (v) => {
    if (v) fetchVocab(v)
  }
)

watch(tab, (id) => {
  if (id === 'grammar' && !grammarLib.value && !grammarLoading.value) loadGrammar()
  if (id === 'spoken' && !spokenLib.value && !spokenLoading.value) loadSpoken()
})

function switchTab(id) {
  // tab 之间切换用 replace，别把每个 tab 都塞进浏览器历史栈
  if (id === tab.value) return
  tab.value = id
  router.replace({ path: `/study/${scopeId.value}`, query: { tab: id } })
}
</script>

<template>
  <div class="min-h-screen bg-canvas pb-20 sm:pb-0">
    <AppHeader title="学习" :subtitle="scopeSubtitle" back="/study" />

    <!-- 页签条：吸在页头下沿，滚动时内容从下方穿过 -->
    <div
      class="sticky top-16 z-10 bg-canvas/[0.92] backdrop-blur-md"
      :class="scrolled ? 'border-b border-line/60' : ''"
    >
      <div class="sp-shell flex h-14 items-center">
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
    </div>

    <main class="sp-shell sp-page-in pb-16 pt-8">
      <!-- 新词 -->
      <div v-if="tab === 'new'" class="mx-auto max-w-4xl">
        <div class="sp-card p-5">
          <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
            <div class="min-w-0">
              <div class="font-semibold text-ink">学新单词</div>
              <p class="mt-0.5 text-xs leading-5 text-ink-mute">
                {{ bankData ? `${bankData.total} 词 · 已学 ${bankData.learned}` : '按备考范围挑一批新词，加进今天的学习清单。' }}
              </p>
            </div>

            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span class="text-ink-mute">每次取</span>
              <div class="sp-segment" role="group" aria-label="每次取几个">
                <button
                  v-for="opt in PULL_OPTIONS"
                  :key="opt"
                  class="sp-segment-item !px-2.5 !py-1 text-xs"
                  :class="pullCount === opt ? 'sp-segment-item-active' : ''"
                  :aria-pressed="pullCount === opt"
                  @click="setPullCount(opt)"
                >
                  {{ opt }}
                </button>
              </div>
              <button class="sp-btn-primary !px-3 !py-1.5 text-xs" :disabled="bankBusy || !bankWords.length" @click="addBankWords">
                {{ bankBusy ? '加入中…' : `加入这 ${bankWords.length} 个` }}
              </button>
            </div>
          </div>

          <div v-if="bankLoading" class="mt-4 grid gap-2 sm:grid-cols-2" aria-label="正在取词"><div v-for="i in 6" :key="i" class="sp-skeleton h-14"></div></div>

          <div v-else-if="bankWords.length" class="mt-4">
            <div class="grid gap-2 sm:grid-cols-2">
              <div v-for="(w, wi) in bankWords" :key="w.term" :style="{ '--i': wi }" class="sp-reveal rounded-xl bg-paper px-3.5 py-2.5 ring-1 ring-line/70">
                <div class="flex items-baseline gap-2">
                  <span class="font-medium text-ink">{{ w.term }}</span>
                  <span v-if="w.phonetic" class="text-[11px] text-ink-mute">{{ w.phonetic }}</span>
                </div>
                <div class="mt-0.5 text-xs leading-5 text-ink-soft">{{ w.pos }} {{ w.meaning_zh }}</div>
              </div>
            </div>
          </div>

          <EmptyState v-else-if="!bankLoading" compact icon="done" title="这一档的词都学过了" text="换一个备考范围看看，或者去复习已经加进来的词。" />
          <p
            v-if="bankTip"
            class="mt-3 rounded-xl px-3 py-2 text-xs leading-5 ring-1"
            :class="bankTipBad ? 'bg-rose-50 text-danger ring-rose-100' : 'bg-brand-50 text-brand-700 ring-brand-100'"
          >
            {{ bankTip }}
          </p>
        </div>
      </div>

      <!-- 语法 -->
      <div v-else-if="tab === 'grammar'" class="mt-2">
        <div class="flex items-baseline justify-between gap-3">
          <div>
            <div class="text-sm font-medium text-ink">语法卡</div>
            <p class="mt-0.5 text-xs text-ink-mute">
              {{ grammarLib ? `${grammarLib.total} 张 · 已学 ${grammarLib.learned} 张` : '按语法点分组，一组一个知识点。' }}
            </p>
          </div>
          <router-link v-if="counts.grammar" to="/review" class="text-xs font-medium text-brand-700 hover:underline">
            今天 {{ counts.grammar }} 张在复习里
          </router-link>
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
      </div>

      <!-- 口语 -->
      <div v-else-if="tab === 'spoken'" class="mx-auto max-w-4xl">
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
    </main>

    <TabBar />
  </div>
</template>
