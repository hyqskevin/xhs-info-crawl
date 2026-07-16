import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import DashboardView from './DashboardView.vue'

vi.mock('@/api/health', () => ({
  getHealth: vi.fn().mockResolvedValue({ status: 'ok', database: 'sqlite' }),
}))

describe('DashboardView', () => {
  it('renders the phase-one system status with Element Plus components', async () => {
    const wrapper = mount(DashboardView, {
      global: {
        stubs: {
          ElCard: { template: '<section class="el-card"><slot /></section>' },
          ElTag: { template: '<span class="el-tag"><slot /></span>' },
          ElIcon: { template: '<span class="el-icon"><slot /></span>' },
          ElAlert: true,
          Connection: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('小红书本地活动信息抓取系统')
    expect(wrapper.text()).toContain('服务运行正常')
    expect(wrapper.text()).toContain('SQLite')
    expect(wrapper.find('.el-card').exists()).toBe(true)
    expect(wrapper.find('.el-tag').exists()).toBe(true)
  })
})
