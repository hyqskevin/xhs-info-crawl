import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LoginView from './LoginView.vue'

const { push, login } = vi.hoisted(() => ({ push: vi.fn(), login: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/client', () => ({ api: { login } }))

describe('LoginView', () => {
  beforeEach(() => { push.mockReset(); login.mockReset() })

  it('submits credentials, stores the token, and navigates to dashboard', async () => {
    login.mockResolvedValue({ data: { data: { access_token: 'component-token' } } })
    const wrapper = mount(LoginView, { global: { plugins: [ElementPlus] } })
    await wrapper.get('input[placeholder="密码"]').setValue('Admin@123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(login).toHaveBeenCalledWith('admin', 'Admin@123')
    expect(localStorage.getItem('token')).toBe('component-token')
    expect(push).toHaveBeenCalledWith('/dashboard')
  })
})
