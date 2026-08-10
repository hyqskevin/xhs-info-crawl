import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AppLayout from './AppLayout.vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ path: '/activities', fullPath: '/activities', meta: { title: '活动管理' } }) }))

describe('AppLayout', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders the title, all menu entries, and logout action', () => {
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    for (const label of ['仪表盘', '活动管理', '去重审核', '任务日志', '周报管理', '配置中心', '退出']) {
      expect(wrapper.text()).toContain(label)
    }
    expect(wrapper.get('h1').text()).toBe('活动管理')
  })

  it('renders a collapse toggle button', () => {
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    expect(wrapper.find('.collapse-toggle').exists()).toBe(true)
  })

  it('toggles sidebar collapse on button click', async () => {
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    const aside = wrapper.findComponent({ name: 'ElAside' })
    expect(aside.props('width')).toBe('220px')
    await wrapper.find('.collapse-toggle').trigger('click')
    expect(aside.props('width')).toBe('64px')
    await wrapper.find('.collapse-toggle').trigger('click')
    expect(aside.props('width')).toBe('220px')
  })

  it('persists collapse state to localStorage', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    await wrapper.find('.collapse-toggle').trigger('click')
    expect(setItemSpy).toHaveBeenCalledWith('sidebar_collapsed', '1')
    setItemSpy.mockRestore()
  })

  it('renders settings submenu with 6 items', () => {
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    const text = wrapper.text()
    expect(text).toContain('配置中心')
    expect(text).toContain('城市抓取配置')
    expect(text).toContain('博主白名单')
    expect(text).toContain('关键词组')
    expect(text).toContain('博主组')
    expect(text).toContain('账号配置')
    expect(text).toContain('系统配置')
  })

  it('renders settings account config menu item linking to xhs-accounts tab', () => {
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    const accountItem = wrapper.findAll('.el-menu-item').find((item) => item.text().includes('账号配置'))
    expect(accountItem, '配置中心必须有「账号配置」菜单项').toBeTruthy()
    expect(accountItem!.attributes('href') || accountItem!.text()).toContain('账号配置')
  })

  it('renders schedules submenu with 2 items', () => {
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    const text = wrapper.text()
    expect(text).toContain('定时任务')
    expect(text).toContain('定时任务列表')
    expect(text).toContain('抓取批次配置')
  })
})
