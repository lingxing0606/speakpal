<script setup lang="ts">
import { computed, onUnmounted, ref, type PropType } from 'vue'
import { useRoute } from 'vue-router'

import api from '../api/client'
import EmptyState from './EmptyState.vue'
import { playRecording, stopRecording } from '../utils/recordings'
import { createRecognizer, speakSmart, stopSpeaking, type SpeechRecognizer } from '../utils/speech'
import type { DrillAttemptOut, DrillItem, ReportOut, SentenceFix } from '../types/api'

const props = defineProps({
  report: { type: Object as PropType<ReportOut>, default: null },
  // 本轮跟读题（GET /sessions/{id}/drills）：概览页签的「已通过 N/M」也用它
  drills: { type: Object as PropType<{ items: DrillItem[]; pass_threshold: number }>, default: () => ({ items: [], pass_threshold: 0.85 }) },
  // 每条纠错对应的本地录音（只在录过这次练习的浏览器里有）
  fixRecordings: { type: Array as PropType<(Blob | null)[]>, default: () => [] },
  // 教练「看这句」高亮的序号：由父组件切换页签后传入
  highlightFix: { type: Number, default: -1 },
})

const route = useRoute()

interface ApiError {
  message?: string
  response?: { data?: { detail?: string } }
}

// ---- 跟读重说：把报告的「改写句」做成练-错-立刻改的闭环 ----
const drillOpen = ref<number | null>(null)
const drillListening = ref(false)
const drillText = ref('')
const drillResult = ref<DrillAttemptOut | null>(null)
const drillBusy = ref(false)
const drillError = ref('')
let drillRecognizer: SpeechRecognizer | null = null

const topFixes = computed(() => (props.drills.items || []).slice(0, 3).filter((it) => it.target))
const passedCount = computed(() => topFixes.value.filter((it) => it.passed).length)
const drillByIndex = computed(() =>
  Object.fromEntries((props.drills.items || []).map((it) => [it.index, it] as [number, DrillItem]))
)

// ---- 加入学习清单：语法/啰嗦两类后端不会自动建卡，要用户自己挑 ----
const ERROR_LABELS: Record<string, string> = {
  spelling: '拼写',
  grammar: '语法',
  stiffness: '表达僵硬',
  wordiness: '啰嗦',
}
const addedMap = ref<Record<number, boolean>>({})
const addBusy = ref<number | null>(null)
const addError = ref<Record<number, string>>({})

// RAG 依据卡（阶段 2）：展开卡片原文 / 加入复习
const ruleOpen = ref<Record<number, boolean>>({})
const ruleAdded = ref<Record<number, boolean>>({})
const ruleBusy = ref<number | null>(null)
const ruleError = ref<Record<number, string>>({})

function toggleRule(i: number) {
  ruleOpen.value = { ...ruleOpen.value, [i]: !ruleOpen.value[i] }
}

function ruleKindLabel(kind: unknown) {
  if (kind === 'spoken') return '口语卡'
  if (kind === 'grammar') return '语法卡'
  return '依据卡'
}

async function addRuleToStudy(fix: SentenceFix, i: number) {
  if (!fix.rule || ruleAdded.value[i] || ruleBusy.value === i) return
  ruleBusy.value = i
  ruleError.value = { ...ruleError.value, [i]: '' }
  try {
    await api.post('/study/items', {
      kind: 'phrase',
      term: fix.rule.title,
      context: fix.rule.text,
      meaning_zh: fix.rule.kind === 'spoken' ? '口语卡依据' : '语法卡依据',
      example: '',
      related: {},
      source_session_id: Number(route.params.id) || null,
    })
    ruleAdded.value = { ...ruleAdded.value, [i]: true }
  } catch (e) {
    const err = e as ApiError
    ruleError.value = {
      ...ruleError.value,
      [i]: '加入失败：' + (err?.response?.data?.detail || err.message),
    }
  } finally {
    ruleBusy.value = null
  }
}

function errorLabel(type: string) {
  return ERROR_LABELS[type] || '表达'
}

async function addToStudy(fix: SentenceFix, i: number) {
  if (addedMap.value[i] || addBusy.value === i) return
  addBusy.value = i
  addError.value = { ...addError.value, [i]: '' }
  try {
    const kind = fix.error_type === 'spelling' ? 'spelling' : 'phrase'
    const reason = fix.reason || ''
    // 拼写卡的题干不能出现纠错原因（原因常直接写出正确拼写），原因放到 related.reason，
    // 等判完之后在卡片反馈里显示
    const related = { ...(fix.related || {}) }
    if (kind === 'spelling' && reason) related.reason = reason
    await api.post('/study/items', {
      kind,
      term: fix.word || fix.better || fix.original,
      context: fix.original,
      meaning_zh: kind === 'spelling' ? '' : reason,
      example: fix.better || '',
      related,
      source_session_id: Number(route.params.id) || null,
    })
    addedMap.value = { ...addedMap.value, [i]: true }
  } catch (e) {
    const err = e as ApiError
    addError.value = { ...addError.value, [i]: '加入失败：' + (err?.response?.data?.detail || err.message) }
  } finally {
    addBusy.value = null
  }
}

