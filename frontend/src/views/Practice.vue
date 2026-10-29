<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '../api/client'
import BrandLogo from '../components/BrandLogo.vue'
import { useSessionStore } from '../stores/session'
import { startAudioCapture } from '../utils/audio'
import { KEY_REQUIRED_MESSAGE, llmReady } from '../utils/llmGate'
import { createRecognizer, speak } from '../utils/speech'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const listening = ref(false)
const interim = ref('')
const sending = ref(false)
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

// 识别出来的这句连同录音一起暂存，用户确认发送时才带上；
// 用户改过文字就不带录音了，免得「语速/停顿」指标和文字对不上
const recognizedText = ref('')
let pendingAudio = null

let recognizer = null
let capturer = null
let timer = null
const elapsed = ref(0)

const DIFFICULTY_LABELS = { easy: '简单', medium: '中等', hard: '困难' }
const difficultyLabel = computed(() => DIFFICULTY_LABELS[session.difficulty] || session.difficulty || '—')
const elapsedText = computed(() => `${Math.floor(elapsed.value / 60)}:${String(elapsed.value % 60).padStart(2, '0')}`)
const hasUserTurn = computed(() => session.turns.some((t) => t.role === 'user'))

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

  // 刷进 /practice/:id：先用服务端记录回填，刷新不丢对话
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
        (data.turns || []).map((t) => ({ role: t.role, content: t.content }))
      )
      scrollBottom()
      // 回填时不重播开场白，否则刷新一次就念一遍
      return
    } catch (e) {
      error.value =
        e?.response?.status === 404
          ? '这次对话找不到了（可能已被删除）。回首页重新开始一次吧。'
          : '恢复对话失败：' + (e?.response?.data?.detail || e.message)
      return
    } finally {
      loadingSession.value = false
    }
  }

  const last = session.turns[session.turns.length - 1]
  if (last && last.role === 'ai') speak(last.content)
})

onUnmounted(() => {
  stopTimer()
  if (recognizer) recognizer.abort?.()
})

function scrollBottom() {
  nextTick(() => {
    if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
  })
}

function startTimer() {
  stopTimer()
  elapsed.value = 0
  timer = setInterval(() => {
    elapsed.value += 1
  }, 1000)
}

