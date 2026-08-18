import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
/// <reference types="vitest/config" />

export default defineConfig({
  envDir: '..',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    exclude: ['src/**/__tests__/**', 'node_modules/**'],
    setupFiles: ['./src/test/setup.ts'],
  },
  build: {
    // 业务前端通过 http://127.0.0.1:<web_port>/ 加载,必须用相对路径
    // 否则用户访问 http://127.0.0.1:5177/subpage 时,/assets/... 会解析到根域名失败
    // 关联: docs/superpowers/specs/2026-08-17-launcher-ui-baseurl-pywebview-design.md
    base: './',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          'vendor-http': ['axios'],
          'vendor-element-plus': ['element-plus', '@element-plus/icons-vue'],
          'vendor-echarts': ['echarts', 'zrender'],
        },
      },
      onwarn(warning, warn) {
        if (warning.code === 'INVALID_ANNOTATION' && warning.id?.includes('/node_modules/@vueuse/core/')) {
          return
        }
        warn(warning)
      },
    },
  },
})
