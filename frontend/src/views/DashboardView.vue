<script setup lang="ts">
import { Connection, VideoPlay } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getHealth } from '@/api/health'
import { api } from '@/api/client'

const status = ref<'loading' | 'ok' | 'error'>('loading')
const database = ref('SQLite')
const cities = ref<any[]>([])
const bloggers = ref<any[]>([])
const submitting = ref(false)
const form = reactive({ city: '', keywords: [] as string[], recent_filter: '一周内', blogger_ids: [] as number[] })
const recentFilters = ['不限', '一天内', '一周内', '半年内']
const selectedCity = computed(() => cities.value.find((city) => city.code === form.city))
const cityKeywords = computed(() => selectedCity.value?.keywords || [])
const cityBloggers = computed(() => bloggers.value.filter((blogger) => blogger.city_code === form.city && blogger.enabled))

watch(() => form.city, () => {
  form.keywords = []
  form.blogger_ids = []
  form.recent_filter = selectedCity.value?.recent_filter || '一周内'
})

async function initialize() {
  const [cityResponse, bloggerResponse] = await Promise.all([api.settings('cities'), api.settings('bloggers')])
  cities.value = cityResponse.data.data.filter((city: any) => city.enabled)
  bloggers.value = bloggerResponse.data.data
  if (cities.value.length) form.city = cities.value[0].code
  try {
    const result = await getHealth()
    database.value = result.database === 'sqlite' ? 'SQLite' : result.database
    status.value = result.status === 'ok' ? 'ok' : 'error'
  } catch {
    status.value = 'error'
  }
}

async function start() {
  if (!form.city) { ElMessage.warning('请选择城市'); return }
  if (!form.keywords.length && !form.blogger_ids.length) { ElMessage.warning('请至少选择一个关键词或博主'); return }
  submitting.value = true
  try {
    await api.createTask({ type: 'mixed', city: form.city, keywords: form.keywords, recent_filter: form.recent_filter, blogger_ids: form.blogger_ids })
    ElMessage.success('抓取任务已提交，可到任务日志查看进度')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || error.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(initialize)
</script>

<template>
  <div class="dashboard">
    <div class="page-intro"><div><p class="eyebrow">PHASE ONE</p><h2>小红书本地活动信息抓取系统</h2><p>从已配置的城市、关键词和博主中选择本次抓取范围。</p></div></div>

    <ElCard shadow="never" class="crawl-card">
      <template #header><div class="card-title"><ElIcon><VideoPlay /></ElIcon><strong>发起抓取</strong></div></template>
      <ElForm label-position="top">
        <div class="crawl-grid">
          <ElFormItem label="城市"><ElSelect v-model="form.city" placeholder="选择城市"><ElOption v-for="city in cities" :key="city.code" :label="city.name" :value="city.code" /></ElSelect></ElFormItem>
          <ElFormItem label="关键词"><ElSelect v-model="form.keywords" multiple collapse-tags collapse-tags-tooltip placeholder="选择一个或多个关键词"><ElOption v-for="word in cityKeywords" :key="word" :label="word" :value="word" /></ElSelect></ElFormItem>
          <ElFormItem label="时间范围"><ElSelect v-model="form.recent_filter"><ElOption v-for="item in recentFilters" :key="item" :label="item" :value="item" /></ElSelect></ElFormItem>
          <ElFormItem label="博主"><ElSelect v-model="form.blogger_ids" multiple collapse-tags collapse-tags-tooltip placeholder="选择一个或多个博主"><ElOption v-for="blogger in cityBloggers" :key="blogger.id" :label="blogger.username" :value="blogger.id" /></ElSelect></ElFormItem>
        </div>
        <div class="crawl-actions"><ElButton type="primary" :icon="VideoPlay" :loading="submitting" @click="start">开始抓取</ElButton><span>任务启动前会检查 Chrome 小红书登录状态</span></div>
      </ElForm>
    </ElCard>

    <ElCard shadow="never" class="status-card"><div class="status-card__content"><ElIcon :size="28" color="var(--el-color-primary)"><Connection /></ElIcon><div><strong>后端服务</strong><p>{{ status === 'ok' ? '服务运行正常' : status === 'loading' ? '正在检查服务' : '服务暂不可用' }}</p></div><ElTag :type="status === 'ok' ? 'success' : status === 'loading' ? 'info' : 'danger'">{{ database }}</ElTag></div></ElCard>
  </div>
</template>

<style scoped>
.crawl-card { margin-bottom: 20px; }
.card-title { display: flex; align-items: center; gap: 8px; }
.crawl-grid { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 0 20px; }
.crawl-grid :deep(.el-select) { width: 100%; }
.crawl-actions { display: flex; align-items: center; gap: 16px; color: var(--el-text-color-secondary); }
@media (max-width: 800px) { .crawl-grid { grid-template-columns: 1fr; } }
</style>
