# P4 启动器 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `launcher/ui/` 独立 Vue 项目,遵循 Material Design 3 暗色主题,通过本地状态服务 API 展示/控制 API/Worker/Beat 进程、OpenCLI 连接、OCR 安装,最终产出 `dist/index.html` 供 PyWebView 加载。

**Architecture:** 独立 Vue 3 + Element Plus 项目(和主 `frontend/` 分开,技术栈相同但独立打包)。UI 通过 `window.location.search` 解析 `statusPort` 参数,用 fetch 轮询 `http://127.0.0.1:<statusPort>` 状态服务接口。M3 设计令牌用 CSS 变量定义在 `:root`,所有组件消费变量而非硬编码颜色。

**Tech Stack:** Vue 3.5 + Element Plus 2.9 + @element-plus/icons-vue + Vitest 3 + jsdom + Vite 7 + TypeScript 5.7 + vue-tsc

**Spec:** `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 4.6 (M3 设计) + § 4.3 (状态服务接口) + § 4.7 (PyWebView 窗口)

---

## 文件结构

```
launcher/ui/
├── package.json                    # 独立依赖(和 frontend/ 分开)
├── vite.config.ts                  # Vite + Vitest 配置
├── tsconfig.json                   # TS 配置
├── tsconfig.node.json              # Vite 配置文件的 TS 配置
├── index.html                      # HTML 入口
├── src/
│   ├── main.ts                     # Vue 应用入口
│   ├── App.vue                     # 根组件(布局 + 轮询 + 底部操作栏)
│   ├── App.spec.ts                 # 根组件测试
│   ├── api/
│   │   └── client.ts               # 状态服务 API 客户端
│   ├── design/
│   │   └── tokens.css              # M3 设计令牌 CSS 变量
│   ├── components/
│   │   ├── ServiceStatus.vue       # 服务状态卡片
│   │   ├── ServiceStatus.spec.ts
│   │   ├── OpenCLIPanel.vue        # OpenCLI 连接卡片
│   │   ├── OpenCLIPanel.spec.ts
│   │   ├── OcrPanel.vue            # OCR 增强卡片
│   │   ├── OcrPanel.spec.ts
│   │   ├── LogViewer.vue           # 日志卡片
│   │   └── LogViewer.spec.ts
│   └── test/
│       └── setup.ts                # Vitest 全局 setup
└── dist/                           # 构建产物(PyWebView 加载这里)
    └── index.html
```

---

## 执行策略

9 个任务,按依赖顺序执行:

- **Task 1**: 项目脚手架(package.json/vite/tsconfig/index.html/main.ts/App.vue 骨架)
- **Task 2**: M3 设计令牌(tokens.css)+ design-tokens.spec.ts
- **Task 3**: API 客户端(client.ts)
- **Task 4**: ServiceStatus 组件 + spec
- **Task 5**: OpenCLIPanel 组件 + spec
- **Task 6**: OcrPanel 组件 + spec
- **Task 7**: LogViewer 组件 + spec
- **Task 8**: App 组件整合(轮询 + 布局 + 底部操作栏)+ spec
- **Task 9**: 构建验证(npm run build 产出 dist/index.html)

每个任务用 TDD:先写测试看到失败,再实现看到通过。

---

## Task 1: 项目脚手架

**Files:**
- Create: `launcher/ui/package.json`
- Create: `launcher/ui/vite.config.ts`
- Create: `launcher/ui/tsconfig.json`
- Create: `launcher/ui/tsconfig.node.json`
- Create: `launcher/ui/index.html`
- Create: `launcher/ui/src/main.ts`
- Create: `launcher/ui/src/App.vue`
- Create: `launcher/ui/src/test/setup.ts`
- Create: `launcher/ui/src/App.spec.ts`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "xhs-launcher-ui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@element-plus/icons-vue": "^2.3.2",
    "element-plus": "^2.9.0",
    "vue": "^3.5.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^6.0.0",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^26.0.0",
    "typescript": "^5.7.0",
    "vite": "^7.0.0",
    "vitest": "^3.0.0",
    "vue-tsc": "^3.0.0"
  }
}
```

- [ ] **Step 2: 创建 vite.config.ts**

```typescript
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

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
  },
})
```

- [ ] **Step 3: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.d.ts", "src/**/*.vue"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: 创建 tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>小红书活动信息抓取系统</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 6: 创建 src/test/setup.ts**

```typescript
import { config } from '@vue/test-utils'

// 全局 stub ElMessage 避免组件测试里弹出真实 DOM
config.global.mocks = {
  $message: {
    success: () => {},
    error: () => {},
    warning: () => {},
    info: () => {},
  },
}
```

- [ ] **Step 7: 创建 src/App.vue(骨架,后续 Task 8 填充)**

```vue
<script setup lang="ts">
// 骨架组件,Task 8 填充完整逻辑
</script>

<template>
  <div class="launcher-app" data-test="launcher-app">
    <h1 data-test="app-title">小红书活动信息抓取系统</h1>
  </div>
</template>

<style scoped>
.launcher-app {
  min-height: 100vh;
  background: var(--md-sys-color-background, #121212);
  color: var(--md-sys-color-on-surface, #e6e6e6);
}
</style>
```

- [ ] **Step 8: 创建 src/main.ts**

```typescript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './design/tokens.css'
import App from './App.vue'

createApp(App).use(ElementPlus).mount('#app')
```

- [ ] **Step 9: 创建 src/App.spec.ts(骨架测试,Task 8 扩展)**

```typescript
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App', () => {
  it('renders the app title', () => {
    const wrapper = mount(App)
    expect(wrapper.get('[data-test="app-title"]').text()).toContain('小红书活动信息抓取系统')
  })
})
```

- [ ] **Step 10: 安装依赖并运行骨架测试**

Run: `cd launcher/ui && npm install && npm run test`
Expected: 1 test passed

- [ ] **Step 11: Commit**

```bash
git add launcher/ui/
git commit -m "feat(launcher-ui): scaffold Vue project with Vite + Element Plus"
```

---

## Task 2: M3 设计令牌(tokens.css)+ design-tokens.spec.ts

**Files:**
- Create: `launcher/ui/src/design/tokens.css`
- Create: `launcher/ui/src/__tests__/design-tokens.spec.ts`

**Spec reference:** `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 4.6.2 (颜色) + § 4.6.3 (排版) + § 4.6.6 (间距与圆角)

- [ ] **Step 1: 创建测试 src/__tests__/design-tokens.spec.ts**

```typescript
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const tokensCss = readFileSync(
  resolve(__dirname, '../design/tokens.css'),
  'utf-8',
)

