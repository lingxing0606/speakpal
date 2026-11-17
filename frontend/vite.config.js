import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: { vendor: ['vue', 'vue-router', 'pinia', 'axios'] },
        // 共享的 TS SFC 会把内部模块后缀（.vue_vue_type_script_setup_true_lang）带进 chunk 名，
        // 只保留 .vue 之前的组件名，产物名与迁移前一致
        chunkFileNames: (chunk) => `assets/${chunk.name.replace(/\.vue.*$/, '')}-[hash].js`,
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
