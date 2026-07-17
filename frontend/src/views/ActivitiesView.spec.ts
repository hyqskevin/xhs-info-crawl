import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElDrawer, ElEmpty, ElImage, ElMessageBox, ElPagination, ElTable } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ActivitiesView from './ActivitiesView.vue'

const mocks = vi.hoisted(() => ({
  activities: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 1, name: '周末艺术展', city_code: 'shanghai', start_time: '2026-07-18T10:00:00Z', location: '静安', status: 'RAW' }] }, pagination: { page: 1, page_size: 20, total: 41 } } }),
  settings: vi.fn().mockResolvedValue({ data: { data: [{ id: 1, name: '上海', code: 'shanghai', enabled: true }] } }),
  activity: vi.fn().mockResolvedValue({ data: { data: { id: 1, name: '周末艺术展', city_code: 'shanghai', start_time: '2026-07-18T10:00:00Z', location: '静安', status: 'RAW', note: { id: 7, title: '宁波活动图集', content: '页面正文', source_url: 'https://xhs/note-7', status: 'PROCESSED' }, images: [{ id: 11, url: '/activities/1/images/11' }, { id: 12, url: '/activities/1/images/12' }] } } }),
  activityImage: vi.fn().mockResolvedValue({ data: new Blob(['image']) }),
  updateActivity: vi.fn(),
  deleteActivity: vi.fn(),
  deleteActivities: vi.fn().mockResolvedValue({ data: { data: { deleted_count: 1, deleted_ids: [1] } } }),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })

describe('ActivitiesView', () => {
  it('renders crawled activities with city names, Chinese review status and pagination', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('周末艺术展')
    expect(wrapper.text()).toContain('上海')
    expect(wrapper.text()).toContain('待审核')
    expect(wrapper.text()).not.toContain('新增活动')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).toContain('活动时间')
    expect(wrapper.getComponent(ElPagination).props('pageSizes')).toEqual([10, 20, 50, 100])
    expect(mocks.activities).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))
  })

  it('shows unknown activity dates as pending confirmation', async () => {
    mocks.activities.mockResolvedValueOnce({ data: { data: { items: [{ id: 2, name: '日期未知活动', city_code: 'shanghai', start_time: null, location: '静安', status: 'NEEDS_REVIEW' }] }, pagination: { page: 1, page_size: 20, total: 1 } } })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('日期未知活动')
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

    expect(mocks.deleteActivities).toHaveBeenCalledWith([1])
    expect(mocks.activities).toHaveBeenCalledTimes(2)
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
    expect(wrapper.text()).toContain('宁波活动图集')
    expect(wrapper.text()).toContain('来源页面图片')
    expect(wrapper.findAllComponents(ElImage)).toHaveLength(2)
    expect(mocks.activityImage.mock.calls).toEqual([[1, 11], [1, 12]])
    expect(createObjectURL).toHaveBeenCalledTimes(2)

    wrapper.getComponent(ElDrawer).vm.$emit('closed')
    await flushPromises()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:first')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:second')
  })

  it('shows an Element Plus empty state when the source note has no images', async () => {
    mocks.activity.mockResolvedValueOnce({ data: { data: { id: 1, name: '周末艺术展', city_code: 'shanghai', start_time: '2026-07-18T10:00:00Z', location: '静安', status: 'RAW', note: { id: 7, title: '无图笔记', content: '', source_url: 'https://xhs/no-image', status: 'PROCESSED' }, images: [] } } })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    expect(wrapper.getComponent(ElEmpty).props('description')).toBe('暂无来源图片')
  })
})
