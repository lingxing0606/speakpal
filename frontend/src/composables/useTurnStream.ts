// 一轮作答的流式收发：发送瞬间插入 pending 的 AI 气泡（三点），首个 delta 在同一个气泡里原地换字；
// delta 先进缓冲、按 rAF 合并后再写进响应式状态；支持停止（保留已收文字）与失败重试（替换原气泡）。
import { ref } from 'vue'

import { streamTurn } from '../api/stream'
import type { TurnIn, TurnOut } from '../types/api'

interface Turn {
  role: 'ai' | 'user'
  content: string
  mode?: string
  asrSource?: string | null
  streaming?: boolean
  pending?: boolean
  aiStatus?: string | null
  flagged?: boolean
  retryable?: boolean
  fading?: boolean
  minHeight?: number
  blob?: unknown
}

interface ApiError {
  name?: string
  message?: string
  response?: { status?: number; data?: { detail?: string; kind?: string } }
}

interface SessionLike {
  sessionId: number | string
  turns: Turn[]
}

interface Request {
  text: string
  audio: unknown
  mode: 'voice' | 'typed'
  blobPromise: Promise<Blob | null> | null
  asrSource: 'cloud' | 'browser' | null
  userRef: Turn
  aiRef: Turn
}

export interface TurnStreamHooks {
  /** 开始发送：清错误、收起提示卡 */
  onSendStart?: () => void
  /** 收到一段 delta（已合并进气泡） */
  onDelta?: (piece: string) => void
  /** 成功拿到 done：目标进度 / 提示预取 / 朗读 / 存录音都在这里做 */
  onDone?: (data: TurnOut, ctx: { mineRef: Turn; blobPromise: Promise<Blob | null> | null }) => void
  /** 这一轮用的是预设追问 */
  onDegraded?: (data: TurnOut) => void
  /** 密钥问题：交给页面弹密钥面板 */
  onKeyError?: (info: { status: number; kind: string; detail?: string }) => void
  /** 其它失败 */
  onFailure?: (message: string) => void
  /** 主动中断 / 离开页面：不提示 */
  onAborted?: () => void
  /** 重试开始：清掉上一次的「已中断」与重试按钮 */
  onRetryStart?: () => void
}

const THINKING_TICK_MS = 200

