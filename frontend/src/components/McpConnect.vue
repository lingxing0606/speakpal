<script setup lang="ts">
import { computed, ref } from 'vue'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const showToken = ref(false)
const tip = ref('')

const PLACEHOLDER = '<点「显示令牌」后复制>'

/** 本机仓库路径客户端无法得知，配置里用占位路径，页面提示替换。 */
const config = computed(() =>
  JSON.stringify(
    {
      mcpServers: {
        speakpal: {
          command: 'C:\\path\\to\\speakpal\\backend\\.venv\\Scripts\\python.exe',
          args: ['C:\\path\\to\\speakpal\\backend\\mcp_server.py'],
          env: {
            SPEAKPAL_API: `${window.location.protocol}//${window.location.hostname}:8000`,
            SPEAKPAL_TOKEN: showToken.value ? auth.token || '' : PLACEHOLDER,
          },
        },
      },
    },
    null,
    2
  )
)

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // 非安全上下文没有 clipboard API：退回临时 textarea + execCommand
    try {
      const el = document.createElement('textarea')
      el.value = text
      el.setAttribute('readonly', '')
      el.style.position = 'fixed'
      el.style.opacity = '0'
      document.body.appendChild(el)
      el.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(el)
      return ok
    } catch {
      return false
    }
  }
}

async function copyConfig() {
  tip.value = ''
  if (!showToken.value) {
    tip.value = '先点「显示令牌」，复制出去的配置里才会带上令牌'
    return
  }
  tip.value = (await copyText(config.value)) ? '配置已复制，粘贴到客户端配置文件即可' : '复制失败，请手动选中配置复制'
}

async function copyToken() {
  tip.value = (await copyText(auth.token || '')) ? '令牌已复制' : '复制失败，请手动选中令牌复制'
}
</script>

<template>
  <section id="mcp" class="sp-card scroll-mt-24 p-6 sm:p-7">
    <h2 class="sp-section-title">连接 AI 助手（MCP）</h2>
    <p class="mt-1 text-xs leading-5 text-ink-soft">
      在 Claude Desktop、Cursor 等支持 MCP 的客户端里直接问「我今天该复习什么」「我最近总犯什么错」，
      也能让它把单词加进生词本、帮你记笔记。助手通过下面的配置连到本机后端，只访问你登录后的数据。
    </p>
    <p class="mt-1 text-xs leading-5 text-ink-mute">
      Claude Desktop 打开「设置 → Developer → Edit Config」，把这段合并进配置文件的
      <code>mcpServers</code> 后重启客户端。命令和参数里的路径换成你仓库的绝对路径；后端端口变了就同步改
      <code>SPEAKPAL_API</code>。
    </p>

    <div class="mt-4 space-y-3">
      <pre class="max-h-72 overflow-auto rounded-xl bg-paper p-3 font-mono text-[11px] leading-5 text-ink-soft ring-1 ring-line/70">{{ config }}</pre>
      <div class="flex flex-wrap items-center gap-2">
        <button class="sp-btn-secondary" @click="copyConfig">复制配置</button>
        <button v-if="!showToken" class="sp-btn-ghost text-brand-700" @click="showToken = true; tip = ''">
          显示令牌
        </button>
        <template v-else>
          <button class="sp-btn-ghost" @click="copyToken">复制令牌</button>
          <button class="sp-btn-ghost" @click="showToken = false; tip = ''">隐藏令牌</button>
        </template>
      </div>
      <p class="text-[11px] leading-5 text-ink-mute">
        当前令牌：<code>{{ showToken ? auth.token || '未登录' : '••••••' }}</code>
      </p>
      <p class="text-[11px] leading-5 text-ink-mute">
        令牌等同登录态：7 天有效，修改密码后立即失效；只写在本机客户端的配置里，不要发给别人。
      </p>
      <p v-if="tip" class="text-xs" :class="tip.includes('失败') || tip.startsWith('先点') ? 'text-ink-soft' : 'text-good'">
        {{ tip }}
      </p>
    </div>
  </section>
</template>
