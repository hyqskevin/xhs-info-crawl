import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import DuplicatesView from './DuplicatesView.vue'

const { duplicates, note, merge, ignore } = vi.hoisted(() => ({
  duplicates: vi.fn(),
  note: vi.fn(),
  merge: vi.fn(),
  ignore: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  api: { duplicates, note, merge, ignore },
}))

describe('DuplicatesView', () => {
  it('loads both posts and renders a comparison', async () => {
    duplicates.mockResolvedValueOnce({
      data: {
        data: {
          items: [
            {
              id: 1,
              note_a_id: 10,
              note_b_id: 11,
              similarity: 0.9,
              matched_fields: ['title'],
            },
          ],
        },
      },
    })
    note.mockImplementation((id: number) =>
      Promise.resolve({
        data: {
          data: {
            id,
            title: id === 10 ? '推文 A' : '推文 B',
            published_at: '2026-07-18',
            activity_count: id === 10 ? 2 : 3,
          },
        },
      }),
    )

    const wrapper = mount(DuplicatesView, {
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    expect(note).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('推文 A')
    expect(wrapper.text()).toContain('推文 B')
    expect(wrapper.text()).toContain('90%')
  })

  it('skips orphan pair without dropping the rest', async () => {
    // 候选 1 一侧不可见 (404)，候选 2 两侧都可见
    duplicates.mockResolvedValueOnce({
      data: {
        data: {
          items: [
            {
              id: 1,
              note_a_id: 999, // 抛 404
              note_b_id: 11,
              similarity: 0.8,
              matched_fields: ['title'],
            },
            {
              id: 2,
              note_a_id: 20,
              note_b_id: 21,
              similarity: 0.7,
              matched_fields: ['content'],
            },
          ],
        },
      },
    })
    note.mockImplementation((id: number) => {
      if (id === 999) {
        return Promise.reject(new Error('404'))
      }
      return Promise.resolve({
        data: { data: { id, title: `推文 ${id}`, published_at: '2026-07-18', activity_count: 1 } },
      })
    })

    const wrapper = mount(DuplicatesView, {
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    // 第一条被丢弃，第二条正常渲染
    expect(wrapper.text()).toContain('推文 20')
    expect(wrapper.text()).toContain('推文 21')
    expect(wrapper.text()).not.toContain('推文 999')
  })
})