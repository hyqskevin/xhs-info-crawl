import { defineStore } from 'pinia'

interface JwtPayload {
  sub: string
  role?: string
  permissions?: string[]
}

function parseJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = JSON.parse(atob(parts[1]))
    return payload as JwtPayload
  } catch {
    return null
  }
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: null as string | null,
    role: null as 'admin' | 'editor' | null,
  }),
  getters: {
    isAdmin: (state) => state.role === 'admin',
    isAuthenticated: (state) => state.token !== null,
  },
  actions: {
    setToken(token: string) {
      this.token = token
      const payload = parseJwtPayload(token)
      const r = payload?.role
      if (r === 'admin' || r === 'editor') {
        this.role = r
      } else {
        this.role = null
      }
    },
    clear() {
      this.token = null
      this.role = null
    },
  },
})