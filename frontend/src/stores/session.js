import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', () => {
  const sessionId = ref(null)
  const scene = ref(null)
  const difficulty = ref('medium')
  const turns = ref([])

  function start(id, sceneObj, diff, opening) {
    sessionId.value = id
    scene.value = sceneObj
    difficulty.value = diff
    turns.value = opening ? [{ role: 'ai', content: opening }] : []
  }

  // 刷新后按服务端记录回填（GET /api/sessions/{id}）
  function restore(id, sceneObj, diff, restoredTurns) {
    sessionId.value = id
    scene.value = sceneObj
    difficulty.value = diff
    turns.value = restoredTurns || []
  }

  function clear() {
    sessionId.value = null
    scene.value = null
    turns.value = []
  }

  return { sessionId, scene, difficulty, turns, start, restore, clear }
})
