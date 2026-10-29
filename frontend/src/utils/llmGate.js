import api from '../api/client'
import { useSettingsStore } from '../stores/settings'

/** 本浏览器或服务端任一有可用密钥就算「已接入」；都没有就必须先配置 */
export async function llmReady() {
  const settings = useSettingsStore()
  if (settings.configured) return { ok: true }
  try {
    const { data } = await api.get('/config/llm')
    return data?.env_configured ? { ok: true } : { ok: false, reason: 'no_key' }
  } catch {
    // 接口不可用时不要挡住用户，交给后端自己拒绝（后端也会返回 409 llm_not_configured）
    return { ok: true }
  }
}

export const KEY_REQUIRED_MESSAGE =
  '还没接入模型：请到「设置」里填一个 API Key，或用服务端配置的兜底密钥。'
