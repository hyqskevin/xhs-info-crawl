import type { ECharts, EChartsOption } from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

export interface UseEChartsOptions<T> {
  /** 图表容器 DOM 引用 */
  container: Ref<HTMLElement | null>
  /** 驱动图表的数据 */
  data: Ref<T>
  /** 将 data 构建为 ECharts option */
  buildOption: (data: T) => EChartsOption
}

export function useECharts<T>(options: UseEChartsOptions<T>) {
  const { container, data, buildOption } = options
  let chart: ECharts | null = null
  let pendingResize = false

  function render() {
    chart?.setOption(buildOption(data.value), true)
  }

  function doResize() {
    chart?.resize()
  }

  function resize() {
    if (chart) {
      doResize()
    } else {
      pendingResize = true
    }
  }

  onMounted(async () => {
    const echarts = await import('echarts')
    chart = echarts.init(container.value!)
    render()
    if (pendingResize) {
      pendingResize = false
      doResize()
    }
    window.addEventListener('resize', doResize)
  })

  watch(() => data.value, render, { deep: true })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', doResize)
    chart?.dispose()
    chart = null
  })

  return { resize }
}
