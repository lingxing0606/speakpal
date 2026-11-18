// 录音 + 转写（服务端 ASR 优先、失败回落浏览器识别）+ 计时/音量，练习页专用。
// 只搬逻辑不改口径：没配 key 就不走云端；云端失败回浏览器结果；两条都空就报「没听到」。
import { computed, getCurrentInstance, onUnmounted, ref } from 'vue'

import api from '../api/client'
import { useSettingsStore } from '../stores/settings'
import { startAudioCapture } from '../utils/audio'
import { createRecognizer } from '../utils/speech'
import { blobToWav } from '../utils/wav'
import type { AudioMeta } from '../types/api'

export interface RecorderResult {
  /** 最终用于填进输入框的文本（云端优先） */
  text: string
  /** 浏览器识别的原文，用来判断用户有没有改过 */
  browserText: string
  /** 这一句的录音元数据与 Blob Promise（发送时才用） */
  audio: AudioMeta | null
  blob: Promise<Blob | null> | null
  asrSource: 'cloud' | 'browser' | null
}

export interface RecorderHandlers {
  onResult?: (result: RecorderResult) => void
  /** 录到了但两句都空 */
  onEmpty?: () => void
  /** 麦克风 / 识别错误，已翻成中文 */
  onError?: (message: string) => void
  /** 开录前清一下上一轮的错误提示 */
  onStart?: () => void
}

// 语音识别错误码翻成用户能懂的话，不把 not-allowed 这种英文码甩到页面上
const SPEECH_ERRORS: Record<string, string> = {
  'not-allowed': '麦克风权限被拒绝了。请在地址栏左侧允许麦克风，或改用「手动输入」。',
  'service-not-allowed': '这个浏览器不允许语音识别，请换 Chrome，或改用「手动输入」。',
  'audio-capture': '没找到可用的麦克风，检查一下设备是否插好或被别的程序占用。',
  network: '语音识别服务连不上网络，过一会儿再试，或改用「手动输入」。',
  'no-speech': '这次没听到声音，再说一遍试试。',
  aborted: '',
}

interface Recognizer {
  start: () => void
  stop: () => void
  abort?: () => void
}

interface Capturer {
  stop: () => AudioMeta | null
  blob: () => Promise<Blob | null>
  level: () => number
}

export function useRecorder({ onResult, onEmpty, onError, onStart }: RecorderHandlers = {}) {
  const settings = useSettingsStore()

  const listening = ref(false)
  const interim = ref('')
  const transcribing = ref(false)
  const elapsed = ref(0)
  // 录音按钮外圈跟着真实音量缩放（0–1）
  const micLevel = ref(0)

  let recognizer: Recognizer | null = null
  let capturer: Capturer | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let levelRaf = 0

  const elapsedText = computed(() => `${Math.floor(elapsed.value / 60)}:${String(elapsed.value % 60).padStart(2, '0')}`)

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

  /** 把这一句的录音送服务端转写；没配 key、格式不支持或上游失败都返回空串，回退浏览器结果 */
  async function transcribeCloud(blobPromise: Promise<Blob | null> | null) {
    try {
      const blob = blobPromise ? await blobPromise : null
      if (!blob) return ''
      const wav = await blobToWav(blob)
      const form = new FormData()
      form.append('file', new File([wav], 'answer.wav', { type: 'audio/wav' }))
      const { data } = await api.post('/asr', form, { timeout: 30000 })
      return String(data?.text || '').trim()
    } catch {
      return ''
    }
  }

  async function startListening() {
    onStart?.()
    recognizer = createRecognizer(
      (text: string) => {
        interim.value = text
      },
      async () => {
        listening.value = false
        stopTimer()
        const browserText = interim.value.trim()
        const audio = capturer ? capturer.stop() : null
        const blob: Promise<Blob | null> | null = capturer ? capturer.blob() : null
        capturer = null
        interim.value = ''
        let asrSource: 'cloud' | 'browser' | null = null
        let text = browserText
        if (settings.canUseLlm && blob) {
          transcribing.value = true
          const cloud = await transcribeCloud(blob)
          transcribing.value = false
          if (cloud) {
            text = cloud
            asrSource = 'cloud'
          }
        }
        if (!text) {
          // 点了麦克风但没出声：必须给反馈，否则用户以为坏了
          onEmpty?.()
          return
        }
        if (!asrSource && browserText) asrSource = 'browser'
        onResult?.({ text, browserText, audio, blob, asrSource })
      },
      (event: { error?: string }) => {
        listening.value = false
        stopTimer()
        if (capturer) {
          capturer.stop()
          capturer = null
        }
        interim.value = ''
        const msg = SPEECH_ERRORS[event?.error || '']
        if (msg) onError?.(msg)
      }
    )
    if (!recognizer) {
      onError?.('当前浏览器不支持语音识别，请用 Chrome，或点「手动输入」。')
      return
    }
    try {
      capturer = await startAudioCapture()
    } catch {
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

  function dispose() {
    stopTimer()
    if (recognizer) recognizer.abort?.()
    if (capturer) {
      capturer.stop()
      capturer = null
    }
  }

  // 页面卸载时收尾（原来写在 Practice 的 onUnmounted 里，跟随 composable 一起走）
  if (getCurrentInstance()) onUnmounted(dispose)

  return {
    listening,
    interim,
    transcribing,
    elapsedText,
    micLevel,
    startListening,
    stopListening,
    toggleListening,
    startTimer,
    stopTimer,
    dispose,
  }
}
