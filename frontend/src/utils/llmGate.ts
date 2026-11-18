import api from '../api/client'
import { useSettingsStore } from '../stores/settings'

export type LlmGateResult = { ok: true } | { ok: false; reason: 'no_key' }

/** 读服务端体验额度（GET /config/llm）；失败当作没有额度，不打扰用户 */
export async function loadDemoQuota(): Promise<void> {
  const settings = useSettingsStore()
  try {
    const { data } = await api.get('/config/llm')
    settings.setDemo(!!data?.demo_available, Number(data?.demo_daily_per_user) || 0, Number(data?.demo_used_today) || 0)
  } catch {
    settings.setDemo(false, 0, 0)
  }
}

/** 本浏览器填了密钥，或服务端开了体验额度，就能用模型 */
export async function llmReady(): Promise<LlmGateResult> {
  const settings = useSettingsStore()
  if (settings.configured) return { ok: true }
  await loadDemoQuota()
  return settings.canUseLlm ? { ok: true } : { ok: false, reason: 'no_key' }
}

export const KEY_REQUIRED_MESSAGE = '还没接入模型：请到「设置」里填一个 API Key。'
