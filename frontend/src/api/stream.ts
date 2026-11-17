// 对话流式输出：POST /api/sessions/{id}/turn/stream，按 SSE 逐段收 AI 回复。
// 浏览器自带的 EventSource 只能 GET、不能带请求头，这里用 fetch + ReadableStream 自己解析。
import api from './client'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import type { AgentTraceStep, ReportOut, TurnIn, TurnOut } from '../types/api'

/** 一条 SSE 事件；data 是 JSON.parse 的结果，按事件名各自断言 */
interface SseEvent {
  event: string
  data: unknown
}

/** 做成 axios 错误的形状，调用方的 e.response.status / data.kind 判断照旧能用 */
interface HttpError extends Error {
  response: { status: number; data: unknown }
}

// 这些状态码说明请求在服务端校验阶段就被拒（什么都没记录），交给 axios 原接口重走一遍：
// 401 要走 axios 拦截器的登出跳转；404/405 是后端还没有流式接口（旧版本）
const FALLBACK_STATUS = new Set([401, 404, 405])

function parseEvent(block: string): SseEvent | null {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  try {
    return { event, data: JSON.parse(data) }
  } catch {
    return null
  }
}

function httpError(status: number, data: unknown): HttpError {
  const detail = (data as { detail?: unknown } | null | undefined)?.detail
  const err = new Error(typeof detail === 'string' ? detail : `HTTP ${status}`) as HttpError
  err.response = { status, data: data || {} }
  return err
}

/** 读取 SSE 响应；onEvent 返回非 undefined 时直接返回该值结束读取。 */
async function readSse<T>(resp: Response, onEvent: (ev: SseEvent) => T | undefined): Promise<T | undefined> {
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let cut
    while ((cut = buffer.indexOf('\n\n')) >= 0) {
      const ev = parseEvent(buffer.slice(0, cut))
      buffer = buffer.slice(cut + 2)
      if (!ev) continue
      const result = onEvent(ev)
      if (result !== undefined) return result
    }
  }
  return undefined
}

export interface TurnStreamHandlers {
  onDelta?: (text: string) => void
  signal?: AbortSignal
}

/**
 * 提交一轮作答并流式接收回复。onDelta(text) 每收到一段调用一次。
 * 成功返回与 /turn 相同的 TurnOut；失败抛错（这一轮服务端没有记录）。
 */
export async function streamTurn(
  sessionId: number | string,
  payload: TurnIn,
  { onDelta, signal }: TurnStreamHandlers = {}
): Promise<TurnOut> {
  const auth = useAuthStore()
  const settings = useSettingsStore()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
    ...settings.headers(),
  }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`

  const resp = await fetch(`/api/sessions/${sessionId}/turn/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })

  if (!resp.ok) {
    if (FALLBACK_STATUS.has(resp.status)) {
      const { data } = await api.post<TurnOut>(`/sessions/${sessionId}/turn`, payload)
      if (data?.ai_reply) onDelta?.(data.ai_reply)
      return data
    }
    const data = await resp.json().catch(() => null)
    throw httpError(resp.status, data)
  }

  const result = await readSse<TurnOut>(resp, (ev) => {
    if (ev.event === 'delta') {
      onDelta?.((ev.data as { text?: string }).text || '')
      return undefined
    }
    if (ev.event === 'done') return ev.data as TurnOut
    if (ev.event === 'error') throw httpError(500, ev.data)
    return undefined
  })
  if (result !== undefined) return result
  // 连接断在 done 之前：服务端整句收完才落库，这一轮按没发出去处理
  throw httpError(0, { detail: '连接中断，这句没有记录，请重发' })
}

export interface FinishStreamHandlers {
  onStage?: (stage: { name: string }) => void
  onTool?: (entry: AgentTraceStep) => void
  onFallback?: () => void
  signal?: AbortSignal
}

export interface FinishStreamResult {
  report: ReportOut
  fallback: boolean
}

/**
 * 结束练习并流式接收报告生成进度。
 * onStage({name}) 每进入一个阶段调用一次；onTool(traceEntry) 每有一次工具调用调用一次。
 * 成功返回 { report, fallback }；404/405 回落普通 finish（fallback=true），401 交给 axios 拦截器登出。
 */
export async function streamFinish(
  sessionId: number | string,
  { onStage, onTool, onFallback, signal }: FinishStreamHandlers = {}
): Promise<FinishStreamResult> {
  const auth = useAuthStore()
  const settings = useSettingsStore()
  const headers: Record<string, string> = { Accept: 'text/event-stream', ...settings.headers() }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`

  const resp = await fetch(`/api/sessions/${sessionId}/finish/stream`, {
    method: 'POST',
    headers,
    signal,
  })

  if (!resp.ok) {
    if (FALLBACK_STATUS.has(resp.status)) {
      // 旧后端没有流式接口 / 登录失效：先告诉界面切成不确定态，再走普通 finish
      onFallback?.()
      const { data } = await api.post<ReportOut>(`/sessions/${sessionId}/finish`)
      return { report: data, fallback: true }
    }
    const data = await resp.json().catch(() => null)
    throw httpError(resp.status, data)
  }

  const result = await readSse<FinishStreamResult>(resp, (ev) => {
    if (ev.event === 'stage') {
      onStage?.(ev.data as { name: string })
      return undefined
    }
    if (ev.event === 'tool') {
      onTool?.(ev.data as AgentTraceStep)
      return undefined
    }
    if (ev.event === 'done') return { report: ev.data as ReportOut, fallback: false }
    if (ev.event === 'error') throw httpError(500, ev.data)
    return undefined
  })
  if (result !== undefined) return result
  throw httpError(0, { detail: '连接中断，报告可能还没生成完，请重试' })
}
