import { http } from '@/api/http'

/**
 * 把 markdown 里的 `/api/v1/reports/image/<storage_key>` 改写成
 * `<http.baseURL>/reports/image/<storage_key>`，让周报预览图片在
 * dev 模式（vite 默认 baseURL=/api/v1）和打包版（baseURL=http://127.0.0.1:8001/api/v1）
 * 都能正常加载。
 *
 * 关联 spec: docs/superpowers/specs/2026-08-18-weekly-report-images-and-zip-design.md
 */
export function resolveReportImageUrls(markdown: string, baseURL?: string): string {
  const prefix = '/api/v1/reports/image/'
  if (!markdown.includes(prefix)) return markdown
  // 优先级: 显式参数 → axios baseURL → 默认 '/api/v1'
  // 空字符串/falsy 视作未提供,不要把它替换成空路径
  const rawBase = baseURL || http.defaults.baseURL || '/api/v1'
  const resolvedBase = rawBase.replace(/\/+$/, '') || '/api/v1'
  // split/join 比 replace 全局替换更稳,避免转义陷阱
  return markdown.split(`${prefix}`).join(`${resolvedBase}/reports/image/`)
}
