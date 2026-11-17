import { ref } from 'vue'
import { defineStore } from 'pinia'

import type { AsrSource, SessionPlan, TurnRole } from '../types/api'

/** 页面里的一条对话（Practice）与恢复出来的历史轮次共用这个形状 */
export interface ChatTurn {
  role: TurnRole
  content: string
  mode?: string
  asrSource?: AsrSource | null
  streaming?: boolean
  pending?: boolean
  aiStatus?: string | null
  flagged?: boolean
  retryable?: boolean
  fading?: boolean
  minHeight?: number
  blob?: Blob | null
}

/** 场景只需要这几个字段：报告页「再来一练」只拿得到 id + name */
export interface SceneLike {
  id: string
  name?: string
  icon?: string
  desc?: string
}

export const useSessionStore = defineStore('session', () => {
  const sessionId = ref<number | null>(null)
  const scene = ref<SceneLike | null>(null)
  const difficulty = ref('medium')
  const turns = ref<ChatTurn[]>([])
  // 本场目标（Agent 的 plan）：建会话时带回，之后每轮由服务端刷新进度
  const plan = ref<SessionPlan | null>(null)

  function start(id: number, sceneObj: SceneLike, diff: string, opening: string, sessionPlan: SessionPlan | null = null) {
    sessionId.value = id
    scene.value = sceneObj
    difficulty.value = diff
    turns.value = opening ? [{ role: 'ai', content: opening }] : []
    plan.value = sessionPlan || null
  }

  // 刷新后按服务端记录回填（GET /api/sessions/{id}）
  function restore(id: number, sceneObj: SceneLike, diff: string, restoredTurns: ChatTurn[], sessionPlan: SessionPlan | null = null) {
    sessionId.value = id
    scene.value = sceneObj
    difficulty.value = diff
    turns.value = restoredTurns || []
    plan.value = sessionPlan || null
  }

  // 每轮作答后服务端会带回最新进度（达成 / 还缺）
  function setPlan(sessionPlan: SessionPlan | null) {
    if (sessionPlan) plan.value = sessionPlan
  }

  function clear() {
    sessionId.value = null
    scene.value = null
    turns.value = []
    plan.value = null
  }

  return { sessionId, scene, difficulty, turns, plan, start, restore, setPlan, clear }
})