export function useTurnStream({ session, scrollBottom, ...hooks }: TurnStreamHooks & { session: SessionLike; scrollBottom: () => void }) {
  const sending = ref(false)
  // 首个 delta 之后：此时才显示「停止」胶囊
  const streaming = ref(false)
  // 从发送到现在的毫秒数（思考态文案用）
  const thinkingMs = ref(0)

  let thinkingTimer: ReturnType<typeof setInterval> | null = null
  let streamAbort: AbortController | null = null
  let raf = 0
  let buffer = ''
  let stoppedByUser = false
  // 只有最后一次请求可重试：发新消息后旧的「已中断」气泡转静态
  let lastRequest: Request | null = null

  function startThinking() {
    thinkingMs.value = 0
    stopThinking()
    thinkingTimer = setInterval(() => {
      thinkingMs.value += THINKING_TICK_MS
    }, THINKING_TICK_MS)
  }

  function stopThinking() {
    if (thinkingTimer) {
      clearInterval(thinkingTimer)
      thinkingTimer = null
    }
  }

  function flush(aiRef: Turn) {
    if (!buffer) return
    aiRef.content += buffer
    buffer = ''
    scrollBottom()
  }

  function scheduleFlush(aiRef: Turn) {
    if (raf) return
    raf = requestAnimationFrame(() => {
      raf = 0
      flush(aiRef)
    })
  }

  async function runTurn(req: Request): Promise<TurnOut> {
    const { aiRef } = req
    stoppedByUser = false
    streamAbort = new AbortController()
    startThinking()
    let first = true
    const data = await streamTurn(
      session.sessionId,
      { transcript: req.text, audio: req.audio, input_mode: req.mode, asr_source: req.asrSource } as unknown as TurnIn,
      {
        signal: streamAbort.signal,
        onDelta(piece) {
          if (!piece) return
          if (first) {
            first = false
            aiRef.pending = false
            aiRef.streaming = true
            streaming.value = true
            stopThinking()
          }
          buffer += piece
          scheduleFlush(aiRef)
        },
      }
    )
    return data
  }

  function applyDone(data: TurnOut, aiRef: Turn) {
    if (raf) {
      cancelAnimationFrame(raf)
      raf = 0
    }
    buffer = ''
    aiRef.content = data.ai_reply
    aiRef.pending = false
    aiRef.streaming = false
    aiRef.minHeight = 0
    aiRef.retryable = false
    aiRef.flagged = !!data.flagged
    aiRef.aiStatus = data.replaced ? 'replaced' : data.degraded ? 'degraded' : null
  }

  async function send(
    text: string,
    audio: unknown = null,
    mode: 'voice' | 'typed' = 'typed',
    blobPromise: Promise<Blob | null> | null = null,
    asrSource: 'cloud' | 'browser' | null = null
  ): Promise<boolean> {
    if (!text || sending.value) return false
    sending.value = true
    hooks.onSendStart?.()
    const mine: Turn = { role: 'user', content: text, mode, asrSource: mode === 'voice' ? asrSource : null }
    session.turns.push(mine)
    // 拿响应式代理（不是原对象），之后挂录音才会刷新界面
    const mineRef = session.turns[session.turns.length - 1]
    // 发送瞬间就把 AI 气泡插进去：三点画在气泡内容位，首字原地替换、高度不变
    session.turns.push({ role: 'ai', content: '', pending: true })
    const aiRef = session.turns[session.turns.length - 1]
    scrollBottom()
    const req: Request = { text, audio, mode, blobPromise, asrSource, userRef: mineRef, aiRef }
    lastRequest = req
    try {
      const data = await runTurn(req)
      applyDone(data, aiRef)
      // 服务端最终采用的转写来源（用户改过文字时它不会带来源）
      mineRef.asrSource = mode === 'voice' ? data.asr_source || null : null
      // 模型这轮没回上来，后端给的是预设追问：明说，别让人以为 AI 在正常聊
      if (data.degraded) hooks.onDegraded?.(data)
      hooks.onDone?.(data, { mineRef, blobPromise })
      return true
    } catch (e) {
      const err = e as ApiError
      // 离开页面导致的中断：这一轮服务端没记录，静默撤掉
      if (err?.name === 'AbortError') {
        if (stoppedByUser) {
          // 用户主动停：保留已收到的文字，标「已停止」，不提供重试
          if (raf) {
            cancelAnimationFrame(raf)
            raf = 0
          }
          aiRef.content += buffer
          buffer = ''
          aiRef.pending = false
          aiRef.streaming = false
          aiRef.aiStatus = 'stopped'
          aiRef.retryable = false
          return false
        }
        const j = session.turns.indexOf(aiRef)
        if (j >= 0) session.turns.splice(j, 1)
        const i = session.turns.indexOf(mine)
        if (i >= 0) session.turns.splice(i, 1)
        hooks.onAborted?.()
        return false
      }
      if (raf) {
        cancelAnimationFrame(raf)
        raf = 0
      }
      aiRef.content += buffer
      buffer = ''
      aiRef.pending = false
      aiRef.streaming = false
      aiRef.aiStatus = 'interrupted'
      const detail = err?.response?.data?.detail
      const kind = err?.response?.data?.kind
      if (err?.response?.status === 409 && (kind === 'llm_not_configured' || detail === 'llm_key_required')) {
        aiRef.retryable = false
        hooks.onKeyError?.({ status: 409, kind: 'llm_not_configured', detail })
      } else if (err?.response?.status === 502 && kind === 'key_invalid') {
        aiRef.retryable = false
        hooks.onKeyError?.({ status: 502, kind: 'key_invalid', detail })
      } else {
        // 真失败：给重试入口（重发同一句，不新增用户气泡）
        aiRef.retryable = true
        hooks.onFailure?.(detail || err?.message || '')
      }
      return false
    } finally {
      sending.value = false
      streaming.value = false
      stopThinking()
      streamAbort = null
    }
  }

  /** 重试：沿用原 transcript/audio，替换这条 AI 气泡，不新增用户气泡 */
  async function retry(turn: Turn): Promise<boolean> {
    if (sending.value || !lastRequest || lastRequest.aiRef !== turn) return false
    const req = lastRequest
    sending.value = true
    hooks.onRetryStart?.()
    turn.aiStatus = null
    turn.retryable = false
    turn.content = ''
    turn.fading = false
    turn.pending = true
    try {
      const data = await runTurn(req)
      applyDone(data, turn)
      hooks.onDone?.(data, { mineRef: req.userRef, blobPromise: req.blobPromise })
      return true
    } catch (e) {
      const err = e as ApiError
      turn.pending = false
      turn.streaming = false
      if (err?.name === 'AbortError' && stoppedByUser) {
        turn.aiStatus = 'stopped'
        turn.retryable = false
        return false
      }
      turn.aiStatus = 'interrupted'
      turn.retryable = true
      hooks.onFailure?.('重试没有成功')
      return false
    } finally {
      sending.value = false
      streaming.value = false
      stopThinking()
      streamAbort = null
    }
  }

  /** 用户点「停止」：即时断开，保留已收文字（这一轮服务端不会记录） */
  function stop() {
    if (!streamAbort) return
    stoppedByUser = true
    streamAbort.abort()
  }

  /** 离开页面：静默断开，不标状态 */
  function abort() {
    streamAbort?.abort()
  }

  return { sending, streaming, thinkingMs, send, retry, stop, abort }
}