function stopTimer() {
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

async function send(text, audio = null) {
  if (!text || sending.value) return false
  const gate = await llmReady()
  if (!gate.ok) {
    error.value = KEY_REQUIRED_MESSAGE
    return false
  }
  sending.value = true
  error.value = ''
  const mine = { role: 'user', content: text }
  session.turns.push(mine)
  scrollBottom()
  try {
    const { data } = await api.post(`/sessions/${session.sessionId}/turn`, {
      transcript: text,
      audio,
    })
    session.turns.push({ role: 'ai', content: data.ai_reply })
    if (data.should_finish) canFinish.value = true
    speak(data.ai_reply)
    scrollBottom()
    return true
  } catch (e) {
    // 后端拒收（空转写 / 超长 / 密钥问题）时，把刚乐观插入的这句撤回，别留下假记录
    const i = session.turns.indexOf(mine)
    if (i >= 0) session.turns.splice(i, 1)
    const detail = e?.response?.data?.detail
    const kind = e?.response?.data?.kind
    if (e?.response?.status === 409 && (kind === 'llm_not_configured' || detail === 'llm_key_required')) {
      error.value = KEY_REQUIRED_MESSAGE
    } else if (e?.response?.status === 502 && kind === 'key_invalid') {
      error.value = '你的密钥被模型服务拒绝了，去设置里换一个再试；这句话没有计入记录。'
    } else {
      error.value = '发送失败：' + (detail || e.message)
    }
    return false
  } finally {
    sending.value = false
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
  manualOpen.value = false
  nextTick(() => manualBtn.value?.focus())
}

async function submitManual() {
  const text = manualText.value.trim()
  if (!text || sending.value) return
  const audio = text === recognizedText.value ? pendingAudio : null
  const ok = await send(text, audio)
  if (!ok) return
  manualText.value = ''
  recognizedText.value = ''
  pendingAudio = null
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
    <header class="sp-header">
      <div class="sp-shell flex items-center justify-between py-2.5">
        <div class="flex min-w-0 items-center gap-2.5">
          <router-link to="/" aria-label="返回首页">
            <BrandLogo :size="28" />
          </router-link>
          <div class="min-w-0">
            <div class="truncate text-sm font-semibold text-ink">{{ session.scene?.name || '练习' }}</div>
            <div class="mt-0.5 flex items-center gap-1.5">
              <span class="sp-chip-brand">难度 {{ difficultyLabel }}</span>
            </div>
          </div>
        </div>
        <button class="sp-btn-ghost" @click="router.push('/')">返回首页</button>
      </div>
    </header>

    <main ref="chatEl" class="sp-shell flex-1 space-y-3 overflow-y-auto py-6">
      <div
        v-for="(t, i) in session.turns"
        :key="i"
        :class="t.role === 'ai' ? 'flex justify-start' : 'flex justify-end'"
      >
        <div
          :class="
            t.role === 'ai'
              ? 'rounded-2xl rounded-tl-md bg-white text-ink ring-1 ring-line'
              : 'rounded-2xl rounded-tr-md bg-brand-600 text-white'
          "
          class="max-w-[80%] px-4 py-2.5 text-sm leading-6 shadow-sm"
        >
          {{ t.content }}
          <button
            v-if="t.role === 'ai'"
            class="ml-1.5 inline-flex h-6 w-6 items-center justify-center rounded-md text-brand-600 transition hover:bg-brand-50"
            aria-label="朗读这句"
            @click="speak(t.content)"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 9.5h3.2L12 5.6v12.8L7.2 14.5H4a.8.8 0 0 1-.8-.8v-3.4a.8.8 0 0 1 .8-.8Z" />
              <path d="M16 9.2a4 4 0 0 1 0 5.6" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="sending" class="flex justify-start">
        <div class="flex items-center gap-1 rounded-2xl rounded-tl-md bg-white px-4 py-3 ring-1 ring-line">
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300 [animation-delay:-0.2s]"></span>
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300 [animation-delay:-0.1s]"></span>
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300"></span>
        </div>
      </div>

      <div v-if="interim" class="flex justify-end">
        <div class="max-w-[80%] rounded-2xl rounded-tr-md bg-brand-50 px-4 py-2.5 text-sm text-brand-700 ring-1 ring-brand-100">
          {{ interim }}…
        </div>
      </div>

      <p v-if="loadingSession" class="text-center text-xs text-ink-mute">正在恢复这次对话…</p>
      <p v-else-if="!session.turns.length" class="text-center text-xs text-ink-mute">
        点下面的麦克风开口说，或者说不了就点「手动输入」
      </p>
    </main>

    <footer class="border-t border-line bg-white/90 backdrop-blur">
      <div class="sp-shell space-y-3 py-3">
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

        <div v-if="manualOpen" class="space-y-2">
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
          <button ref="manualBtn" class="sp-btn-secondary" :disabled="sending" @click="openManual">手动输入</button>

          <div class="flex flex-col items-center gap-1">
            <button
              ref="micBtn"
              :class="
                listening
                  ? 'sp-mic sp-mic-rec sp-mic-pulse'
                  : 'sp-mic sp-mic-idle'
              "
              :disabled="sending || finishing"
              :aria-label="listening ? '停止录音' : '开始录音'"
              @click="toggleListening"
            >
              <svg v-if="!listening" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="9" y="2.8" width="6" height="11" rx="3" />
                <path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0" />
                <path d="M12 17.8v3.4" />
              </svg>
              <svg v-else width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                <rect x="7" y="7" width="10" height="10" rx="2.4" fill="currentColor" />
              </svg>
            </button>
            <span class="h-4 text-[11px]" :class="listening ? 'font-medium text-ink-soft' : 'text-ink-mute'">
              {{ listening ? `录音中 ${elapsedText}` : sending ? '正在回复…' : '点一下说话' }}
            </span>
          </div>

          <button class="sp-btn-soft" :disabled="finishing || sending" @click="requestFinish">
            {{ finishing ? '生成中…' : '结束并出报告' }}
          </button>
        </div>
      </div>
    </footer>
  </div>
</template>
