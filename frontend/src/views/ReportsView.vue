<script setup lang="ts">
import { Delete, Download, Plus, View } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DOMPurify from 'dompurify'
import { api } from '@/api/client'

const rows = ref<any[]>([])
const cities = ref<any[]>([])
const preview = ref('')
const previewHtml = ref('')
async function renderPreview() {
  if (!preview.value) { previewHtml.value = ''; return }
  const { marked } = await import('marked')
  previewHtml.value = DOMPurify.sanitize(marked.parse(preview.value, { async: false }) as string)
}
watch(preview, renderPreview)
const dialog = ref(false)
const generating = ref(false)
const form = reactive<{ weekDate: Date | null; city: string }>({ weekDate: new Date(), city: '' })
const cityNames = computed(() => Object.fromEntries(cities.value.map((city) => [city.code, city.name])))

function toIsoWeek(value: Date): string {
  const date = new Date(Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()))
  const day = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - day)
  const year = date.getUTCFullYear()
  const yearStart = new Date(Date.UTC(year, 0, 1))
  const week = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  return `${year}-W${String(week).padStart(2, '0')}`
}

async function load() {
  const [reportResponse, cityResponse] = await Promise.all([api.reports(), api.settings('cities')])
  rows.value = reportResponse.data.data
  cities.value = cityResponse.data.data.filter((city: any) => city.enabled)
  if (!form.city && cities.value.length) form.city = cities.value[0].code
}

async function generate() {
  if (!form.weekDate) { ElMessage.warning('请选择周次'); return }
  if (!form.city) { ElMessage.warning('请选择城市'); return }
  generating.value = true
  try {
    await api.generateReport({ week: toIsoWeek(form.weekDate), cities: [form.city] })
    ElMessage.success('周报生成成功')
    await load()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || error.response?.data?.detail || '周报生成失败')
  } finally {
    generating.value = false
  }
}

async function show(id: number) {
  preview.value = (await api.report(id)).data.data.content
  dialog.value = true
}

async function download(row: any, format: 'md' | 'xlsx') {
  try {
    const response = await api.downloadReport(row.id, format)
    const disposition = response.headers?.['content-disposition'] || ''
    const matched = disposition.match(/filename="?([^";]+)"?/i)
    const filename = matched?.[1] || `${row.week}.${format}`
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch {
    ElMessage.error('周报下载失败')
  }
}

async function remove(row: any) {
  await ElMessageBox.confirm(`确认删除周报「${row.week}」？删除后不可恢复。`, '删除周报', { type: 'warning' })
  try {
    await api.deleteReport(row.id)
    ElMessage.success('周报已删除')
    await load()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '周报删除失败')
  }
}

onMounted(load)
</script>

<template>
  <ElCard shadow="never">
    <div class="toolbar">
      <ElDatePicker v-model="form.weekDate" type="week" format="YYYY 第 ww 周" placeholder="选择周次" aria-label="周次" />
      <ElSelect v-model="form.city" placeholder="选择城市" filterable aria-label="城市">
        <ElOption v-for="city in cities" :key="city.code" :label="city.name" :value="city.code" />
      </ElSelect>
      <ElButton type="primary" :icon="Plus" :loading="generating" @click="generate">生成周报</ElButton>
    </div>
    <ElTable :data="rows">
      <ElTableColumn prop="week" label="周次" />
      <ElTableColumn label="城市"><template #default="scope">{{ (scope.row.cities || []).map((code: string) => cityNames[code] || code).join('、') }}</template></ElTableColumn>
      <ElTableColumn prop="note_count" label="推文数" />
      <ElTableColumn prop="activity_count" label="活动数" />
      <ElTableColumn prop="status" label="状态" />
      <ElTableColumn label="操作" min-width="300" class-name="action-column"><template #default="scope"><ElButton text :icon="View" @click="show(scope.row.id)">预览</ElButton><ElButton text :icon="Download" @click="download(scope.row,'md')">Markdown</ElButton><ElButton text :icon="Download" @click="download(scope.row,'xlsx')">Excel</ElButton><ElButton text type="danger" :icon="Delete" @click="remove(scope.row)">删除</ElButton></template></ElTableColumn>
    </ElTable>
  </ElCard>
  <ElDialog v-model="dialog" title="周报预览" width="760"><div class="report-preview" v-html="previewHtml"></div></ElDialog>
</template>

<style scoped>
.report-preview :deep(h1) { font-size: 22px; margin: 0 0 12px; }
.report-preview :deep(h2) { font-size: 18px; margin: 16px 0 8px; }
.report-preview :deep(p) { margin: 6px 0; line-height: 1.7; }
.report-preview :deep(ul) { padding-left: 20px; }
</style>
