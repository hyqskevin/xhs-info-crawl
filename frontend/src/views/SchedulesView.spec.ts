import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox, ElSelect, ElTimePicker } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SchedulesView from './SchedulesView.vue'

const mocks = vi.hoisted(() => ({
  settings: vi.fn().mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
    ? [{ id: 1, name: '宁波', code: 'nb', keywords: [], recent_filter: '一周内', enabled: true }]
    : [{ id: 9, username: '活动博主', profile_url: 'https://xhs/u/9', city_codes: ['nb'], enabled: true }] } })),
  keywordGroups: vi.fn().mockResolvedValue({ data: { data: { items: [
    { id: 11, name: '展览组', words: ['展览'], city_codes: ['nb'], enabled: true },
  ] } } }),
  bloggerGroups: vi.fn().mockResolvedValue({ data: { data: { items: [
    { id: 21, name: '本地号', blogger_ids: [9], enabled: true },
  ] } } }),
  createBloggerGroup: vi.fn().mockResolvedValue({ data: { data: { id: 22 } } }),
  updateBloggerGroupMembers: vi.fn().mockResolvedValue({ data: { data: {} } }),
  deleteBloggerGroup: vi.fn().mockResolvedValue({ data: { data: {} } }),
  schedules: vi.fn().mockResolvedValue({ data: { data: { items: [
    { id: 31, name: '每周一早上', enabled: true, day_of_week: 1, hour: 9, minute: 30, city_code: 'nb',
      keyword_group_ids: [11], blogger_group_ids: [21], recent_filter: '一周内',
      last_task: { id: 41, status: 'COMPLETED', started_at: '2026-07-20T09:30:00Z' } },
    { id: 32, name: '每周三下午', enabled: false, day_of_week: 3, hour: 14, minute: 0, city_code: 'nb',
      keyword_group_ids: [], blogger_group_ids: [21], recent_filter: null, last_task: null },
  ] } } }),
  createSchedule: vi.fn().mockResolvedValue({ data: { data: { id: 33 } } }),
  updateSchedule: vi.fn().mockResolvedValue({ data: { data: { id: 31 } } }),
  deleteSchedule: vi.fn().mockResolvedValue({ data: { data: { deleted_id: 31 } } }),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })

function mountView() {
  return mount(SchedulesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
}

describe('SchedulesView', () => {
  it('lists schedules with weekly period, groups and last run status', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(mocks.schedules).toHaveBeenCalled()
    expect(wrapper.text()).toContain('每周一早上')
    expect(wrapper.text()).toContain('每周一 09:30')
    expect(wrapper.text()).toContain('每周三 14:00')
    expect(wrapper.text()).toContain('宁波')
    expect(wrapper.text()).toContain('展览组')
    expect(wrapper.text()).toContain('本地号')
    expect(wrapper.text()).toContain('成功')
    expect(wrapper.text()).toContain('未执行')
    expect(wrapper.text()).toContain('停用')
  })

  it('creates a schedule with weekday, time, city and both group kinds', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增定时任务'))!.trigger('click')
    await flushPromises()

    const dialog = document.body.querySelector('.el-dialog')!
    const nameInput = dialog.querySelector<HTMLInputElement>('input[aria-label="定时任务名称"]')!
    nameInput.value = '周五晚间'
    nameInput.dispatchEvent(new Event('input'))

    const dialogWrapper = wrapper.findComponent({ name: 'ElDialog' })
    const selects = dialogWrapper.findAllComponents(ElSelect)
    // 顺序：星期 / 城市 / 关键词组 / 博主组 / 时间范围
    selects[0].vm.$emit('update:modelValue', 5)
    selects[1].vm.$emit('update:modelValue', 'nb')
    selects[2].vm.$emit('update:modelValue', [11])
    selects[3].vm.$emit('update:modelValue', [21])
    const timePicker = dialogWrapper.findComponent(ElTimePicker)
    timePicker.vm.$emit('update:modelValue', '21:15')
    await flushPromises()

    const saveButton = Array.from(dialog.querySelectorAll('button')).find((b) => b.textContent?.includes('保存'))!
    saveButton.dispatchEvent(new Event('click'))
    await flushPromises()

    expect(mocks.createSchedule).toHaveBeenCalledWith(expect.objectContaining({
      name: '周五晚间',
      day_of_week: 5,
      hour: 21,
      minute: 15,
      city_code: 'nb',
      keyword_group_ids: [11],
      blogger_group_ids: [21],
    }))
  })

  it('blocks submission when neither group kind is selected', async () => {
    const warningSpy = vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('新增定时任务'))!.trigger('click')
    await flushPromises()

    const dialog = document.body.querySelector('.el-dialog')!
    const nameInput = dialog.querySelector<HTMLInputElement>('input[aria-label="定时任务名称"]')!
    nameInput.value = '空组任务'
    nameInput.dispatchEvent(new Event('input'))
    const dialogWrapper = wrapper.findComponent({ name: 'ElDialog' })
    dialogWrapper.findAllComponents(ElSelect)[1].vm.$emit('update:modelValue', 'nb')
    await flushPromises()
    const saveButton = Array.from(dialog.querySelectorAll('button')).find((b) => b.textContent?.includes('保存'))!
    saveButton.dispatchEvent(new Event('click'))
    await flushPromises()

    expect(mocks.createSchedule).not.toHaveBeenCalled()
    expect(warningSpy).toHaveBeenCalledWith(expect.stringContaining('关键词组或博主组'))
    warningSpy.mockRestore()
  })

  it('deletes a schedule after confirmation', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text().includes('删除'))!.trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(mocks.deleteSchedule).toHaveBeenCalledWith(31)
  })

  it('manages keyword groups and blogger groups in the second tab', async () => {
    const wrapper = mountView()
    await flushPromises()
    const groupTab = wrapper.findAll('input[type="radio"]').find((r) => r.attributes('value') === 'groups')!
    await groupTab.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('关键词组')
    expect(wrapper.text()).toContain('博主组')
    // 默认展示关键词组管理（复用现有组件）
    expect(wrapper.text()).toContain('展览组')
    expect(mocks.keywordGroups).toHaveBeenCalled()

    const bloggerSubTab = wrapper.findAll('input[type="radio"]').find((r) => r.attributes('value') === 'blogger')!
    await bloggerSubTab.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('本地号')
    expect(wrapper.text()).toContain('活动博主')
    expect(mocks.bloggerGroups).toHaveBeenCalled()
  })
})
