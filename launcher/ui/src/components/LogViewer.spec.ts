import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LogViewer from './LogViewer.vue'

describe('LogViewer', () => {
  it('renders title', () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    expect(wrapper.text()).toContain('日志')
  })

  it('shows empty state when no lines', () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    expect(wrapper.text()).toContain('暂无日志')
  })

  it('renders log lines', () => {
    const lines = ['14:30:01 API 启动成功', '14:30:03 Worker 启动成功']
    const wrapper = mount(LogViewer, { props: { lines } })
    const items = wrapper.findAll('[data-test="log-line"]')
    expect(items).toHaveLength(2)
    expect(wrapper.text()).toContain('14:30:01 API 启动成功')
    expect(wrapper.text()).toContain('14:30:03 Worker 启动成功')
  })

  it('emits refresh event when refresh button clicked', async () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    await wrapper.get('[data-test="refresh-logs-btn"]').trigger('click')
    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  it('emits open-dir event when open dir button clicked', async () => {
    const wrapper = mount(LogViewer, { props: { lines: [] } })
    await wrapper.get('[data-test="open-log-dir-btn"]').trigger('click')
    expect(wrapper.emitted('open-dir')).toBeTruthy()
  })

  it('applies monospace font to log lines', () => {
    const wrapper = mount(LogViewer, { props: { lines: ['line1'] } })
    const line = wrapper.get('[data-test="log-line"]')
    expect(line.classes()).toContain('log-line')
  })
})
