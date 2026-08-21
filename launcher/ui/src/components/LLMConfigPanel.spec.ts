import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import LLMConfigPanel from './LLMConfigPanel.vue'
import type { SystemConfig } from '@/api/client'

// Mock 整个 @/api/client — 不发真 HTTP
const saveSystemConfigMock = vi.fn()
const getSystemConfigMock = vi.fn()

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return {
    ...actual,
    getSystemConfig: () => getSystemConfigMock(),
    saveSystemConfig: (payload: Partial<SystemConfig>) => saveSystemConfigMock(payload),
  }
})

// 默认 SystemConfig:全空字符串,字段对齐 launcher client.ts
function makeSystemConfig(over: Partial<SystemConfig> = {}): SystemConfig {
  return {
    minimax_api_key: '',
    minimax_base_url: '',
    minimax_model: '',
    minimax_vision_model: '',
    minimax_timeout_seconds: '60',
    minimax_concurrency: '1',
    ocr_enabled: 'false',
    ocr_language: 'ch',
    ocr_min_confidence: '0.5',
    ocr_parallel_workers: '1',
    opencli_bin: '',
    chrome_bin: '',
    chrome_user_data_dir: '',
    data_dir: '/tmp/test',
    log_dir: '/tmp/test/logs',
    ...over,
  }
}

describe('LLMConfigPanel', () => {
  beforeEach(() => {
    saveSystemConfigMock.mockReset()
    saveSystemConfigMock.mockResolvedValue({
      ok: true,
      saved_keys: ['OCR_ENABLED'],
      restart: { api: true, worker: true },
    })
  })

  it('mounts and renders the LLM card', async () => {
    getSystemConfigMock.mockResolvedValue(makeSystemConfig())
    const wrapper = mount(LLMConfigPanel)
    await flushPromises()
    expect(wrapper.find('[data-test="llm-card"]').exists()).toBe(true)
  })

  it('auto-saves OCR_ENABLED when switch toggled (no need to click save)', async () => {
    // 改动 5:OCR 开关 @change 时自动 PUT,无需用户点保存按钮。
    // 关联 spec: docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 5
    // 关联设计: docs/packaging-design.md §3.7
    getSystemConfigMock.mockResolvedValue(makeSystemConfig({ ocr_enabled: 'false' }))
    const wrapper = mount(LLMConfigPanel)
    await flushPromises()

    const ocrSwitchRoot = wrapper.find('[data-test="ocr-enabled"]')
    expect(ocrSwitchRoot.exists()).toBe(true)

    // el-switch 渲染成 <div><input type="checkbox"></div>,找内部 input 设值并 trigger change
    const ocrInput = ocrSwitchRoot.find('input[type="checkbox"]')
    expect(ocrInput.exists()).toBe(true)
    await ocrInput.setValue(true)
    await ocrSwitchRoot.trigger('change')
    await flushPromises()

    expect(saveSystemConfigMock).toHaveBeenCalled()
    const calls = saveSystemConfigMock.mock.calls
    const lastCall = calls.at(-1)?.[0] as Partial<SystemConfig> | undefined
    expect(lastCall?.ocr_enabled).toBe('true')
  })

  it('does not require clicking the save button for OCR toggle', async () => {
    // 用户经常拨了开关但忘了点保存 — 改动 5 把 OCR 开关变成'实时同步'控件,
    // 不应该依赖保存按钮。断言:拨动一次开关,saveSystemConfig 已被调用且包含 ocr_enabled。
    getSystemConfigMock.mockResolvedValue(makeSystemConfig({ ocr_enabled: 'false' }))
    const wrapper = mount(LLMConfigPanel)
    await flushPromises()
    saveSystemConfigMock.mockClear()

    const ocrSwitchRoot = wrapper.find('[data-test="ocr-enabled"]')
    const ocrInput = ocrSwitchRoot.find('input[type="checkbox"]')
    await ocrInput.setValue(true)
    await ocrSwitchRoot.trigger('change')
    await flushPromises()

    const ocrCalls = saveSystemConfigMock.mock.calls.filter((c) => {
      const payload = c[0] as Partial<SystemConfig>
      return Object.prototype.hasOwnProperty.call(payload, 'ocr_enabled')
    })
    expect(ocrCalls.length).toBeGreaterThan(0)
  })
})
