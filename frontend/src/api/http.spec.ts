import { describe, expect, it, vi } from 'vitest'

import { http } from './http'

describe('http client', () => {
  it('adds the bearer token to authenticated API requests', async () => {
    localStorage.setItem('token', 'api-token')
    const adapter = vi.fn(async (config) => ({ data: {}, status: 200, statusText: 'OK', headers: {}, config }))
    await http.get('/health', { adapter })
    expect(adapter.mock.calls[0][0].headers.Authorization).toBe('Bearer api-token')
  })
})
