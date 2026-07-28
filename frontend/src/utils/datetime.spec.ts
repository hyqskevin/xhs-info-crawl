import { describe, expect, it } from 'vitest'

import { formatUtcAsShanghai } from './datetime'

describe('formatUtcAsShanghai', () => {
  it('converts UTC naive strings to Asia/Shanghai wall clock (+8h)', () => {
    // 后端 created_at 为 UTC naive（无 Z 后缀），需按 UTC 解析再转东八区
    expect(formatUtcAsShanghai('2026-07-28T00:46:14')).toBe('2026-07-28 08:46:14')
  })

  it('handles values that already carry a Z suffix', () => {
    expect(formatUtcAsShanghai('2026-07-28T00:46:14Z')).toBe('2026-07-28 08:46:14')
  })

  it('rolls over to the next day when +8h crosses midnight', () => {
    expect(formatUtcAsShanghai('2026-07-27T17:00:00')).toBe('2026-07-28 01:00:00')
  })

  it('returns dash for empty values and keeps invalid input as-is', () => {
    expect(formatUtcAsShanghai(null)).toBe('-')
    expect(formatUtcAsShanghai(undefined)).toBe('-')
    expect(formatUtcAsShanghai('')).toBe('-')
    expect(formatUtcAsShanghai('not-a-date')).toBe('not-a-date')
  })
})
