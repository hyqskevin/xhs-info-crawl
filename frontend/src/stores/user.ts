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

function readRoleFromStorage(): 'admin' | 'editor' | null {
  const token = localStorage.getItem('token')
  if (!token) return null
  const payload = parseJwtPayload(token)
  const r = payload?.role
  return r === 'admin' || r === 'editor' ? r : null
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: null as string | null,
    role: null as 'admin' | 'editor' | null,
  }),
  getters: {
    /** 优先用 store 状态；page refresh 后 store 未初始化时退到 localStorage 解析 token */
    isAdmin(): boolean {
      if (this.role === 'admin') return true
      return readRoleFromStorage() === 'admin'
    },
    isAuthenticated(): boolean {
      if (this.token !== null) return true
      return !!localStorage.getItem('token')
    },
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
      localStorage.removeItem('token')
    },
  },
})