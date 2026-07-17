import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import TasksView from './TasksView.vue'

const mocks = vi.hoisted(() => ({ tasks: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 8, type: 'mixed', status: 'PAUSED', total_notes: 3, error_message: '需要登录' }] } } }), logs: vi.fn() }))
vi.mock('@/api/client', () => ({ api: mocks }))

describe('TasksView', () => {
  it('is a crawl monitoring page without trigger controls', async () => {
    const wrapper = mount(TasksView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('等待登录')
    expect(wrapper.text()).toContain('抓取日志')
    expect(wrapper.text()).not.toContain('开始抓取')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).not.toContain('关键词，逗号分隔')
  })
})
