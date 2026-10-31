import { useSettingsStore } from '../stores/settings'

/** 只认本浏览器里填的密钥：服务端不再提供兜底，没有就必须先配置 */
export async function llmReady() {
  const settings = useSettingsStore()
  return settings.configured ? { ok: true } : { ok: false, reason: 'no_key' }
}

export const KEY_REQUIRED_MESSAGE = '还没接入模型：请到「设置」里填一个 API Key。'
