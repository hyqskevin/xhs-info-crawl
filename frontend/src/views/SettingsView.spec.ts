import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import SettingsView from './SettingsView.vue'

const { settings } = vi.hoisted(() => ({ settings: vi.fn().mockResolvedValue({ data: { data: [{ id: 1, name: '上海', code: 'shanghai' }] } }) }))
vi.mock('@/api/client', () => ({ api: { settings, createSetting: vi.fn(), deleteSetting: vi.fn(), testOpenCLI: vi.fn() } }))

describe('SettingsView', () => {
  it('loads city settings and renders all configuration categories', async () => {
    const wrapper = mount(SettingsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(settings).toHaveBeenCalledWith('cities')
    expect(wrapper.text()).toContain('上海')
    expect(wrapper.text()).toContain('城市')
    expect(wrapper.text()).toContain('关键词')
    expect(wrapper.text()).toContain('博主')
    expect(wrapper.text()).toContain('测试 OpenCLI')
  })
})
