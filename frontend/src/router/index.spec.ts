import { beforeEach, describe, expect, it } from 'vitest'

import router from './index'

describe('router guards', () => {
  beforeEach(async () => { localStorage.clear(); await router.push('/login'); await router.isReady() })

  it('redirects anonymous users from business routes to login', async () => {
    await router.push('/activities')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('redirects authenticated users away from login', async () => {
    localStorage.setItem('token', 'token')
    await router.push('/dashboard')
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/dashboard')
  })
})
