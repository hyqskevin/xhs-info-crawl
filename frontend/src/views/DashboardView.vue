<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'

import { getHealth } from '@/api/health'

const status = ref<'loading' | 'ok' | 'error'>('loading')
const database = ref('SQLite')

onMounted(async () => {
  try {
    const result = await getHealth()
    database.value = result.database === 'sqlite' ? 'SQLite' : result.database
    status.value = result.status === 'ok' ? 'ok' : 'error'
  } catch {
    status.value = 'error'
  }
})
</script>

<template>
  <div class="dashboard">
    <div class="page-intro">
      <div>
        <p class="eyebrow">PHASE ONE</p>
        <h2>小红书本地活动信息抓取系统</h2>
        <p>本地运行的活动采集、审核和双格式导出工作台。</p>
      </div>
    </div>

    <ElCard shadow="never" class="status-card">
      <div class="status-card__content">
        <ElIcon :size="28" color="var(--el-color-primary)"><Connection /></ElIcon>
        <div>
          <strong>后端服务</strong>
          <p>{{ status === 'ok' ? '服务运行正常' : status === 'loading' ? '正在检查服务' : '服务暂不可用' }}</p>
        </div>
        <ElTag :type="status === 'ok' ? 'success' : status === 'loading' ? 'info' : 'danger'">
          {{ database }}
        </ElTag>
      </div>
    </ElCard>

    <ElAlert
      title="脚手架阶段"
      description="当前已建立前端、API、SQLite 与 Celery 基础；抓取和数据处理能力将在后续任务中实现。"
      type="info"
      show-icon
      :closable="false"
    />
  </div>
</template>
