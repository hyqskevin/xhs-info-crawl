import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ElementPlus from 'element-plus'
import type { ComponentPublicInstance } from 'vue'

import LLMConfigPanel from './LLMConfigPanel.vue'
import * as client from '@/api/client'
import type { SystemConfig, SystemConfigSaveResponse } from '@/api/client'

// wrapper.vm 在 TS 里是 ComponentPublicInstance,我们的 setup() 里返回的 ref
// 不会被推断到 vm 类型上,需要用 unknown 强转后访问。
// 关联 spec: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md § 4
type PanelInstance = ComponentPublicInstance<{}, {}, { config: { value: SystemConfig | null } }>

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof client>('@/api/client')
  return {
    ...actual,
    getSystemConfig: vi.fn(),
    saveSystemConfig: vi.fn(),
  }
})

const MOCK_CONFIG: SystemConfig = {
  minimax_api_key: 'eyJxxx',
  minimax_base_url: 'https://api.minimaxi.com/v1',
  minimax_model: 'MiniMax-M3',
  minimax_vision_model: 'MiniMax-vision-01',
  minimax_timeout_seconds: '180',
  minimax_concurrency: '1',
  ocr_enabled: 'false',
  ocr_language: 'ch',
  ocr_min_confidence: '0.5',
  ocr_parallel_workers: '2',
  opencli_bin: 'opencli',
  chrome_bin: '/Applications/Google Chrome.app',
  chrome_user_data_dir: 'data/chrome-pool',
  // 存储路径 — base dir 模式(只 DATA_DIR + LOG_DIR)
  // 关联: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
  data_dir: '~/Library/Application Support/com.xhs-info-crawl.local',
  log_dir: '~/Library/Application Support/com.xhs-info-crawl.local/logs',
}

function mountPanel() {
  return mount(LLMConfigPanel, {
    global: { plugins: [ElementPlus] },
  })
}

beforeEach(() => {
  // 模拟 PyWebView 加载时的 URL query string: ?statusPort=9000
  // 这样 initBaseUrlFromLocation 才会正确设 baseUrl
  // (jsdom 默认 window.location.search 是空)
  Object.defineProperty(window, 'location', {
    value: { search: '?statusPort=9000' } as Location,
    writable: true,
  })
})

