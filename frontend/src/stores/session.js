import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', () => {
  const sessionId = ref(null)
  const scene = ref(null)
  const difficulty = ref('medium')
  const turns = ref([])
  // 本场目标（Agent 的 plan）：建会话时带回，之后每轮由服务端刷新进度
  const plan = ref(null)

  function start(id, sceneObj, diff, opening, sessionPlan = null) {
    sessionId.value = id
    scene.value = sceneObj
    difficulty.value = diff
    turns.value = opening ? [{ role: 'ai', content: opening }] : []
    plan.value = sessionPlan || null
  }

  // 刷新后按服务端记录回填（GET /api/sessions/{id}）
  function restore(id, sceneObj, diff, restoredTurns, sessionPlan = null) {
    sessionId.value = id
    scene.value = sceneObj
    difficulty.value = diff
    turns.value = restoredTurns || []
    plan.value = sessionPlan || null
  }

  // 每轮作答后服务端会带回最新进度（达成 / 还缺）
  function setPlan(sessionPlan) {
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
