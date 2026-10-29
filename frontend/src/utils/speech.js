import api from '../api/client'
import { useSettingsStore } from '../stores/settings'

let currentAudio = null
// 浏览器没配 key 时也允许试服务端兜底；409 之后本次会话不再重试，避免每条回复白打一次
let serverTtsTried = false
let serverTtsEnv = null

async function serverTtsAvailable() {
  if (serverTtsEnv !== null) return serverTtsEnv
  try {
    const { data } = await api.get('/config/llm')
    serverTtsEnv = !!data?.tts_env_configured
  } catch {
    serverTtsEnv = false
  }
  return serverTtsEnv
}

/** 保存新 key / 改了服务端配置后调用，清掉「本会话不再试」的标记，让新配置立刻生效 */
export function resetTtsProbe() {
  serverTtsTried = false
  serverTtsEnv = null
}

function stopAudio() {
  if (currentAudio) {
    try {
      currentAudio.pause()
    } catch {
      // 忽略
    }
    currentAudio = null
  }
}

/** 浏览器内置朗读（不需要 key，永远可用的兜底） */
export function speak(text, lang = 'en-US', rate = 1) {
  stopAudio()
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = lang
  utter.rate = rate
  window.speechSynthesis.speak(utter)
}

/**
 * 播放服务端返回的音频。返回 false 表示确实放不出来，调用方要回落浏览器朗读。
 */
function playBlob(blob, onFail) {
  try {
    stopAudio()
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    currentAudio = audio
    audio.onended = () => URL.revokeObjectURL(url)
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      onFail && onFail()
    }
    audio.play().catch(() => {
      URL.revokeObjectURL(url)
      onFail && onFail()
    })
    return true
  } catch {
    return false
  }
}

/**
 * 优先用服务端的语音合成，没配或任何一步失败都回落浏览器朗读。
 * 朗读挂掉不能把整个练习带崩，所以这里永远不抛错。
 */
export async function speakSmart(text, { lang = 'en-US', rate = 1 } = {}) {
  if (!text) return
  let settings = null
  try {
    settings = useSettingsStore()
  } catch {
    settings = null
  }

  const hasBrowserKey = !!settings?.ttsConfigured
  // 配了浏览器 key，或服务端有兜底 key，都值得试一次服务端合成
  const mayUseServer = hasBrowserKey || ((await serverTtsAvailable()) && !serverTtsTried)

  if (mayUseServer) {
    try {
      const { data } = await api.post(
        '/tts',
        { text, speed: rate },
        { responseType: 'blob', timeout: 20000 }
      )
      if (data && data.size > 0) {
        let failed = false
        playBlob(data, () => {
          failed = true
          // 拿到字节但播不出来（内容不是音频、编解码不支持）：回落浏览器朗读
          speak(text, lang, rate)
        })
        if (!failed) return
        return
      }
    } catch {
      // 409 没配 key：服务端也没有兜底，本会话不再试
      serverTtsTried = true
    }
  }

  speak(text, lang, rate)
}

export function stopSpeaking() {
  stopAudio()
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

export function createRecognizer(onResult, onEnd, onError) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) return null

  const rec = new SpeechRecognition()
  rec.lang = 'en-US'
  rec.interimResults = true
  rec.continuous = false
  rec.onresult = (event) => {
    let text = ''
    for (let i = 0; i < event.results.length; i += 1) {
      text += event.results[i][0].transcript
    }
    onResult(text)
  }
  rec.onend = () => onEnd()
  rec.onerror = (event) => onError && onError(event)
  return rec
}