describe('M3 design tokens', () => {
  it('defines M3 dark surface colors', () => {
    expect(tokensCss).toContain('--md-sys-color-background')
    expect(tokensCss).toContain('--md-sys-color-surface')
    expect(tokensCss).toContain('--md-sys-color-surface-variant')
    expect(tokensCss).toContain('--md-sys-color-surface-container-high')
  })

  it('defines M3 on-surface text colors', () => {
    expect(tokensCss).toContain('--md-sys-color-on-surface')
    expect(tokensCss).toContain('--md-sys-color-on-surface-variant')
  })

  it('defines brand primary color (xiaohongshu red)', () => {
    expect(tokensCss).toContain('--md-sys-color-primary')
    expect(tokensCss).toContain('--md-sys-color-on-primary')
    expect(tokensCss).toContain('--md-sys-color-primary-container')
  })

  it('defines semantic state colors', () => {
    expect(tokensCss).toContain('--md-sys-color-success')
    expect(tokensCss).toContain('--md-sys-color-on-success')
    expect(tokensCss).toContain('--md-sys-color-error')
    expect(tokensCss).toContain('--md-sys-color-on-error')
    expect(tokensCss).toContain('--md-sys-color-warning')
    expect(tokensCss).toContain('--md-sys-color-on-warning')
  })

  it('defines M3 elevation shadows', () => {
    expect(tokensCss).toContain('--md-sys-elevation-1')
    expect(tokensCss).toContain('--md-sys-elevation-2')
  })

  it('defines M3 type scale', () => {
    expect(tokensCss).toContain('--md-sys-typescale-headline-medium')
    expect(tokensCss).toContain('--md-sys-typescale-title-large')
    expect(tokensCss).toContain('--md-sys-typescale-title-medium')
    expect(tokensCss).toContain('--md-sys-typescale-body-large')
    expect(tokensCss).toContain('--md-sys-typescale-body-medium')
    expect(tokensCss).toContain('--md-sys-typescale-label-large')
    expect(tokensCss).toContain('--md-sys-typescale-label-medium')
  })

  it('defines M3 spacing on 4dp grid', () => {
    expect(tokensCss).toContain('--md-sys-spacing-1')
    expect(tokensCss).toContain('--md-sys-spacing-2')
    expect(tokensCss).toContain('--md-sys-spacing-4')
    expect(tokensCss).toContain('--md-sys-spacing-8')
  })

  it('defines M3 shape corners', () => {
    expect(tokensCss).toContain('--md-sys-shape-corner-small')
    expect(tokensCss).toContain('--md-sys-shape-corner-medium')
    expect(tokensCss).toContain('--md-sys-shape-corner-large')
  })
})
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd launcher/ui && npm run test -- src/__tests__/design-tokens.spec.ts`
Expected: FAIL (tokens.css 不存在或缺少变量)

- [ ] **Step 3: 创建 src/design/tokens.css**

```css
/* M3 Dark Theme baseline + 品牌色定制
 * 关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 4.6.2-4.6.6
 */
:root {
  /* M3 Dark Surface 层级(深灰而非纯黑,表达 elevation) */
  --md-sys-color-background: #121212;
  --md-sys-color-surface: #1c1c1e;
  --md-sys-color-surface-variant: #2c2c2e;
  --md-sys-color-surface-container-high: #3a3a3c;

  /* M3 On-Surface 文字色 */
  --md-sys-color-on-surface: #e6e6e6;
  --md-sys-color-on-surface-variant: #9b9b9d;

  /* 品牌主色(primary = 小红书红,降饱和度适配暗色) */
  --md-sys-color-primary: #ff5c5c;
  --md-sys-color-on-primary: #ffffff;
  --md-sys-color-primary-container: #4d1a1a;

  /* 状态语义色 */
  --md-sys-color-success: #4ade80;
  --md-sys-color-on-success: #003314;
  --md-sys-color-error: #f87171;
  --md-sys-color-on-error: #4d0000;
  --md-sys-color-warning: #fbbf24;
  --md-sys-color-on-warning: #4d3500;

  /* M3 Elevation 阴影 */
  --md-sys-elevation-1: 0px 1px 2px rgba(0, 0, 0, 0.3), 0px 1px 3px 1px rgba(0, 0, 0, 0.15);
  --md-sys-elevation-2: 0px 2px 6px 2px rgba(0, 0, 0, 0.15), 0px 1px 2px rgba(0, 0, 0, 0.3);

  /* M3 Type Scale */
  --md-sys-typescale-headline-large: 600 28px/36px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-headline-medium: 600 24px/32px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-title-large: 500 20px/28px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-title-medium: 500 16px/24px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-body-large: 400 16px/24px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-body-medium: 400 14px/20px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-label-large: 500 14px/20px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-label-medium: 500 12px/16px 'Inter', 'PingFang SC', sans-serif;

  /* M3 Spacing (4dp 网格) */
  --md-sys-spacing-1: 4px;
  --md-sys-spacing-2: 8px;
  --md-sys-spacing-3: 12px;
  --md-sys-spacing-4: 16px;
  --md-sys-spacing-5: 20px;
  --md-sys-spacing-6: 24px;
  --md-sys-spacing-8: 32px;

  /* M3 Shape (圆角) */
  --md-sys-shape-corner-small: 8px;
  --md-sys-shape-corner-medium: 12px;
  --md-sys-shape-corner-large: 16px;
  --md-sys-shape-corner-full: 9999px;
}

/* 全局基础样式 */
body {
  margin: 0;
  background: var(--md-sys-color-background);
  color: var(--md-sys-color-on-surface);
  font: var(--md-sys-typescale-body-medium);
  -webkit-font-smoothing: antialiased;
}
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd launcher/ui && npm run test -- src/__tests__/design-tokens.spec.ts`
Expected: 8 tests passed

- [ ] **Step 5: Commit**

```bash
git add launcher/ui/src/design/ launcher/ui/src/__tests__/
git commit -m "feat(launcher-ui): add M3 design tokens CSS variables"
```

---

## Task 3: API 客户端(client.ts)

**Files:**
- Create: `launcher/ui/src/api/client.ts`
- Create: `launcher/ui/src/api/client.spec.ts`

**接口契约(来自 launcher/status_server.py):**
- `GET /status` → `{ api: {state, pid}, worker: {state, pid}, beat: {state, pid} }`
- `POST /service/{name}/restart` → `{ ok: bool }`
- `POST /service/all/stop` → `{ ok: bool }`
- `GET /opencli/test` → `{ ok, version, reason, message }`
- `GET /opencli/download-url` → `{ url: string }`
- `GET /ocr/status` → `{ status: 'not_installed'|'installing'|'installed', version: string }`
- `POST /ocr/install` → `{ ok: bool, message: string }`
- `GET /ocr/install-progress` → `{ active: bool, percent: number, message: string, ok?: bool }`
- `POST /ocr/test` → `{ ok: bool, reason?: string, message?: string }`
- `GET /logs/tail?lines=N` → `{ lines: string[] }`

- [ ] **Step 1: 创建测试 src/api/client.spec.ts**

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchStatus,
  restartService,
  stopAll,
  testOpencli,
  getOpencliDownloadUrl,
  getOcrStatus,
  installOcr,
  getOcrInstallProgress,
  testOcr,
  getLogsTail,
  setBaseUrl,
} from './client'

describe('launcher api client', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    setBaseUrl('http://127.0.0.1:9001')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('fetchStatus calls GET /status', async () => {
    const mockData = { api: { state: 'running', pid: 1 }, worker: { state: 'running', pid: 2 }, beat: { state: 'running', pid: 3 } }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as Response)

    const result = await fetchStatus()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/status')
    expect(result).toEqual(mockData)
  })

  it('restartService calls POST /service/{name}/restart', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response)

    const result = await restartService('api')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/service/api/restart', { method: 'POST' })
    expect(result).toEqual({ ok: true })
  })

  it('stopAll calls POST /service/all/stop', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response)

    await stopAll()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/service/all/stop', { method: 'POST' })
  })

  it('testOpencli calls GET /opencli/test', async () => {
    const mockData = { ok: true, version: '1.8.6', reason: '', message: '连接正常' }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as Response)

    const result = await testOpencli()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/opencli/test')
    expect(result).toEqual(mockData)
  })

  it('getOpencliDownloadUrl calls GET /opencli/download-url', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ url: 'https://opencli.info/download' }),
    } as Response)

    const result = await getOpencliDownloadUrl()
    expect(result).toEqual({ url: 'https://opencli.info/download' })
  })

  it('getOcrStatus calls GET /ocr/status', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'not_installed', version: '' }),
    } as Response)

    const result = await getOcrStatus()
    expect(result).toEqual({ status: 'not_installed', version: '' })
  })

  it('installOcr calls POST /ocr/install', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, message: '安装已启动' }),
    } as Response)

    const result = await installOcr()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/ocr/install', { method: 'POST' })
    expect(result).toEqual({ ok: true, message: '安装已启动' })
  })

  it('getOcrInstallProgress calls GET /ocr/install-progress', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ active: false, percent: 0, message: '' }),
    } as Response)

    const result = await getOcrInstallProgress()
    expect(result).toEqual({ active: false, percent: 0, message: '' })
  })

  it('testOcr calls POST /ocr/test', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, text: '测试文字', latency_ms: 123 }),
    } as Response)

    const result = await testOcr()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/ocr/test', { method: 'POST' })
    expect(result).toEqual({ ok: true, text: '测试文字', latency_ms: 123 })
  })

  it('getLogsTail calls GET /logs/tail with lines param', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ lines: ['line1', 'line2'] }),
    } as Response)

    const result = await getLogsTail(50)
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/logs/tail?lines=50')
    expect(result).toEqual({ lines: ['line1', 'line2'] })
  })

  it('throws on fetch error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network error'))
    await expect(fetchStatus()).rejects.toThrow('network error')
  })
})
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd launcher/ui && npm run test -- src/api/client.spec.ts`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 创建 src/api/client.ts**