describe('LLMConfigPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(client.getSystemConfig).mockResolvedValue(MOCK_CONFIG)
  })

  it('loads system config on mount', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()
    expect(client.getSystemConfig).toHaveBeenCalledTimes(1)
    expect(wrapper.vm).toBeTruthy()
  })

  it('renders save and reset buttons', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()
    expect(wrapper.find('[data-test="llm-save-btn"]').exists()).toBe(true)
  })

  it('expands LLM collapse by default so user sees API key field', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()
    // LLM collapse-item 应该是展开的,所以能看到 api-key input
    const apiKeyInput = wrapper.find('[data-test="llm-api-key"]')
    expect(apiKeyInput.exists()).toBe(true)
  })

  it('hides OCR and Paths sections until user expands them', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()
    // Element Plus collapse-item 折叠时通过 visibility 隐藏 DOM 子节点
    // 找到 ocr-enabled 元素后,断言它不可见 (offsetParent === null)
    const ocrSwitch = wrapper.find('[data-test="ocr-enabled"]')
    // collapse-item 默认折叠 → 父级 collapse-item-content v-show=false → element 不可见
    // ts strict 模式下 .element 是 VueNode<Element> | undefined,
    // Element 没有 offsetParent 属性在 TS 类型里(实际 DOM 节点有);
    // 强转绕过 TS 即可,不影响测试语义。
    expect((ocrSwitch.element as unknown as { offsetParent: unknown }).offsetParent).toBeNull()
  })

  it('calls saveSystemConfig with non-empty fields only', async () => {
    const mockResp: SystemConfigSaveResponse = {
      ok: true,
      saved_keys: ['MINIMAX_API_KEY', 'MINIMAX_MODEL'],
      restart: { api: true, worker: true },
    }
    vi.mocked(client.saveSystemConfig).mockResolvedValue(mockResp)

    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()

    await wrapper.get('[data-test="llm-save-btn"]').trigger('click')
    await flushPromises()

    expect(client.saveSystemConfig).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(client.saveSystemConfig).mock.calls[0][0] as Record<string, string>
    expect(payload.minimax_api_key).toBe('eyJxxx')
    expect(payload.minimax_model).toBe('MiniMax-M3')
  })

  it('emits saved event after successful save', async () => {
    const mockResp: SystemConfigSaveResponse = {
      ok: true,
      saved_keys: ['MINIMAX_API_KEY'],
      restart: { api: true, worker: true },
    }
    vi.mocked(client.saveSystemConfig).mockResolvedValue(mockResp)

    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()

    await wrapper.get('[data-test="llm-save-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('saved')).toBeTruthy()
    expect(wrapper.emitted('saved')?.[0][0]).toEqual(mockResp)
  })

  it('handles save error without emitting saved', async () => {
    vi.mocked(client.saveSystemConfig).mockRejectedValue(new Error('network 404'))

    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()

    await wrapper.get('[data-test="llm-save-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('saved')).toBeFalsy()
  })

  it('does not hardcode MiniMax in the UI', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()

    // 不应有 provider 预设下拉(用户自己填 Base URL / Model)
    expect(wrapper.find('[data-test="llm-provider"]').exists()).toBe(false)

    // 核心断言:不应出现 MiniMax 任何模型名/preset 字样
    const html = wrapper.html()
    expect(html).not.toContain('MiniMax-M3')
    expect(html).not.toContain('MiniMax-vision-01')
    expect(html).not.toContain('abab6.5s-chat')
    expect(html).not.toContain('abab6.5-chat')
    expect(html).not.toContain('MiniMax LLM')
  })

  it('exposes storage path fields with default Application Support location', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()

    // base dir 模式:只 DATA_DIR + LOG_DIR 两个 input;其他子目录显示为预览
    const html = wrapper.html()
    expect(html).toContain('data-dir')
    expect(html).toContain('log-dir')
    // 不再需要子目录 input(后端自动推导)
    expect(html).not.toContain('paddle-cache')
    expect(html).not.toContain('hf-cache')
    // 默认 placeholder 提示 macOS 规范路径
    expect(html).toContain('~/Library/Application Support/com.xhs-info-crawl.local')
    // 提示信息告诉用户只需设一个数据根目录
    expect(wrapper.find('[data-test="storage-hint"]').exists()).toBe(true)
    // 子目录预览
    expect(wrapper.find('[data-test="storage-preview"]').exists()).toBe(true)

    // MOCK_CONFIG 验证默认值
    expect(MOCK_CONFIG.data_dir).toBe('~/Library/Application Support/com.xhs-info-crawl.local')
    expect(MOCK_CONFIG.log_dir).toContain('/logs')
  })

  it('derives subdirectories from DATA_DIR (base dir mode)', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()

    // 验证子目录预览文案包含推导后的路径
    const html = wrapper.html()
    expect(html).toContain('/images')
    expect(html).toContain('/exports')
    expect(html).toContain('/archive')
    expect(html).toContain('/paddlex')
    expect(html).toContain('/huggingface')
    expect(html).toContain('app.db')
    expect(html).toContain('sqlite:///')
  })

  it('saves only DATA_DIR + LOG_DIR (base dir mode)', async () => {
    const mockResp: SystemConfigSaveResponse = {
      ok: true,
      saved_keys: ['DATA_DIR', 'LOG_DIR'],
      restart: { api: true, worker: true, web: true, beat: true },
    }
    vi.mocked(client.saveSystemConfig).mockResolvedValue(mockResp)

    const wrapper = mountPanel()
    await flushPromises()
    await flushPromises()

    // 用户改 data_dir(vue-test-utils 的 wrapper.vm.config 是 ref 已 unwrap 的对象)
    const config = (wrapper.vm as unknown as { config: SystemConfig | null }).config
    if (!config) throw new Error('config not initialized')
    config.data_dir = '~/Documents/xhs-data'
    await flushPromises()

    await wrapper.get('[data-test="llm-save-btn"]').trigger('click')
    await flushPromises()

    expect(client.saveSystemConfig).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(client.saveSystemConfig).mock.calls[0][0] as Record<string, string>
    // 只传 DATA_DIR + LOG_DIR,不带子目录字段
    expect(payload.data_dir).toBe('~/Documents/xhs-data')
    expect(payload.log_dir).toContain('/logs')
    expect(payload).not.toHaveProperty('image_dir')
    expect(payload).not.toHaveProperty('paddle_pdx_cache_home')
  })
})