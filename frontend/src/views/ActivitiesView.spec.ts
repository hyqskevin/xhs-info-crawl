import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElDrawer, ElEmpty, ElImage, ElMessage, ElMessageBox, ElPagination, ElTable } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ActivitiesView from './ActivitiesView.vue'

const mocks = vi.hoisted(() => ({
  notes: vi.fn().mockResolvedValue({ data: { data: { items: [{ id: 1, title: '周末艺术展推文', city_code: 'shanghai', published_at: '2026-07-18T10:00:00Z', review_status: 'PENDING', processing_status: 'PROCESSED', activity_count: 2, summary: '正文：展会详情\n[图片 1 OCR] 2026-07-20 18:00 徐汇滨江' }] }, pagination: { page: 1, page_size: 20, total: 41 } } }),
  settings: vi.fn().mockResolvedValue({ data: { data: [{ id: 1, name: '上海', code: 'shanghai', enabled: true }] } }),
  note: vi.fn().mockResolvedValue({ data: { data: { id: 1, title: '周末艺术展推文', content: '页面正文', city_code: 'shanghai', published_at: '2026-07-18T10:00:00Z', source_url: 'https://xhs/note-7', review_status: 'PENDING', summary: '正文：页面正文\n[图片 1 OCR] 2026-07-20 18:00 徐汇滨江', activities: [{ id: 11, name: '活动一', location: '静安', start_time: '2026-07-20T18:00:00Z', end_time: '2026-07-20T22:00:00Z' }, { id: 12, name: '活动二', location: '外滩', start_time: null, end_time: null }], images: [{ id: 21 }, { id: 22 }] } } }),
  noteImage: vi.fn().mockResolvedValue({ data: new Blob(['image']) }),
  updateActivity: vi.fn(),
  deleteActivity: vi.fn(),
  deleteNotes: vi.fn().mockResolvedValue({ data: { data: { deleted_count: 1, deleted_ids: [1] } } }),
  approveNotes: vi.fn().mockResolvedValue({ data: { data: { approved_count: 1, approved_ids: [1] } } }),
  updateNote: vi.fn().mockResolvedValue({ data: { data: { id: 1 } } }),
  reviewNote: vi.fn().mockResolvedValue({ data: { data: { id: 1, review_status: 'APPROVED' } } }),
}))
vi.mock('@/api/client', () => ({ api: mocks }))

afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })

describe('ActivitiesView', () => {
  it('passes the keyword input value to the notes API and omits empty keyword', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    mocks.notes.mockClear()

    const input = wrapper.find('input[aria-label="关键字"]')
    await input.setValue('咖啡')
    await wrapper.findAll('button').find((item) => item.text().includes('筛选'))!.trigger('click')
    await flushPromises()
    expect(mocks.notes).toHaveBeenLastCalledWith(expect.objectContaining({ keyword: '咖啡' }))

    await input.setValue('  ')
    await wrapper.findAll('button').find((item) => item.text().includes('筛选'))!.trigger('click')
    await flushPromises()
    expect(mocks.notes).toHaveBeenLastCalledWith(expect.not.objectContaining({ keyword: expect.anything() }))
  })

  it('clears the keyword along with other filters on reset', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const input = wrapper.find('input[aria-label="关键字"]')
    await input.setValue('艺术展')
    expect((input.element as HTMLInputElement).value).toBe('艺术展')
    await wrapper.findAll('button').find((item) => item.text().includes('重置'))!.trigger('click')
    await flushPromises()
    const inputAfter = wrapper.find('input[aria-label="关键字"]')
    expect((inputAfter.element as HTMLInputElement).value).toBe('')
  })

  it('renders crawled activities with city names, Chinese review status and pagination', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('周末艺术展推文')
    expect(wrapper.text()).toContain('上海')
    expect(wrapper.text()).toContain('待审核')
    expect(wrapper.text()).not.toContain('新增活动')
    expect(wrapper.text()).not.toContain('城市代码')
    expect(wrapper.text()).toContain('发布时间')
    expect(wrapper.text()).toContain('识别活动')
    expect(wrapper.getComponent(ElPagination).props('pageSizes')).toEqual([10, 20, 50, 100])
    expect(mocks.notes).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))
  })

  it('shows the note publish time as YYYY-MM-DD only (no hours/minutes)', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    // mock published_at = 2026-07-18T10:00:00Z → formatDate 输出 "2026-07-18"
    expect(wrapper.text()).toContain('2026-07-18')
    // 不应该渲染时分秒 "10:00:00"（否则与"详情活动表格"含时分秒的设计不一致）
    expect(wrapper.text()).not.toContain('10:00:00')
    expect(wrapper.text()).not.toContain('18 10:00')
  })

  it('shows unknown activity dates as pending confirmation', async () => {
    mocks.notes.mockResolvedValueOnce({ data: { data: { items: [{ id: 2, title: '日期未知推文', city_code: 'shanghai', published_at: null, created_at: null, review_status: 'PENDING', activity_count: 1 }] }, pagination: { page: 1, page_size: 20, total: 1 } } })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.text()).toContain('日期未知推文')
    expect(wrapper.text()).toContain('待确认')
  })

  it('batch deletes only explicitly selected activities', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    wrapper.getComponent(ElTable).vm.$emit('selection-change', [{ id: 1 }])
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text().includes('批量删除'))!
    expect(button.attributes('disabled')).toBeUndefined()

    await button.trigger('click')
    await flushPromises()

    expect(mocks.deleteNotes).toHaveBeenCalledWith([1])
    expect(mocks.notes).toHaveBeenCalledTimes(2)
  })

  it('batch approves selected activities and refreshes the list', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text().includes('批量通过'))!
    expect(button).toBeDefined()
    expect(button.attributes('disabled')).toBeDefined()

    wrapper.getComponent(ElTable).vm.$emit('selection-change', [{ id: 1 }])
    await flushPromises()
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    await flushPromises()

    expect(mocks.approveNotes).toHaveBeenCalledWith([1])
    expect(mocks.notes).toHaveBeenCalledTimes(2)
  })

  it('opens a wide detail drawer with source note images and releases blob URLs', async () => {
    const createObjectURL = vi.fn().mockReturnValueOnce('blob:first').mockReturnValueOnce('blob:second')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    expect(wrapper.getComponent(ElDrawer).props('size')).toBe('70%')
    expect(wrapper.text()).toContain('周末艺术展推文')
    expect(wrapper.text()).toContain('活动一')
    expect(wrapper.text()).toContain('活动二')
    expect(wrapper.text()).toContain('来源页面图片')
    expect(wrapper.findAllComponents(ElImage)).toHaveLength(2)
    expect(mocks.noteImage.mock.calls).toEqual([[1, 21], [1, 22]])
    expect(createObjectURL).toHaveBeenCalledTimes(2)

    wrapper.getComponent(ElDrawer).vm.$emit('closed')
    await flushPromises()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:first')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:second')
  })

  it('shows activity table columns: name / location / start time / end time / actions', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    // 5 列：名称 / 地点 / 开始时间 / 结束时间 / 操作（无"状态"列）
    const headers = wrapper.findAll('.el-drawer thead th').map((cell) => cell.text())
    const activityHeaderStart = headers.indexOf('名称')
    expect(activityHeaderStart).toBeGreaterThanOrEqual(0)
    const sliced = headers.slice(activityHeaderStart, activityHeaderStart + 5)
    expect(sliced).toEqual(['名称', '地点', '开始时间', '结束时间', '操作'])
  })

  it('renders activity date cells including placeholders for missing values', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    // mock 第一行有 start_time/end_time；第二行均为 null → 显示"待确认"和"-"
    // 不直接断言完整时间字符串（依赖运行环境的 toLocaleString 输出）
    // 改测：开始时间 cell 不为"待确认"，第二个活动开始时间是"待确认"
    const startTimeCells = wrapper.findAll('.el-drawer .el-table__row').map((row) => row.findAll('td')[2]?.text() || '')
    // 第一行有 start_time（格式含年份），第二行 null → "待确认"
    expect(startTimeCells.length).toBeGreaterThanOrEqual(2)
    expect(startTimeCells[1]).toBe('待确认')
    expect(startTimeCells[0]).not.toBe('待确认')
    expect(startTimeCells[0]).not.toBe('-')
    // 结束时间 cell：第一行有具体时间（非 "-"/非"待确认"），第二行 "-"
    const endTimeCells = wrapper.findAll('.el-drawer .el-table__row').map((row) => row.findAll('td')[3]?.text() || '')
    expect(endTimeCells[1]).toBe('-')
    expect(endTimeCells[0]).not.toBe('-')
    expect(endTimeCells[0]).not.toBe('待确认')
  })

  it('does NOT render a summary column in the note list (OCR lives in the detail drawer)', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    // 列表头不再含「摘要」列；OCR 文字不出现在列表行
    const html = wrapper.html()
    expect(html).not.toContain('row-summary')
    const headers = wrapper.findAll('.el-table thead th').map((cell) => cell.text())
    expect(headers).not.toContain('摘要')
    // 详情页（drawer 内）OCR 仍可显示（之前测试覆盖）
  })

  it('shows an Element Plus empty state when the source note has no images', async () => {
    mocks.note.mockResolvedValueOnce({ data: { data: { id: 1, title: '无图笔记', content: '', source_url: 'https://xhs/no-image', review_status: 'PENDING', activities: [], images: [] } } })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    expect(wrapper.getComponent(ElEmpty).props('description')).toBe('暂无来源图片')
  })

  it('edits a note from the list without submitting the read-only source URL', async () => {
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((item) => item.text().includes('编辑推文'))!.trigger('click')
    await flushPromises()
    const source = wrapper.get('input[aria-label="原文链接"]')
    expect(source.attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="推文标题"]').setValue('更新后的推文')
    await wrapper.findAll('button').find((item) => item.text().includes('保存推文'))!.trigger('click')
    await flushPromises()

    expect(mocks.updateNote).toHaveBeenCalledWith(1, {
      title: '更新后的推文',
      content: '页面正文',
      city_code: 'shanghai',
      published_at: '2026-07-18T10:00:00.000Z',
    })
    expect(mocks.updateNote.mock.calls[0][1]).not.toHaveProperty('source_url')
    expect(mocks.notes).toHaveBeenCalledTimes(2)
  })

  it('confirms and reviews one note from the list', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((item) => item.text() === '驳回')!.trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalledWith('确认驳回这篇推文？', '单篇审核确认', { type: 'warning' })
    expect(mocks.reviewNote).toHaveBeenCalledWith(1, 'REJECTED')
    expect(mocks.notes).toHaveBeenCalledTimes(2)
  })

  it('reviews from the detail drawer and refreshes both detail and list', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('详情'))!.trigger('click')
    await flushPromises()

    const drawerApprove = wrapper.findAll('.el-drawer button').find((item) => item.text() === '通过')!
    await drawerApprove.trigger('click')
    await flushPromises()

    expect(mocks.reviewNote).toHaveBeenCalledWith(1, 'APPROVED')
    expect(mocks.note).toHaveBeenCalledTimes(2)
    expect(mocks.notes).toHaveBeenCalledTimes(2)
  })

  it('shows an error toast when single review fails', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    vi.spyOn(ElMessage, 'error')
    mocks.reviewNote.mockRejectedValueOnce(new Error('network'))
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.findAll('button').find((item) => item.text() === '通过')!.trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('审核失败，请重试')
    expect(mocks.notes).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['APPROVED', '通过'],
    ['REJECTED', '驳回'],
  ])('hides the %s target action when the note already has that status', async (status, action) => {
    mocks.notes.mockResolvedValueOnce({ data: { data: { items: [{ id: 1, title: '已审核推文', city_code: 'shanghai', published_at: null, review_status: status, activity_count: 1 }] }, pagination: { total: 1 } } })
    const wrapper = mount(ActivitiesView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    const actions = wrapper.get('.row-actions').findAll('button').map((button) => button.text())
    expect(actions).not.toContain(action)
  })
})