```typescript
/**
 * 启动器状态服务 API 客户端。
 *
 * baseUrl 从 window.location.search 的 statusPort 参数解析,
 * PyWebView 加载 file:///.../dist/index.html?statusPort=<port> 时传入。
 */

let baseUrl = 'http://127.0.0.1:8001'

export function setBaseUrl(url: string): void {
  baseUrl = url
}

export function getBaseUrl(): string {
  return baseUrl
}

/**
 * 从 window.location.search 解析 statusPort,初始化 baseUrl。
 * 在 main.ts 调用一次即可。
 */
export function initBaseUrlFromLocation(): void {
  if (typeof window === 'undefined') return
  const params = new URLSearchParams(window.location.search)
  const port = params.get('statusPort')
  if (port) {
    baseUrl = `http://127.0.0.1:${port}`
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${baseUrl}${path}`, init)
  return resp.json() as Promise<T>
}

export interface ServiceState {
  state: 'running' | 'stopped' | 'crashed'
  pid: number | null
}

export interface StatusResponse {
  api: ServiceState
  worker: ServiceState
  beat: ServiceState
}

export function fetchStatus(): Promise<StatusResponse> {
  return request<StatusResponse>('/status')
}

export function restartService(name: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/service/${name}/restart`, { method: 'POST' })
}

export function stopAll(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/service/all/stop', { method: 'POST' })
}

export interface OpencliTestResult {
  ok: boolean
  version: string
  reason: string
  message: string
}

export function testOpencli(): Promise<OpencliTestResult> {
  return request<OpencliTestResult>('/opencli/test')
}

export function getOpencliDownloadUrl(): Promise<{ url: string }> {
  return request<{ url: string }>('/opencli/download-url')
}

export interface OcrStatus {
  status: 'not_installed' | 'installing' | 'installed'
  version: string
}

export function getOcrStatus(): Promise<OcrStatus> {
  return request<OcrStatus>('/ocr/status')
}

export function installOcr(): Promise<{ ok: boolean; message: string }> {
  return request<{ ok: boolean; message: string }>('/ocr/install', { method: 'POST' })
}

export interface OcrInstallProgress {
  active: boolean
  percent: number
  message: string
  ok?: boolean
}

export function getOcrInstallProgress(): Promise<OcrInstallProgress> {
  return request<OcrInstallProgress>('/ocr/install-progress')
}

export interface OcrTestResult {
  ok: boolean
  reason?: string
  message?: string
  text?: string
  latency_ms?: number
}

export function testOcr(): Promise<OcrTestResult> {
  return request<OcrTestResult>('/ocr/test', { method: 'POST' })
}

export function getLogsTail(lines = 50): Promise<{ lines: string[] }> {
  return request<{ lines: string[] }>(`/logs/tail?lines=${lines}`)
}
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd launcher/ui && npm run test -- src/api/client.spec.ts`
Expected: 11 tests passed

- [ ] **Step 5: Commit**

```bash
git add launcher/ui/src/api/
git commit -m "feat(launcher-ui): add status server API client"
```

---

## Task 4: ServiceStatus 组件

**Files:**
- Create: `launcher/ui/src/components/ServiceStatus.vue`
- Create: `launcher/ui/src/components/ServiceStatus.spec.ts`

**Props:** `status: StatusResponse`(api/worker/beat 三服务状态)
**Emits:** `restart(name)` / `stop-all`

**UI 行为(来自 spec § 4.6.4 服务状态卡片):**
- 三行:API / Worker / Beat
- 每行:状态圆点(运行中=success 绿 / 停止=on-surface-variant 灰 / 异常=error 红)+ 服务名 + 状态文字 + [重启] 按钮
- 状态文字:running → "运行中 (PID xxx)" / stopped → "已停止" / crashed → "异常退出"

- [ ] **Step 1: 创建测试 src/components/ServiceStatus.spec.ts**

```typescript
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ServiceStatus from './ServiceStatus.vue'
import type { StatusResponse } from '@/api/client'

describe('ServiceStatus', () => {
  const runningStatus: StatusResponse = {
    api: { state: 'running', pid: 1001 },
    worker: { state: 'running', pid: 1002 },
    beat: { state: 'running', pid: 1003 },
  }

  it('renders three service rows', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    const rows = wrapper.findAll('[data-test="service-row"]')
    expect(rows).toHaveLength(3)
  })

  it('shows service names api/worker/beat', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    expect(wrapper.text()).toContain('API')
    expect(wrapper.text()).toContain('Worker')
    expect(wrapper.text()).toContain('Beat')
  })

  it('shows running state with pid', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('1001')
  })

  it('shows stopped state without pid', () => {
    const stoppedStatus: StatusResponse = {
      api: { state: 'stopped', pid: null },
      worker: { state: 'stopped', pid: null },
      beat: { state: 'stopped', pid: null },
    }
    const wrapper = mount(ServiceStatus, { props: { status: stoppedStatus } })
    expect(wrapper.text()).toContain('已停止')
  })

  it('shows crashed state', () => {
    const crashedStatus: StatusResponse = {
      api: { state: 'crashed', pid: null },
      worker: { state: 'running', pid: 1002 },
      beat: { state: 'running', pid: 1003 },
    }
    const wrapper = mount(ServiceStatus, { props: { status: crashedStatus } })
    expect(wrapper.text()).toContain('异常退出')
  })

  it('emits restart event with service name when restart button clicked', async () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    const restartButtons = wrapper.findAll('[data-test="restart-btn"]')
    expect(restartButtons).toHaveLength(3)
    await restartButtons[0].trigger('click')
    expect(wrapper.emitted('restart')).toBeTruthy()
    expect(wrapper.emitted('restart')![0]).toEqual(['api'])
  })

  it('emits stop-all event when stop all button clicked', async () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    await wrapper.get('[data-test="stop-all-btn"]').trigger('click')
    expect(wrapper.emitted('stop-all')).toBeTruthy()
  })

  it('applies success color class to running service dot', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    const dot = wrapper.get('[data-test="dot-api"]')
    expect(dot.classes()).toContain('dot--running')
  })

  it('applies error color class to crashed service dot', () => {
    const crashedStatus: StatusResponse = {
      api: { state: 'crashed', pid: null },
      worker: { state: 'running', pid: 1002 },
      beat: { state: 'running', pid: 1003 },
    }
    const wrapper = mount(ServiceStatus, { props: { status: crashedStatus } })
    const dot = wrapper.get('[data-test="dot-api"]')
    expect(dot.classes()).toContain('dot--crashed')
  })
})
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd launcher/ui && npm run test -- src/components/ServiceStatus.spec.ts`
Expected: FAIL (组件不存在)

- [ ] **Step 3: 创建 src/components/ServiceStatus.vue**

```vue
<script setup lang="ts">
import type { StatusResponse, ServiceState } from '@/api/client'

