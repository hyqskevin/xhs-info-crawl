import axios from 'axios'
import qs from 'qs'

/**
 * 解析后端 base URL,优先级:
 * 1. 打包版启动器注入的 window.__APP_CONFIG__.apiBaseUrl(如 http://127.0.0.1:8001)
 * 2. import.meta.env.VITE_API_BASE_URL(开发模式默认 /api/v1,搭配 vite proxy)
 *
 * 关联 spec: docs/superpowers/specs/2026-08-16-packaged-frontend-static-serving-design.md
 */
function resolveApiBaseUrl(): string {
  const runtime = (window as unknown as { __APP_CONFIG__?: { apiBaseUrl?: string } }).__APP_CONFIG__
  if (runtime?.apiBaseUrl) return runtime.apiBaseUrl
  return import.meta.env.VITE_API_BASE_URL || '/api/v1'
}

export const http = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS),
  paramsSerializer: (params) => qs.stringify(params, { arrayFormat: 'repeat' }),
})
http.interceptors.request.use(config=>{const token=localStorage.getItem('token');if(token) config.headers.Authorization=`Bearer ${token}`;return config})
http.interceptors.response.use(r=>r,e=>{if(e.response?.status===401&&location.pathname!=='/login'&&!e.config?.skipAuthRedirect){localStorage.removeItem('token');location.href='/login'}return Promise.reject(e)})
