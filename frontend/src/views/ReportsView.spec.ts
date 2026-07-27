import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElDatePicker, ElMessage, ElSelect } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ReportsView from './ReportsView.vue'

const { reports, generateReport, settings, downloadReport, deleteReport, report, confirm } = vi.hoisted(() => ({
  reports: vi.fn().mockResolvedValue({ data: { data: [{ id: 3, week: '2026-W29', cities: ['nb'], note_count: 1, activity_count: 2, status: 'GENERATED' }] } }),
  generateReport: vi.fn().mockResolvedValue({ data: { data: { id: 4 } } }),
  settings: vi.fn().mockResolvedValue({ data: { data: [{ id: 1, name: '宁波', code: 'nb', enabled: true }] } }),
  downloadReport: vi.fn().mockResolvedValue({ data: new Blob(['report']), headers: {} }),
  deleteReport: vi.fn().mockResolvedValue({ data: { data: { id: 3 } } }),
  report: vi.fn().mockResolvedValue({ data: { data: { content: '# 本周推文周报\n\n## 活动标题\n\n- 时间：7.20\n- 地点：宁波' } } }),
  confirm: vi.fn().mockResolvedValue('confirm'),
}))
vi.mock('@/api/client', () => ({ api: { reports, generateReport, settings, downloadReport, deleteReport, report } }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<typeof ElementPlus>('element-plus')
  return {
    ...actual,
    ElMessageBox: { confirm },
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  }
})

describe('ReportsView', () => {
  afterEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('renders report formats and generates a weekly report', async () => {
    const wrapper = mount(ReportsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('2026-W29')
    expect(wrapper.text()).toContain('宁波')
    expect(wrapper.text()).toContain('Markdown')
    expect(wrapper.text()).toContain('Excel')
    expect(wrapper.text()).toContain('推文数')
    wrapper.getComponent(ElDatePicker).vm.$emit('update:modelValue', new Date('2026-07-13T00:00:00'))
    wrapper.getComponent(ElSelect).vm.$emit('update:modelValue', 'nb')
    await wrapper.findAll('button').find((button) => button.text().includes('生成周报'))!.trigger('click')
    await flushPromises()
    expect(generateReport).toHaveBeenCalledWith({ week: '2026-W29', cities: ['nb'] })
    expect(wrapper.getComponent(ElSelect).props('multiple')).not.toBe(true)
    await wrapper.findAll('button').find((button) => button.text().includes('Markdown'))!.trigger('click')
    await flushPromises()
    expect(downloadReport).toHaveBeenCalledWith(3, 'md')
  })

  it('shows the backend reason when no approved activity can be exported', async () => {
    generateReport.mockRejectedValueOnce({ response: { data: { message: '所选城市和周次没有已通过活动，请先在活动管理中审核通过' } } })
    const error = vi.spyOn(ElMessage, 'error')
    const wrapper = mount(ReportsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    wrapper.getComponent(ElDatePicker).vm.$emit('update:modelValue', new Date('2026-07-13T00:00:00'))
    wrapper.getComponent(ElSelect).vm.$emit('update:modelValue', 'nb')

    await wrapper.findAll('button').find((button) => button.text().includes('生成周报'))!.trigger('click')
    await flushPromises()

    expect(error).toHaveBeenCalledWith('所选城市和周次没有已通过活动，请先在活动管理中审核通过')
  })

  it('deletes a report after confirmation and reloads the list', async () => {
    const wrapper = mount(ReportsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text().includes('删除'))!.trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalled()
    expect(deleteReport).toHaveBeenCalledWith(3)
    expect(reports).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('2026-W29')
  })

  it('renders the preview as sanitized markdown HTML', async () => {
    const wrapper = mount(ReportsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text().includes('预览'))!.trigger('click')
    await flushPromises()

    expect(report).toHaveBeenCalledWith(3)
    const previewEl = wrapper.find('.report-preview')
    expect(previewEl.exists()).toBe(true)
    expect(previewEl.html()).toContain('<h1>本周推文周报</h1>')
    expect(previewEl.html()).toContain('<h2>活动标题</h2>')
  })
})