interface Props {
  status: StatusResponse
}

const props = defineProps<Props>()
const emit = defineEmits<{
  restart: [name: string]
  'stop-all': []
}>()

const services: { key: keyof StatusResponse; label: string }[] = [
  { key: 'api', label: 'API' },
  { key: 'worker', label: 'Worker' },
  { key: 'beat', label: 'Beat' },
]

function stateText(state: ServiceState): string {
  if (state.state === 'running') return `运行中${state.pid ? ' (PID ' + state.pid + ')' : ''}`
  if (state.state === 'crashed') return '异常退出'
  return '已停止'
}
</script>

<template>
  <el-card class="service-status-card" data-test="service-status-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">服务状态</span>
        <el-button size="small" data-test="stop-all-btn" @click="emit('stop-all')">
          停止全部
        </el-button>
      </div>
    </template>

    <div
      v-for="svc in services"
      :key="svc.key"
      class="service-row"
      data-test="service-row"
    >
      <span
        class="dot"
        :class="`dot--${props.status[svc.key].state}`"
        :data-test="`dot-${svc.key}`"
      />
      <span class="service-name">{{ svc.label }}</span>
      <span class="service-state">{{ stateText(props.status[svc.key]) }}</span>
      <el-button
        size="small"
        :data-test="`restart-btn`"
        @click="emit('restart', svc.key)"
      >
        重启
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.service-status-card {
  background: var(--md-sys-color-surface);
  color: var(--md-sys-color-on-surface);
  border: none;
  box-shadow: var(--md-sys-elevation-1);
  border-radius: var(--md-sys-shape-corner-medium);
  margin-bottom: var(--md-sys-spacing-4);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font: var(--md-sys-typescale-title-large);
}

.service-row {
  display: flex;
  align-items: center;
  gap: var(--md-sys-spacing-3);
  padding: var(--md-sys-spacing-2) 0;
  font: var(--md-sys-typescale-body-large);
}

.service-name {
  min-width: 80px;
  font: var(--md-sys-typescale-label-large);
}

.service-state {
  flex: 1;
  color: var(--md-sys-color-on-surface-variant);
  font: var(--md-sys-typescale-body-medium);
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: var(--md-sys-shape-corner-full);
  display: inline-block;
}

.dot--running {
  background: var(--md-sys-color-success);
}

.dot--stopped {
  background: var(--md-sys-color-on-surface-variant);
}

.dot--crashed {
  background: var(--md-sys-color-error);
}
</style>
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd launcher/ui && npm run test -- src/components/ServiceStatus.spec.ts`
Expected: 9 tests passed

- [ ] **Step 5: Commit**

```bash
git add launcher/ui/src/components/ServiceStatus.vue launcher/ui/src/components/ServiceStatus.spec.ts
git commit -m "feat(launcher-ui): add ServiceStatus component"
```

---

## Task 5: OpenCLIPanel 组件

**Files:**
- Create: `launcher/ui/src/components/OpenCLIPanel.vue`
- Create: `launcher/ui/src/components/OpenCLIPanel.spec.ts`

**Props:** `result: OpencliTestResult | null`(测试结果,null=未测试)
**Emits:** `test()` / `download()`

**UI 行为(来自 spec § 4.6.4 OpenCLI 卡片):**
- 标题 "OpenCLI 连接" + 状态 chip(未检测/已连接/未连接)
- [测试连接] 按钮(outlined)+ [下载 OpenCLI] 按钮(filled)
- 测试结果:ok=true → 绿色 ✓ + 版本号;ok=false → 红色 ✗ + message

- [ ] **Step 1: 创建测试 src/components/OpenCLIPanel.spec.ts**

```typescript
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OpenCLIPanel from './OpenCLIPanel.vue'
import type { OpencliTestResult } from '@/api/client'

describe('OpenCLIPanel', () => {
  it('renders title and undetected chip when result is null', () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: false } })
    expect(wrapper.text()).toContain('OpenCLI 连接')
    expect(wrapper.text()).toContain('未检测')
  })

  it('renders success chip and version when result ok', () => {
    const result: OpencliTestResult = { ok: true, version: '1.8.6', reason: '', message: '连接正常' }
    const wrapper = mount(OpenCLIPanel, { props: { result, loading: false } })
    expect(wrapper.text()).toContain('已连接')
    expect(wrapper.text()).toContain('1.8.6')
  })

  it('renders error chip and message when result not ok', () => {
    const result: OpencliTestResult = { ok: false, version: '', reason: 'not_installed', message: '未安装 OpenCLI' }
    const wrapper = mount(OpenCLIPanel, { props: { result, loading: false } })
    expect(wrapper.text()).toContain('未连接')
    expect(wrapper.text()).toContain('未安装 OpenCLI')
  })

  it('emits test event when test button clicked', async () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: false } })
    await wrapper.get('[data-test="test-opencli-btn"]').trigger('click')
    expect(wrapper.emitted('test')).toBeTruthy()
  })

  it('emits download event when download button clicked', async () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: false } })
    await wrapper.get('[data-test="download-opencli-btn"]').trigger('click')
    expect(wrapper.emitted('download')).toBeTruthy()
  })

  it('disables test button when loading', () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: true } })
    const btn = wrapper.get('[data-test="test-opencli-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('shows loading text when loading', () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: true } })
    expect(wrapper.text()).toContain('测试中')
  })
})
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd launcher/ui && npm run test -- src/components/OpenCLIPanel.spec.ts`
Expected: FAIL (组件不存在)

- [ ] **Step 3: 创建 src/components/OpenCLIPanel.vue**

```vue
<script setup lang="ts">
import type { OpencliTestResult } from '@/api/client'

interface Props {
  result: OpencliTestResult | null
  loading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  test: []
  download: []
}>()

function chipType(): 'success' | 'danger' | 'info' {
  if (!props.result) return 'info'
  return props.result.ok ? 'success' : 'danger'
}

function chipText(): string {
  if (props.loading) return '测试中'
  if (!props.result) return '未检测'
  return props.result.ok ? '已连接' : '未连接'
}
</script>

