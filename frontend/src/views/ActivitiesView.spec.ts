import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox, ElPagination, ElTable } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ActivitiesView from './ActivitiesView.vue'

const mocks = vi.hoisted(() => ({
  activities: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 1, name: '周末艺术展', city_code: 'shanghai', start_time: '2026-07-18T10:00:00Z', location: '静安', status: 'RAW' }] }, pagination: { page: 1, page_size: 20, total: 41 } } }),
  settings: vi.fn().mockResolvedValue({ data: { data: [{ id: 1, name: '上海', code: 'shanghai', enabled: true }] } }),
  activity: vi.fn(),
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
})
