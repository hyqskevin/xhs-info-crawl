<script setup lang="ts">
import { Connection, Link, RefreshRight, VideoPlay } from '@element-plus/icons-vue'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getHealth } from '@/api/health'
import { api } from '@/api/client'

const status = ref<'loading' | 'ok' | 'error'>('loading')
const database = ref('SQLite')
const cities = ref<any[]>([])
const bloggers = ref<any[]>([])
const submitting = ref(false)
const restarting = ref(false)
const openingLogin = ref(false)
const stopping = ref(false)
const lastTask = ref<any>(null)
let pollTimer: ReturnType<typeof setInterval> | undefined
const form = reactive({ city: '', keywords: [] as string[], recent_filter: '一周内', blogger_ids: [] as number[] })
const recentFilters = ['不限', '一天内', '一周内', '半年内']
const selectedCity = computed(() => cities.value.find((city) => city.code === form.city))
const cityKeywords = computed(() => selectedCity.value?.keywords || [])
const cityBloggers = computed(() => bloggers.value.filter((blogger: any) => (blogger.city_codes || []).includes(form.city) && blogger.enabled))
const incompleteBloggers = computed(() => form.blogger_ids.filter((id: number) => {
  const b = bloggers.value.find((x: any) => x.id === id)
  return b && !b.profile_url
}))
const statusLabels: Record<string, string> = { PENDING: '等待中', RUNNING: '抓取中', STOP_REQUESTED: '正在停止', STOPPED: '已停止', COMPLETED: '已完成', COMPLETED_WITH_ERRORS: '完成但有错误', FAILED: '失败', PAUSED: '等待登录' }
const stageLabels: Record<string, string> = { SEARCHING: '搜索笔记', DOWNLOADING: '下载笔记', OCR: 'OCR 识别', EXTRACTING: '提取活动', ARCHIVING: '归档结果' }

watch(() => form.city, () => {
  form.keywords = []
  form.blogger_ids = []
  form.recent_filter = selectedCity.value?.recent_filter || '一周内'
})

async function initialize() {
  const [cityResponse, bloggerResponse] = await Promise.all([api.settings('cities'), api.settings('bloggers'), loadLatestTask()])
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
  pollTimer = setInterval(loadLatestTask, 3000)
}

async function loadLatestTask() {
  try { lastTask.value = (await api.dashboard()).data.data.last_task } catch { /* health card reports service errors */ }
}