<template>
  <el-card class="opencli-card" data-test="opencli-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">OpenCLI 连接</span>
        <el-tag :type="chipType()" data-test="opencli-chip">{{ chipText() }}</el-tag>
      </div>
    </template>

    <div v-if="result" class="result-area" data-test="opencli-result">
      <p v-if="result.ok" class="result-success">
        ✓ 连接正常<span v-if="result.version"> · 版本 {{ result.version }}</span>
      </p>
      <p v-else class="result-error">
        ✗ {{ result.message }}
      </p>
    </div>

    <div class="actions">
      <el-button
        :disabled="loading"
        data-test="test-opencli-btn"
        @click="emit('test')"
      >
        {{ loading ? '测试中...' : '测试连接' }}
      </el-button>
      <el-button type="primary" data-test="download-opencli-btn" @click="emit('download')">
        下载 OpenCLI
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.opencli-card {
  background: var(--md-sys-color-surface);
  color: var(--md-sys-color-on-surface);
  border: none;
  box-shadow: var(--md-sys-elevation-1);
  border-radius: var(--md-sys-shape-corner-medium);
  margin-bottom: var(--md-sys-spacing-4);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font: var(--md-sys-typescale-title-large);
}

.result-area {
  margin-bottom: var(--md-sys-spacing-3);
}

.result-success {
  color: var(--md-sys-color-success);
  font: var(--md-sys-typescale-body-medium);
  margin: 0;
}

.result-error {
  color: var(--md-sys-color-error);
  font: var(--md-sys-typescale-body-medium);
  margin: 0;
}

.actions {
  display: flex;
  gap: var(--md-sys-spacing-2);
}
</style>
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd launcher/ui && npm run test -- src/components/OpenCLIPanel.spec.ts`
Expected: 7 tests passed

- [ ] **Step 5: Commit**

```bash
git add launcher/ui/src/components/OpenCLIPanel.vue launcher/ui/src/components/OpenCLIPanel.spec.ts
git commit -m "feat(launcher-ui): add OpenCLIPanel component"
```

---

## Task 6: OcrPanel 组件

**Files:**
- Create: `launcher/ui/src/components/OcrPanel.vue`
- Create: `launcher/ui/src/components/OcrPanel.spec.ts`

**Props:** `status: OcrStatus`(OCR 安装状态)、`progress: OcrInstallProgress`(安装进度)、`testResult: OcrTestResult | null`、`installing: boolean`、`testing: boolean`
**Emits:** `install()` / `test()`

**UI 行为(来自 spec § 4.6.4 OCR 增强 Card + § 5.3 状态显示):**
- 标题 "OCR 增强" + 状态 chip(not_installed=未安装/installing=安装中/installed=已安装)
- 副标题 "PaddleOCR 图片本地识别"
- [下载安装 OCR] 按钮(filled)+ [测试 OCR] 按钮(outlined)
- 安装中:进度条(M3 Linear Progress)+ percent + message
- 测试结果:ok=true → 绿色 ✓ + 识别文字 + 耗时;ok=false → 红色 ✗ + reason/message

- [ ] **Step 1: 创建测试 src/components/OcrPanel.spec.ts**

```typescript
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OcrPanel from './OcrPanel.vue'
import type { OcrStatus, OcrInstallProgress, OcrTestResult } from '@/api/client'

describe('OcrPanel', () => {
  const notInstalledStatus: OcrStatus = { status: 'not_installed', version: '' }
  const installedStatus: OcrStatus = { status: 'installed', version: '3.7.0' }
  const emptyProgress: OcrInstallProgress = { active: false, percent: 0, message: '' }

  it('renders title and not_installed chip', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('OCR 增强')
    expect(wrapper.text()).toContain('PaddleOCR 图片本地识别')
    expect(wrapper.text()).toContain('未安装')
  })

  it('renders installed chip with version', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('已安装')
    expect(wrapper.text()).toContain('3.7.0')
  })

  it('renders installing chip when status is installing', () => {
    const installingStatus: OcrStatus = { status: 'installing', version: '' }
    const wrapper = mount(OcrPanel, {
      props: { status: installingStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('安装中')
  })

  it('emits install event when install button clicked', async () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    await wrapper.get('[data-test="install-ocr-btn"]').trigger('click')
    expect(wrapper.emitted('install')).toBeTruthy()
  })

  it('emits test event when test button clicked', async () => {
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    await wrapper.get('[data-test="test-ocr-btn"]').trigger('click')
    expect(wrapper.emitted('test')).toBeTruthy()
  })

  it('disables install button when installing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: { active: true, percent: 30, message: '下载中' }, testResult: null, installing: true, testing: false },
    })
    const btn = wrapper.get('[data-test="install-ocr-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('shows progress bar when installing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: { active: true, percent: 45, message: '下载中' }, testResult: null, installing: true, testing: false },
    })
    expect(wrapper.find('[data-test="install-progress"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('45')
    expect(wrapper.text()).toContain('下载中')
  })

  it('hides progress bar when not installing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.find('[data-test="install-progress"]').exists()).toBe(false)
  })

  it('shows test success result with text and latency', () => {
    const testResult: OcrTestResult = { ok: true, text: '识别到的文字', latency_ms: 1234 }
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('识别到的文字')
    expect(wrapper.text()).toContain('1234')
  })

  it('shows test error result with message', () => {
    const testResult: OcrTestResult = { ok: false, reason: 'ocr_disabled', message: 'OCR 未启用' }
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('OCR 未启用')
  })

  it('shows testing text when testing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult: null, installing: false, testing: true },
    })
    expect(wrapper.text()).toContain('测试中')
  })
})
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd launcher/ui && npm run test -- src/components/OcrPanel.spec.ts`
Expected: FAIL (组件不存在)

- [ ] **Step 3: 创建 src/components/OcrPanel.vue**

```vue
<script setup lang="ts">
import type { OcrStatus, OcrInstallProgress, OcrTestResult } from '@/api/client'

interface Props {
  status: OcrStatus
  progress: OcrInstallProgress
  testResult: OcrTestResult | null
  installing: boolean
  testing: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  install: []
  test: []
}>()

function chipType(): 'success' | 'warning' | 'info' {
  if (props.status.status === 'installed') return 'success'
  if (props.status.status === 'installing') return 'warning'
  return 'info'
}

function chipText(): string {
  if (props.status.status === 'installed') return '已安装'
  if (props.status.status === 'installing') return '安装中'
  return '未安装'
}
</script>

