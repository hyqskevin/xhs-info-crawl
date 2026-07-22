import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PosterWizardView from './PosterWizardView.vue'

const mocks = vi.hoisted(() => ({
  posterCandidates: vi.fn().mockResolvedValue({ data: { data: { items: [
    { id: 1, title: '宁波周末活动', city_code: 'nb', image_count: 3 },
    { id: 2, title: '上海展览', city_code: 'sh', image_count: 2 },
  ] } } }),
  posterTemplates: vi.fn().mockResolvedValue({ data: { data: { items: [
    { id: 7, name: '橙橙周末合集', description: '橙底白字', html_template: '<div/>', css_text: '.p{}' },
  ] } } }),
  noteImages: vi.fn().mockResolvedValue({ data: { data: { image_urls: ['/img/1.jpg', '/img/2.jpg'] } } }),
  createPosterTask: vi.fn().mockResolvedValue({ data: { data: { id: 42 } } }),
  posterPreview: vi.fn().mockResolvedValue({ data: { data: { html: '<html/>', items_count: 1 } } }),
  posterRender: vi.fn().mockResolvedValue({ data: { data: { url: '/api/v1/poster-tasks/42/download' } } }),
  posterDownload: vi.fn().mockResolvedValue({ data: new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: 'image/png' }) }),
}))

vi.mock('@/api/client', () => ({ api: mocks }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<typeof ElementPlus>('element-plus')
  return { ...actual, ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }
})

function factory() {
  return mount(PosterWizardView, { global: { plugins: [ElementPlus] } })
}

describe('PosterWizardView', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'tk-test')
    URL.createObjectURL = vi.fn(() => 'blob:1')
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => vi.clearAllMocks())

  it('loads candidates and templates on mount', async () => {
    factory()
    await flushPromises()
    expect(mocks.posterCandidates).toHaveBeenCalled()
    expect(mocks.posterTemplates).toHaveBeenCalled()
  })

  it('next step does nothing if no candidate selected', async () => {
    const wrapper = factory()
    await flushPromises()
    const buttons = wrapper.findAll('button')
    const nextBtn = buttons.find((b) => b.text().includes('下一步'))!
    await nextBtn.trigger('click')
    await flushPromises()
    // 仍然在 step=1（无跳转）
    expect((wrapper.vm as any).step).toBe(1)
  })

  it('preview calls preview endpoint after save', async () => {
    const wrapper = factory()
    await flushPromises()
    ;(wrapper.vm as any).selectedIds = [1]
    ;(wrapper.vm as any).templateId = 7
    ;(wrapper.vm as any).items = [{ type: 'note', id: 1, title: 'x', fields: {}, image_url: '' }]
    // 直接调用内部方法
    await (wrapper.vm as any).preview()
    expect(mocks.createPosterTask).toHaveBeenCalled()
    expect(mocks.posterPreview).toHaveBeenCalledWith(42)
  })

  it('render endpoint called and renders url appears', async () => {
    const wrapper = factory()
    await flushPromises()
    ;(wrapper.vm as any).taskId = 42
    await (wrapper.vm as any).renderNow()
    await flushPromises()
    expect(mocks.posterRender).toHaveBeenCalledWith(42)
    expect((wrapper.vm as any).renderedUrl).toContain('/download')
  })
})
