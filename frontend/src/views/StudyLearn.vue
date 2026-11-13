<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import AppHeader from '../components/AppHeader.vue'
import MnemonicCard from '../components/MnemonicCard.vue'
import { useSettingsStore } from '../stores/settings'

const BATCH_KEY = 'speakpal.studyBatch'
const MAX_BATCH = 50
const STEPS = [
  { id: 'recognize', label: '认' },
  { id: 'spell', label: '拼' },
  { id: 'use', label: '用' },
]

const route = useRoute()
const router = useRouter()
const settings = useSettingsStore()

const batch = ref(null)
const ready = ref(false)
const index = ref(0)
const step = ref('recognize')
const passed = ref(0)
const skipped = ref(0)
const processing = ref(false)
const finishing = ref(false)
const done = ref(false)
const flash = ref(false)
const cardEl = ref(null)

const showLeaveConfirm = ref(false)
const pendingPath = ref('')
const leaveConfirmed = ref(false)

const mnemonicOpen = ref(false)
const mnemonicLoading = ref(false)
const mnemonicFailed = ref(false)
const mnemonicCache = new Map()

const options = ref([])
const correctIndex = ref(-1)
const selected = ref(-1)
const recognizedAnswer = ref('')
const distractorPool = ref([])
const optionEls = []

const spellInput = ref('')
const spellInputEl = ref(null)
const spellAttempts = ref(0)
const spellDone = ref(false)
const spellFailed = ref(false)
const spellResult = ref('')

const useText = ref('')
const useInputEl = ref(null)
const useChecking = ref(false)
const useFeedback = ref(null)
const wordPassed = ref(true)
const finishedWord = ref(false)

let flashTimer = null

const scope = computed(() => String(route.params.scope || '').toLowerCase())
const total = computed(() => batch.value?.words?.length || 0)
const word = computed(() => batch.value?.words?.[index.value] || null)
const processed = computed(() => passed.value + skipped.value)
const remaining = computed(() => Math.max(0, total.value - processed.value))
const headerSubtitle = computed(() =>
  batch.value ? `${batch.value.scopeName || ''} · ${passed.value}/${total.value}` : ''
)
const progress = computed(() =>
  done.value ? 100 : total.value ? Math.round((passed.value / total.value) * 100) : 0
)
const stepIndex = computed(() => Math.max(0, STEPS.findIndex((s) => s.id === step.value)))
const stepNow = computed(() => STEPS[stepIndex.value] || STEPS[0])
const canNext = computed(() => {
  if (step.value === 'recognize') return !!recognizedAnswer.value
  if (step.value === 'spell') return spellDone.value
  if (step.value === 'use') return !!useFeedback.value?.passed
  return false
})
const nextLabel = computed(() => (step.value === 'use' ? '下一个词 →' : '下一步'))
const spellSubmitLabel = computed(() => (spellAttempts.value ? '再试一次' : '提交'))
const spellDiff = computed(() => {
  const typed = spellInput.value.trim().toLowerCase()
  const target = String(word.value?.term || '').toLowerCase()
  const max = Math.max(typed.length, target.length)
  return Array.from({ length: max }, (_, i) => ({
    typed: typed[i] || '',
    target: target[i] || '',
    ok: typed[i] && typed[i] === target[i],
  }))
})
const spellDiffCount = computed(() => distance(spellInput.value.trim(), word.value?.term || ''))

function reducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

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

