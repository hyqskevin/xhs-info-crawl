<script setup lang="ts">
import { CircleCheck, Delete, Edit, Refresh, Search, View } from '@element-plus/icons-vue'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/api/client'

const rows = ref<any[]>([])
const cities = ref<any[]>([])
const total = ref(0)
const dialog = ref(false)
const drawer = ref(false)
const detail = ref<any>({})
const imageUrls = ref<string[]>([])
const imagesLoading = ref(false)
const editingId = ref<number | null>(null)
const selectedRows = ref<any[]>([])
const batchDeleting = ref(false)
const batchApproving = ref(false)
const filters = reactive({ city: '', status: '', dates: [] as string[], page: 1, page_size: 20 })
const form = reactive<any>({})
const statusLabels: Record<string, string> = { NEEDS_REVIEW: '待完善', RAW: '待审核', APPROVED: '已通过', PUBLISHED: '已发布' }
const statusTypes: Record<string, string> = { NEEDS_REVIEW: 'warning', RAW: 'primary', APPROVED: 'success', PUBLISHED: 'info' }
const cityNames = computed(() => Object.fromEntries(cities.value.map((city) => [city.code, city.name])))
const detailDrawerSize = computed(() => window.innerWidth < 768 ? '95%' : '70%')

function queryParams() {
  return {
    city: filters.city || undefined,
    status: filters.status || undefined,
    start_date: filters.dates?.[0] || undefined,
    end_date: filters.dates?.[1] || undefined,
    page: filters.page,
    page_size: filters.page_size,
  }
}

async function load() {
  const response = await api.activities(queryParams())
  rows.value = response.data.data.items
  total.value = response.data.pagination.total
}

async function initialize() {
  cities.value = (await api.settings('cities')).data.data
  await load()
}

function applyFilters() { filters.page = 1; load() }
function resetFilters() { Object.assign(filters, { city: '', status: '', dates: [], page: 1, page_size: 20 }); load() }
function changePageSize() { filters.page = 1; load() }
function formatTime(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '待确认' }

function openEdit(row: any) {
  editingId.value = row.id
  Object.keys(form).forEach((key) => delete form[key])
  Object.assign(form, row)
  dialog.value = true
}

async function save() {
  const data = { ...form, start_time: form.start_time ? new Date(form.start_time).toISOString() : null, end_time: form.end_time ? new Date(form.end_time).toISOString() : null }
  await api.updateActivity(editingId.value!, data)
  dialog.value = false
  ElMessage.success('保存成功')
  await load()
}

async function remove(id: number) {
  await ElMessageBox.confirm('确认删除该活动？', '删除确认', { type: 'warning' })
  await api.deleteActivity(id)
  ElMessage.success('已删除')
  await load()
}

