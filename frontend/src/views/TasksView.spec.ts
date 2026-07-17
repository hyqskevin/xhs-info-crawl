import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import TasksView from './TasksView.vue'

const mocks = vi.hoisted(() => ({ tasks: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 8, type: 'mixed', status: 'COMPLETED_WITH_ERRORS', total_notes: 10, downloaded_notes: 9, ocr_notes: 8, extracted_notes: 7, success_notes: 7, failed_notes: 1, current_stage: null, error_message: '一条失败' }] } } }), logs: vi.fn() }))
vi.mock('@/api/client', () => ({ api: mocks }))

describe('TasksView', () => {
  it('is a crawl monitoring page without trigger controls', async () => {
    const wrapper = mount(TasksView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('完成但有错误')
    expect(wrapper.text()).toContain('已下载')
    expect(wrapper.text()).toContain('OCR 完成')
    expect(wrapper.text()).toContain('提取完成')
    expect(wrapper.text()).toContain('抓取日志')
    expect(wrapper.text()).not.toContain('开始抓取')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).not.toContain('关键词，逗号分隔')
  })
})
