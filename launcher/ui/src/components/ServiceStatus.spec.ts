import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ServiceStatus from './ServiceStatus.vue'
import type { StatusResponse } from '@/api/client'

describe('ServiceStatus', () => {
  const runningStatus: StatusResponse = {
    api: { state: 'running', pid: 1001 },
    worker: { state: 'running', pid: 1002 },
    beat: { state: 'running', pid: 1003 },
  }

  it('renders three service rows', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    const rows = wrapper.findAll('[data-test="service-row"]')
    expect(rows).toHaveLength(3)
  })

  it('shows service names api/worker/beat', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    expect(wrapper.text()).toContain('API')
    expect(wrapper.text()).toContain('Worker')
    expect(wrapper.text()).toContain('Beat')
  })

  it('shows running state with pid', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('1001')
  })

  it('shows stopped state without pid', () => {
    const stoppedStatus: StatusResponse = {
      api: { state: 'stopped', pid: null },
      worker: { state: 'stopped', pid: null },
      beat: { state: 'stopped', pid: null },
    }
    const wrapper = mount(ServiceStatus, { props: { status: stoppedStatus } })
    expect(wrapper.text()).toContain('已停止')
  })

  it('shows crashed state', () => {
    const crashedStatus: StatusResponse = {
      api: { state: 'crashed', pid: null },
      worker: { state: 'running', pid: 1002 },
      beat: { state: 'running', pid: 1003 },
    }
    const wrapper = mount(ServiceStatus, { props: { status: crashedStatus } })
    expect(wrapper.text()).toContain('异常退出')
  })

  it('emits restart event with service name when restart button clicked', async () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    const restartButtons = wrapper.findAll('[data-test="restart-btn"]')
    expect(restartButtons).toHaveLength(3)
    await restartButtons[0].trigger('click')
    expect(wrapper.emitted('restart')).toBeTruthy()
    expect(wrapper.emitted('restart')![0]).toEqual(['api'])
  })

  it('emits stop-all event when stop all button clicked', async () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    await wrapper.get('[data-test="stop-all-btn"]').trigger('click')
    expect(wrapper.emitted('stop-all')).toBeTruthy()
  })

  it('applies success color class to running service dot', () => {
    const wrapper = mount(ServiceStatus, { props: { status: runningStatus } })
    const dot = wrapper.get('[data-test="dot-api"]')
    expect(dot.classes()).toContain('dot--running')
  })

  it('applies error color class to crashed service dot', () => {
    const crashedStatus: StatusResponse = {
      api: { state: 'crashed', pid: null },
      worker: { state: 'running', pid: 1002 },
      beat: { state: 'running', pid: 1003 },
    }
    const wrapper = mount(ServiceStatus, { props: { status: crashedStatus } })
    const dot = wrapper.get('[data-test="dot-api"]')
    expect(dot.classes()).toContain('dot--crashed')
  })
})
