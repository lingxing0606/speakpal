<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import { streamFinish } from '../api/stream'
import AppHeader from '../components/AppHeader.vue'
import ChatBubble from '../components/ChatBubble.vue'
import EmptyState from '../components/EmptyState.vue'
import FinishProgress from '../components/FinishProgress.vue'
import GoalProgress from '../components/GoalProgress.vue'
import HintCard from '../components/HintCard.vue'
import { useRecorder } from '../composables/useRecorder'
import { useTurnStream } from '../composables/useTurnStream'
import { useSessionStore } from '../stores/session'
import { KEY_REQUIRED_MESSAGE, llmReady } from '../utils/llmGate'
import { loadRecordings, playRecording, saveRecording, stopRecording } from '../utils/recordings'
import { speakSmart, stopSpeaking } from '../utils/speech'
import type { AgentTraceStep, AsrSource, AudioMeta, HintItem, SceneFrameOut, SessionTurnOut } from '../types/api'
import type { ChatTurn } from '../stores/session'

interface ApiError {
  message?: string
  response?: { status?: number; data?: { detail?: string } }
}

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const finishing = ref(false)
const confirmingFinish = ref(false)
// 出报告的流式进度：阶段、教练工具调用、开始时间与失败信息
const finishStage = ref('')
const finishTools = ref<AgentTraceStep[]>([])
const finishStartedAt = ref(0)
const finishFailed = ref('')
const finishFallback = ref(false)
const canFinish = ref(false)
const error = ref('')
const chatEl = ref<HTMLElement | null>(null)
// 目标条与控制组件（GoalProgress / 录音 / 流式各管一段，这里只留引用）
const goalRef = ref<InstanceType<typeof GoalProgress> | null>(null)
const micBtn = ref<HTMLButtonElement | null>(null)
const manualBtn = ref<HTMLButtonElement | null>(null)
const manualOpen = ref(false)
const manualText = ref('')
const manualInput = ref<HTMLTextAreaElement | null>(null)
const loadingSession = ref(false)
// AI 朗读语速：A2 听不懂时能降速重听
const speechRate = ref(1)
const SPEECH_RATES = [
  { value: 0.85, label: '慢' },
  { value: 1, label: '正常' },
  { value: 1.15, label: '快' },
]

// 句型脚手架：卡住时给三条场景句式，用提示不扣分
const frames = ref<SceneFrameOut[]>([])
const framesOpen = ref(false)
const framesLoading = ref(false)

async function ensureFrames() {
  if (frames.value.length) return
  const sceneId = session.scene?.id
  if (!sceneId) return
  framesLoading.value = true
  try {
    const { data } = await api.get(`/scenes/${sceneId}/frames`)
    frames.value = data?.frames || []
  } catch (e) {
    const err = e as ApiError
    error.value = '拿不到句型提示：' + (err?.response?.data?.detail || err.message)
  } finally {
    framesLoading.value = false
  }
}

async function toggleFrames() {
  if (framesOpen.value) {
    framesOpen.value = false
    return
  }
  framesOpen.value = true
  await ensureFrames()
}

function useFrame(f: SceneFrameOut) {
  manualText.value = f.en
  recognizedText.value = ''
  pendingAudio = null
  pendingBlob = null
  pendingAsrSource = null
  framesOpen.value = false
  openManual()
}

// 识别出来的这句连同录音一起暂存，用户确认发送时才带上；
// 用户改过文字就不带录音了，免得「语速/停顿」指标和文字对不上
const recognizedText = ref('')
let pendingAudio: AudioMeta | null = null
// 这句的录音文件（Promise<Blob|null>），发送成功后存到本地供回放
let pendingBlob: Promise<Blob | null> | null = null
// 这一句的转写来源：cloud（服务端 ASR）/ browser（浏览器识别）；打字 / 改过文字为 null
let pendingAsrSource: AsrSource | null = null

// 回放自己说过的话：同一时间只放一句
const playingIndex = ref(-1)

