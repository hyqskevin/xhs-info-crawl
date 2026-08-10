import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OcrPanel from './OcrPanel.vue'
import type { OcrStatus, OcrInstallProgress, OcrTestResult } from '@/api/client'

describe('OcrPanel', () => {
  const notInstalledStatus: OcrStatus = { status: 'not_installed', version: '' }
  const installedStatus: OcrStatus = { status: 'installed', version: '3.7.0' }
  const emptyProgress: OcrInstallProgress = { active: false, percent: 0, message: '' }

  it('renders title and not_installed chip', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('OCR 增强')
    expect(wrapper.text()).toContain('PaddleOCR 图片本地识别')
    expect(wrapper.text()).toContain('未安装')
  })

  it('renders installed chip with version', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('已安装')
    expect(wrapper.text()).toContain('3.7.0')
  })

  it('renders installing chip when status is installing', () => {
    const installingStatus: OcrStatus = { status: 'installing', version: '' }
    const wrapper = mount(OcrPanel, {
      props: { status: installingStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('安装中')
  })

  it('emits install event when install button clicked', async () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    await wrapper.get('[data-test="install-ocr-btn"]').trigger('click')
    expect(wrapper.emitted('install')).toBeTruthy()
  })

  it('emits test event when test button clicked', async () => {
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    await wrapper.get('[data-test="test-ocr-btn"]').trigger('click')
    expect(wrapper.emitted('test')).toBeTruthy()
  })

  it('disables install button when installing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: { active: true, percent: 30, message: '下载中' }, testResult: null, installing: true, testing: false },
    })
    const btn = wrapper.get('[data-test="install-ocr-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('shows progress bar when installing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: { active: true, percent: 45, message: '下载中' }, testResult: null, installing: true, testing: false },
    })
    expect(wrapper.find('[data-test="install-progress"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('45')
    expect(wrapper.text()).toContain('下载中')
  })

  it('hides progress bar when not installing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: notInstalledStatus, progress: emptyProgress, testResult: null, installing: false, testing: false },
    })
    expect(wrapper.find('[data-test="install-progress"]').exists()).toBe(false)
  })

  it('shows test success result with text and latency', () => {
    const testResult: OcrTestResult = { ok: true, text: '识别到的文字', latency_ms: 1234 }
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('识别到的文字')
    expect(wrapper.text()).toContain('1234')
  })

  it('shows test error result with message', () => {
    const testResult: OcrTestResult = { ok: false, reason: 'ocr_disabled', message: 'OCR 未启用' }
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult, installing: false, testing: false },
    })
    expect(wrapper.text()).toContain('OCR 未启用')
  })

  it('shows testing text when testing', () => {
    const wrapper = mount(OcrPanel, {
      props: { status: installedStatus, progress: emptyProgress, testResult: null, installing: false, testing: true },
    })
    expect(wrapper.text()).toContain('测试中')
  })
})
