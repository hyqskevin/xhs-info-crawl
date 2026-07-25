<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ tasks: any[] }>()
const container = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '-'
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function buildOption() {
  const tasks = props.tasks || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['发现', '成功', '失败'] },
    grid: { left: 44, right: 16, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: tasks.map((t: any) => formatTime(t.started_at)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '发现', type: 'line', smooth: true, data: tasks.map((t: any) => t.total_notes) },
      { name: '成功', type: 'line', smooth: true, data: tasks.map((t: any) => t.success_notes) },
      { name: '失败', type: 'line', smooth: true, data: tasks.map((t: any) => t.failed_notes) },
    ],
  }
}

function render() {
  chart?.setOption(buildOption())
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  chart = echarts.init(container.value!)
  render()
  window.addEventListener('resize', resize)
})
watch(() => props.tasks, render, { deep: true })
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="container" class="chart-container" aria-label="抓取趋势图" />
</template>

<style scoped>
.chart-container { width: 100%; height: 320px; }
</style>
