<script setup lang="ts">
import { VideoPlay, View } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'

const rows = ref<any[]>([])
const logs = ref<any[]>([])
const drawer = ref(false)
const submitting = ref(false)
const form = reactive({ cities: 'shanghai', keywords: '周末活动,展览' })

async function load() {
  rows.value = (await api.tasks()).data.data.items
}

async function start() {
  if (submitting.value) return
  submitting.value = true
  try {
    await api.createTask({
      type: 'keyword',
      cities: form.cities.split(',').map((item) => item.trim()).filter(Boolean),
      keywords: form.keywords.split(',').map((item) => item.trim()).filter(Boolean),
    })
    ElMessage.success('任务已提交')
    await load()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || error.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

async function show(id: number) {
  logs.value = (await api.logs(id)).data.data
  drawer.value = true
}

onMounted(load)
</script>

<template>
  <ElCard shadow="never">
    <div class="toolbar">
      <ElInput v-model="form.cities" placeholder="城市代码，逗号分隔" />
      <ElInput v-model="form.keywords" placeholder="关键词，逗号分隔" />
      <ElButton type="primary" :icon="VideoPlay" :loading="submitting" :disabled="submitting" @click="start">开始抓取</ElButton>
    </div>
    <ElAlert title="任务会先检查 Chrome 小红书登录态；未登录时自动暂停" type="info" show-icon :closable="false" />
    <ElTable :data="rows">
      <ElTableColumn prop="id" label="ID" width="70" />
      <ElTableColumn prop="type" label="类型" />
      <ElTableColumn prop="status" label="状态"><template #default="scope"><ElTag>{{ scope.row.status }}</ElTag></template></ElTableColumn>
      <ElTableColumn prop="total_notes" label="笔记" />
      <ElTableColumn prop="error_message" label="错误" />
      <ElTableColumn label="操作"><template #default="scope"><ElButton text :icon="View" @click="show(scope.row.id)">日志</ElButton></template></ElTableColumn>
    </ElTable>
  </ElCard>
  <ElDrawer v-model="drawer" title="任务日志">
    <ElTimeline><ElTimelineItem v-for="item in logs" :key="item.id" :timestamp="item.created_at">{{ item.level }} - {{ item.message }}</ElTimelineItem></ElTimeline>
  </ElDrawer>
</template>
