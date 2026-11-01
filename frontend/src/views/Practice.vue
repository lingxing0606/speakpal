<script setup>
import { computed, markRaw, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import { streamTurn } from '../api/stream'
import AppHeader from '../components/AppHeader.vue'
import BrandLogo from '../components/BrandLogo.vue'
import EmptyState from '../components/EmptyState.vue'
import { useSessionStore } from '../stores/session'
import { startAudioCapture } from '../utils/audio'
import { KEY_REQUIRED_MESSAGE, llmReady } from '../utils/llmGate'
import { loadRecordings, playRecording, saveRecording, stopRecording } from '../utils/recordings'
import { createRecognizer, speakSmart, stopSpeaking } from '../utils/speech'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const listening = ref(false)
const interim = ref('')
const sending = ref(false)
// 流式回复已经开始出字：此时收起「正在输入」的三个点
const streaming = ref(false)
let streamAbort = null
const finishing = ref(false)
const confirmingFinish = ref(false)
const canFinish = ref(false)
const error = ref('')
const chatEl = ref(null)
const micBtn = ref(null)
const manualBtn = ref(null)
const manualOpen = ref(false)
const manualText = ref('')
const manualInput = ref(null)
const loadingSession = ref(false)
// AI 朗读语速：A2 听不懂时能降速重听
const speechRate = ref(1)
const SPEECH_RATES = [
  { value: 0.85, label: '慢' },
  { value: 1, label: '正常' },
  { value: 1.15, label: '快' },
]

// 句型脚手架：卡住时给三种说法，用提示不扣分
const frames = ref([])
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
    error.value = '拿不到句型提示：' + (e?.response?.data?.detail || e.message)
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

function useFrame(f) {
  manualText.value = f.en
  recognizedText.value = ''
  pendingAudio = null
  pendingBlob = null
  framesOpen.value = false
  openManual()
}

// 识别出来的这句连同录音一起暂存，用户确认发送时才带上；
// 用户改过文字就不带录音了，免得「语速/停顿」指标和文字对不上
const recognizedText = ref('')
let pendingAudio = null
// 这句的录音文件（Promise<Blob|null>），发送成功后存到本地供回放
let pendingBlob = null

// 回放自己说过的话：同一时间只放一句
const playingIndex = ref(-1)

async function togglePlayback(t, i) {
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

// 按「第几句用户发言」把本地录音挂回对话（刷新 / 从历史回来时）
async function attachRecordings(id) {
  const blobs = await loadRecordings(id)
  if (!Object.keys(blobs).length) return
  let ord = 0
  for (const t of session.turns) {
    if (t.role !== 'user') continue
    ord += 1
    if (blobs[ord] && !t.blob) t.blob = markRaw(blobs[ord])
  }
}

// 手动输入条打开后 8 秒没动键盘，就在输入框上方递三条可用说法；每次进练习页只递一次
const hintVisible = ref(false)
const hintOffered = ref(false)
const hintFrames = computed(() => frames.value.slice(0, 3))
let hintTimer = null

function clearHintTimer() {
  if (hintTimer) {
    clearTimeout(hintTimer)
    hintTimer = null
  }
}

async function offerHint() {
  if (hintOffered.value || !manualOpen.value || manualText.value.trim()) return
  hintOffered.value = true
  await ensureFrames()
  // 场景没有句型提示时不要挂一行空提示
  if (frames.value.length && manualOpen.value && !manualText.value.trim()) hintVisible.value = true
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

watch([manualOpen, manualText], ([open, text]) => {
  // 一打字就收起；关掉输入条也收起
  if (!open || text.trim()) {
    hideHint()
    return
  }
  scheduleHint()
})

// 点一条就把句式填进输入框，光标放末尾
function useHintFrame(f) {
  manualText.value = f.en
  recognizedText.value = ''
  pendingAudio = null
  pendingBlob = null
  hintVisible.value = false
  nextTick(() => {
    const el = manualInput.value
    if (!el) return
    el.focus()
    const len = el.value.length
    el.setSelectionRange(len, len)
  })
}

let recognizer = null
let capturer = null
let timer = null
const elapsed = ref(0)
// 录音按钮外圈跟着真实音量缩放（0–1）
const micLevel = ref(0)
let levelRaf = 0

function trackLevel() {
  cancelAnimationFrame(levelRaf)
  const tick = () => {
    const rms = capturer?.level?.() || 0
    // 说话时 RMS 常在 0.02–0.2，映射到 0–1 并做一点平滑
    const target = Math.min(1, Math.max(0, (rms - 0.015) * 6))
    micLevel.value = micLevel.value * 0.6 + target * 0.4
    levelRaf = requestAnimationFrame(tick)
  }
  levelRaf = requestAnimationFrame(tick)
}

function stopLevel() {
  cancelAnimationFrame(levelRaf)
  micLevel.value = 0
}

const DIFFICULTY_LABELS = { easy: '简单', medium: '中等', hard: '困难' }
const difficultyLabel = computed(() => DIFFICULTY_LABELS[session.difficulty] || session.difficulty || '—')
const elapsedText = computed(() => `${Math.floor(elapsed.value / 60)}:${String(elapsed.value % 60).padStart(2, '0')}`)
const hasUserTurn = computed(() => session.turns.some((t) => t.role === 'user'))
const userTurnCount = computed(() => session.turns.filter((t) => t.role === 'user').length)
// 常驻进度：别让人说两句就点结束，也别等到第 4 轮才知道能出报告
const progressHint = computed(() => {
  if (canFinish.value) return '聊得差不多了，可以出报告了'
  const left = 3 - userTurnCount.value
  if (left > 0) return `再说 ${left} 句就能出报告`
  return '可以点「结束并出报告」看评分'
})

// 进对话前先确认有密钥：不让人听完开场白、录完一句才被拒
const blocked = ref(false)
const blockReason = ref('')

// 进页缺密钥 / 发送时被 502 拒，都落到同一张页内面板
function showKeyPanel(reason = '') {
  blockReason.value = reason
  blocked.value = true
}

// 语音识别错误码翻成用户能懂的话，不把 not-allowed 这种英文码甩到页面上
const SPEECH_ERRORS = {
  'not-allowed': '麦克风权限被拒绝了。请在地址栏左侧允许麦克风，或改用「手动输入」。',
  'service-not-allowed': '这个浏览器不允许语音识别，请换 Chrome，或改用「手动输入」。',
  'audio-capture': '没找到可用的麦克风，检查一下设备是否插好或被别的程序占用。',
  network: '语音识别服务连不上网络，过一会儿再试，或改用「手动输入」。',
  'no-speech': '这次没听到声音，再说一遍试试。',
  aborted: '',
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
  await loadSession(id)
})

// 刷进 /practice/:id：先用服务端记录回填，刷新不丢对话
async function loadSession(id) {
  if (id && session.sessionId !== id) {
    loadingSession.value = true
    try {
      const { data } = await api.get(`/sessions/${id}`)
      if (data.status === 'finished' && data.report_id) {
        router.replace(`/report/${id}`)
        return
      }
      session.restore(
        id,
        { id: data.scene_id, name: data.scene_name },
        data.difficulty,
        (data.turns || []).map((t) => ({ role: t.role, content: t.content, mode: t.input_mode }))
      )
      attachRecordings(id)
      scrollBottom()
      // 回填时不重播开场白，否则刷新一次就念一遍
      return
    } catch (e) {
      error.value =
        e?.response?.status === 404
          ? '这次对话找不到了，回首页重新开始一次吧。'
          : '恢复对话失败：' + (e?.response?.data?.detail || e.message)
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
  streamAbort?.abort()
  stopRecording()
  stopTimer()
  clearHintTimer()
  if (recognizer) recognizer.abort?.()
})

function scrollBottom() {
  nextTick(() => {
    if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
  })
}

function startTimer() {
  stopTimer()
  trackLevel()
  elapsed.value = 0
  timer = setInterval(() => {
    elapsed.value += 1
  }, 1000)
}

function stopTimer() {
  stopLevel()
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function startListening() {
  error.value = ''
  recognizer = createRecognizer(
    (text) => {
      interim.value = text
    },
    () => {
      listening.value = false
      stopTimer()
      const text = interim.value.trim()
      pendingAudio = capturer ? capturer.stop() : null
      pendingBlob = capturer ? capturer.blob() : null
      capturer = null
      interim.value = ''
      if (!text) {
        // 点了麦克风但没出声：必须给反馈，否则用户以为坏了
        error.value = '这次没听到声音，再点一次麦克风试试，或者改用「手动输入」。'
        nextTick(() => micBtn.value?.focus())
        return
      }
      // 识别结果先落到输入条：说错、识别错都能改，按 Enter 才真的发出去
      recognizedText.value = text
      manualText.value = text
      manualOpen.value = true
      nextTick(() => manualInput.value?.focus())
    },
    (event) => {
      listening.value = false
      stopTimer()
      if (capturer) {
        capturer.stop()
        capturer = null
      }
      pendingAudio = null
      pendingBlob = null
      interim.value = ''
      const msg = SPEECH_ERRORS[event?.error]
      if (msg) error.value = msg
    }
  )
  if (!recognizer) {
    error.value = '当前浏览器不支持语音识别，请用 Chrome，或点「手动输入」。'
    return
  }
  try {
    capturer = await startAudioCapture()
  } catch (e) {
    capturer = null
  }
  interim.value = ''
  listening.value = true
  startTimer()
  recognizer.start()
}

function stopListening() {
  if (recognizer) recognizer.stop()
  if (!recognizer) {
    listening.value = false
    stopTimer()
  }
}

function toggleListening() {
  if (listening.value) stopListening()
  else startListening()
}

async function send(text, audio = null, mode = 'typed', blobPromise = null) {
  if (!text || sending.value) return false
  const gate = await llmReady()
  if (!gate.ok) {
    error.value = KEY_REQUIRED_MESSAGE
    return false
  }
  sending.value = true
  error.value = ''
  const mine = { role: 'user', content: text, mode }
  session.turns.push(mine)
  // 拿响应式代理（不是原对象），之后挂录音才会刷新界面
  const mineRef = session.turns[session.turns.length - 1]
  scrollBottom()
  // AI 气泡收到第一段才插入；之后边收边追加
  let aiRef = null
  streamAbort = new AbortController()
  try {
    const data = await streamTurn(
      session.sessionId,
      { transcript: text, audio, input_mode: mode },
      {
        signal: streamAbort.signal,
        onDelta(piece) {
          if (!piece) return
          if (!aiRef) {
            session.turns.push({ role: 'ai', content: '', streaming: true })
            aiRef = session.turns[session.turns.length - 1]
            streaming.value = true
          }
          aiRef.content += piece
          scrollBottom()
        },
      }
    )
    // 以 done 里的整句为准：中途断流时服务端会换成预设追问
    if (aiRef) {
      aiRef.content = data.ai_reply
      aiRef.streaming = false
    } else {
      session.turns.push({ role: 'ai', content: data.ai_reply })
    }
    if (blobPromise) {
      const sid = session.sessionId
      blobPromise.then((blob) => {
        if (!blob) return
        saveRecording(sid, data.turn_index, blob)
        mineRef.blob = markRaw(blob)
      })
    }
    // 模型这轮没回上来，后端给的是预设追问：明说，别让人以为 AI 在正常聊
    if (data.degraded) {
      error.value = '模型这一轮没有响应（超时、限流或服务异常），上面是预设的追问。可以继续说，或稍后再试。'
    }
    if (data.should_finish) canFinish.value = true
    speakSmart(data.ai_reply, { rate: speechRate.value })
    scrollBottom()
    return true
  } catch (e) {
    // 后端拒收（空转写 / 超长 / 密钥问题）或流断了：把刚乐观插入的这句和半截回复都撤回
    if (aiRef) {
      const j = session.turns.indexOf(aiRef)
      if (j >= 0) session.turns.splice(j, 1)
    }
    const i = session.turns.indexOf(mine)
    if (i >= 0) session.turns.splice(i, 1)
    // 离开页面导致的中断不用提示
    if (e?.name === 'AbortError') return false
    const detail = e?.response?.data?.detail
    const kind = e?.response?.data?.kind
    if (e?.response?.status === 409 && (kind === 'llm_not_configured' || detail === 'llm_key_required')) {
      error.value = KEY_REQUIRED_MESSAGE
      showKeyPanel('还没接入模型密钥。配好之后就能继续这段对话。')
    } else if (e?.response?.status === 502 && kind === 'key_invalid') {
      error.value = '你的密钥被模型服务拒绝了，去设置里换一个再试；这句话没有计入记录。'
      showKeyPanel('你的密钥被模型服务拒绝了，换一个再继续。这句话没有计入记录。')
    } else {
      error.value = '发送失败：' + (detail || e.message)
    }
    return false
  } finally {
    sending.value = false
    streaming.value = false
    streamAbort = null
  }
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
  const ok = await send(text, audio, mode, blobPromise)
  if (!ok) return
  manualText.value = ''
  recognizedText.value = ''
  pendingAudio = null
  pendingBlob = null
  manualOpen.value = false
  nextTick(() => manualBtn.value?.focus())
}

function onManualKeydown(event) {
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

async function finish() {
  finishing.value = true
  error.value = ''
  try {
    await api.post(`/sessions/${session.sessionId}/finish`)
    router.push(`/report/${session.sessionId}`)
  } catch (e) {
    confirmingFinish.value = false
    error.value = '生成报告失败：' + (e?.response?.data?.detail || e.message)
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

    <main v-if="!blocked" ref="chatEl" class="sp-shell-narrow flex-1 space-y-4 overflow-y-auto pb-6 pt-8">
      <div
        v-for="(t, i) in session.turns"
        :key="i"
        :class="t.role === 'ai' ? 'flex items-end justify-start gap-2.5' : 'flex justify-end'"
        class="animate-rise"
      >
        <span v-if="t.role === 'ai'" class="mb-0.5 hidden shrink-0 sm:inline-flex" aria-hidden="true"><BrandLogo :size="28" /></span>
        <div
          :class="
            t.role === 'ai'
              ? 'rounded-[1.25rem] rounded-bl-md bg-white text-ink ring-1 ring-line/80'
              : 'rounded-[1.25rem] rounded-br-md bg-brand-600 text-white'
          "
          class="max-w-[82%] px-4 py-3 text-[15px] leading-7 shadow-soft"
        >
          <span
            v-if="t.role === 'user'"
            class="mb-1 inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-white/90"
          >
            <svg v-if="t.mode === 'voice'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
              <rect x="9" y="2.8" width="6" height="11" rx="3" />
              <path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0" />
              <path d="M12 17.8v3.4" />
            </svg>
            <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
            {{ t.mode === 'voice' ? '录音' : '打字' }}
          </span>
          <button
            v-if="t.role === 'user' && t.blob"
            class="mb-1 ml-1 inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-medium text-white/90 transition hover:bg-white/25"
            :aria-label="playingIndex === i ? '停止回放' : '回放我的录音'"
            @click="togglePlayback(t, i)"
          >
            <svg v-if="playingIndex === i" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="1.5" />
            </svg>
            <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M8 5.5v13l10.5-6.5L8 5.5Z" />
            </svg>
            {{ playingIndex === i ? '停止' : '回放' }}
          </button>
          {{ t.content }}
          <span
            v-if="t.streaming"
            class="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-brand-300"
            aria-hidden="true"
          ></span>
          <button
            v-if="t.role === 'ai' && !t.streaming"
            class="ml-1.5 inline-flex h-6 w-6 items-center justify-center rounded-md text-brand-600 transition hover:bg-brand-50"
            aria-label="朗读这句"
            @click="speakSmart(t.content, { rate: speechRate })"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 9.5h3.2L12 5.6v12.8L7.2 14.5H4a.8.8 0 0 1-.8-.8v-3.4a.8.8 0 0 1 .8-.8Z" />
              <path d="M16 9.2a4 4 0 0 1 0 5.6" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="sending && !streaming" class="flex items-end justify-start gap-2.5">
        <span class="mb-0.5 hidden shrink-0 sm:inline-flex" aria-hidden="true"><BrandLogo :size="28" /></span>
        <div class="flex items-center gap-1 rounded-[1.25rem] rounded-bl-md bg-white px-4 py-3.5 ring-1 ring-line/80">
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300 [animation-delay:-0.2s]"></span>
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300 [animation-delay:-0.1s]"></span>
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300"></span>
        </div>
      </div>

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
        text="点下面的麦克风说一句英文，说不出来可以「手动输入」或看「三种说法」。"
      />
    </main>

    <footer v-if="!blocked" class="sticky bottom-0 z-10 bg-gradient-to-t from-canvas via-canvas/95 to-canvas/0 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4">
      <div class="sp-shell-narrow">
      <div class="space-y-3 rounded-card bg-white/95 p-4 shadow-dock ring-1 ring-line/80 backdrop-blur sm:p-5">
        <p v-if="!manualOpen" class="text-center text-[11px] text-ink-mute">{{ progressHint }}</p>

        <p v-if="error" class="sp-alert-error">{{ error }}</p>

        <div
          v-if="canFinish && !confirmingFinish"
          class="rounded-xl bg-brand-50 px-3.5 py-2 text-xs text-brand-700 ring-1 ring-brand-100"
        >
          已经聊了几轮，可以点右下「结束并出报告」看评分了。
        </div>

        <div
          v-if="confirmingFinish"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800 ring-1 ring-amber-100"
        >
          <span>生成报告后这次对话就结束了，确定吗？</span>
          <div class="flex gap-2">
            <button class="sp-btn-primary py-1.5" :disabled="finishing" @click="finish">
              {{ finishing ? '生成中…' : '确认生成' }}
            </button>
            <button class="sp-btn-ghost py-1.5" @click="confirmingFinish = false">继续聊</button>
          </div>
        </div>

        <div v-if="framesOpen" class="rounded-xl bg-canvas p-3 ring-1 ring-line">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-ink-soft">三种说法 · 用提示不扣分</span>
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

        <div v-if="manualOpen" class="space-y-2">
          <div class="min-h-[26px]">
            <div v-if="hintVisible" class="flex flex-wrap items-center gap-1.5">
              <span class="text-xs text-ink-mute">不知道怎么说？试试这些用法：</span>
              <button
                v-for="f in hintFrames"
                :key="f.en"
                class="sp-chip-line transition hover:bg-brand-50"
                @click="useHintFrame(f)"
              >
                {{ f.en }}
              </button>
            </div>
          </div>
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
            <span class="text-[11px] text-ink-mute">收起不会丢掉你写的内容。</span>
            <button v-if="manualText" class="text-[11px] text-danger hover:underline" @click="discardManual">清空草稿</button>
          </div>
        </div>

        <div v-else class="flex items-center justify-between gap-3">
          <div class="flex flex-col gap-1.5">
            <button ref="manualBtn" class="sp-btn-secondary" :disabled="sending" @click="openManual">手动输入</button>
            <button class="sp-btn-ghost !px-2 !py-1 text-[11px]" :disabled="sending" @click="toggleFrames">
              三种说法
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
              {{ listening ? `录音中 ${elapsedText}` : sending ? '正在回复…' : '点一下说话' }}
            </span>
          </div>

          <button class="sp-btn bg-brand-700 text-white shadow-soft hover:bg-brand-800" :disabled="finishing || sending" @click="requestFinish">
            {{ finishing ? '生成中…' : '结束并出报告' }}
          </button>
        </div>
      </div>
      </div>
    </footer>
  </div>
</template>
