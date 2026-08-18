import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
/// <reference types="vitest/config" />

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    setupFiles: ['./src/test/setup.ts'],
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // PyWebView 用 file:// 协议加载,绝对路径 /assets/... 会被解析到
    // 文件系统根目录(/assets) 而非 index.html 同级目录,导致 JS/CSS 404 → 空白。
    // 永远用相对路径,打包脚本不再需要 sed 修复。
    // 关联: docs/superpowers/specs/2026-08-17-launcher-ui-baseurl-pywebview-design.md
    base: './',
  },
})
