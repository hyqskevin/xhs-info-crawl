import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElDatePicker, ElMessage, ElSelect } from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import ReportsView from './ReportsView.vue'

const { reports, generateReport, settings, downloadReport } = vi.hoisted(() => ({
  reports: vi.fn().mockResolvedValue({ data: { data: [{ id: 3, week: '2026-W29', cities: ['nb'], activity_count: 2, status: 'GENERATED' }] } }),
  generateReport: vi.fn().mockResolvedValue({ data: { data: { id: 4 } } }),
  settings: vi.fn().mockResolvedValue({ data: { data: [{ id: 1, name: '宁波', code: 'nb', enabled: true }] } }),
  downloadReport: vi.fn().mockResolvedValue({ data: new Blob(['report']), headers: {} }),
}))
vi.mock('@/api/client', () => ({ api: { reports, generateReport, settings, downloadReport, report: vi.fn() } }))

describe('ReportsView', () => {
  it('renders report formats and generates a weekly report', async () => {
    const wrapper = mount(ReportsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('2026-W29')
    expect(wrapper.text()).toContain('宁波')
    expect(wrapper.text()).toContain('Markdown')
    expect(wrapper.text()).toContain('Excel')
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
})
