import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import AppLayout from './AppLayout.vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ path: '/activities', meta: { title: '活动管理' } }) }))

describe('AppLayout', () => {
  it('renders the title, all menu entries, and logout action', () => {
    const wrapper = mount(AppLayout, { global: { plugins: [ElementPlus], stubs: { RouterView: true } } })
    for (const label of ['仪表盘', '活动管理', '去重审核', '任务日志', '周报管理', '配置中心', '退出']) {
      expect(wrapper.text()).toContain(label)
    }
    expect(wrapper.get('h1').text()).toBe('活动管理')
  })
})
