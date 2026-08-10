import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

// mock API client
vi.mock('@/api/client', () => ({
  fetchStatus: vi.fn().mockResolvedValue({
    api: { state: 'running', pid: 1 },
    worker: { state: 'running', pid: 2 },
    beat: { state: 'running', pid: 3 },
  }),
  restartService: vi.fn().mockResolvedValue({ ok: true }),
  stopAll: vi.fn().mockResolvedValue({ ok: true }),
  testOpencli: vi.fn().mockResolvedValue({ ok: true, version: '1.8.6', reason: '', message: '连接正常' }),
  getOpencliDownloadUrl: vi.fn().mockResolvedValue({ url: 'https://opencli.info/download' }),
  getOcrStatus: vi.fn().mockResolvedValue({ status: 'not_installed', version: '' }),
  installOcr: vi.fn().mockResolvedValue({ ok: true, message: '安装已启动' }),
  getOcrInstallProgress: vi.fn().mockResolvedValue({ active: false, percent: 0, message: '' }),
  testOcr: vi.fn().mockResolvedValue({ ok: true, text: '测试', latency_ms: 100 }),
  getLogsTail: vi.fn().mockResolvedValue({ lines: ['line1', 'line2'] }),
  setBaseUrl: vi.fn(),
  initBaseUrlFromLocation: vi.fn(),
}))

describe('App', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('renders app title in top app bar', () => {
    const wrapper = mount(App)
    expect(wrapper.get('[data-test="app-title"]').text()).toContain('小红书活动信息抓取系统')
  })

  it('renders ServiceStatus component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'ServiceStatus' }).exists()).toBe(true)
  })

  it('renders OpenCLIPanel component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'OpenCLIPanel' }).exists()).toBe(true)
  })

  it('renders OcrPanel component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'OcrPanel' }).exists()).toBe(true)
  })

  it('renders LogViewer component', () => {
    const wrapper = mount(App)
    expect(wrapper.findComponent({ name: 'LogViewer' }).exists()).toBe(true)
  })

  it('renders bottom action bar with open-web button', () => {
    const wrapper = mount(App)
    expect(wrapper.find('[data-test="open-web-btn"]').exists()).toBe(true)
  })

  it('renders stop-all button in bottom action bar', () => {
    const wrapper = mount(App)
    expect(wrapper.find('[data-test="app-stop-all-btn"]').exists()).toBe(true)
  })

  it('renders exit button in bottom action bar', () => {
    const wrapper = mount(App)
    expect(wrapper.find('[data-test="exit-btn"]').exists()).toBe(true)
  })

  it('fetches status on mount', async () => {
    const { fetchStatus } = await import('@/api/client')
    mount(App)
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchStatus).toHaveBeenCalled()
  })

  it('fetches logs on mount', async () => {
    const { getLogsTail } = await import('@/api/client')
    mount(App)
    await vi.advanceTimersByTimeAsync(0)
    expect(getLogsTail).toHaveBeenCalled()
  })
})