async function batchRemove() {
  if (!selectedRows.value.length) return
  await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 条活动？`, '批量删除确认', { type: 'warning' })
  batchDeleting.value = true
  try {
    const response = await api.deleteActivities(selectedRows.value.map((row) => row.id))
    ElMessage.success(`已删除 ${response.data.data.deleted_count} 条活动`)
    selectedRows.value = []
    await load()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '批量删除失败')
  } finally {
    batchDeleting.value = false
  }
}

async function batchApprove() {
  if (!selectedRows.value.length) return
  await ElMessageBox.confirm(`确认将选中的 ${selectedRows.value.length} 条活动标记为已通过？`, '批量审核确认', { type: 'warning' })
  batchApproving.value = true
  try {
    const response = await api.approveActivities(selectedRows.value.map((row) => row.id))
    ElMessage.success(`已通过 ${response.data.data.approved_count} 条活动`)
    selectedRows.value = []
    await load()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '批量审核失败')
  } finally {
    batchApproving.value = false
  }
}

function releaseImages() {
  imageUrls.value.forEach((url) => URL.revokeObjectURL(url))
  imageUrls.value = []
}

async function show(id: number) {
  releaseImages()
  detail.value = (await api.activity(id)).data.data
  drawer.value = true
  imagesLoading.value = true
  try {
    const responses = await Promise.all((detail.value.images || []).map((image: any) => api.activityImage(id, image.id)))
    imageUrls.value = responses.map((response: any) => URL.createObjectURL(response.data))
  } catch {
    ElMessage.error('部分来源图片加载失败')
  } finally {
    imagesLoading.value = false
  }
}
onMounted(initialize)
onUnmounted(releaseImages)
</script>

<template>
  <ElCard shadow="never" class="page-card">
    <div class="toolbar filters-toolbar">
      <ElSelect v-model="filters.city" placeholder="城市" clearable class="filter-item">
        <ElOption v-for="city in cities" :key="city.code" :label="city.name" :value="city.code" />
      </ElSelect>
      <ElDatePicker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="活动开始日期" end-placeholder="活动结束日期" aria-label="活动时间" />
      <ElSelect v-model="filters.status" placeholder="审核状态" clearable class="filter-item"><ElOption v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" /></ElSelect>
      <ElButton :icon="Search" @click="applyFilters">筛选</ElButton>
      <ElButton :icon="Refresh" @click="resetFilters">重置</ElButton>
      <ElButton type="success" :icon="CircleCheck" :disabled="!selectedRows.length" :loading="batchApproving" @click="batchApprove">批量通过</ElButton>
      <ElButton type="danger" :icon="Delete" :disabled="!selectedRows.length" :loading="batchDeleting" @click="batchRemove">批量删除</ElButton>
    </div>

    <ElTable :data="rows" @selection-change="selectedRows = $event">
      <ElTableColumn type="selection" width="48" />
      <ElTableColumn prop="name" label="活动名称" min-width="200" show-overflow-tooltip />
      <ElTableColumn label="城市" width="110"><template #default="scope">{{ cityNames[scope.row.city_code] || scope.row.city_code }}</template></ElTableColumn>
      <ElTableColumn label="活动时间" width="190"><template #default="scope">{{ formatTime(scope.row.start_time) }}</template></ElTableColumn>
      <ElTableColumn prop="location" label="地点" min-width="180" show-overflow-tooltip />
      <ElTableColumn label="状态" width="110"><template #default="scope"><ElTag :type="statusTypes[scope.row.status] as any">{{ statusLabels[scope.row.status] || scope.row.status }}</ElTag></template></ElTableColumn>
      <ElTableColumn label="操作" width="220"><template #default="scope"><ElButton text :icon="View" @click="show(scope.row.id)">详情</ElButton><ElButton text type="primary" :icon="Edit" @click="openEdit(scope.row)">编辑审核</ElButton><ElButton text type="danger" @click="remove(scope.row.id)">删除</ElButton></template></ElTableColumn>
    </ElTable>
    <ElPagination v-model:current-page="filters.page" v-model:page-size="filters.page_size" :page-sizes="[10, 20, 50, 100]" :total="total" layout="total, sizes, prev, pager, next, jumper" @current-change="load" @size-change="changePageSize" />
  </ElCard>

  <ElDialog v-model="dialog" title="编辑并审核活动" width="680">
    <ElForm label-width="90px">
      <ElFormItem label="名称"><ElInput v-model="form.name" /></ElFormItem>
      <ElFormItem label="城市"><ElSelect v-model="form.city_code" style="width: 100%"><ElOption v-for="city in cities" :key="city.code" :label="city.name" :value="city.code" /></ElSelect></ElFormItem>
      <ElFormItem label="开始时间"><ElDatePicker v-model="form.start_time" type="datetime" style="width: 100%" /></ElFormItem>
      <ElFormItem label="结束时间"><ElDatePicker v-model="form.end_time" type="datetime" style="width: 100%" /></ElFormItem>
      <ElFormItem label="地点"><ElInput v-model="form.location" /></ElFormItem>
      <ElFormItem label="费用"><ElInput v-model="form.price" /></ElFormItem>
      <ElFormItem label="类型"><ElInput v-model="form.type" /></ElFormItem>
      <ElFormItem label="审核状态"><ElSelect v-model="form.status" style="width: 100%"><ElOption label="待完善" value="NEEDS_REVIEW" /><ElOption label="待审核" value="RAW" /><ElOption label="已通过" value="APPROVED" /></ElSelect></ElFormItem>
      <ElFormItem label="来源"><ElInput v-model="form.source_url" disabled /></ElFormItem>
      <ElFormItem label="摘要"><ElInput v-model="form.summary" type="textarea" /></ElFormItem>
    </ElForm>
    <template #footer><ElButton @click="dialog = false">取消</ElButton><ElButton type="primary" @click="save">保存</ElButton></template>
  </ElDialog>

  <ElDrawer v-model="drawer" title="活动详情" :size="detailDrawerSize" @closed="releaseImages">
    <ElDescriptions :column="1" border>
      <ElDescriptionsItem label="名称">{{ detail.name }}</ElDescriptionsItem>
      <ElDescriptionsItem label="时间">{{ formatTime(detail.start_time) }}</ElDescriptionsItem>
      <ElDescriptionsItem label="地点">{{ detail.location }}</ElDescriptionsItem>
      <ElDescriptionsItem label="费用">{{ detail.price }}</ElDescriptionsItem>
      <ElDescriptionsItem label="状态">{{ statusLabels[detail.status] || detail.status }}</ElDescriptionsItem>
      <ElDescriptionsItem label="摘要">{{ detail.summary }}</ElDescriptionsItem>
      <ElDescriptionsItem label="原文标题">{{ detail.note?.title || '-' }}</ElDescriptionsItem>
      <ElDescriptionsItem label="原文链接"><ElLink v-if="detail.note?.source_url" :href="detail.note.source_url" type="primary" target="_blank">查看小红书原文</ElLink><span v-else>-</span></ElDescriptionsItem>
    </ElDescriptions>
    <section class="source-images">
      <h3>来源页面图片</h3>
      <ElSkeleton v-if="imagesLoading" :rows="4" animated />
      <div v-else-if="imageUrls.length" class="source-image-grid">
        <ElImage v-for="(url, index) in imageUrls" :key="url" :src="url" :preview-src-list="imageUrls" :initial-index="index" fit="cover" lazy />
      </div>
      <ElEmpty v-else description="暂无来源图片" />
    </section>
  </ElDrawer>
</template>

<style scoped>
.filters-toolbar { flex-wrap: wrap; }
.filter-item { width: 180px; }
.source-images { margin-top: 24px; }
.source-images h3 { margin: 0 0 14px; color: var(--el-text-color-primary); }
.source-image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; }
.source-image-grid :deep(.el-image) { width: 100%; height: 220px; border-radius: var(--el-border-radius-base); background: var(--el-fill-color-light); }
</style>
