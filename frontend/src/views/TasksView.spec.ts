import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import TasksView from './TasksView.vue'

const { tasks, createTask } = vi.hoisted(() => ({
  tasks: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 8, type: 'keyword', status: 'PAUSED', total_notes: 3, error_message: '需要登录' }] } } }),
  createTask: vi.fn().mockResolvedValue({ data: { data: { id: 9 } } }),
}))
vi.mock('@/api/client', () => ({ api: { tasks, createTask, logs: vi.fn() } }))

describe('TasksView', () => {
  it('renders task state and submits the configured crawl', async () => {
    const wrapper = mount(TasksView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('PAUSED')
    await wrapper.findAll('button').find((button) => button.text().includes('开始抓取'))!.trigger('click')
    await flushPromises()
    expect(createTask).toHaveBeenCalledWith({ type: 'keyword', cities: ['shanghai'], keywords: ['周末活动', '展览'] })
  })
})
