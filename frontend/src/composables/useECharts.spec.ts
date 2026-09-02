import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { useECharts } from './useECharts'

const mockSetOption = vi.fn()
const mockResize = vi.fn()
const mockDispose = vi.fn()
const mockInit = vi.fn(() => ({ setOption: mockSetOption, resize: mockResize, dispose: mockDispose }))

vi.mock('echarts', () => ({
  default: { init: mockInit },
  init: mockInit,
}))

describe('useECharts', () => {
  beforeEach(() => {
    vi.stubGlobal('addEventListener', vi.fn())
    vi.stubGlobal('removeEventListener', vi.fn())
    mockInit.mockClear()
    mockSetOption.mockClear()
    mockResize.mockClear()
    mockDispose.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('initializes chart and renders option on mount', async () => {
    const Comp = defineComponent({
      template: '<div ref="container" />',
      setup() {
        const container = ref<HTMLElement | null>(null)
        const data = ref([1, 2])
        useECharts({
          container,
          data,
          buildOption: (d) => ({ series: [{ data: d }] } as any),
        })
        return { container }
      },
    })
    mount(Comp)
    await flushPromises()
    expect(mockInit).toHaveBeenCalled()
    expect(mockSetOption).toHaveBeenCalledWith({ series: [{ data: [1, 2] }] }, true)
  })

  it('re-renders when data changes', async () => {
    const Comp = defineComponent({
      template: '<div ref="container" />',
      setup() {
        const container = ref<HTMLElement | null>(null)
        const data = ref([1])
        useECharts({ container, data, buildOption: (d) => ({ series: [{ data: d }] } as any) })
        return { container, data }
      },
    })
    const wrapper = mount(Comp)
    await flushPromises()
    mockSetOption.mockClear()
    wrapper.vm.data = [2]
    await flushPromises()
    expect(mockSetOption).toHaveBeenCalledWith({ series: [{ data: [2] }] }, true)
  })

  it('exposes resize function and disposes on unmount', async () => {
    const Comp = defineComponent({
      template: '<div ref="container" />',
      setup() {
        const container = ref<HTMLElement | null>(null)
        const data = ref([1])
        const { resize } = useECharts({ container, data, buildOption: () => ({}) })
        resize()
        return { container }
      },
    })
    const wrapper = mount(Comp)
    await flushPromises()
    expect(mockResize).toHaveBeenCalled()
    wrapper.unmount()
    await flushPromises()
    expect(mockDispose).toHaveBeenCalled()
  })
})
