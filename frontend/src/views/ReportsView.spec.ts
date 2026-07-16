import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import ReportsView from './ReportsView.vue'

const { reports, generateReport } = vi.hoisted(() => ({
  reports: vi.fn().mockResolvedValue({ data: { data: [{ id: 3, week: '2026-W29', cities: 'shanghai', activity_count: 2, status: 'GENERATED' }] } }),
  generateReport: vi.fn().mockResolvedValue({ data: { data: { id: 4 } } }),
}))
vi.mock('@/api/client', () => ({ api: { reports, generateReport, report: vi.fn() } }))

describe('ReportsView', () => {
  it('renders report formats and generates a weekly report', async () => {
    const wrapper = mount(ReportsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('2026-W29')
    expect(wrapper.text()).toContain('Markdown')
    expect(wrapper.text()).toContain('Excel')
    await wrapper.findAll('button').find((button) => button.text().includes('生成周报'))!.trigger('click')
    await flushPromises()
    expect(generateReport).toHaveBeenCalledWith({ week: '2025-W29', cities: ['shanghai'] })
  })
})
