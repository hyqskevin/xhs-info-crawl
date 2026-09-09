const SHANGHAI_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

function shanghaiParts(date: Date): Record<string, string> {
  const parts = SHANGHAI_FORMATTER.formatToParts(date)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return { y: get('year'), mo: get('month'), d: get('day'), h: get('hour'), mi: get('minute'), s: get('second') }
}

/**
 * 全站时间口径 = 北京墙钟：后端 datetime 带 +08:00 后缀（CnJsonResponse），
 * 历史 Z 后缀仍兼容，naive 兜底按北京墙钟。仅格式化，无时区换算语义。
 * 空值返回 '-'；无法解析的输入原样返回。
 */
export function formatCnDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}+08:00`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return value
  const p = shanghaiParts(date)
  return `${p.y}-${p.mo}-${p.d} ${p.h}:${p.mi}:${p.s}`
}

/** Date → 北京墙钟 naive ISO（YYYY-MM-DDTHH:mm:ss），供表单提交。 */
export function toCnWallString(date: Date): string {
  const p = shanghaiParts(date)
  return `${p.y}-${p.mo}-${p.d}T${p.h}:${p.mi}:${p.s}`
}

/** 北京墙钟文件名戳（YYYY-MM-DD-HH-mm）。 */
export function cnWallStamp(date: Date = new Date()): string {
  const p = shanghaiParts(date)
  return `${p.y}-${p.mo}-${p.d}-${p.h}-${p.mi}`
}
