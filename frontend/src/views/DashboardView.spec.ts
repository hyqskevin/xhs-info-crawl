import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox, ElSelect } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DashboardView from './DashboardView.vue'

vi.mock('@/api/health', () => ({ getHealth: vi.fn().mockResolvedValue({ status: 'ok', database: 'sqlite' }) }))
const mocks = vi.hoisted(() => ({
  settings: vi.fn().mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
    ? [{ id: 1, name: '上海', code: 'shanghai', keywords: ['周末活动', '展览'], recent_filter: '一周内', enabled: true }]
    : [{ id: 9, username: '活动博主', city_code: 'shanghai', enabled: true }] } })),
  createTask: vi.fn().mockResolvedValue({ data: { data: { id: 3 } } }),
  dashboard: vi.fn().mockResolvedValue({ data: { data: { last_task: { id: 4, status: 'FAILED', total_notes: 113, downloaded_notes: 5, ocr_notes: 5, extracted_notes: 5, success_notes: 5, failed_notes: 1, current_stage: null, current_note: null, error_message: 'bad date', progress_percent: 5.3 } } } }),
  restartTask: vi.fn().mockResolvedValue({ data: { data: { id: 4, status: 'PENDING' } } }),
  stopTask: vi.fn().mockResolvedValue({ data: { data: { id: 4, status: 'STOP_REQUESTED' } } }),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => vi.clearAllMocks())

describe('DashboardView', () => {
  it('starts a crawl from configured city, keywords, time and bloggers', async () => {
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('发起抓取')
    expect(wrapper.text()).toContain('城市')
    expect(wrapper.text()).toContain('关键词')
    expect(wrapper.text()).toContain('时间范围')
    expect(wrapper.text()).toContain('博主')

    const selects = wrapper.findAllComponents(ElSelect)
    selects[0].vm.$emit('update:modelValue', 'shanghai')
    await flushPromises()
    selects[1].vm.$emit('update:modelValue', ['周末活动'])
    selects[2].vm.$emit('update:modelValue', '一天内')
    selects[3].vm.$emit('update:modelValue', [9])
    await wrapper.findAll('button').find((button) => button.text().includes('开始抓取'))!.trigger('click')
    await flushPromises()

    expect(mocks.createTask).toHaveBeenCalledWith({ type: 'mixed', city: 'shanghai', keywords: ['周末活动'], recent_filter: '一天内', blogger_ids: [9] })
  })

  it('shows latest crawl progress and restarts a failed task', async () => {
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('最近抓取任务')
    expect(wrapper.text()).toContain('发现113')
    expect(wrapper.text()).toContain('提取完成5')
    const restart = wrapper.findAll('button').find((button) => button.text().includes('继续抓取'))!
    await restart.trigger('click')
    await flushPromises()
    expect(mocks.restartTask).toHaveBeenCalledWith(4)
  })

  it('shows skipped progress and safely stops a running task', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 4, status: 'RUNNING', total_notes: 20, downloaded_notes: 8, ocr_notes: 7, extracted_notes: 5, success_notes: 5, failed_notes: 1, skipped_notes: 4, current_stage: 'OCR', current_note: '周末活动', error_message: null, progress_percent: 50 } } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('已跳过4')
    const stop = wrapper.findAll('button').find((button) => button.text().includes('停止抓取'))!
    await stop.trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(mocks.stopTask).toHaveBeenCalledWith(4)
  })

  it('allows a stopped task to continue', async () => {
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 4, status: 'STOPPED', total_notes: 20, downloaded_notes: 8, ocr_notes: 7, extracted_notes: 5, success_notes: 5, failed_notes: 0, skipped_notes: 4, current_stage: null, current_note: null, error_message: null, progress_percent: 45 } } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('已停止')
    await wrapper.findAll('button').find((button) => button.text().includes('继续抓取'))!.trigger('click')
    await flushPromises()
    expect(mocks.restartTask).toHaveBeenCalledWith(4)
  })
})
