import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox, ElSelect } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DashboardView from './DashboardView.vue'

vi.mock('@/api/health', () => ({ getHealth: vi.fn().mockResolvedValue({ status: 'ok', database: 'sqlite' }) }))
const mocks = vi.hoisted(() => ({
  settings: vi.fn().mockImplementation((kind: string) => Promise.resolve({ data: { data: kind === 'cities'
    ? [{ id: 1, name: '上海', code: 'shanghai', keywords: ['周末活动', '展览'], recent_filter: '一周内', enabled: true }]
    : [{ id: 9, username: '活动博主', profile_url: 'https://www.xiaohongshu.com/user/profile/abc', city_codes: ['shanghai'], enabled: true },
       { id: 10, username: '未补充博主', profile_url: '', city_codes: ['shanghai'], enabled: true }] } })),
  createTask: vi.fn().mockResolvedValue({ data: { data: { id: 3 } } }),
  keywordGroups: vi.fn().mockImplementation((params: any) => Promise.resolve({ data: { data: { items: params && params.city_code === 'shanghai' ? [
    { id: 11, name: '上海-展览', words: ['展览'], city_codes: ['shanghai'], enabled: true },
    { id: 12, name: '上海-亲子', words: ['亲子'], city_codes: ['shanghai'], enabled: true },
  ] : [] } } })),
  dashboard: vi.fn().mockResolvedValue({ data: { data: { last_task: { id: 4, status: 'FAILED', total_notes: 113, downloaded_notes: 5, ocr_notes: 5, extracted_notes: 5, success_notes: 5, failed_notes: 1, current_stage: null, current_note: null, error_message: 'bad date', progress_percent: 5.3 } } } }),
  restartTask: vi.fn().mockResolvedValue({ data: { data: { id: 4, status: 'PENDING' } } }),
  openXhsLogin: vi.fn().mockResolvedValue({ data: { data: { url: 'https://www.xiaohongshu.com/explore' } } }),
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
    selects[1].vm.$emit('update:modelValue', [12])
    selects[2].vm.$emit('update:modelValue', '一天内')
    selects[3].vm.$emit('update:modelValue', [9])
    await wrapper.findAll('button').find((button) => button.text().includes('开始抓取'))!.trigger('click')
    await flushPromises()

    expect(mocks.createTask).toHaveBeenCalledWith({ type: 'mixed', city: 'shanghai', keyword_group_ids: [12], recent_filter: '一天内', blogger_ids: [9] })
  })

  it('blocks task submission when selected blogger has no profile_url', async () => {
    const warningSpy = vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const selects = wrapper.findAllComponents(ElSelect)
    selects[0].vm.$emit('update:modelValue', 'shanghai')
    await flushPromises()
    selects[3].vm.$emit('update:modelValue', [10])  // id=10 是未补充的博主
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text().includes('开始抓取'))!.trigger('click')
    await flushPromises()

    expect(mocks.createTask).not.toHaveBeenCalled()
    expect(warningSpy).toHaveBeenCalledWith(expect.stringContaining('博主信息不完整'))
    warningSpy.mockRestore()
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

  it('exposes an explicit "结束抓取" button for FAILED tasks', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 7, status: 'FAILED', total_notes: 0, downloaded_notes: 0, ocr_notes: 0, extracted_notes: 0, success_notes: 0, failed_notes: 0, current_stage: 'SEARCHING', current_note: null, error_message: 'Missing url', progress_percent: 0 } } } })
    mocks.stopTask.mockResolvedValueOnce({ data: { data: { id: 7, status: 'STOPPED' } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const finishButton = wrapper.findAll('button').find((button) => button.text().includes('结束抓取'))
    expect(finishButton, 'FAILED 任务必须显示"结束抓取"按钮').toBeTruthy()
    await finishButton!.trigger('click')
    await flushPromises()
    expect(mocks.stopTask).toHaveBeenCalledWith(7)
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

  it('opens Chrome login and resumes a paused task', async () => {
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 4, status: 'PAUSED', total_notes: 102, downloaded_notes: 19, ocr_notes: 19, extracted_notes: 19, success_notes: 19, failed_notes: 0, skipped_notes: 0, skipped_activities: 3, current_stage: 'DOWNLOADING', current_note: '活动笔记', error_message: '请在 Chrome 登录小红书后重试', progress_percent: 18.6 } } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('打开小红书登录')
    expect(wrapper.text()).toContain('检测登录并继续')
    expect(wrapper.text()).toContain('活动已跳过3')
    await wrapper.findAll('button').find((button) => button.text().includes('打开小红书登录'))!.trigger('click')
    await flushPromises()
    expect(mocks.openXhsLogin).toHaveBeenCalled()
    await wrapper.findAll('button').find((button) => button.text().includes('检测登录并继续'))!.trigger('click')
    await flushPromises()
    expect(mocks.restartTask).toHaveBeenCalledWith(4)
  })

  it('shows the security verification reason with manual recovery controls', async () => {
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 12, status: 'PAUSED', total_notes: 20, downloaded_notes: 4, ocr_notes: 4, extracted_notes: 3, success_notes: 3, failed_notes: 0, skipped_notes: 0, current_stage: 'DOWNLOADING', current_note: '活动笔记', error_message: '检测到小红书安全验证，请在 Chrome 完成后点击检测登录并继续', progress_percent: 20 } } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('检测到小红书安全验证')
    expect(wrapper.text()).toContain('打开小红书登录')
    expect(wrapper.text()).toContain('检测登录并继续')
  })

  it('hides the error alert when the last task completed with errors (status COMPLETED_WITH_ERRORS)', async () => {
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 21, status: 'COMPLETED_WITH_ERRORS', total_notes: 50, downloaded_notes: 50, ocr_notes: 50, extracted_notes: 48, success_notes: 48, failed_notes: 1, skipped_notes: 0, current_stage: null, current_note: null, error_message: '某条笔记失败', progress_percent: 100 } } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const alert = wrapper.find('.el-alert--error')
    expect(alert.exists(), 'COMPLETED_WITH_ERRORS 状态不应显示红色 Alert').toBe(false)
    expect(wrapper.text()).not.toContain('某条笔记失败')
  })

  it('shows the error alert when the last task is FAILED', async () => {
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 22, status: 'FAILED', total_notes: 30, downloaded_notes: 5, ocr_notes: 5, extracted_notes: 5, success_notes: 5, failed_notes: 1, current_stage: null, current_note: null, error_message: 'opencli 子进程崩溃', progress_percent: 17 } } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const alert = wrapper.find('.el-alert--error')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('opencli 子进程崩溃')
  })

  it('shows the error alert when the last task is RUNNING', async () => {
    mocks.dashboard.mockResolvedValueOnce({ data: { data: { last_task: { id: 23, status: 'RUNNING', total_notes: 60, downloaded_notes: 30, ocr_notes: 28, extracted_notes: 25, success_notes: 25, failed_notes: 0, skipped_notes: 5, current_stage: 'OCR', current_note: '周末笔记', error_message: '等待下次重试', progress_percent: 50 } } } })
    const wrapper = mount(DashboardView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const alert = wrapper.find('.el-alert--error')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('等待下次重试')
  })
})
