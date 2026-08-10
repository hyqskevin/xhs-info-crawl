import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OpenCLIPanel from './OpenCLIPanel.vue'
import type { OpencliTestResult } from '@/api/client'

describe('OpenCLIPanel', () => {
  it('renders title and undetected chip when result is null', () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: false } })
    expect(wrapper.text()).toContain('OpenCLI 连接')
    expect(wrapper.text()).toContain('未检测')
  })

  it('renders success chip and version when result ok', () => {
    const result: OpencliTestResult = { ok: true, version: '1.8.6', reason: '', message: '连接正常' }
    const wrapper = mount(OpenCLIPanel, { props: { result, loading: false } })
    expect(wrapper.text()).toContain('已连接')
    expect(wrapper.text()).toContain('1.8.6')
  })

  it('renders error chip and message when result not ok', () => {
    const result: OpencliTestResult = { ok: false, version: '', reason: 'not_installed', message: '未安装 OpenCLI' }
    const wrapper = mount(OpenCLIPanel, { props: { result, loading: false } })
    expect(wrapper.text()).toContain('未连接')
    expect(wrapper.text()).toContain('未安装 OpenCLI')
  })

  it('emits test event when test button clicked', async () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: false } })
    await wrapper.get('[data-test="test-opencli-btn"]').trigger('click')
    expect(wrapper.emitted('test')).toBeTruthy()
  })

  it('emits download event when download button clicked', async () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: false } })
    await wrapper.get('[data-test="download-opencli-btn"]').trigger('click')
    expect(wrapper.emitted('download')).toBeTruthy()
  })

  it('disables test button when loading', () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: true } })
    const btn = wrapper.get('[data-test="test-opencli-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('shows loading text when loading', () => {
    const wrapper = mount(OpenCLIPanel, { props: { result: null, loading: true } })
    expect(wrapper.text()).toContain('测试中')
  })
})