async function togglePlayback(t: ChatTurn, i: number) {
  if (playingIndex.value === i) {
    stopRecording()
    playingIndex.value = -1
    return
  }
  stopSpeaking()
  playingIndex.value = i
  const ok = await playRecording(t.blob, () => {
    if (playingIndex.value === i) playingIndex.value = -1
  })
  if (!ok) error.value = '这段录音放不出来，可能是浏览器不支持这种格式。'
}

// 朗读某条 AI 回复（气泡里的喇叭按钮）
function onSpeakTurn(t: ChatTurn) {
  speakSmart(t.content, { rate: speechRate.value })
}

// 重试：沿用原句，替换这条气泡；记 h0 保持高度，内容先淡出 120ms 再回到三点
async function retryTurn(t: ChatTurn) {
  if (sending.value) return
  const el = document.querySelector(`[data-turn="${session.turns.indexOf(t)}"]`)
  const bubble = el?.querySelector<HTMLElement>('[data-role="ai"]')
  t.minHeight = bubble?.offsetHeight || 0
  t.fading = true
  await new Promise((resolve) => setTimeout(resolve, 120))
  t.fading = false
  await retryStream(t)
}

// 按「第几句用户发言」把本地录音挂回对话（刷新 / 从历史回来时）
async function attachRecordings(id: number) {
  const blobs = await loadRecordings(id)
  if (!Object.keys(blobs).length) return
  let ord = 0
  for (const t of session.turns) {
    if (t.role !== 'user') continue
    ord += 1
    if (blobs[ord] && !t.blob) t.blob = markRaw(blobs[ord])
  }
}

// ---- 动态提示卡：8 秒自动 / ? 手动 / 预取 / 换一批（规格见 docs/ui-visual.md 7.3）----
const hintVisible = ref(false)
const hintOffered = ref(false) // 本轮是否已自动递过
const hints = ref<HintItem[]>([])
const hintSource = ref('frames')
const hintLoading = ref(false)
const hintRefreshLeft = ref(2) // 每轮换一批上限
const hintDegraded = ref(false) // 本会话已降到通用句型，不再重试模型
const hintGhostLayer = ref<HTMLElement | null>(null)
let hintTimer: ReturnType<typeof setTimeout> | null = null

function clearHintTimer() {
  if (hintTimer) {
    clearTimeout(hintTimer)
    hintTimer = null
  }
}

function framesAsHints(): HintItem[] {
  return frames.value.slice(0, 3).map((f) => ({ en: f.en, zh: f.zh, tag: '通用句型' }))
}

