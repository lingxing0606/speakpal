// 对话流式输出：POST /api/sessions/{id}/turn/stream，按 SSE 逐段收 AI 回复。
// 浏览器自带的 EventSource 只能 GET、不能带请求头，这里用 fetch + ReadableStream 自己解析。
import api from './client'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'

// 这些状态码说明请求在服务端校验阶段就被拒（什么都没记录），交给 axios 原接口重走一遍：
// 401 要走 axios 拦截器的登出跳转；404/405 是后端还没有流式接口（旧版本）
const FALLBACK_STATUS = new Set([401, 404, 405])

function parseEvent(block) {
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

/** 做成 axios 错误的形状，调用方的 e.response.status / data.kind 判断照旧能用 */
function httpError(status, data) {
  const err = new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${status}`)
  err.response = { status, data: data || {} }
  return err
}

/**
 * 提交一轮作答并流式接收回复。onDelta(text) 每收到一段调用一次。
 * 成功返回与 /turn 相同的 TurnOut；失败抛错（这一轮服务端没有记录）。
 */
export async function streamTurn(sessionId, payload, { onDelta, signal } = {}) {
  const auth = useAuthStore()
  const settings = useSettingsStore()
  const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...settings.headers() }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`

  const resp = await fetch(`/api/sessions/${sessionId}/turn/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })

  if (!resp.ok) {
    if (FALLBACK_STATUS.has(resp.status)) {
      const { data } = await api.post(`/sessions/${sessionId}/turn`, payload)
      if (data?.ai_reply) onDelta?.(data.ai_reply)
      return data
    }
    let data = null
    try {
      data = await resp.json()
    } catch {
      data = null
    }
    throw httpError(resp.status, data)
  }

  const reader = resp.body.getReader()
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
      if (ev.event === 'delta') onDelta?.(ev.data.text || '')
      else if (ev.event === 'done') return ev.data
      else if (ev.event === 'error') throw httpError(500, ev.data)
    }
  }
  // 连接断在 done 之前：服务端整句收完才落库，这一轮按没发出去处理
  throw httpError(0, { detail: '连接中断，这句没有记录，请重发' })
}
