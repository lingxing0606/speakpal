import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'sp_llm'

function readSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const saved = readSaved()
  const apiKey = ref(saved.api_key || '')
  const baseUrl = ref(saved.base_url || '')
  const model = ref(saved.model || '')

  /** 本浏览器是否已配置密钥 */
  const configured = computed(() => !!apiKey.value.trim())

  /** 只显示后四位，界面上不出现完整密钥 */
  const masked = computed(() => {
    const key = apiKey.value.trim()
    if (!key) return ''
    return key.length <= 4 ? '****' : `****${key.slice(-4)}`
  })

  function persist() {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        api_key: apiKey.value.trim(),
        base_url: baseUrl.value.trim(),
        model: model.value.trim(),
      })
    )
  }

  function save({ apiKey: key, baseUrl: base, model: name }) {
    apiKey.value = key || ''
    baseUrl.value = base || ''
    model.value = name || ''
    persist()
  }

  function clear() {
    apiKey.value = ''
    baseUrl.value = ''
    model.value = ''
    localStorage.removeItem(STORAGE_KEY)
  }

  /** 每个请求带上自己的密钥，服务端不落库，用完即弃 */
  function headers() {
    const out = {}
    if (apiKey.value.trim()) out['X-LLM-Key'] = apiKey.value.trim()
    if (baseUrl.value.trim()) out['X-LLM-Base-URL'] = baseUrl.value.trim()
    if (model.value.trim()) out['X-LLM-Model'] = model.value.trim()
    return out
  }

  return { apiKey, baseUrl, model, configured, masked, save, clear, headers, persist }
})