// 本地回放：同一时间只放一句
const playingFix = ref(-1)

function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

async function toggleFixPlayback(i: number) {
  if (playingFix.value === i) {
    stopRecording()
    playingFix.value = -1
    return
  }
  stopSpeaking()
  playingFix.value = i
  await playRecording(props.fixRecordings[i], () => {
    if (playingFix.value === i) playingFix.value = -1
  })
}

function stopDrillListen() {
  if (drillRecognizer) {
    drillRecognizer.abort?.()
    drillRecognizer = null
  }
  drillListening.value = false
}

function openDrill(item: DrillItem) {
  stopDrillListen()
  drillError.value = ''
  drillOpen.value = item.index
  drillText.value = ''
  drillResult.value = null
}

function closeDrill() {
  stopDrillListen()
  drillError.value = ''
  drillOpen.value = null
  drillResult.value = null
  drillText.value = ''
}

function toggleDrillListen(item: DrillItem) {
  if (drillListening.value) {
    stopDrillListen()
    return
  }
  drillText.value = ''
  drillResult.value = null
  drillError.value = ''
  drillRecognizer = createRecognizer(
    (text) => {
      drillText.value = text
    },
    () => {
      drillListening.value = false
      if (drillText.value.trim()) submitDrill(item)
    },
    (event) => {
      drillListening.value = false
      const map: Record<string, string> = {
        'not-allowed': '麦克风权限被拒绝了。请在地址栏左侧允许，或先听一遍原句。',
        'no-speech': '没听到声音，再点一次麦克风试试。',
        'audio-capture': '没找到麦克风，检查一下设备。',
      }
      const msg = map[event?.error || '']
      if (msg) drillError.value = msg
    }
  )
  if (!drillRecognizer) {
    drillError.value = '当前浏览器不支持语音识别，请换 Chrome 再跟读。'
    return
  }
  drillListening.value = true
  drillRecognizer.start()
}

async function submitDrill(item: DrillItem) {
  const text = drillText.value.trim()
  if (!text || drillBusy.value) return
  drillBusy.value = true
  try {
    const { data } = await api.post(`/sessions/${route.params.id}/drills/${item.index}/attempt`, {
      transcript: text,
    })
    drillResult.value = data
    item.attempts = data.attempts
    item.best_similarity = data.best_similarity
    item.passed = data.passed
  } catch (e) {
    const err = e as ApiError
    drillError.value = '评定失败：' + (err?.response?.data?.detail || err.message)
  } finally {
    drillBusy.value = false
  }
}

// 教练建议「看这句」：父组件切到本页签后调这里，把目标句滚到视口中间并闪一次
const fixEls: (HTMLElement | null)[] = []

function scrollTo(index: number) {
  const el = fixEls[index]
  if (!el) return false
  el.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'center' })
  return true
}

defineExpose({ scrollTo })

onUnmounted(() => {
  stopDrillListen()
})
</script>

