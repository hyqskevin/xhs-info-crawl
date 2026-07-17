<script setup lang="ts">
import { View } from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'
import { api } from '@/api/client'

const rows = ref<any[]>([])
const logs = ref<any[]>([])
const drawer = ref(false)
const statusLabels: Record<string, string> = { PENDING: '等待中', RUNNING: '抓取中', DOWNLOADING: '下载中', COMPLETED: '已完成', FAILED: '失败', PAUSED: '等待登录' }

async function load() { rows.value = (await api.tasks()).data.data.items }
async function show(id: number) { logs.value = (await api.logs(id)).data.data; drawer.value = true }
onMounted(load)
</script>

<template>
  <ElCard shadow="never">
    <template #header><strong>抓取日志</strong></template>
    <ElAlert title="此页面仅用于监控抓取任务；请在仪表盘发起新的抓取" type="info" show-icon :closable="false" />
    <ElTable :data="rows">
      <ElTableColumn prop="id" label="任务 ID" width="100" />
      <ElTableColumn label="状态" width="130"><template #default="scope"><ElTag>{{ statusLabels[scope.row.status] || scope.row.status }}</ElTag></template></ElTableColumn>
      <ElTableColumn prop="total_notes" label="发现笔记" width="110" />
      <ElTableColumn prop="success_notes" label="成功" width="90" />
      <ElTableColumn prop="failed_notes" label="失败" width="90" />
      <ElTableColumn prop="created_at" label="创建时间" min-width="180" />
      <ElTableColumn prop="error_message" label="错误" min-width="220" show-overflow-tooltip />
      <ElTableColumn label="操作" width="100"><template #default="scope"><ElButton text :icon="View" @click="show(scope.row.id)">日志</ElButton></template></ElTableColumn>
    </ElTable>
  </ElCard>
  <ElDrawer v-model="drawer" title="任务日志"><ElTimeline><ElTimelineItem v-for="item in logs" :key="item.id" :timestamp="item.created_at">{{ item.level }} - {{ item.message }}</ElTimelineItem></ElTimeline></ElDrawer>
</template>
