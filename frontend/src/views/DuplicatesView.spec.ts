import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import DuplicatesView from './DuplicatesView.vue'

const { duplicates, note } = vi.hoisted(() => ({
  duplicates: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 1, note_a_id: 10, note_b_id: 11, similarity: 0.9, matched_fields: ['title'] }] } } }),
  note: vi.fn((id: number) => Promise.resolve({ data: { data: { id, title: id === 10 ? '推文 A' : '推文 B', published_at: '2026-07-18', activity_count: id === 10 ? 2 : 3 } } })),
}))
vi.mock('@/api/client', () => ({ api: { duplicates, note, merge: vi.fn(), ignore: vi.fn() } }))

describe('DuplicatesView', () => {
  it('loads both posts and renders a comparison', async () => {
    const wrapper = mount(DuplicatesView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(note).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('推文 A')
    expect(wrapper.text()).toContain('推文 B')
    expect(wrapper.text()).toContain('90%')
  })
})