<template>
  <el-card class="ocr-card" data-test="ocr-card">
    <template #header>
      <div class="card-header">
        <div>
          <div class="card-title">OCR 增强</div>
          <div class="card-subtitle">PaddleOCR 图片本地识别</div>
        </div>
        <el-tag :type="chipType()" data-test="ocr-chip">
          {{ chipText() }}<span v-if="status.version"> · {{ status.version }}</span>
        </el-tag>
      </div>
    </template>

    <div v-if="installing || progress.active" class="progress-area" data-test="install-progress">
      <el-progress :percentage="progress.percent" :stroke-width="8" />
      <p class="progress-message">{{ progress.message }} · {{ progress.percent }}%</p>
    </div>

    <div v-if="testResult && !testing" class="test-result" data-test="ocr-test-result">
      <p v-if="testResult.ok" class="test-success">
        ✓ 识别成功 · 耗时 {{ testResult.latency_ms }}ms
        <span v-if="testResult.text"> · {{ testResult.text }}</span>
      </p>
      <p v-else class="test-error">
        ✗ {{ testResult.message || testResult.reason || '测试失败' }}
      </p>
    </div>

    <div class="actions">
      <el-button
        type="primary"
        :disabled="installing"
        data-test="install-ocr-btn"
        @click="emit('install')"
      >
        {{ installing ? '安装中...' : '下载安装 OCR' }}
      </el-button>
      <el-button
        :disabled="testing || status.status !== 'installed'"
        data-test="test-ocr-btn"
        @click="emit('test')"
      >
        {{ testing ? '测试中...' : '测试 OCR' }}
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.ocr-card {
  background: var(--md-sys-color-surface);
  color: var(--md-sys-color-on-surface);
  border: none;
  box-shadow: var(--md-sys-elevation-1);
  border-radius: var(--md-sys-shape-corner-medium);
  margin-bottom: var(--md-sys-spacing-4);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.card-title {
  font: var(--md-sys-typescale-title-large);
}

.card-subtitle {
  font: var(--md-sys-typescale-body-medium);
  color: var(--md-sys-color-on-surface-variant);
  margin-top: var(--md-sys-spacing-1);
}

.progress-area {
  margin-bottom: var(--md-sys-spacing-3);
}

.progress-message {
  font: var(--md-sys-typescale-body-medium);
  color: var(--md-sys-color-on-surface-variant);
  margin: var(--md-sys-spacing-2) 0 0;
}

.test-result {
  margin-bottom: var(--md-sys-spacing-3);
}

.test-success {
  color: var(--md-sys-color-success);
  font: var(--md-sys-typescale-body-medium);
  margin: 0;
}

.test-error {
  color: var(--md-sys-color-error);
  font: var(--md-sys-typescale-body-medium);
  margin: 0;
}

.actions {
  display: flex;
  gap: var(--md-sys-spacing-2);
}
</style>
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd launcher/ui && npm run test -- src/components/OcrPanel.spec.ts`
Expected: 10 tests passed

- [ ] **Step 5: Commit**

```bash
git add launcher/ui/src/components/OcrPanel.vue launcher/ui/src/components/OcrPanel.spec.ts
git commit -m "feat(launcher-ui): add OcrPanel component"
```

---

## Task 7: LogViewer 组件

**Files:**
- Create: `launcher/ui/src/components/LogViewer.vue`
- Create: `launcher/ui/src/components/LogViewer.spec.ts`

**Props:** `lines: string[]`(日志行数组)
**Emits:** `refresh()`(刷新日志)

**UI 行为(来自 spec § 4.6.4 日志 Card):**
- 标题 "日志" + [刷新] 按钮 + [打开日志目录] 按钮
- 日志列表:等宽字体显示,自动滚动到底部
- 空状态:"暂无日志"

- [ ] **Step 1: 创建测试 src/components/LogViewer.spec.ts**

```typescript
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import LogViewer from './LogViewer.vue'

describe('LogViewer', () => {
  it('renders title', () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    expect(wrapper.text()).toContain('日志')
  })

  it('shows empty state when no lines', () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    expect(wrapper.text()).toContain('暂无日志')
  })

  it('renders log lines', () => {
    const lines = ['14:30:01 API 启动成功', '14:30:03 Worker 启动成功']
    const wrapper = mount(LogViewer, { props: { lines } })
    const items = wrapper.findAll('[data-test="log-line"]')
    expect(items).toHaveLength(2)
    expect(wrapper.text()).toContain('14:30:01 API 启动成功')
    expect(wrapper.text()).toContain('14:30:03 Worker 启动成功')
  })

  it('emits refresh event when refresh button clicked', async () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    await wrapper.get('[data-test="refresh-logs-btn"]').trigger('click')
    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  it('emits open-dir event when open dir button clicked', async () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    await wrapper.get('[data-test="open-log-dir-btn"]').trigger('click')
    expect(wrapper.emitted('open-dir')).toBeTruthy()
  })

  it('applies monospace font to log lines', () => {
    const wrapper = mount(LogViewer, { props: { lines: ['line1'] } })
    const line = wrapper.get('[data-test="log-line"]')
    expect(line.classes()).toContain('log-line')
  })
})
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd launcher/ui && npm run test -- src/components/LogViewer.spec.ts`
Expected: FAIL (组件不存在)

- [ ] **Step 3: 创建 src/components/LogViewer.vue**

```vue
<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

interface Props {
  lines: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  refresh: []
  'open-dir': []
}>()

const container = ref<HTMLElement | null>(null)

watch(
  () => props.lines,
  async () => {
    await nextTick()
    if (container.value) {
      container.value.scrollTop = container.value.scrollHeight
    }
  },
)
</script>

<template>
  <el-card class="log-card" data-test="log-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">日志</span>
        <div class="header-actions">
          <el-button size="small" data-test="refresh-logs-btn" @click="emit('refresh')">
            刷新
          </el-button>
          <el-button size="small" data-test="open-log-dir-btn" @click="emit('open-dir')">
            打开日志目录
          </el-button>
        </div>
      </div>
    </template>

    <div v-if="lines.length === 0" class="empty-state" data-test="empty-state">
      暂无日志
    </div>
    <div v-else ref="container" class="log-container" data-test="log-container">
      <div
        v-for="(line, idx) in lines"
        :key="idx"
        class="log-line"
        data-test="log-line"
      >
        {{ line }}
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.log-card {
  background: var(--md-sys-color-surface-variant);
  color: var(--md-sys-color-on-surface);
  border: none;
  box-shadow: none;
  border-radius: var(--md-sys-shape-corner-medium);
  margin-bottom: var(--md-sys-spacing-4);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font: var(--md-sys-typescale-title-medium);
}

.header-actions {
  display: flex;
  gap: var(--md-sys-spacing-2);
}

.empty-state {
  color: var(--md-sys-color-on-surface-variant);
  font: var(--md-sys-typescale-body-medium);
  padding: var(--md-sys-spacing-4);
  text-align: center;
}

