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
  // 关联: docs/superpowers/specs/2026-08-17-launcher-ui-baseurl-pywebview-design.md
  // PyWebView 加载 file://.../index.html?statusPort=9000 时,
  // window.location.search 在 macOS WKWebView 上不一定包含 query string,
  // 所以 fallback 到 window.pywebview.api.getStatusPort() (注入的 JS API)
  // PyWebView 把 Python 的 get_status_port / getStatusPort 都暴露成 getStatusPort
  // (snake_case 会被自动转 camelCase);两个都试一下,谁有值用谁。
  const params = new URLSearchParams(window.location.search)
  const port = params.get('statusPort')
  if (port) {
    baseUrl = `http://127.0.0.1:${port}`
    return
  }
  const pywebview = (
    window as unknown as {
      pywebview?: {
        api?: {
          getStatusPort?: () => number | Promise<number>
          get_status_port?: () => number | Promise<number>
        }
      }
    }
  ).pywebview
  const apiPortFn = pywebview?.api?.getStatusPort ?? pywebview?.api?.get_status_port
  const apiPort = apiPortFn?.()
  if (apiPort && typeof apiPort === 'number') {
    baseUrl = `http://127.0.0.1:${apiPort}`
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = init ? await fetch(`${baseUrl}${path}`, init) : await fetch(`${baseUrl}${path}`)
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
  // 细粒度独立状态(对应后端 status_server /opencli/test 的 daemon/chrome/extension 三块)
  daemon: {
    running: boolean
    port: number
  }
  chrome: {
    running: boolean
    path: string
  }
  extension: {
    connected: boolean
    profile: string
  }
}

export function testOpencli(): Promise<OpencliTestResult> {
  return request<OpencliTestResult>('/opencli/test')
}

export function getOpencliDownloadUrl(): Promise<{ url: string }> {
  return request<{ url: string }>('/opencli/download-url')
}

// ── LLM / OCR / opencli 系统配置 ──

/**
 * launcher 侧 .env 读写接口字段。
 * 与后端 system-config 端点字段对齐,前端用这些字段配置后端 LLM。
 * 关联 spec: docs/superpowers/specs/2026-08-17-launcher-system-config-and-opencli-verify-design.md § 3
 */
export interface SystemConfig {
  minimax_api_key: string
  minimax_base_url: string
  minimax_model: string
  minimax_vision_model: string
  minimax_timeout_seconds: string  // 跟 .env 一致用 string 表示
  minimax_concurrency: string
  ocr_enabled: string
  ocr_language: string
  ocr_min_confidence: string
  ocr_parallel_workers: string
  opencli_bin: string
  chrome_bin: string
  chrome_user_data_dir: string
  // 存储路径 — base dir 模式
  // 关联: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
  // 用户只设 DATA_DIR;其他子目录(IMAGE_DIR/EXPORT_DIR/ARCHIVE_DIR/
  // PADDLE_PDX_CACHE_HOME/HF_HOME/DATABASE_URL)由 backend Settings 自动从 DATA_DIR 推导
  data_dir: string
  log_dir: string
}

export interface SystemConfigSaveResponse {
  ok: boolean
  saved_keys: string[]
  restart: { api: unknown; worker: unknown; web?: unknown; beat?: unknown }
}

export function getSystemConfig(): Promise<SystemConfig> {
  return request<SystemConfig>('/system-config')
}

export async function saveSystemConfig(
  payload: Partial<SystemConfig>,
): Promise<SystemConfigSaveResponse> {
  const resp = await fetch(`${baseUrl}/system-config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return (await resp.json()) as SystemConfigSaveResponse
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

/**
 * 启动器自动生成的初始密码信息。
 * 关联 spec: docs/superpowers/specs/2026-08-16-launcher-password-visibility-design.md § 2
 */
export interface InitialPasswordResult {
  password: string
  auto_generated: boolean
  generated_at: string | null
}

/**
 * 拉取初始密码:204 No Content 表示用户手动配置(不展示 banner)。
 */
export async function getInitialPassword(): Promise<InitialPasswordResult | null> {
  const resp = await fetch(`${baseUrl}/initial-password`)
  if (resp.status === 204) {
    return null
  }
  return (await resp.json()) as InitialPasswordResult
}
