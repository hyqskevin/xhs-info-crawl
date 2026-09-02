<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useECharts } from '@/composables/useECharts'

const props = defineProps<{ counts: Record<string, number> }>()
const container = ref<HTMLElement | null>(null)

const statusLabels: Record<string, string> = {
  COMPLETED: '成功',
  COMPLETED_WITH_ERRORS: '部分成功',
  FAILED: '失败',
  STOPPED: '已停止',
  OTHER: '其他',
}
const order = ['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'STOPPED', 'OTHER']

function buildOption(counts: Record<string, number>) {
  const data = counts || {}
  const seriesData = order
    .filter((key) => data[key])
    .map((key) => ({ name: statusLabels[key] || key, value: data[key] }))
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['38%', '65%'],
        center: ['50%', '44%'],
        label: { formatter: '{b}\n{d}%' },
        data: seriesData,
      },
    ],
  }
}

useECharts({ container, data: toRef(props, 'counts'), buildOption })
</script>

<template>
  <div ref="container" class="chart-container" aria-label="抓取成功率图" />
</template>

<style scoped>
.chart-container { width: 100%; height: 320px; }
</style>