<template>
  <div v-if="topFixes.length" class="sp-card flex flex-wrap items-center justify-between gap-3 p-5">
    <div class="flex flex-wrap items-center gap-2 text-xs">
      <span class="sp-chip-brand">已通过 {{ passedCount }}/{{ (report.sentence_fixes || []).length }}</span>
      <router-link to="/pronunciation" class="font-medium text-brand-700 underline-offset-2 hover:underline">
        练 ship / sheep
      </router-link>
    </div>
  </div>

  <div class="sp-card p-6">
    <EmptyState
      v-if="!(report.sentence_fixes || []).length"
      compact
      icon="done"
      title="没有需要改的句子"
      text="这次说的话里没有挑出要改写的句子。换个难一点的场景，或多说几句再看看。"
    />
    <div
      v-for="(f, i) in (report.sentence_fixes || [])"
      :key="i"
      :ref="(el) => (fixEls[i] = el as HTMLElement | null)"
      :style="{ '--i': Math.min(i, 10) }"
      class="sp-reveal mt-3 rounded-2xl bg-paper p-4 text-sm ring-1 ring-line/70 transition duration-200 hover:ring-brand-200"
      :class="highlightFix === i ? '!ring-2 !ring-brand-200' : ''"
    >
      <div class="flex items-start gap-2">
        <span class="mt-0.5 text-[11px] font-medium text-ink-mute">原句</span>
        <div :class="f.better ? 'text-rose-500 line-through decoration-rose-300' : 'text-ink-soft'" class="leading-6">
          {{ f.original }}
        </div>
      </div>
      <div v-if="f.better" class="mt-1.5 flex items-start gap-2">
        <span class="mt-0.5 text-[11px] font-medium text-brand-700">改写</span>
        <div class="leading-6 text-brand-700">{{ f.better }}</div>
      </div>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <span class="sp-chip-line">{{ errorLabel(f.error_type) }}</span>
        <span v-if="f.natural" class="text-xs leading-5 text-ink-soft">更自然：{{ f.natural }}</span>
      </div>
      <div class="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-line/70 pt-2">
        <div class="min-w-0 text-xs leading-5 text-ink-soft">{{ f.reason }}</div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            v-if="fixRecordings[i]"
            class="sp-btn-ghost !px-3 !py-1 text-xs"
            :aria-label="playingFix === i ? '停止回放' : '听我当时怎么说的'"
            @click="toggleFixPlayback(i)"
          >
            {{ playingFix === i ? '停止' : '听我的录音' }}
          </button>
          <button
            v-if="drillByIndex[i]"
            class="sp-btn-secondary !px-3 !py-1 text-xs"
            @click="openDrill(drillByIndex[i])"
          >
            {{ drillByIndex[i].passed ? '已通过 · 再练' : '重说这句' }}
          </button>
          <button
            class="sp-btn-ghost !px-3 !py-1 text-xs"
            :disabled="addedMap[i] || addBusy === i"
            @click="addToStudy(f, i)"
          >
            {{ addedMap[i] ? '已加入清单' : '加入学习清单' }}
          </button>
        </div>
      </div>

      <div v-if="f.rule_ref" class="mt-2 rounded-xl bg-white p-3 ring-1 ring-line/70">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <button
            class="min-w-0 text-left text-[12px] font-medium text-brand-700 underline-offset-2 hover:underline"
            :aria-expanded="!!ruleOpen[i]"
            @click="toggleRule(i)"
          >
            依据：{{ ruleKindLabel(f.rule?.kind) }} · {{ f.rule?.title || f.rule_ref }}
          </button>
          <button
            class="sp-btn-ghost shrink-0 !px-2 !py-1 text-[11px]"
            :disabled="!f.rule || ruleAdded[i] || ruleBusy === i"
            @click="addRuleToStudy(f, i)"
          >
            {{ ruleAdded[i] ? '已加入复习' : ruleBusy === i ? '加入中…' : '加入复习' }}
          </button>
        </div>
        <p v-if="ruleOpen[i]" class="mt-2 text-[12px] leading-5 text-ink-soft">
          {{ f.rule?.text || '这张卡没有可展示的原文。' }}
        </p>
        <p v-if="ruleError[i]" class="mt-1 text-[11px] leading-5 text-danger">{{ ruleError[i] }}</p>
      </div>
      <p v-if="addError[i]" class="mt-1 text-[11px] leading-5 text-danger">{{ addError[i] }}</p>

      <div
        v-if="drillByIndex[i] && drillOpen === i"
        class="mt-2 rounded-xl bg-white p-3 ring-1 ring-brand-100"
      >
        <p class="text-[11px] leading-5 text-ink-mute">
          目标句：<span class="font-medium text-brand-700">{{ drillByIndex[i].target }}</span>
        </p>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <button class="sp-btn-ghost !px-2 !py-1 text-xs" @click="speakSmart(drillByIndex[i].target, { rate: 0.9 })">
            先听一遍
          </button>
          <button
            class="sp-btn-primary !px-3 !py-1.5 text-xs"
            :disabled="drillBusy"
            @click="toggleDrillListen(drillByIndex[i])"
          >
            {{ drillListening ? '正在听…点一下停' : '点一下说' }}
          </button>
          <button class="sp-btn-ghost !px-2 !py-1 text-xs" @click="closeDrill">收起</button>
        </div>
        <p v-if="drillText" class="mt-2 text-xs leading-5 text-ink-soft">听到：{{ drillText }}</p>
        <p v-if="drillError" class="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 ring-1 ring-amber-100">
          {{ drillError }}
        </p>
        <div
          v-if="drillResult"
          class="mt-2 rounded-lg px-3 py-2 text-xs leading-5"
          :class="drillResult.passed ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100' : 'bg-amber-50 text-amber-800 ring-1 ring-amber-100'"
        >
          <div class="font-medium">
            {{ drillResult.passed ? '过了！' : '还不够接近' }} · 相似度
            {{ Math.round(drillResult.similarity * 100) }}% · 第 {{ drillResult.attempts }} 次
          </div>
          <div class="mt-0.5">{{ drillResult.feedback }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