.log-container {
  max-height: 240px;
  overflow-y: auto;
  font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.log-line {
  color: var(--md-sys-color-on-surface-variant);
  padding: var(--md-sys-spacing-1) var(--md-sys-spacing-2);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd launcher/ui && npm run test -- src/components/LogViewer.spec.ts`
Expected: 6 tests passed

- [ ] **Step 5: Commit**

```bash
git add launcher/ui/src/components/LogViewer.vue launcher/ui/src/components/LogViewer.spec.ts
git commit -m "feat(launcher-ui): add LogViewer component"
```

---

## Task 8: App 组件整合

**Files:**
- Modify: `launcher/ui/src/App.vue`(替换 Task 1 骨架)
- Modify: `launcher/ui/src/main.ts`(加入 initBaseUrlFromLocation)
- Modify: `launcher/ui/src/App.spec.ts`(替换 Task 1 骨架测试)

**职责:**
- 整合 4 个子组件(ServiceStatus / OpenCLIPanel / OcrPanel / LogViewer)
- 轮询 `/status`(每 3s)和 `/logs/tail`(每 5s)
- 顶部 Top App Bar(应用名 + 版本号)
- 底部操作栏([打开网页] / [停止全部] / [退出])
- OpenCLI 测试/下载交互
- OCR 安装/测试交互
- 安装进度轮询(每 2s,安装中时)

- [ ] **Step 1: 替换 src/App.spec.ts**

```typescript
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

// mock API client
vi.mock('@/api/client', () => ({
  fetchStatus: vi.fn().mockResolvedValue({
    api: { state: 'running', pid: 1 },
    worker: { state: 'running', pid: 2 },
    beat: { state: 'running', pid: 3 },
  }),
  restartService: vi.fn().mockResolvedValue({ ok: true }),
  stopAll: vi.fn().mockResolvedValue({ ok: true }),
  testOpencli: vi.fn().mockResolvedValue({ ok: true, version: '1.8.6', reason: '', message: '连接正常' }),
  getOpencliDownloadUrl: vi.fn().mockResolvedValue({ url: 'https://opencli.info/download' }),
  getOcrStatus: vi.fn().mockResolvedValue({ status: 'not_installed', version: '' }),
  installOcr: vi.fn().mockResolvedValue({ ok: true, message: '安装已启动' }),
  getOcrInstallProgress: vi.fn().mockResolvedValue({ active: false, percent: 0, message: '' }),
  testOcr: vi.fn().mockResolvedValue({ ok: true, text: '测试', latency_ms: 100 }),
  getLogsTail: vi.fn().mockResolvedValue({ lines: ['line1', 'line2'] }),
  setBaseUrl: vi.fn(),
  initBaseUrlFromLocation: vi.fn(),
}))

describe('App', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('renders app title in top app bar', () => {
    const wrapper = mount(App)
    expect(wrapper.get('[data-test="app-title"]').text()).toContain('小红书活动信息抓取系统')
  })

  it('renders ServiceStatus component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'ServiceStatus' }).exists()).toBe(true)
  })

  it('renders OpenCLIPanel component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'OpenCLIPanel' }).exists()).toBe(true)
  })

  it('renders OcrPanel component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'OcrPanel' }).exists()).toBe(true)
  })

  it('renders LogViewer component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'LogViewer' }).exists()).toBe(true)
  })

  it('renders bottom action bar with open-web button', () => {
    const wrapper = mount(App)
    expect(wrapper.find('[data-test="open-web-btn"]').exists()).toBe(true)
  })

  it('renders stop-all button in bottom action bar', () => {
    const wrapper = mount(App)
    expect(wrapper.find('[data-test="app-stop-all-btn"]').exists()).toBe(true)
  })

  it('renders exit button in bottom action bar', () => {
    const wrapper = mount(App)
    expect(wrapper.find('[data-test="exit-btn"]').exists()).toBe(true)
  })

  it('fetches status on mount', async () => {
    const { fetchStatus } = await import('@/api/client')
    mount(App)
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchStatus).toHaveBeenCalled()
  })

  it('fetches logs on mount', async () => {
    const { getLogsTail } = await import('@/api/client')
    mount(App)
    await vi.advanceTimersByTimeAsync(0)
    expect(getLogsTail).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd launcher/ui && npm run test -- src/App.spec.ts`
Expected: FAIL (App.vue 还是骨架)

- [ ] **Step 3: 替换 src/App.vue**

```vue
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ServiceStatus from './components/ServiceStatus.vue'
import OpenCLIPanel from './components/OpenCLIPanel.vue'
import OcrPanel from './components/OcrPanel.vue'
import LogViewer from './components/LogViewer.vue'
import {
  fetchStatus,
  restartService,
  stopAll,
  testOpencli,
  getOpencliDownloadUrl,
  getOcrStatus,
  installOcr,
  getOcrInstallProgress,
  testOcr,
  getLogsTail,
  initBaseUrlFromLocation,
  type StatusResponse,
  type OpencliTestResult,
  type OcrStatus,
  type OcrInstallProgress,
  type OcrTestResult,
} from './api/client'

const APP_VERSION = '0.1.0'
const STATUS_POLL_MS = 3000
const LOGS_POLL_MS = 5000
const PROGRESS_POLL_MS = 2000

const status = ref<StatusResponse>({
  api: { state: 'stopped', pid: null },
  worker: { state: 'stopped', pid: null },
  beat: { state: 'stopped', pid: null },
})
const opencliResult = ref<OpencliTestResult | null>(null)
const opencliLoading = ref(false)
const ocrStatus = ref<OcrStatus>({ status: 'not_installed', version: '' })
const ocrProgress = ref<OcrInstallProgress>({ active: false, percent: 0, message: '' })
const ocrTestResult = ref<OcrTestResult | null>(null)
const ocrInstalling = ref(false)
const ocrTesting = ref(false)
const logLines = ref<string[]>([])

let statusTimer: ReturnType<typeof setInterval> | null = null
let logsTimer: ReturnType<typeof setInterval> | null = null
let progressTimer: ReturnType<typeof setInterval> | null = null

async function refreshStatus() {
  try {
    status.value = await fetchStatus()
  } catch (e) {
    // 静默失败,下次轮询重试
  }
}

async function refreshLogs() {
  try {
    const resp = await getLogsTail(50)
    logLines.value = resp.lines
  } catch (e) {
    // 静默失败
  }
}

async function refreshOcrStatus() {
  try {
    ocrStatus.value = await getOcrStatus()
  } catch (e) {
    // 静默失败
  }
}

async function refreshOcrProgress() {
  try {
    ocrProgress.value = await getOcrInstallProgress()
    if (!ocrProgress.value.active && ocrInstalling.value) {
      ocrInstalling.value = false
      if (progressTimer) {
        clearInterval(progressTimer)
        progressTimer = null
      }
      await refreshOcrStatus()
      if (ocrProgress.value.ok) {
        ElMessage.success('OCR 安装完成')
      } else {
        ElMessage.error(`OCR 安装失败: ${ocrProgress.value.message}`)
      }
    }
  } catch (e) {
    // 静默失败
  }
}

async function handleRestart(name: string) {
  try {
    await restartService(name)
    ElMessage.success(`${name} 已重启`)
    await refreshStatus()
  } catch (e) {
    ElMessage.error(`重启 ${name} 失败`)
  }
}

async function handleStopAll() {
  try {
    await stopAll()
    ElMessage.success('已停止全部服务')
    await refreshStatus()
  } catch (e) {
    ElMessage.error('停止服务失败')
  }
}

async function handleOpencliTest() {
  opencliLoading.value = true
  try {
    opencliResult.value = await testOpencli()
  } catch (e) {
    opencliResult.value = { ok: false, version: '', reason: 'api_error', message: '测试失败' }
  } finally {
    opencliLoading.value = false
  }
}

async function handleOpencliDownload() {
  try {
    const { url } = await getOpencliDownloadUrl()
    window.open(url, '_blank')
  } catch (e) {
    ElMessage.error('获取下载链接失败')
  }
}

async function handleOcrInstall() {
  ocrInstalling.value = true
  ocrTestResult.value = null
  try {
    await installOcr()
    progressTimer = setInterval(refreshOcrProgress, PROGRESS_POLL_MS)
  } catch (e) {
    ocrInstalling.value = false
    ElMessage.error('启动安装失败')
  }
}

async function handleOcrTest() {
  ocrTesting.value = true
  try {
    ocrTestResult.value = await testOcr()
  } catch (e) {
    ocrTestResult.value = { ok: false, reason: 'api_error', message: '测试失败' }
  } finally {
    ocrTesting.value = false
  }
}

function handleOpenWeb() {
  const port = new URLSearchParams(window.location.search).get('apiPort') || '8000'
  window.open(`http://127.0.0.1:${port}`, '_blank')
}

function handleExit() {
  // PyWebView 注入的 API:window.pywebview.api.exit()
  const pywebview = (window as unknown as { pywebview?: { api?: { exit: () => void } } }).pywebview
  if (pywebview?.api?.exit) {
    pywebview.api.exit()
  } else {
    // 无 PyWebView 时(开发模式)只停止服务
    handleStopAll()
  }
}

onMounted(async () => {
  initBaseUrlFromLocation()
  await Promise.all([refreshStatus(), refreshLogs(), refreshOcrStatus()])
  statusTimer = setInterval(refreshStatus, STATUS_POLL_MS)
  logsTimer = setInterval(refreshLogs, LOGS_POLL_MS)
})

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
  if (logsTimer) clearInterval(logsTimer)
  if (progressTimer) clearInterval(progressTimer)
})
</script>