async function start() {
  if (!form.city) { ElMessage.warning('请选择城市'); return }
  if (!form.keywords.length && !form.blogger_ids.length) { ElMessage.warning('请至少选择一个关键词或博主'); return }
  if (incompleteBloggers.value.length) {
    ElMessage.warning(`所选博主信息不完整（${incompleteBloggers.value.length} 个），请到配置中心点"补充博主信息"后再发起抓取`)
    return
  }
  submitting.value = true
  try {
    await api.createTask({ type: 'mixed', city: form.city, keywords: form.keywords, recent_filter: form.recent_filter, blogger_ids: form.blogger_ids })
    ElMessage.success('抓取任务已提交，可到任务日志查看进度')
    await loadLatestTask()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || error.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

async function restart() {
  if (!lastTask.value) return
  restarting.value = true
  try {
    await api.restartTask(lastTask.value.id)
    ElMessage.success(lastTask.value.status === 'PAUSED' ? '登录状态正常，任务已继续抓取' : '任务已继续抓取')
    await loadLatestTask()
  } catch (error:any) {
    ElMessage.error(error.response?.data?.message === 'AUTH_REQUIRED' ? '尚未检测到小红书登录状态，请登录后重试' : error.response?.data?.message || error.response?.data?.detail || '任务续跑失败')
  } finally { restarting.value = false }
}

async function openLogin() {
  openingLogin.value = true
  try {
    await api.openXhsLogin()
    ElMessage.success('已打开 Chrome 小红书登录页')
  } catch (error:any) {
    ElMessage.error(error.response?.data?.message || '无法打开 Chrome 小红书登录页')
  } finally { openingLogin.value = false }
}

async function stop() {
  if (!lastTask.value) return
  await ElMessageBox.confirm('当前笔记完成后停止，已处理数据会保留。确认停止抓取？', '安全停止', { type: 'warning' })
  stopping.value = true
  try {
    await api.stopTask(lastTask.value.id)
    ElMessage.success('已请求安全停止')
    await loadLatestTask()
  } catch (error:any) {
    ElMessage.error(error.response?.data?.detail || '停止任务失败')
  } finally { stopping.value = false }
}

async function finish() {
  if (!lastTask.value) return
  await ElMessageBox.confirm('此任务已失败。结束抓取将强制清理残留状态并关闭 Browser 标签，已抓取数据会保留。确认结束？', '结束抓取', { type: 'warning' })
  stopping.value = true
  try {
    await api.stopTask(lastTask.value.id)
    ElMessage.success('抓取已结束')
    await loadLatestTask()
  } catch (error:any) {
    ElMessage.error(error.response?.data?.detail || '结束抓取失败')
  } finally { stopping.value = false }
}

onMounted(initialize)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
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
          <ElFormItem label="博主">
          <ElSelect v-model="form.blogger_ids" multiple collapse-tags collapse-tags-tooltip placeholder="选择一个或多个博主">
            <ElOption v-for="blogger in cityBloggers" :key="blogger.id" :value="blogger.id">
              <span style="float:left">{{ blogger.username }}</span>
              <span v-if="!blogger.profile_url" style="float:right;color:var(--el-color-warning);font-size:12px">待补充</span>
            </ElOption>
          </ElSelect>
        </ElFormItem>
        </div>
        <div class="crawl-actions"><ElButton type="primary" :icon="VideoPlay" :loading="submitting" @click="start">开始抓取</ElButton><span>任务启动前会检查 Chrome 小红书登录状态</span></div>
      </ElForm>
    </ElCard>

    <ElCard v-if="lastTask" shadow="never" class="progress-card">
      <template #header><div class="card-title"><strong>最近抓取任务 #{{ lastTask.id }}</strong><ElTag>{{ statusLabels[lastTask.status] || lastTask.status }}</ElTag></div></template>
      <div class="progress-summary">
        <div><span>当前阶段</span><strong>{{ stageLabels[lastTask.current_stage] || '未执行' }}</strong></div>
        <div><span>当前笔记</span><strong>{{ lastTask.current_note || '-' }}</strong></div>
        <div><span>发现</span><strong>{{ lastTask.total_notes }}</strong></div>
        <div><span>已下载</span><strong>{{ lastTask.downloaded_notes }}</strong></div>
        <div><span>OCR 完成</span><strong>{{ lastTask.ocr_notes }}</strong></div>
        <div><span>提取完成</span><strong>{{ lastTask.extracted_notes }}</strong></div>
        <div><span>失败</span><strong>{{ lastTask.failed_notes }}</strong></div>
        <div><span>已跳过</span><strong>{{ lastTask.skipped_notes || 0 }}</strong></div>
        <div><span>活动已跳过</span><strong>{{ lastTask.skipped_activities || 0 }}</strong></div>
      </div>
      <ElProgress :percentage="lastTask.progress_percent || 0" :indeterminate="lastTask.progress_percent == null && ['PENDING','RUNNING'].includes(lastTask.status)" />
      <ElAlert v-if="lastTask.error_message" :title="lastTask.error_message" type="error" :closable="false" />
      <ElButton v-if="['FAILED','STOPPED'].includes(lastTask.status)" type="primary" :icon="RefreshRight" :loading="restarting" @click="restart">继续抓取</ElButton>
      <ElButton v-if="lastTask.status === 'FAILED'" type="danger" :loading="stopping" @click="finish">结束抓取</ElButton>
      <ElButton v-if="lastTask.status === 'PAUSED'" :icon="Link" :loading="openingLogin" @click="openLogin">打开小红书登录</ElButton>
      <ElButton v-if="lastTask.status === 'PAUSED'" type="primary" :icon="RefreshRight" :loading="restarting" @click="restart">检测登录并继续</ElButton>
      <ElButton v-if="['PENDING','RUNNING','STOP_REQUESTED'].includes(lastTask.status)" type="danger" :loading="stopping || lastTask.status === 'STOP_REQUESTED'" :disabled="lastTask.status === 'STOP_REQUESTED'" @click="stop">停止抓取</ElButton>
    </ElCard>

    <ElCard shadow="never" class="status-card"><div class="status-card__content"><ElIcon :size="28" color="var(--el-color-primary)"><Connection /></ElIcon><div><strong>后端服务</strong><p>{{ status === 'ok' ? '服务运行正常' : status === 'loading' ? '正在检查服务' : '服务暂不可用' }}</p></div><ElTag :type="status === 'ok' ? 'success' : status === 'loading' ? 'info' : 'danger'">{{ database }}</ElTag></div></ElCard>
  </div>
</template>

<style scoped>
.crawl-card { margin-bottom: 20px; }
.progress-card { margin-bottom: 20px; }
.progress-card .card-title { justify-content: space-between; }
.progress-summary { display: grid; grid-template-columns: repeat(4,minmax(120px,1fr)); gap: 14px; margin-bottom: 16px; }
.progress-summary div { display: flex; flex-direction: column; gap: 4px; }
.progress-summary span { color: var(--el-text-color-secondary); }
.progress-card .el-alert,.progress-card .el-button { margin-top: 14px; }
.card-title { display: flex; align-items: center; gap: 8px; }
.crawl-grid { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 0 20px; }
.crawl-grid :deep(.el-select) { width: 100%; }
.crawl-actions { display: flex; align-items: center; gap: 16px; color: var(--el-text-color-secondary); }
@media (max-width: 800px) { .crawl-grid { grid-template-columns: 1fr; } }
</style>
