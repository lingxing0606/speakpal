<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import { useSessionStore } from '../stores/session'
import { startAudioCapture } from '../utils/audio'
import { createRecognizer, speak } from '../utils/speech'

const router = useRouter()
const session = useSessionStore()

const listening = ref(false)
const interim = ref('')
const sending = ref(false)
const finishing = ref(false)
const error = ref('')
const chatEl = ref(null)
let recognizer = null
let capturer = null

onMounted(() => {
  if (!session.sessionId) {
    router.push('/')
    return
  }
  const last = session.turns[session.turns.length - 1]
  if (last && last.role === 'ai') speak(last.content)
})

function scrollBottom() {
  nextTick(() => {
    if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
  })
}

async function startListening() {
  error.value = ''
  recognizer = createRecognizer(
    (text) => {
      interim.value = text
    },
    () => {
      listening.value = false
      const text = interim.value.trim()
      const audio = capturer ? capturer.stop() : null
      capturer = null
      interim.value = ''
      if (text) send(text, audio)
    },
    (event) => {
      listening.value = false
      if (capturer) {
        capturer.stop()
        capturer = null
      }
      error.value = '语音识别出错：' + (event?.error || '未知')
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
  recognizer.start()
}

function stopListening() {
  if (recognizer) recognizer.stop()
}

async function send(text, audio = null) {
  if (!text || sending.value) return
  sending.value = true
  session.turns.push({ role: 'user', content: text })
  scrollBottom()
  try {
    const { data } = await api.post(`/sessions/${session.sessionId}/turn`, {
      transcript: text,
      audio,
    })
    session.turns.push({ role: 'ai', content: data.ai_reply })
    speak(data.ai_reply)
    scrollBottom()
  } catch (e) {
    error.value = '发送失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    sending.value = false
  }
}

function manualSend() {
  const text = window.prompt('输入你的回答（英文）')
  if (text && text.trim()) send(text.trim())
}

async function finish() {
  finishing.value = true
  error.value = ''
  try {
    await api.post(`/sessions/${session.sessionId}/finish`)
    router.push(`/report/${session.sessionId}`)
  } catch (e) {
    error.value = '生成报告失败：' + (e?.response?.data?.detail || e.message)
  } finally {
    finishing.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col bg-slate-50">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <div>
          <div class="font-semibold">{{ session.scene?.name || '练习' }}</div>
          <div class="text-xs text-slate-500">难度 {{ session.difficulty }}</div>
        </div>
        <button class="text-sm text-slate-500 hover:text-slate-800" @click="router.push('/')">返回首页</button>
      </div>
    </header>

    <main ref="chatEl" class="mx-auto w-full max-w-3xl flex-1 space-y-3 overflow-y-auto px-4 py-6">
      <div
        v-for="(t, i) in session.turns"
        :key="i"
        :class="t.role === 'ai' ? 'flex justify-start' : 'flex justify-end'"
      >
        <div
          :class="t.role === 'ai' ? 'bg-white ring-1 ring-slate-200' : 'bg-indigo-600 text-white'"
          class="max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-6"
        >
          {{ t.content }}
          <button v-if="t.role === 'ai'" class="ml-2 text-xs text-indigo-500" @click="speak(t.content)">🔊</button>
        </div>
      </div>

      <div v-if="interim" class="flex justify-end">
        <div class="max-w-[80%] rounded-2xl bg-indigo-100 px-4 py-2 text-sm text-indigo-700">{{ interim }}…</div>
      </div>

      <p v-if="error" class="text-sm text-rose-500">{{ error }}</p>
    </main>

    <footer class="border-t border-slate-200 bg-white">
      <div class="mx-auto flex max-w-3xl items-center justify-center gap-4 px-4 py-4">
        <button class="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600" :disabled="sending" @click="manualSend">
          手动输入
        </button>
        <button
          :class="listening ? 'bg-rose-500' : 'bg-indigo-600'"
          class="h-14 w-14 rounded-full text-xl text-white shadow-lg"
          @click="listening ? stopListening() : startListening()"
        >
          {{ listening ? '■' : '🎤' }}
        </button>
        <button class="rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white" :disabled="finishing" @click="finish">
          {{ finishing ? '生成中…' : '结束并出报告' }}
        </button>
      </div>
    </footer>
  </div>
</template>
