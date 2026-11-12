import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'sp_llm'
// 报告口径偏好单独存：报告页要先用本地值渲染，再被服务端覆盖（规格 B7）
const SCALE_KEY = 'speakpal.reportScale'
const CET_VIEW_KEY = 'speakpal.reportCetView'
const SCALE_IDS = ['ielts', 'cefr', 'toefl', 'duolingo', 'cet']

function readSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function readScale() {
  const saved = localStorage.getItem(SCALE_KEY)
  return SCALE_IDS.includes(saved) ? saved : 'ielts'
}

export const useSettingsStore = defineStore('settings', () => {
  const saved = readSaved()
  const apiKey = ref(saved.api_key || '')
  const baseUrl = ref(saved.base_url || '')
  const model = ref(saved.model || '')

  // 语音合成（可选）：不填就用浏览器内置朗读
  const ttsKey = ref(saved.tts_key || '')
  const ttsBaseUrl = ref(saved.tts_base_url || '')
  const ttsModel = ref(saved.tts_model || '')
  const ttsVoice = ref(saved.tts_voice || '')
  // 练习难度偏好：设置页里改，首页/历史/报告开练时统一读这里
  const prefDifficulty = ref(saved.pref_difficulty || '')
  // 新词范围（gaokao/cet4/cet6）：服务端为准，本地只做兜底缓存
  const wordScope = ref(saved.word_scope || '')
  // 报告默认量表（本地先渲染，服务端为准）与四六级展示方式（range | pass，只存本地）
  const reportScale = ref(readScale())
  const reportCetView = ref(localStorage.getItem(CET_VIEW_KEY) === 'pass' ? 'pass' : 'range')
  const cetPassOnly = computed(() => reportCetView.value === 'pass')

  /** 本浏览器是否已配置对话模型密钥 */
  const configured = computed(() => !!apiKey.value.trim())
  /** 本浏览器是否已配置语音合成密钥（可选） */
  const ttsConfigured = computed(() => !!ttsKey.value.trim())

  /** 只显示后四位，界面上不出现完整密钥 */
  function mask(key) {
    const k = (key || '').trim()
    if (!k) return ''
    return k.length <= 4 ? '****' : `****${k.slice(-4)}`
  }
  const masked = computed(() => mask(apiKey.value))
  const ttsMasked = computed(() => mask(ttsKey.value))

  function persist() {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        api_key: apiKey.value.trim(),
        base_url: baseUrl.value.trim(),
        model: model.value.trim(),
        tts_key: ttsKey.value.trim(),
        tts_base_url: ttsBaseUrl.value.trim(),
        tts_model: ttsModel.value.trim(),
        tts_voice: ttsVoice.value.trim(),
        pref_difficulty: prefDifficulty.value,
        word_scope: wordScope.value,
      })
    )
  }

  function save({ apiKey: key, baseUrl: base, model: name }) {
    apiKey.value = key || ''
    baseUrl.value = base || ''
    model.value = name || ''
    persist()
  }

  function saveTts({ key, baseUrl: base, model: name, voice }) {
    ttsKey.value = key || ''
    ttsBaseUrl.value = base || ''
    ttsModel.value = name || ''
    ttsVoice.value = voice || ''
    persist()
  }

  function setPrefDifficulty(value) {
    prefDifficulty.value = value || ''
    persist()
  }

  function setWordScope(value) {
    wordScope.value = value || ''
    persist()
  }

  /** 默认量表：本地先存，报告页/设置页共用；服务端值为准时由调用方覆盖 */
  function setReportScale(value) {
    reportScale.value = SCALE_IDS.includes(value) ? value : 'ielts'
    localStorage.setItem(SCALE_KEY, reportScale.value)
  }

  /** 四六级展示方式：range（分数段）| pass（只看通过水平），只存本地 */
  function setReportCetView(value) {
    reportCetView.value = value === 'pass' ? 'pass' : 'range'
    localStorage.setItem(CET_VIEW_KEY, reportCetView.value)
  }

  function setCetPassOnly(value) {
    setReportCetView(value ? 'pass' : 'range')
  }

  function clear() {
    apiKey.value = ''
    baseUrl.value = ''
    model.value = ''
    ttsKey.value = ''
    ttsBaseUrl.value = ''
    ttsModel.value = ''
    ttsVoice.value = ''
    localStorage.removeItem(STORAGE_KEY)
  }

  /** 每个请求带上自己的密钥，服务端不落库，用完即弃 */
  function headers() {
    const out = {}
    if (apiKey.value.trim()) out['X-LLM-Key'] = apiKey.value.trim()
    if (baseUrl.value.trim()) out['X-LLM-Base-URL'] = baseUrl.value.trim()
    if (model.value.trim()) out['X-LLM-Model'] = model.value.trim()
    if (ttsKey.value.trim()) out['X-TTS-Key'] = ttsKey.value.trim()
    if (ttsBaseUrl.value.trim()) out['X-TTS-Base-URL'] = ttsBaseUrl.value.trim()
    if (ttsModel.value.trim()) out['X-TTS-Model'] = ttsModel.value.trim()
    if (ttsVoice.value.trim()) out['X-TTS-Voice'] = ttsVoice.value.trim()
    return out
  }

  return {
    apiKey,
    baseUrl,
    model,
    ttsKey,
    ttsBaseUrl,
    ttsModel,
    ttsVoice,
    prefDifficulty,
    setPrefDifficulty,
    wordScope,
    setWordScope,
    reportScale,
    setReportScale,
    reportCetView,
    setReportCetView,
    cetPassOnly,
    setCetPassOnly,
    configured,
    ttsConfigured,
    masked,
    ttsMasked,
    save,
    saveTts,
    clear,
    headers,
    persist,
  }
})
