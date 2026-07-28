import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import TasksView from './TasksView.vue'

const mocks = vi.hoisted(() => ({
  tasks: vi.fn().mockResolvedValue({
    data: {
      data: {
        items: [
          { id: 8, type: 'mixed', status: 'COMPLETED_WITH_ERRORS', total_notes: 10, downloaded_notes: 7, ocr_notes: 7, extracted_notes: 7, success_notes: 7, failed_notes: 1, skipped_notes: 2, current_stage: null, error_message: '一条失败', created_at: '2026-07-28T00:46:14' },
          { id: 9, type: 'mixed', status: 'STOPPED', total_notes: 0, downloaded_notes: 0, ocr_notes: 0, extracted_notes: 0, success_notes: 0, failed_notes: 0, skipped_notes: 0, current_stage: null, error_message: null, created_at: '2026-07-27T16:00:00' },
        ],
      },
    },
  }),
  logs: vi.fn(),
  batchDeleteTasks: vi.fn().mockResolvedValue({ data: { data: { deleted_count: 2, deleted_ids: [8, 9] } } }),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

describe('TasksView', () => {
  it('is a crawl monitoring page without trigger controls', async () => {
    const wrapper = mount(TasksView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('完成但有错误')
    expect(wrapper.text()).toContain('已下载')
    expect(wrapper.text()).toContain('OCR 完成')
    expect(wrapper.text()).toContain('提取完成')
    expect(wrapper.text()).toContain('已跳过')
    expect(wrapper.text()).toContain('100%')
    expect(wrapper.text()).toContain('抓取日志')
    expect(wrapper.text()).not.toContain('开始抓取')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).not.toContain('关键词，逗号分隔')
  })

  it('sends batch delete request with selected ids when the user confirms the prompt', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mount(TasksView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    mocks.batchDeleteTasks.mockClear()
    mocks.tasks.mockClear()

    // ElTable selection 在 jsdom 下 hover 触发，绕开点击直接 emit selection-change
    const table = wrapper.findComponent({ name: 'ElTable' })
    const items = [
      { id: 8, type: 'mixed', status: 'COMPLETED_WITH_ERRORS', total_notes: 10, downloaded_notes: 7, ocr_notes: 7, extracted_notes: 7, success_notes: 7, failed_notes: 1, skipped_notes: 2, current_stage: null, error_message: '一条失败' },
      { id: 9, type: 'mixed', status: 'STOPPED', total_notes: 0, downloaded_notes: 0, ocr_notes: 0, extracted_notes: 0, success_notes: 0, failed_notes: 0, skipped_notes: 0, current_stage: null, error_message: null },
    ]
    table.vm.$emit('selection-change', items)
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const batchButton = buttons.find((btn) => btn.text().includes('批量删除') && !btn.element.disabled)!
    await batchButton.trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(mocks.batchDeleteTasks).toHaveBeenCalledWith([8, 9])
    expect(mocks.tasks).toHaveBeenCalled()
  })

  it('displays created_at converted from UTC to Asia/Shanghai (+8h)', async () => {
    const wrapper = mount(TasksView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    // 后端 created_at 为 UTC naive：00:46:14 UTC = 东八区 08:46:14
    expect(wrapper.text()).toContain('2026-07-28 08:46:14')
    expect(wrapper.text()).toContain('2026-07-28 00:00:00')
    expect(wrapper.text()).not.toContain('00:46:14Z')
  })

  it('shows log timestamps converted to Asia/Shanghai in the drawer', async () => {
    mocks.logs.mockResolvedValueOnce({
      data: { data: [{ id: 1, level: 'ERROR', message: '笔记处理失败', created_at: '2026-07-28T00:46:07' }] },
    })
    const wrapper = mount(TasksView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text().includes('日志'))!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('笔记处理失败')
    expect(wrapper.text()).toContain('2026-07-28 08:46:07')
  })
})
