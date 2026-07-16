import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import DuplicatesView from './DuplicatesView.vue'

const { duplicates, activity } = vi.hoisted(() => ({
  duplicates: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 1, activity_a_id: 10, activity_b_id: 11, similarity: 0.9, matched_fields: 'city,date' }] } } }),
  activity: vi.fn((id: number) => Promise.resolve({ data: { data: { id, name: id === 10 ? '活动 A' : '活动 B', start_time: '2026-07-18', location: id === 10 ? '静安' : '徐汇' } } })),
}))
vi.mock('@/api/client', () => ({ api: { duplicates, activity, merge: vi.fn(), ignore: vi.fn() } }))

describe('DuplicatesView', () => {
  it('loads both activities and renders a comparison', async () => {
    const wrapper = mount(DuplicatesView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(activity).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('活动 A')
    expect(wrapper.text()).toContain('活动 B')
    expect(wrapper.text()).toContain('90%')
  })
})