<template>
  <div class="launcher-app" data-test="launcher-app">
    <header class="top-app-bar" data-test="top-app-bar">
      <h1 class="app-title" data-test="app-title">小红书活动信息抓取系统</h1>
      <span class="app-version">v{{ APP_VERSION }}</span>
    </header>

    <main class="main-content">
      <ServiceStatus
        :status="status"
        @restart="handleRestart"
        @stop-all="handleStopAll"
      />

      <OpenCLIPanel
        :result="opencliResult"
        :loading="opencliLoading"
        @test="handleOpencliTest"
        @download="handleOpencliDownload"
      />

      <OcrPanel
        :status="ocrStatus"
        :progress="ocrProgress"
        :test-result="ocrTestResult"
        :installing="ocrInstalling"
        :testing="ocrTesting"
        @install="handleOcrInstall"
        @test="handleOcrTest"
      />

      <LogViewer :lines="logLines" @refresh="refreshLogs" @open-dir="() => {}" />
    </main>

    <footer class="bottom-action-bar" data-test="bottom-action-bar">
      <el-button type="primary" data-test="open-web-btn" @click="handleOpenWeb">
        打开网页
      </el-button>
      <el-button data-test="app-stop-all-btn" @click="handleStopAll">
        停止全部
      </el-button>
      <el-button text data-test="exit-btn" @click="handleExit">
        退出
      </el-button>
    </footer>
  </div>
</template>

<style scoped>
.launcher-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--md-sys-color-background);
  color: var(--md-sys-color-on-surface);
}

.top-app-bar {
  background: var(--md-sys-color-surface);
  box-shadow: var(--md-sys-elevation-2);
  padding: var(--md-sys-spacing-4) var(--md-sys-spacing-6);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.app-title {
  font: var(--md-sys-typescale-headline-medium);
  margin: 0;
}

.app-version {
  font: var(--md-sys-typescale-label-medium);
  color: var(--md-sys-color-on-surface-variant);
}

.main-content {
  flex: 1;
  padding: var(--md-sys-spacing-4) var(--md-sys-spacing-6);
  overflow-y: auto;
}

.bottom-action-bar {
  background: var(--md-sys-color-surface-container-high);
  padding: var(--md-sys-spacing-3) var(--md-sys-spacing-6);
  display: flex;
  justify-content: flex-end;
  gap: var(--md-sys-spacing-2);
}
</style>
```

- [ ] **Step 4: 替换 src/main.ts(加入 initBaseUrlFromLocation)**

```typescript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './design/tokens.css'
import App from './App.vue'

createApp(App).use(ElementPlus).mount('#app')
```

(main.ts 在 Task 1 已创建,无需改动,initBaseUrlFromLocation 在 App.vue onMounted 里调用)

- [ ] **Step 5: 运行测试看到通过**

Run: `cd launcher/ui && npm run test -- src/App.spec.ts`
Expected: 10 tests passed

- [ ] **Step 6: 运行全部测试确认无回归**

Run: `cd launcher/ui && npm run test`
Expected: 所有测试通过(ServiceStatus 9 + OpenCLIPanel 7 + OcrPanel 10 + LogViewer 6 + App 10 + design-tokens 8 + client 11 + 原 App 骨架 1 已被替换 = 61 passed)

- [ ] **Step 7: Commit**

```bash
git add launcher/ui/src/App.vue launcher/ui/src/App.spec.ts
git commit -m "feat(launcher-ui): integrate all components in App with polling and actions"
```

---

## Task 9: 构建验证

**Files:** 无新建,只验证 `npm run build`

- [ ] **Step 1: 运行构建**

Run: `cd launcher/ui && npm run build`
Expected: 产出 `dist/index.html` + `dist/assets/*`,vue-tsc 类型检查通过

- [ ] **Step 2: 验证 dist/index.html 存在且引用了 assets**

Run: `ls launcher/ui/dist/ && head -20 launcher/ui/dist/index.html`
Expected: 存在 `index.html` 和 `assets/` 目录,HTML 引用了 `/assets/*.js` 和 `/assets/*.css`

- [ ] **Step 3: 验证 PyWebView 可加载(手动验证,记入验收文档)**

PyWebView 加载 `file:///.../launcher/ui/dist/index.html?statusPort=<port>&apiPort=<port>`,UI 正常显示暗色主题,三张卡片(服务状态/OpenCLI/OCR)+ 日志卡 + 底部操作栏。

- [ ] **Step 4: Commit(如有改动)**

```bash
git add launcher/ui/dist/
git commit -m "build(launcher-ui): produce dist for PyWebView loading"
```

(注:`dist/` 通常不提交,由打包脚本构建时生成。这里只为验证构建成功,提交可跳过或按项目 .gitignore 约定处理。)

---

## Self-Review

**1. Spec coverage:**
- § 4.6.1 M3 设计原则(颜色角色/三层对比/排版五角色/Elevation/暗色优先/状态色语义) → tokens.css + 各组件 CSS ✓
- § 4.6.2 颜色方案 → tokens.css ✓
- § 4.6.3 排版 Type Scale → tokens.css ✓
- § 4.6.4 布局(Top App Bar / 服务状态 Card / OpenCLI Card / OCR Card / 日志 Card / 底部操作栏) → App.vue + 4 个组件 ✓
- § 4.6.5 M3 组件映射(el-card / el-tag / el-button / el-progress) → 各组件 ✓
- § 4.6.6 间距与圆角 → tokens.css ✓
- § 4.3 状态服务接口(10 个端点) → client.ts ✓
- § 4.7 PyWebView 窗口(加载 file://.../dist/index.html?statusPort=) → main.ts + App.vue initBaseUrlFromLocation ✓
- § 5.3 OCR 状态显示(not_installed/installing/installed) → OcrPanel ✓
- § 8.3 启动器 UI 组件测试(5 个组件 spec + 1 个设计令牌 spec) → 6 个 spec 文件 ✓

**2. Placeholder scan:**
- 无 TBD/TODO 占位
- 所有步骤都有完整代码
- 测试代码完整,无"类似 Task N"引用

**3. Type consistency:**
- `StatusResponse` / `ServiceState` 在 client.ts 定义,ServiceStatus.vue 和 App.vue 消费 ✓
- `OpencliTestResult` 在 client.ts 定义,OpenCLIPanel.vue 和 App.vue 消费 ✓
- `OcrStatus` / `OcrInstallProgress` / `OcrTestResult` 在 client.ts 定义,OcrPanel.vue 和 App.vue 消费 ✓
- `restartService(name: string)` / `stopAll()` 等函数签名在 client.ts 定义,App.vue 调用 ✓
- 组件 emits:ServiceStatus `restart: [name: string]` / `stop-all: []`;OpenCLIPanel `test: []` / `download: []`;OcrPanel `install: []` / `test: []`;LogViewer `refresh: []` / `open-dir: []` —— 与 App.vue 的 handler 签名一致 ✓

**4. 额外检查:**
- launcher/ui/package.json 依赖版本和 frontend/package.json 对齐(vue 3.5 / element-plus 2.9 / vitest 3 / vite 7 / typescript 5.7 / vue-tsc 3)
- launcher/ui/vite.config.ts 不需要 server.proxy(因为 file:// 加载,直接 fetch 状态服务)
- launcher/ui/ 独立 tsconfig,不和主项目共享
- 测试用 vi.useFakeTimers 避免真实 setInterval 卡住测试
- App.vue 的 onUnmounted 清理所有 timer,无内存泄漏
