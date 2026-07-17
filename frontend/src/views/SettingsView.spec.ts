import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SettingsView from './SettingsView.vue'

const mocks = vi.hoisted(() => ({
  settings: vi.fn().mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
    ? [{ id: 1, name: '宁波', code: 'nb', keywords: ['周末活动', '展览'], recent_filter: '一周内', enabled: true }]
    : [] } })),
  createSetting: vi.fn(),
  updateSetting: vi.fn(),
  deleteSetting: vi.fn(),
  testOpenCLI: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })

describe('SettingsView', () => {
  it('shows city keywords and recent filter without exposing internal code', async () => {
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(mocks.settings).toHaveBeenCalledWith('cities')
    expect(wrapper.text()).toContain('宁波')
    expect(wrapper.text()).toContain('周末活动')
    expect(wrapper.text()).toContain('一周内')
    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).not.toContain('关键词配置')
  })

  it('opens one city form containing keywords and supported XHS time ranges', async () => {
    const wrapper = mount(SettingsView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('新增城市'))!.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('新增城市')
    expect(document.body.textContent).toContain('关键词')
    expect(document.body.textContent).toContain('抓取时间范围')
    expect(document.body.textContent).not.toContain('城市代码')
  })
})