function shuffle(list) {
  const out = [...list]
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

function readBatch() {
  try {
    const raw = sessionStorage.getItem(BATCH_KEY)
    if (!raw) return null
    const data = JSON.parse(raw)
    if (!data || !Array.isArray(data.words) || !data.words.length) return null
    return { ...data, words: data.words.slice(0, MAX_BATCH) }
  } catch {
    return null
  }
}

async function ensurePool() {
  const meanings = new Set(
    (batch.value?.words || []).map((w) => String(w.meaning_zh || '').trim()).filter(Boolean)
  )
  if (meanings.size < 4) {
    try {
      const { data } = await api.get('/study/vocab', { params: { limit: 30 } })
      for (const w of data?.items || []) {
        const meaning = String(w.meaning_zh || '').trim()
        if (meaning) meanings.add(meaning)
      }
    } catch {
      // 取不到池子就用下面的通用兜底
    }
  }
  for (const fallback of ['一个动作', '一种状态', '一种情绪', '一个人']) {
    if (meanings.size >= 4) break
    meanings.add(fallback)
  }
  distractorPool.value = [...meanings]
}

function buildOptions() {
  const correct = String(word.value?.meaning_zh || '').trim() || '（暂无释义）'
  const meanings = new Set(
    (batch.value?.words || []).map((w) => String(w.meaning_zh || '').trim()).filter(Boolean)
  )
  const pool = [...new Set([...meanings, ...distractorPool.value])].filter(
    (item) => item && item !== correct
  )
  const picks = shuffle(pool).slice(0, 3)
  for (const fallback of ['一个动作', '一种状态', '一种情绪', '一个人']) {
    if (picks.length >= 3) break
    if (fallback !== correct && !picks.includes(fallback)) picks.push(fallback)
  }
  const list = shuffle([correct, ...picks]).slice(0, 4)
  options.value = list
  correctIndex.value = list.indexOf(correct)
  selected.value = -1
  recognizedAnswer.value = ''
}

function resetWordState() {
  step.value = 'recognize'
  recognizedAnswer.value = ''
  mnemonicOpen.value = false
  mnemonicLoading.value = false
  mnemonicFailed.value = false
  spellInput.value = ''
  spellAttempts.value = 0
  spellDone.value = false
  spellFailed.value = false
  spellResult.value = ''
  useText.value = ''
  useChecking.value = false
  useFeedback.value = null
  wordPassed.value = true
  finishedWord.value = false
  buildOptions()
}

function shakeOption(i) {
  if (reducedMotion()) return
  const el = optionEls[i]
  el?.animate(
    [
      { transform: 'translateX(0)' },
      { transform: 'translateX(-3px)' },
      { transform: 'translateX(3px)' },
      { transform: 'translateX(0)' },
    ],
    { duration: 260, easing: 'ease-out' }
  )
}

function chooseOption(i) {
  if (recognizedAnswer.value || processing.value || done.value) return
  selected.value = i
  if (i === correctIndex.value) {
    recognizedAnswer.value = 'correct'
  } else {
    recognizedAnswer.value = 'wrong'
    shakeOption(i)
  }
}

function optionClass(i) {
  if (!recognizedAnswer.value) return 'hover:ring-brand-300'
  if (i === correctIndex.value) return 'ring-brand-400 bg-brand-50 text-brand-700'
  if (i === selected.value) return 'ring-rose-300 bg-rose-50'
  return 'opacity-55'
}

function openMnemonic() {
  if (mnemonicLoading.value) return
  mnemonicOpen.value = true
  mnemonicLoading.value = true
}

function onMnemonicDone(payload) {
  mnemonicLoading.value = false
  if (word.value) mnemonicCache.set(word.value.term, payload)
}

function onMnemonicFail() {
  mnemonicLoading.value = false
  mnemonicOpen.value = false
  mnemonicFailed.value = true
}

async function submitSpell() {
  if (processing.value || spellDone.value || !spellInput.value.trim()) return
  const diff = distance(spellInput.value, word.value?.term || '')
  if (diff === 0) {
    spellDone.value = true
    spellResult.value = 'correct'
    return
  }
  spellResult.value = 'wrong'
  if (!reducedMotion()) {
    spellInputEl.value?.animate(
      [
        { transform: 'translateX(0)' },
        { transform: 'translateX(-3px)' },
        { transform: 'translateX(3px)' },
        { transform: 'translateX(0)' },
      ],
      { duration: 260, easing: 'ease-out' }
    )
  }
  if (spellAttempts.value === 0) {
    spellAttempts.value = 1
    nextTick(() => spellInputEl.value?.focus())
    return
  }
  spellAttempts.value = 2
  spellDone.value = true
  spellFailed.value = true
  wordPassed.value = false
}

async function submitUse() {
  if (processing.value || useChecking.value || useFeedback.value?.passed) return
  if (!useText.value.trim()) return
  useChecking.value = true
  useFeedback.value = null
  if (!settings.configured) {
    // 没有 key 时不做造句判分：直接通过，给中性提示，不阻塞
    useFeedback.value = { title: '这次没拿到反馈', body: '', passed: true, neutral: true }
    useChecking.value = false
    return
  }
  try {
    const { data } = await api.post('/study/words/sentence-check', {
      term: word.value.term,
      sentence: useText.value.trim(),
    })
    if (data?.ok) {
      if (data.suggestion) {
        useFeedback.value = { title: '✓ 用对了', body: data.suggestion, passed: true }
      } else {
        // 模型没给建议（含超时 / 坏 JSON 的后端兜底）：中性通过
        useFeedback.value = { title: '这次没拿到反馈', body: '', passed: true, neutral: true }
      }
    } else {
      useFeedback.value = {
        title: '再改一下',
        body: data?.suggestion || '试着把这个词放进一个完整句子里。',
        passed: false,
      }
    }
  } catch {
    useFeedback.value = { title: '这次没拿到反馈', body: '', passed: true, neutral: true }
  } finally {
    useChecking.value = false
  }
}

function onUseInput() {
  if (useFeedback.value && !useFeedback.value.passed) useFeedback.value = null
}

function nextStep() {
  if (processing.value || !canNext.value) return
  if (step.value === 'recognize') {
    step.value = 'spell'
    mnemonicOpen.value = false
    mnemonicLoading.value = false
    nextTick(() => spellInputEl.value?.focus())
    return
  }
  if (step.value === 'spell') {
    step.value = 'use'
    nextTick(() => useInputEl.value?.focus())
    return
  }
  completeWord()
}

async function completeWord() {
  if (processing.value || finishedWord.value || done.value) return
  processing.value = true
  finishedWord.value = true
  if (wordPassed.value) {
    try {
      await api.post('/study/words/learn', {
        term: word.value.term,
        meaning_zh: word.value.meaning_zh || '',
        example: word.value.example || '',
        context: word.value.context || '',
        recognized: true,
        spelled: true,
        used: true,
      })
    } catch {
      // 写卡失败也不把用户卡在流程里；复习队列里没有它，完成面板仍按通过计
    }
    passed.value += 1
    if (!reducedMotion()) {
      cardEl.value?.animate([{ transform: 'scale(1.01)' }, { transform: 'scale(1)' }], {
        duration: 120,
        easing: 'ease-out',
      })
    }
  } else {
    skipped.value += 1
  }
  if (passed.value + skipped.value >= total.value) {
    await finishBatch()
  } else {
    nextWord()
  }
  processing.value = false
}

async function finishBatch() {
  if (finishing.value) return
  finishing.value = true
  sessionStorage.removeItem(BATCH_KEY)
  if (!reducedMotion() && cardEl.value) {
    const anim = cardEl.value.animate(
      [
        { transform: 'scaleY(1) translateY(0)', opacity: 1 },
        { transform: 'scaleY(0.6) translateY(-40px)', opacity: 0 },
      ],
      { duration: 260, easing: 'ease-out', fill: 'forwards' }
    )
    await anim.finished.catch(() => {})
    anim.cancel()
  }
  done.value = true
  if (!reducedMotion()) {
    flash.value = true
    clearTimeout(flashTimer)
    flashTimer = setTimeout(() => {
      flash.value = false
    }, 160)
  }
  finishing.value = false
}

function nextWord() {
  index.value += 1
  resetWordState()
  nextTick(() => {
    if (!reducedMotion()) {
      cardEl.value?.animate(
        [
          { opacity: 0, transform: 'translateX(-12px)' },
          { opacity: 1, transform: 'translateX(0)' },
        ],
        { duration: 240, easing: 'ease-out' }
      )
    }
  })
}

async function skipWord() {
  if (processing.value || finishedWord.value || done.value) return
  processing.value = true
  finishedWord.value = true
  if (!reducedMotion() && cardEl.value) {
    const anim = cardEl.value.animate(
      [
        { transform: 'translateX(0)', opacity: 1 },
        { transform: 'translateX(200px)', opacity: 0 },
      ],
      { duration: 220, easing: 'ease-out', fill: 'forwards' }
    )
    await anim.finished.catch(() => {})
    anim.cancel()
  }
  skipped.value += 1
  if (passed.value + skipped.value >= total.value) {
    await finishBatch()
  } else {
    nextWord()
  }
  processing.value = false
}

function onKeydown(event) {
  if (done.value || showLeaveConfirm.value || finishing.value) return
  const tag = event.target?.tagName
  const typing = tag === 'INPUT' || tag === 'TEXTAREA'
  if (step.value === 'recognize' && !typing && /^[1-4]$/.test(event.key)) {
    event.preventDefault()
    chooseOption(Number(event.key) - 1)
    return
  }
  if (event.key !== 'Enter') return
  if (typing) {
    if (step.value === 'use' && event.shiftKey) return
    event.preventDefault()
    if (step.value === 'spell') {
      if (spellDone.value) nextStep()
      else submitSpell()
    } else if (step.value === 'use') {
      if (useFeedback.value?.passed) nextStep()
      else submitUse()
    }
    return
  }
  if (tag === 'BUTTON' || tag === 'A') return
  if (canNext.value) {
    event.preventDefault()
    nextStep()
  }
}

onBeforeRouteLeave((to) => {
  if (done.value || leaveConfirmed.value || processed.value >= total.value) return true
  pendingPath.value = to.fullPath
  showLeaveConfirm.value = true
  return false
})

function cancelLeave() {
  showLeaveConfirm.value = false
  pendingPath.value = ''
}

function confirmLeave() {
  leaveConfirmed.value = true
  showLeaveConfirm.value = false
  sessionStorage.removeItem(BATCH_KEY)
  const path = pendingPath.value || `/study/${scope.value}?tab=new`
  pendingPath.value = ''
  router.push(path)
}

function again() {
  router.push(`/study/${scope.value}?tab=new`)
}

function backScope() {
  router.push(`/study/${scope.value}`)
}

onMounted(async () => {
  const data = readBatch()
  if (!data || data.scope !== scope.value) {
    router.replace(`/study/${scope.value}?tab=new`)
    return
  }
  batch.value = data
  await ensurePool()
  buildOptions()
  ready.value = true
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(flashTimer)
})
</script>

<template>
  <div class="min-h-screen bg-canvas pb-10">
    <AppHeader title="学新词" :subtitle="headerSubtitle" :back="`/study/${scope}?tab=new`" />

    <main class="sp-shell pb-8 pt-8">
      <div class="sp-bar !h-1 mb-5 overflow-hidden rounded-full" aria-hidden="true">
        <div
          class="sp-bar-fill"
          :class="flash ? 'bg-brand-300' : ''"
          :style="{ width: `${progress}%`, transitionDuration: '240ms' }"
        ></div>
      </div>

      <div v-if="!ready" class="sp-skeleton mx-auto h-72 max-w-xl rounded-card" aria-label="正在准备这一批"></div>

      <template v-else-if="batch && word">
        <div v-if="!done" ref="cardEl" class="mx-auto max-w-xl">
          <div class="sp-card p-5 sm:p-8">
            <div class="sp-step-dots justify-between">
              <div class="hidden items-center gap-2 sm:flex">
                <div v-for="(s, i) in STEPS" :key="s.id" class="flex items-center gap-1.5">
                  <span
                    class="h-2 w-2 rounded-full"
                    :class="i < stepIndex ? 'bg-brand-500' : i === stepIndex ? 'bg-brand-600 ring-2 ring-brand-100' : 'bg-sand-200'"
                  ></span>
                  <span class="text-[12px]" :class="i === stepIndex ? 'font-medium text-ink' : 'text-ink-mute'">{{ s.label }}</span>
                </div>
              </div>
              <span class="text-[12px] text-ink-mute sm:hidden">{{ stepNow.label }} · {{ stepIndex + 1 }}/3</span>
              <span class="text-[11px] text-ink-mute">{{ index + 1 }} / {{ total }}</span>
            </div>
            <div class="mt-2 hidden grid-cols-3 gap-1 sm:grid">
              <span v-for="(s, i) in STEPS" :key="s.id" class="h-0.5 rounded-full" :class="i <= stepIndex ? 'bg-brand-400' : 'bg-sand-200'"></span>
            </div>

            <!-- 认 -->
            <div v-if="step === 'recognize'" class="mt-6">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="sp-word">{{ word.term }}</div>
                  <div class="mt-2 flex flex-wrap items-center gap-2">
                    <span v-if="word.phonetic" class="text-[12px] text-ink-mute">{{ word.phonetic }}</span>
                    <span v-if="word.pos" class="sp-chip-line !py-0.5 !text-[11px]">{{ word.pos }}</span>
                  </div>
                </div>
                <button class="shrink-0 text-[11px] text-ink-mute transition hover:text-ink" @click="skipWord">跳过这个词</button>
              </div>

              <p class="mt-5 text-[12px] text-ink-mute">选一个意思</p>
              <div class="mt-2 space-y-2">
                <button
                  v-for="(opt, i) in options"
                  :key="`${word.term}-${i}`"
                  :ref="(el) => (optionEls[i] = el)"
                  class="sp-pick"
                  :class="optionClass(i)"
                  :disabled="!!recognizedAnswer"
                  @click="chooseOption(i)"
                >
                  <span class="w-4 shrink-0 text-[11px] text-ink-mute">{{ i + 1 }}</span>
                  <span class="min-w-0 flex-1">{{ opt }}</span>
                  <span v-if="recognizedAnswer && i === correctIndex" class="shrink-0 text-brand-700">✓</span>
                </button>
              </div>

              <div
                class="overflow-hidden transition-[max-height,opacity] duration-[240ms] ease-out"
                :class="recognizedAnswer ? 'max-h-[1200px] opacity-100' : 'max-h-0 opacity-0'"
              >
                <div class="mt-5 rounded-xl bg-canvas px-4 py-3">
                  <div class="flex flex-wrap items-center gap-2 text-[12px]">
                    <span v-if="word.pos" class="sp-chip-line !py-0.5 !text-[11px]">{{ word.pos }}</span>
                    <span class="text-ink">{{ word.meaning_zh || '（暂无释义）' }}</span>
                  </div>
                  <p v-if="word.example" class="sp-num mt-2 text-[13px] italic leading-6 text-ink-soft">{{ word.example }}</p>
                  <p v-if="word.example_zh" class="mt-1 text-[11px] text-ink-mute">{{ word.example_zh }}</p>
                  <div class="mt-3 flex justify-end">
                    <button
                      v-if="!mnemonicFailed"
                      class="sp-btn-ghost !px-2 !py-1 text-[11px]"
                      :disabled="mnemonicLoading"
                      @click="openMnemonic"
                    >
                      {{ mnemonicLoading ? '在想…' : 'AI 助记 ✦' }}
                    </button>
                  </div>
                  <MnemonicCard
                    v-if="mnemonicOpen && !mnemonicFailed"
                    :key="word.term"
                    :term="word.term"
                    :meaning-zh="word.meaning_zh"
                    :related="word.related"
                    :initial="mnemonicCache.get(word.term)"
                    @done="onMnemonicDone"
                    @fail="onMnemonicFail"
                  />
                </div>
              </div>
            </div>

            <!-- 拼 -->
            <div v-else-if="step === 'spell'" class="mt-6">
              <p class="text-center text-[13px] text-ink">{{ word.meaning_zh || '按提示写出这个词' }}</p>
              <p v-if="word.phonetic" class="mt-1 text-center text-[12px] text-ink-mute">{{ word.phonetic }}</p>

              <div class="mt-7 text-center">
                <div v-if="spellDone && !spellFailed" class="sp-word !text-[34px]">{{ word.term }}</div>
                <template v-else-if="spellResult === 'wrong'">
                  <div class="flex flex-wrap items-center justify-center gap-0.5 font-mono text-2xl">
                    <span
                      v-for="(ch, i) in spellDiff"
                      :key="i"
                      :class="ch.ok ? 'text-good' : 'text-danger underline decoration-wavy'"
                    >{{ ch.typed || '·' }}</span>
                  </div>
                  <div class="mt-1 text-[11px] text-ink-mute">差 {{ spellDiffCount }} 个字母</div>
                </template>
                <div v-else class="flex items-center justify-center gap-1.5">
                  <span v-for="i in 3" :key="i" class="sp-diff"></span>
                </div>
              </div>

              <input
                ref="spellInputEl"
                v-model="spellInput"
                class="sp-input mt-6 text-center font-mono text-lg"
                :class="spellResult === 'correct' ? 'ring-2 ring-brand-400' : ''"
                placeholder="拼写"
                :disabled="spellDone"
                @keydown.enter.exact.prevent="submitSpell"
              />

              <div class="mt-3 flex justify-center">
                <button class="sp-btn-primary !px-4 !py-2 text-xs" :disabled="!spellInput.trim() || spellDone" @click="submitSpell">
                  {{ spellSubmitLabel }}
                </button>
              </div>
              <p v-if="spellDone && spellFailed" class="mt-2 text-center text-[11px] text-ink-mute">这个词先跳过，继续下一个</p>
            </div>

            <!-- 用 -->
            <div v-else class="mt-6">
              <div class="text-[12px] text-ink-mute">用这个词说一句</div>
              <div class="sp-word mt-1 !text-[24px]">{{ word.term }}</div>
              <p class="mt-1 text-[11px] text-ink-mute">{{ word.meaning_zh || '（暂无释义）' }}</p>

              <textarea
                ref="useInputEl"
                v-model="useText"
                rows="2"
                class="sp-input mt-4 resize-y"
                placeholder="写一句完整的话"
                @input="onUseInput"
                @keydown.enter.exact.prevent="submitUse"
              ></textarea>

              <div class="mt-2 flex items-center justify-between gap-3">
                <span v-if="useChecking" class="text-[12px] text-ink-mute">AI 在看…</span>
                <span v-else></span>
                <button class="sp-btn-primary !px-4 !py-2 text-xs" :disabled="!useText.trim() || useChecking || !!useFeedback?.passed" @click="submitUse">
                  {{ useFeedback && !useFeedback.passed ? '再试一次' : '提交' }}
                </button>
              </div>

              <Transition
                enter-active-class="transition duration-[220ms] ease-out"
                enter-from-class="translate-y-2 opacity-0"
                leave-active-class="transition duration-[160ms] ease-in"
                leave-to-class="opacity-0"
              >
                <div
                  v-if="useFeedback"
                  class="mt-3 rounded-xl px-4 py-3 text-sm ring-1"
                  :class="useFeedback.neutral
                    ? 'bg-canvas text-ink-soft ring-line/60'
                    : useFeedback.passed
                      ? 'bg-brand-50 text-brand-700 ring-brand-100'
                      : 'bg-amber-50 text-amber-800 ring-amber-100'"
                >
                  <div class="font-medium">{{ useFeedback.title }}</div>
                  <p v-if="useFeedback.body" class="mt-0.5 text-[13px] leading-5">{{ useFeedback.body }}</p>
                </div>
              </Transition>
            </div>
          </div>

          <div class="sticky bottom-0 z-10 mt-4 bg-gradient-to-t from-canvas via-canvas/95 to-transparent py-3 sm:static sm:bg-none sm:p-0">
            <div class="flex items-center justify-between gap-3">
              <button
                v-if="step !== 'recognize'"
                class="text-[11px] text-ink-mute transition hover:text-ink"
                :disabled="processing"
                @click="skipWord"
              >跳过这个词</button>
              <span v-else></span>
              <button class="sp-btn-primary" :disabled="!canNext || processing || finishing" @click="nextStep">
                {{ nextLabel }}
              </button>
            </div>
          </div>
        </div>

        <!-- 完成面板 -->
        <div
          class="mx-auto max-w-xl overflow-hidden transition-[max-height] duration-[320ms] ease-out"
          :class="done ? 'max-h-[900px]' : 'max-h-0'"
        >
          <div class="sp-card-soft mt-2 p-5 sm:p-6">
            <div class="flex items-end gap-8">
              <div>
                <div class="sp-num text-[32px] font-semibold leading-none text-ink">{{ passed }}</div>
                <div class="mt-1 text-[12px] text-ink-mute">学完</div>
              </div>
              <div>
                <div class="sp-num text-[32px] font-semibold leading-none text-ink-mute">{{ skipped }}</div>
                <div class="mt-1 text-[12px] text-ink-mute">跳过</div>
              </div>
            </div>
            <div class="mt-4 flex flex-wrap items-center gap-2">
              <span class="sp-chip-brand">已进复习</span>
              <span class="text-xs text-ink-mute">今天可以再过一遍</span>
            </div>
            <div class="mt-4 flex flex-col gap-2 sm:flex-row">
              <router-link to="/review" class="sp-btn-primary">去复习</router-link>
              <button class="sp-btn-secondary" @click="again">再学一批</button>
              <button class="sp-btn-secondary" @click="backScope">回范围</button>
            </div>
          </div>
        </div>
      </template>
    </main>

    <Transition
      enter-active-class="transition-opacity duration-[160ms] ease-out"
      leave-active-class="transition-opacity duration-[160ms] ease-in"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div v-if="showLeaveConfirm" class="fixed inset-0 z-40 flex items-end justify-center bg-ink/40 p-0 backdrop-blur-sm sm:items-center sm:p-4">
        <div class="w-full max-w-md rounded-t-card bg-white p-6 shadow-lift ring-1 ring-line/80 sm:rounded-card">
          <div class="sp-section-title">还没学完</div>
          <p class="mt-2 text-sm leading-6 text-ink-soft">
            还有 {{ remaining }} 个没学完，退出后这些不进复习。
          </p>
          <div class="mt-5 flex gap-2.5">
            <button class="sp-btn-secondary flex-1" @click="cancelLeave">继续学</button>
            <button class="sp-btn-primary flex-1" @click="confirmLeave">退出</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
