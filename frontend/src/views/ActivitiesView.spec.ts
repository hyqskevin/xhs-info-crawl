import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElDrawer, ElEmpty, ElImage, ElMessageBox, ElPagination, ElTable } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ActivitiesView from './ActivitiesView.vue'

const mocks = vi.hoisted(() => ({
  notes: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 1, title: '周末艺术展推文', city_code: 'shanghai', published_at: '2026-07-18T10:00:00Z', review_status: 'PENDING', processing_status: 'PROCESSED', activity_count: 2 }] }, pagination: { page: 1, page_size: 20, total: 41 } } }),
  settings: vi.fn().mockResolvedValue({ data: { data: [{ id: 1, name: '上海', code: 'shanghai', enabled: true }] } }),
  note: vi.fn().mockResolvedValue({ data: { data: { id: 1, title: '周末艺术展推文', content: '页面正文', source_url: 'https://xhs/note-7', review_status: 'PENDING', activities: [{ id: 11, name: '活动一', location: '静安', status: 'RAW' }, { id: 12, name: '活动二', location: '外滩', status: 'RAW' }], images: [{ id: 21 }, { id: 22 }] } } }),
  noteImage: vi.fn().mockResolvedValue({ data: new Blob(['image']) }),
  updateActivity: vi.fn(),
  deleteActivity: vi.fn(),
  deleteNotes: vi.fn().mockResolvedValue({ data: { data: { deleted_count: 1, deleted_ids: [1] } } }),
  approveNotes: vi.fn().mockResolvedValue({ data: { data: { approved_count: 1, approved_ids: [1] } } }),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })

describe('ActivitiesView', () => {
  it('renders crawled activities with city names, Chinese review status and pagination', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('周末艺术展推文')
    expect(wrapper.text()).toContain('上海')
    expect(wrapper.text()).toContain('待审核')
    expect(wrapper.text()).not.toContain('新增活动')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).toContain('发布时间')
    expect(wrapper.text()).toContain('识别活动')
    expect(wrapper.getComponent(ElPagination).props('pageSizes')).toEqual([10, 20, 50, 100])
    expect(mocks.notes).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))
  })

  it('shows unknown activity dates as pending confirmation', async () => {
    mocks.notes.mockResolvedValueOnce({ data: { data: { items: [{ id: 2, title: '日期未知推文', city_code: 'shanghai', published_at: null, created_at: null, review_status: 'PENDING', activity_count: 1 }] }, pagination: { page: 1, page_size: 20, total: 1 } } })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('日期未知推文')
    expect(wrapper.text()).toContain('待确认')
  })

  it('batch deletes only explicitly selected activities', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    wrapper.getComponent(ElTable).vm.$emit('selection-change', [{ id: 1 }])
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text().includes('批量删除'))!
    expect(button.attributes('disabled')).toBeUndefined()

    await button.trigger('click')
    await flushPromises()

    expect(mocks.deleteNotes).toHaveBeenCalledWith([1])
    expect(mocks.notes).toHaveBeenCalledTimes(2)
  })

  it('batch approves selected activities and refreshes the list', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text().includes('批量通过'))!
    expect(button).toBeDefined()
    expect(button.attributes('disabled')).toBeDefined()

    wrapper.getComponent(ElTable).vm.$emit('selection-change', [{ id: 1 }])
    await flushPromises()
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    await flushPromises()

    expect(mocks.approveNotes).toHaveBeenCalledWith([1])
    expect(mocks.notes).toHaveBeenCalledTimes(2)
  })

  it('opens a wide detail drawer with source note images and releases blob URLs', async () => {
    const createObjectURL = vi.fn().mockReturnValueOnce('blob:first').mockReturnValueOnce('blob:second')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    expect(wrapper.getComponent(ElDrawer).props('size')).toBe('70%')
    expect(wrapper.text()).toContain('周末艺术展推文')
    expect(wrapper.text()).toContain('活动一')
    expect(wrapper.text()).toContain('活动二')
    expect(wrapper.text()).toContain('来源页面图片')
    expect(wrapper.findAllComponents(ElImage)).toHaveLength(2)
    expect(mocks.noteImage.mock.calls).toEqual([[1, 21], [1, 22]])
    expect(createObjectURL).toHaveBeenCalledTimes(2)

    wrapper.getComponent(ElDrawer).vm.$emit('closed')
    await flushPromises()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:first')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:second')
  })

  it('shows an Element Plus empty state when the source note has no images', async () => {
    mocks.note.mockResolvedValueOnce({ data: { data: { id: 1, title: '无图笔记', content: '', source_url: 'https://xhs/no-image', review_status: 'PENDING', activities: [], images: [] } } })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    expect(wrapper.getComponent(ElEmpty).props('description')).toBe('暂无来源图片')
  })
})
