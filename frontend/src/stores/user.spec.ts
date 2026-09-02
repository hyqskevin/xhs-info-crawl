import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore, parseJwtPayload } from './user'

function makeJwt(payload: object): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.signature`
}

describe('parseJwtPayload', () => {
  it('parses payload from a valid JWT', () => {
    const token = makeJwt({ sub: 'admin', role: 'admin', permissions: ['*'] })
    expect(parseJwtPayload(token)).toEqual({ sub: 'admin', role: 'admin', permissions: ['*'] })
  })

  it('returns null for malformed token', () => {
    expect(parseJwtPayload('not-a-jwt')).toBeNull()
    expect(parseJwtPayload('only.two.parts')).toBeNull()
  })

  it('returns null for invalid base64 payload', () => {
    expect(parseJwtPayload('header.!!!.signature')).toBeNull()
  })
})

describe('useUserStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('setToken parses role from JWT payload', () => {
    const store = useUserStore()
    const token = makeJwt({ sub: 'admin', role: 'admin', permissions: ['*'] })
    store.setToken(token)
    expect(store.role).toBe('admin')
    expect(store.isAdmin).toBe(true)
    expect(store.isAuthenticated).toBe(true)
  })

  it('setToken parses editor role', () => {
    const store = useUserStore()
    const token = makeJwt({ sub: 'alice', role: 'editor', permissions: ['notes:review'] })
    store.setToken(token)
    expect(store.role).toBe('editor')
    expect(store.isAdmin).toBe(false)
  })

  it('clear resets state', () => {
    const store = useUserStore()
    store.setToken(makeJwt({ sub: 'admin', role: 'admin' }))
    store.clear()
    expect(store.token).toBeNull()
    expect(store.role).toBeNull()
    expect(store.isAdmin).toBe(false)
    expect(store.isAuthenticated).toBe(false)
  })

  it('setToken with malformed JWT leaves role null', () => {
    const store = useUserStore()
    store.setToken('not-a-jwt')
    expect(store.role).toBeNull()
    expect(store.isAdmin).toBe(false)
  })
})