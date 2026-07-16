import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import ActivitiesView from './ActivitiesView.vue'

const { activities } = vi.hoisted(() => ({ activities: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 1, name: '周末艺术展', city_code: 'shanghai', start_time: '2026-07-18T10:00:00Z', location: '静安', status: 'RAW' }] }, pagination: { total: 1 } } }) }))
vi.mock('@/api/client', () => ({ api: { activities, activity: vi.fn(), createActivity: vi.fn(), updateActivity: vi.fn(), deleteActivity: vi.fn() } }))

describe('ActivitiesView', () => {
  it('loads activities and opens the create dialog', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('周末艺术展')
    expect(activities).toHaveBeenCalled()
    await wrapper.findAll('button').find((button) => button.text().includes('新增活动'))!.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('新增活动')
  })
})