// 取提示：失败不弹错，回场景句型（与后端降级同一口径）
async function fetchHints({ refresh = false }: { refresh?: boolean } = {}) {
  if (!session.sessionId || hintLoading.value) return false
  hintLoading.value = true
  try {
    const body = refresh
      ? { nonce: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}` }
      : {}
    const { data } = await api.post(`/sessions/${session.sessionId}/hint`, body)
    hints.value = data?.hints || []
    hintSource.value = data?.source === 'llm' ? 'llm' : 'frames'
    if (hintSource.value !== 'llm') hintDegraded.value = true
    return true
  } catch {
    return false
  } finally {
    hintLoading.value = false
  }
}

async function useFramesFallback() {
  await ensureFrames()
  const list = framesAsHints()
  if (!list.length) return false
  hints.value = list
  hintSource.value = 'frames'
  return true
}

async function showHints({ force = false }: { force?: boolean } = {}) {
  if (!manualOpen.value) return
  if (hintVisible.value && !force) return
  if (hintDegraded.value) {
    if (await useFramesFallback()) hintVisible.value = true
    return
  }
  if (hints.value.length) {
    hintVisible.value = true
    return
  }
  if (hintLoading.value) {
    hintVisible.value = true
    return
  }
  hintVisible.value = true
  const ok = await fetchHints()
  if (!ok) await useFramesFallback()
  if (!hints.value.length) hintVisible.value = false
}

async function offerHint() {
  if (hintOffered.value || !manualOpen.value || manualText.value.trim()) return
  hintOffered.value = true
  await showHints()
}

function scheduleHint() {
  clearHintTimer()
  if (hintOffered.value) return
  hintTimer = setTimeout(offerHint, 8000)
}

function hideHint() {
  hintVisible.value = false
  clearHintTimer()
}

// ? 手动入口：自动递过、已有草稿时都能用
function requestHint() {
  hintOffered.value = true
  showHints({ force: true })
}

async function refreshHints() {
  if (hintLoading.value || hintRefreshLeft.value <= 0) return
  hintRefreshLeft.value -= 1
  const ok = await fetchHints({ refresh: true })
  if (!ok) hintRefreshLeft.value += 1
}

// 预取下一轮：不显示卡片，点开即得
function prefetchHints() {
  if (hintDegraded.value) return
  fetchHints()
}

// 点条目：覆盖草稿、光标置末尾、输入框闪一次；英文 ghost 从条目飞进输入框
function pickHint(hint: HintItem, event?: MouseEvent) {
  const rowRect = (event?.currentTarget as HTMLElement | null)?.getBoundingClientRect() || null
  manualText.value = hint.en
  recognizedText.value = ''
  pendingAudio = null
  pendingBlob = null
  pendingAsrSource = null
  hintVisible.value = false
  nextTick(() => {
    const el = manualInput.value
    if (!el) return
    el.focus()
    const len = el.value.length
    el.setSelectionRange(len, len)
    if (reducedMotion()) return
    el.animate(
      [
        { backgroundColor: 'rgba(213, 241, 234, 0.6)' },
        { backgroundColor: 'rgba(255, 255, 255, 0)' },
      ],
      { duration: 120, easing: 'ease-out' }
    )
    if (rowRect) flyHintGhost(hint.en, rowRect, el.getBoundingClientRect())
  })
}

function flyHintGhost(text: string, fromRect: DOMRect, toRect: DOMRect) {
  const layer = hintGhostLayer.value
  if (!layer) return
  const el = document.createElement('span')
  el.textContent = text
  el.className = 'pointer-events-none absolute whitespace-nowrap text-[13px] font-medium text-ink'
  layer.appendChild(el)
  const rect = el.getBoundingClientRect()
  const startX = fromRect.left + fromRect.width / 2
  const startY = fromRect.top + fromRect.height / 2
  el.style.left = `${startX - rect.width / 2}px`
  el.style.top = `${startY - rect.height / 2}px`
  const dx = toRect.left + 10 - startX
  const dy = toRect.top + 12 - startY
  el.animate(
    [
      { transform: 'translate(0px, 0px) scale(1)', opacity: 1 },
      { transform: `translate(${dx}px, ${dy}px) scale(0.92)`, opacity: 0.85 },
    ],
    { duration: 260, easing: 'cubic-bezier(0.3,0.9,0.25,1)', fill: 'forwards' }
  ).finished.then(() => el.remove(), () => el.remove())
}

watch([manualOpen, manualText], ([open, text]) => {
  // 一打字就收起，并且本轮不再用 8 秒自动打扰；关掉输入条也收起
  if (!open || text.trim()) {
    if (text.trim()) hintOffered.value = true
    hideHint()
    return
  }
  scheduleHint()
})

const DIFFICULTY_LABELS: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
const difficultyLabel = computed(() => DIFFICULTY_LABELS[session.difficulty] || session.difficulty || '—')
const hasUserTurn = computed(() => session.turns.some((t) => t.role === 'user'))
const userTurnCount = computed(() => session.turns.filter((t) => t.role === 'user').length)
// Agent 本场计划：目标来自场景任务清单，达成由服务端每轮按关键词规则算
const planGoals = computed(() => session.plan?.goals || [])
const planAchieved = computed(() => session.plan?.achieved || [])
// 常驻进度：别让人说两句就点结束，也别等到第 4 轮才知道能出报告
const progressHint = computed(() => {
  if (canFinish.value) {
    return planGoals.value.length ? '目标都达成了，可以出报告了' : '聊得差不多了，可以出报告了'
  }
  if (planGoals.value.length) {
    const left = planGoals.value.length - planAchieved.value.length
    const done = `本轮 ${planGoals.value.length} 个目标已达成 ${planAchieved.value.length} 个`
    return left > 0 ? `${done}，再补 ${left} 个就能出报告` : done
  }
  const left = 3 - userTurnCount.value
  if (left > 0) return `再说 ${left} 句就能出报告`
  return '可以点「结束并出报告」看评分'
})

function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

// 录音 + 转写：服务端 ASR 优先，失败回落浏览器识别；结果只落输入条，按 Enter 才发出去
const { listening, interim, transcribing, elapsedText, micLevel, toggleListening } = useRecorder({
  onResult({ text, audio, blob, asrSource }) {
    pendingAudio = audio
    pendingBlob = blob
    pendingAsrSource = asrSource
    // 识别结果先落到输入条：说错、识别错都能改，按 Enter 才真的发出去
    recognizedText.value = text
    manualText.value = text
    manualOpen.value = true
    nextTick(() => manualInput.value?.focus())
  },
  onEmpty() {
    // 点了麦克风但没出声：必须给反馈，否则用户以为坏了
    error.value = '这次没听到声音，再点一次麦克风试试，或者改用「手动输入」。'
    nextTick(() => micBtn.value?.focus())
  },
  onError(message) {
    pendingAudio = null
    pendingBlob = null
    pendingAsrSource = null
    error.value = message
  },
  onStart() {
    error.value = ''
  },
})

// 一轮作答的流式收发：乐观插入用户气泡、边收边写 AI 气泡、done 覆盖成服务端整句
const {
  sending,
  streaming,
  thinkingMs,
  send: sendTurn,
  retry: retryStream,
  stop: stopStream,
  abort: abortStream,
} = useTurnStream({
  session,
  scrollBottom,
  onSendStart() {
    error.value = ''
    hintVisible.value = false
  },
  onDegraded() {
    // 模型这轮没回上来，后端给的是预设追问：明说，别让人以为 AI 在正常聊
    error.value = '模型这一轮没有响应（超时、限流或服务异常），上面是预设的追问。可以继续说，或稍后再试。'
  },
  onKeyError({ status, kind }) {
    if (status === 409 && kind === 'llm_not_configured') {
      error.value = KEY_REQUIRED_MESSAGE
      showKeyPanel('还没接入模型密钥。配好之后就能继续这段对话。')
      return
    }
    error.value = '你的密钥被模型服务拒绝了，去设置里换一个再试；这句话没有计入记录。'
    showKeyPanel('你的密钥被模型服务拒绝了，换一个再继续。这句话没有计入记录。')
  },
  onFailure(message) {
    error.value = '发送失败：' + message
  },
  onDone(data, { mineRef, blobPromise }) {
    if (blobPromise) {
      const sid = session.sessionId
      blobPromise.then((blob) => {
        if (!blob) return
        saveRecording(sid, data.turn_index, blob)
        mineRef.blob = markRaw(blob)
      })
    }
    // 目标进度以服务端为准：老会话没有 plan，就不更新
    const hadPlan = planGoals.value.length > 0
    session.setPlan(data.plan)
    if (!hadPlan && planGoals.value.length) {
      // 老会话补上目标：条直接出现，不做飞行
      goalRef.value?.syncAchieved(planAchieved.value)
    } else if (planGoals.value.length) {
      goalRef.value?.animateNew(planAchieved.value, chatEl.value)
    }
    if (data.should_finish) canFinish.value = true
    // 新一轮：重置提示状态并静默预取，点开即得
    hintRefreshLeft.value = 2
    hintOffered.value = false
    hints.value = []
    prefetchHints()
    speakSmart(data.ai_reply, { rate: speechRate.value })
    scrollBottom()
  },
})

// 进对话前先确认有密钥：不让人听完开场白、录完一句才被拒
const blocked = ref(false)
const blockReason = ref('')

// 进页缺密钥 / 发送时被 502 拒，都落到同一张页内面板
function showKeyPanel(reason = '') {
  blockReason.value = reason
  blocked.value = true
}

onMounted(async () => {
  const id = Number(route.params.id)
  if (!id && !session.sessionId) {
    router.push('/')
    return
  }
  const gate = await llmReady()
  if (!gate.ok) {
    blocked.value = true
    blockReason.value = ''
    return
  }
  // 带着 plan 进页面（首页开练 / 刷新回填）：chip 直接就是已达成的样子
  goalRef.value?.syncAchieved(planAchieved.value)
  if (planGoals.value.length) goalRef.value?.finishStripEnter()
  await loadSession(id)
})

// 刷进 /practice/:id：先用服务端记录回填，刷新不丢对话
async function loadSession(id: number) {
  if (id && session.sessionId !== id) {
    loadingSession.value = true
    try {
      const { data } = await api.get(`/sessions/${id}`)
      if (data.status === 'finished' && data.report_id) {
        router.replace(`/report/${id}`)
        return
      }
      if (data.plan?.goals?.length) goalRef.value?.beginStripEnter()
      session.restore(
        id,
        { id: data.scene_id, name: data.scene_name },
        data.difficulty,
        (data.turns || []).map((t: SessionTurnOut) => ({
          role: t.role,
          content: t.content,
          mode: t.input_mode,
          asrSource: t.role === 'user' ? t.asr_source || null : null,
        })),
        data.plan
      )
      goalRef.value?.syncAchieved(planAchieved.value)
      if (data.plan?.goals?.length) goalRef.value?.finishStripEnter()
      attachRecordings(id)
      scrollBottom()
      // 回填时不重播开场白，否则刷新一次就念一遍
      return
    } catch (e) {
      const err = e as ApiError
      error.value =
        err?.response?.status === 404
          ? '这次对话找不到了，回首页重新开始一次吧。'
          : '恢复对话失败：' + (err?.response?.data?.detail || err.message)
      return
    } finally {
      loadingSession.value = false
    }
  }

  const last = session.turns[session.turns.length - 1]
  if (last && last.role === 'ai') speakSmart(last.content, { rate: speechRate.value })
}

onUnmounted(() => {
  // 离开页面时断开还在收的回复（这一轮服务端不会记录）
  abortStream()
  stopRecording()
  clearHintTimer()
  hintGhostLayer.value?.replaceChildren()
})

function scrollBottom() {
  nextTick(() => {
    // main 不再是滚动容器：整页滚动，保持最后一条气泡贴底
    window.scrollTo({ top: document.documentElement.scrollHeight })
  })
}

async function send(
  text: string,
  audio: AudioMeta | null = null,
  mode: 'voice' | 'typed' = 'typed',
  blobPromise: Promise<Blob | null> | null = null,
  asrSource: AsrSource | null = null
) {
  if (!text || sending.value) return false
  const gate = await llmReady()
  if (!gate.ok) {
    error.value = KEY_REQUIRED_MESSAGE
    return false
  }
  return sendTurn(text, audio, mode, blobPromise, asrSource)
}

async function openManual() {
  // 不清空草稿：识别结果或写了一半的话都留着
  manualOpen.value = true
  await nextTick()
  manualInput.value?.focus()
}

function closeManual() {
  // 收起但保留草稿，Esc 不会把写了一半的话吞掉
  manualOpen.value = false
  nextTick(() => manualBtn.value?.focus())
}

function discardManual() {
  manualText.value = ''
  recognizedText.value = ''
  pendingAudio = null
  pendingBlob = null
  pendingAsrSource = null
  manualOpen.value = false
  nextTick(() => manualBtn.value?.focus())
}

async function submitManual() {
  const text = manualText.value.trim()
  if (!text || sending.value) return
  const audio = text === recognizedText.value ? pendingAudio : null
  const mode = audio ? 'voice' : 'typed'
  // 改过文字就不算这段录音的转写了，录音也不留（和语速指标同一条规则）
  const blobPromise = audio ? pendingBlob : null
  const asrSource = audio ? pendingAsrSource : null
  const ok = await send(text, audio, mode, blobPromise, asrSource)
  if (!ok) return
  manualText.value = ''
  recognizedText.value = ''
  pendingAudio = null
  pendingBlob = null
  pendingAsrSource = null
  manualOpen.value = false
  nextTick(() => manualBtn.value?.focus())
}

function onManualKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submitManual()
  } else if (event.key === 'Escape') {
    closeManual()
  }
}

function requestFinish() {
  error.value = ''
  if (!hasUserTurn.value) {
    error.value = '先至少聊一轮，说一句再生成报告。'
    return
  }
  confirmingFinish.value = true
}

function cancelFinish() {
  confirmingFinish.value = false
  finishFailed.value = ''
  finishStage.value = ''
  finishTools.value = []
}

async function finish() {
  if (finishing.value) return
  finishing.value = true
  error.value = ''
  finishFailed.value = ''
  finishFallback.value = false
  finishStage.value = ''
  finishTools.value = []
  finishStartedAt.value = Date.now()
  try {
    const { fallback } = await streamFinish(session.sessionId as number, {
      onStage: (event) => {
        finishStage.value = event?.name || ''
      },
      onTool: (entry) => {
        finishTools.value = [...finishTools.value, entry]
      },
      onFallback: () => {
        finishFallback.value = true
      },
    })
    finishFallback.value = fallback
    finishStage.value = 'done'
    if (!fallback && !reducedMotion()) {
      await new Promise((resolve) => setTimeout(resolve, 160))
    }
    router.push(`/report/${session.sessionId}`)
  } catch (e) {
    const err = e as ApiError
    if (err?.response?.status === 409) {
      // 会话已经结束（另一个页面/请求先生成了报告）：直接去看报告
      router.replace(`/report/${session.sessionId}`)
      return
    }
    finishFailed.value = err?.response?.data?.detail || err.message || '生成报告失败'
  } finally {
    finishing.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col bg-canvas">
    <AppHeader :title="session.scene?.name || '练习'" :subtitle="`难度 ${difficultyLabel}`" back="/" :nav="false" narrow>
      <div class="sp-segment !p-0.5" role="group" aria-label="AI 朗读语速">
        <span class="hidden pl-2 pr-1 text-[11px] text-ink-mute sm:inline">语速</span>
        <button
          v-for="r in SPEECH_RATES"
          :key="r.value"
          class="rounded-full px-2.5 py-1 text-[12px] font-medium transition"
          :class="speechRate === r.value ? 'bg-white text-brand-700 shadow-soft ring-1 ring-line/80' : 'text-ink-mute hover:text-ink'"
          :aria-pressed="speechRate === r.value"
          @click="speechRate = r.value"
        >
          {{ r.label }}
        </button>
      </div>
      <router-link to="/settings" class="sp-btn-ghost hidden sm:inline-flex">设置</router-link>
    </AppHeader>

    <GoalProgress ref="goalRef" />

    <div v-if="blocked" class="sp-shell-narrow py-12">
      <div class="sp-card mx-auto max-w-lg p-7 ring-brand-100">
        <div class="font-semibold text-ink">{{ blockReason || '进对话前要先接入一个模型密钥' }}</div>
        <p v-if="blockReason" class="mt-1.5 text-sm leading-6 text-ink-soft">
          换一个能用的密钥就能接着这段对话，刚才那句话没有计入记录。
        </p>
        <p v-else class="mt-1.5 text-sm leading-6 text-ink-soft">
          练习要调用模型陪聊和评分，没有密钥会中途卡住。密钥只存在你自己的浏览器里，不上传、不写数据库。
        </p>
        <div class="mt-4 flex flex-wrap items-center gap-2">
          <button class="sp-btn-primary" @click="router.push('/settings?onboarding=1')">去设置填密钥</button>
          <button v-if="blockReason" class="sp-btn-ghost" @click="blocked = false">返回练习</button>
          <button v-else class="sp-btn-ghost" @click="router.push('/')">返回首页</button>
        </div>
      </div>
    </div>

    <main v-if="!blocked" ref="chatEl" class="sp-shell-narrow flex-1 space-y-4 pb-6 pt-4">
      <ChatBubble
        v-for="(t, i) in session.turns"
        :key="i"
        :turn="t"
        :index="i"
        :playing-index="playingIndex"
        :speech-rate="speechRate"
        :thinking-ms="thinkingMs"
        @toggle-playback="togglePlayback"
        @speak="onSpeakTurn"
        @retry="retryTurn"
      />

      <div v-if="interim" class="flex justify-end">
        <div class="max-w-[82%] rounded-[1.25rem] rounded-br-md border border-dashed border-brand-300 bg-brand-50 px-4 py-3 text-[15px] leading-7 text-brand-700">
          {{ interim }}…
        </div>
      </div>

      <div v-if="loadingSession" class="space-y-4" aria-label="正在恢复这次对话">
        <div class="sp-skeleton h-16 w-3/4 rounded-[1.25rem]"></div>
        <div class="sp-skeleton ml-auto h-12 w-1/2 rounded-[1.25rem]"></div>
        <div class="sp-skeleton h-16 w-2/3 rounded-[1.25rem]"></div>
      </div>
      <EmptyState
        v-else-if="!session.turns.length"
        icon="practice"
        title="准备好就开口"
        text="点下面的麦克风说一句英文，说不出来可以「手动输入」或看「场景句型」。"
      />
    </main>

    <footer v-if="!blocked" class="sticky bottom-0 z-10 bg-gradient-to-t from-canvas via-canvas/95 to-canvas/0 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4">
      <div class="sp-shell-narrow">
      <div class="relative space-y-3 rounded-card bg-white/95 p-4 shadow-dock ring-1 ring-line/80 backdrop-blur sm:p-5">
        <!-- 停止生成：浮在输入区上沿右侧，不改 dock 高度；只在首个 delta 之后出现 -->
        <Transition name="sp-stop">
          <button
            v-if="streaming"
            class="sp-stop-pill absolute bottom-full right-0 z-20 mb-2"
            aria-label="停止生成"
            @click="stopStream"
          >
            <span class="h-1.5 w-1.5 rounded-[2px] bg-white" aria-hidden="true"></span>
            停止
          </button>
        </Transition>
        <Transition
          enter-active-class="sp-hint-card-enter"
          leave-active-class="sp-hint-card-leave"
          enter-from-class="sp-hint-card-enter-from"
          leave-to-class="sp-hint-card-leave-to"
        >
          <HintCard
            v-if="hintVisible && manualOpen"
            :hints="hints"
            :source="hintSource"
            :loading="hintLoading && !hints.length"
            :busy="hintLoading && hints.length > 0"
            :can-refresh="hintRefreshLeft > 0"
            @pick="pickHint"
            @refresh="refreshHints"
            @close="hideHint"
          />
        </Transition>
        <p v-if="!manualOpen" class="text-center text-[11px] text-ink-mute">{{ progressHint }}</p>

        <p v-if="error" class="sp-alert-error">{{ error }}</p>

        <div
          v-if="canFinish && !confirmingFinish"
          class="rounded-xl bg-brand-50 px-3.5 py-2 text-xs text-brand-700 ring-1 ring-brand-100"
        >
          已经聊了几轮，可以点右下「结束并出报告」看评分了。
        </div>

        <FinishProgress
          v-if="confirmingFinish && (finishing || finishFailed)"
          :stage="finishStage"
          :tools="finishTools"
          :started-at="finishStartedAt"
          :failed="finishFailed"
          :fallback="finishFallback"
          @retry="finish"
        />

        <div
          v-else-if="confirmingFinish"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800 ring-1 ring-amber-100"
        >
          <span>生成报告后这次对话就结束了，确定吗？</span>
          <div class="flex gap-2">
            <button class="sp-btn-primary py-1.5" @click="finish">确认生成</button>
            <button class="sp-btn-ghost py-1.5" @click="cancelFinish">继续聊</button>
          </div>
        </div>

        <div v-if="framesOpen" class="rounded-xl bg-canvas p-3 ring-1 ring-line">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-ink-soft">场景句型 · 用提示不扣分</span>
            <button class="text-[11px] text-ink-mute hover:text-ink-soft" @click="framesOpen = false">收起</button>
          </div>
          <p v-if="framesLoading" class="mt-2 text-xs text-ink-mute">正在取…</p>
          <div v-else class="mt-2 grid gap-2 sm:grid-cols-3">
            <button
              v-for="f in frames"
              :key="f.en"
              class="rounded-xl bg-white px-3 py-2 text-left ring-1 ring-line transition hover:ring-brand-300"
              @click="useFrame(f)"
            >
              <div class="text-xs font-medium leading-5 text-ink">{{ f.en }}</div>
              <div class="mt-0.5 text-[11px] leading-5 text-ink-mute">{{ f.zh }}</div>
            </button>
          </div>
          <p v-if="!framesLoading && !frames.length" class="mt-2 text-xs text-ink-mute">
            这个场景暂时没有句型提示。
          </p>
        </div>

        <div
          v-if="manualOpen"
          class="space-y-2"
          :class="finishing ? 'pointer-events-none opacity-60' : ''"
        >
          <p v-if="recognizedText" class="text-xs text-brand-700">
            这是识别到的内容，确认或改一下，按 Enter 发送。
          </p>
          <div class="flex items-end gap-2">
            <textarea
              ref="manualInput"
              v-model="manualText"
              rows="2"
              class="sp-input resize-none"
              placeholder="用英文写下你的回答，Enter 发送，Shift+Enter 换行"
              @keydown="onManualKeydown"
            ></textarea>
            <button class="sp-btn-primary shrink-0" :disabled="sending || !manualText.trim()" @click="submitManual">发送</button>
            <button class="sp-btn-ghost shrink-0" @click="closeManual">收起</button>
          </div>
          <div class="flex items-center justify-between">
            <button
              class="inline-flex h-6 min-w-[40px] items-center gap-1 rounded-lg px-1 text-[11px] text-ink-mute transition hover:text-brand-700"
              aria-label="生成一条针对当前问题的提示"
              @click="requestHint"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M9 18h6M10 21h4" />
                <path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2h5c.1-.8.5-1.5 1.1-2A6 6 0 0 0 12 3Z" />
              </svg>
              ? 提示
            </button>
            <button v-if="manualText" class="text-[11px] text-danger hover:underline" @click="discardManual">清空草稿</button>
          </div>
        </div>

        <div
          v-else
          class="flex items-center justify-between gap-3"
          :class="finishing ? 'pointer-events-none opacity-60' : ''"
        >
          <div class="flex flex-col gap-1.5">
            <button ref="manualBtn" class="sp-btn-secondary" :disabled="sending" @click="openManual">手动输入</button>
            <button class="sp-btn-ghost !px-2 !py-1 text-[11px]" :disabled="sending" @click="toggleFrames">
              场景句型
            </button>
          </div>

          <div class="flex flex-col items-center gap-1">
            <button
              ref="micBtn"
              :style="{ '--level': micLevel }"
              :class="
                listening
                  ? 'sp-mic sp-mic-rec sp-mic-pulse !h-16 !w-16'
                  : 'sp-mic sp-mic-idle !h-16 !w-16 hover:scale-105 active:scale-95'
              "
              :disabled="sending || finishing"
              :aria-label="listening ? '停止录音' : '开始录音'"
              @click="toggleListening"
            >
              <span v-if="listening" class="sp-mic-level" aria-hidden="true"></span>
              <svg v-if="!listening" class="relative" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="9" y="2.8" width="6" height="11" rx="3" />
                <path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0" />
                <path d="M12 17.8v3.4" />
              </svg>
              <svg v-else class="relative" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                <rect x="7" y="7" width="10" height="10" rx="2.4" fill="currentColor" />
              </svg>
            </button>
            <span class="h-4 text-[11px]" :class="listening ? 'font-medium text-ink-soft' : 'text-ink-mute'">
              {{ listening ? `录音中 ${elapsedText}` : transcribing ? '云端转写中…' : sending ? '正在回复…' : '点一下说话' }}
            </span>
          </div>

          <button class="sp-btn bg-brand-700 text-white shadow-soft hover:bg-brand-800" :disabled="finishing || sending" @click="requestFinish">
            {{ finishing ? '生成中…' : '结束并出报告' }}
          </button>
        </div>
      </div>
      </div>
    </footer>

    <!-- 提示填入时的英文 ghost 落点层 -->
    <div ref="hintGhostLayer" class="pointer-events-none fixed inset-0 z-50" aria-hidden="true"></div>
  </div>
</template>
