<script setup lang="ts">
import { CircleCheck, CircleClose, Delete, Edit, Refresh, Search, View } from '@element-plus/icons-vue'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/api/client'

const rows = ref<any[]>([])
const cities = ref<any[]>([])
const total = ref(0)
const drawer = ref(false)
const editDialog = ref(false)
const noteEditDialog = ref(false)
const noteSaving = ref(false)
const noteEditFromDetail = ref(false)
const detail = ref<any>({ activities: [], images: [] })
const form = reactive<any>({})
const noteForm = reactive<any>({ title: '', content: '', city_code: '', published_at: null, source_url: '' })
const editingId = ref<number | null>(null)
const imageUrls = ref<string[]>([])
const imagesLoading = ref(false)
const selectedRows = ref<any[]>([])
const batchDeleting = ref(false)
const batchApproving = ref(false)
const filters = reactive({ city: '', review_status: '', keyword: '', dates: [] as string[], page: 1, page_size: 20 })
const statusLabels: Record<string, string> = { PENDING: '待审核', APPROVED: '已通过', REJECTED: '未通过', RAW: '待审核', NEEDS_REVIEW: '待完善' }
const statusTypes: Record<string, string> = { PENDING: 'primary', APPROVED: 'success', REJECTED: 'danger', RAW: 'primary', NEEDS_REVIEW: 'warning' }
const cityNames = computed(() => Object.fromEntries(cities.value.map((city) => [city.code, city.name])))
const detailDrawerSize = computed(() => window.innerWidth < 768 ? '95%' : '70%')

function queryParams() {
  const params: any = { city: filters.city || undefined, review_status: filters.review_status || undefined, start_date: filters.dates?.[0] || undefined, end_date: filters.dates?.[1] || undefined, page: filters.page, page_size: filters.page_size }
  const kw = filters.keyword?.trim()
  if (kw) params.keyword = kw
  return params
}
async function load() { const response = await api.notes(queryParams()); rows.value = response.data.data.items; total.value = response.data.pagination.total }
async function initialize() { cities.value = (await api.settings('cities')).data.data; await load() }
function applyFilters() { filters.page = 1; load() }
function resetFilters() { Object.assign(filters, { city: '', review_status: '', keyword: '', dates: [], page: 1, page_size: 20 }); load() }
function formatTime(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '待确认' }
function formatDate(value: string | null) { return value ? new Date(value).toISOString().slice(0, 10) : '待确认' }

async function batchRemove() {
  if (!selectedRows.value.length) return
  await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 篇推文及其活动？`, '批量删除确认', { type: 'warning' })
  batchDeleting.value = true
  try { const response = await api.deleteNotes(selectedRows.value.map(row => row.id)); ElMessage.success(`已删除 ${response.data.data.deleted_count} 篇推文`); selectedRows.value = []; await load() }
  finally { batchDeleting.value = false }
}
async function batchApprove() {
  if (!selectedRows.value.length) return
  await ElMessageBox.confirm(`确认通过选中的 ${selectedRows.value.length} 篇推文？`, '批量审核确认', { type: 'warning' })
  batchApproving.value = true
  try { const response = await api.approveNotes(selectedRows.value.map(row => row.id)); ElMessage.success(`已通过 ${response.data.data.approved_count} 篇推文`); selectedRows.value = []; await load() }
  finally { batchApproving.value = false }
}
function releaseImages() { imageUrls.value.forEach(url => URL.revokeObjectURL(url)); imageUrls.value = [] }
async function show(id: number) {
  releaseImages(); detail.value = (await api.note(id)).data.data; drawer.value = true; imagesLoading.value = true
  try { const responses = await Promise.all((detail.value.images || []).map((image: any) => api.noteImage(id, image.id))); imageUrls.value = responses.map((response: any) => URL.createObjectURL(response.data)) }
  catch { ElMessage.error('部分来源图片加载失败') }
  finally { imagesLoading.value = false }
}
function openEdit(activity: any) { editingId.value = activity.id; Object.keys(form).forEach(key => delete form[key]); Object.assign(form, activity); editDialog.value = true }
async function saveActivity() { await api.updateActivity(editingId.value!, { ...form, start_time: form.start_time ? new Date(form.start_time).toISOString() : null, end_time: form.end_time ? new Date(form.end_time).toISOString() : null }); editDialog.value = false; await show(detail.value.id); await load(); ElMessage.success('活动已更新') }
async function removeActivity(activity: any) { await ElMessageBox.confirm('确认删除该识别活动？', '删除确认', { type: 'warning' }); await api.deleteActivity(activity.id); await show(detail.value.id); await load() }
async function openNoteEdit(note: any, fromDetail = false) {
  const value = fromDetail ? note : (await api.note(note.id)).data.data
  Object.assign(noteForm, {
    id: value.id,
    title: value.title || '',
    content: value.content || '',
    city_code: value.city_code || '',
    published_at: value.published_at ? new Date(value.published_at) : null,
    source_url: value.source_url || '',
  })
  noteEditFromDetail.value = fromDetail
  noteEditDialog.value = true
}
async function saveNote() {
  if (!noteForm.title.trim() || !noteForm.city_code) { ElMessage.warning('请填写推文标题并选择城市'); return }
  noteSaving.value = true
  try {
    await api.updateNote(noteForm.id, {
      title: noteForm.title.trim(),
      content: noteForm.content,
      city_code: noteForm.city_code,
      published_at: noteForm.published_at ? new Date(noteForm.published_at).toISOString() : null,
    })
    noteEditDialog.value = false
    await load()
    if (noteEditFromDetail.value) await show(noteForm.id)
    ElMessage.success('推文已更新')
  } catch { ElMessage.error('推文更新失败，请重试') }
  finally { noteSaving.value = false }
}
async function reviewNote(note: any, target: 'APPROVED' | 'REJECTED', fromDetail = false) {
  const action = target === 'APPROVED' ? '通过' : '驳回'
  try {
    await ElMessageBox.confirm(`确认${action}这篇推文？`, '单篇审核确认', { type: 'warning' })
    await api.reviewNote(note.id, target)
    await load()
    if (fromDetail) await show(note.id)
    ElMessage.success(`推文已${action}`)
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('审核失败，请重试')
  }
}
onMounted(initialize)
onUnmounted(releaseImages)
</script>

<template>
  <ElCard shadow="never" class="page-card">
    <div class="toolbar filters-toolbar">
      <ElSelect v-model="filters.city" placeholder="城市" clearable class="filter-item"><ElOption v-for="city in cities" :key="city.code" :label="city.name" :value="city.code" /></ElSelect>
      <ElInput v-model="filters.keyword" placeholder="搜索推文标题或正文" clearable class="filter-item" aria-label="关键字" @keyup.enter="applyFilters" />
      <ElDatePicker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="推文开始日期" end-placeholder="推文结束日期" aria-label="发布时间" />
      <ElSelect v-model="filters.review_status" placeholder="审核状态" clearable class="filter-item"><ElOption label="待审核" value="PENDING" /><ElOption label="已通过" value="APPROVED" /><ElOption label="已驳回" value="REJECTED" /></ElSelect>
      <ElButton :icon="Search" @click="applyFilters">筛选</ElButton><ElButton :icon="Refresh" @click="resetFilters">重置</ElButton>
      <ElButton type="success" :icon="CircleCheck" :disabled="!selectedRows.length" :loading="batchApproving" @click="batchApprove">批量通过</ElButton>
      <ElButton type="danger" :icon="Delete" :disabled="!selectedRows.length" :loading="batchDeleting" @click="batchRemove">批量删除</ElButton>
    </div>
    <ElTable :data="rows" @selection-change="selectedRows = $event">
      <ElTableColumn type="selection" width="48" /><ElTableColumn prop="title" label="推文标题" min-width="260" show-overflow-tooltip />
      <ElTableColumn label="城市" width="110"><template #default="scope">{{ cityNames[scope.row.city_code] || scope.row.city_code }}</template></ElTableColumn>
      <ElTableColumn label="发布时间" width="190"><template #default="scope">{{ formatDate(scope.row.published_at) }}</template></ElTableColumn>
      <ElTableColumn prop="activity_count" label="识别活动" width="110" />
      <ElTableColumn label="审核状态" width="110"><template #default="scope"><ElTag :type="statusTypes[scope.row.review_status] as any">{{ statusLabels[scope.row.review_status] || scope.row.review_status }}</ElTag></template></ElTableColumn>
      <ElTableColumn label="操作" min-width="330"><template #default="scope"><div class="row-actions"><ElButton text :icon="View" @click="show(scope.row.id)">详情</ElButton><ElButton text :icon="Edit" @click="openNoteEdit(scope.row)">编辑推文</ElButton><ElButton v-if="scope.row.review_status !== 'APPROVED'" text type="success" :icon="CircleCheck" @click="reviewNote(scope.row, 'APPROVED')">通过</ElButton><ElButton v-if="scope.row.review_status !== 'REJECTED'" text type="danger" :icon="CircleClose" @click="reviewNote(scope.row, 'REJECTED')">驳回</ElButton></div></template></ElTableColumn>
    </ElTable>
    <ElPagination v-model:current-page="filters.page" v-model:page-size="filters.page_size" :page-sizes="[10,20,50,100]" :total="total" layout="total, sizes, prev, pager, next, jumper" @current-change="load" @size-change="filters.page=1;load()" />
  </ElCard>
  <ElDrawer v-model="drawer" title="推文详情" :size="detailDrawerSize" @closed="releaseImages">
    <div class="detail-actions"><ElButton :icon="Edit" @click="openNoteEdit(detail, true)">编辑推文</ElButton><ElButton v-if="detail.review_status !== 'APPROVED'" type="success" :icon="CircleCheck" @click="reviewNote(detail, 'APPROVED', true)">通过</ElButton><ElButton v-if="detail.review_status !== 'REJECTED'" type="danger" :icon="CircleClose" @click="reviewNote(detail, 'REJECTED', true)">驳回</ElButton></div>
    <ElDescriptions :column="1" border><ElDescriptionsItem label="标题">{{ detail.title }}</ElDescriptionsItem><ElDescriptionsItem label="审核状态"><ElTag :type="statusTypes[detail.review_status] as any">{{ statusLabels[detail.review_status] || detail.review_status }}</ElTag></ElDescriptionsItem><ElDescriptionsItem label="正文">{{ detail.content || '-' }}</ElDescriptionsItem><ElDescriptionsItem label="原文"><ElLink :href="detail.source_url" target="_blank" type="primary">查看小红书原文</ElLink></ElDescriptionsItem></ElDescriptions>
    <h3>识别活动</h3>
    <ElTable :data="detail.activities || []">
      <ElTableColumn prop="name" label="名称" min-width="160" />
      <ElTableColumn prop="location" label="地点" min-width="140" />
      <ElTableColumn label="开始时间" min-width="160" show-overflow-tooltip><template #default="scope">{{ formatTime(scope.row.start_time) }}</template></ElTableColumn>
      <ElTableColumn label="结束时间" min-width="160" show-overflow-tooltip><template #default="scope">{{ scope.row.end_time ? formatTime(scope.row.end_time) : '-' }}</template></ElTableColumn>
      <ElTableColumn label="操作" width="150"><template #default="scope"><ElButton text :icon="Edit" @click="openEdit(scope.row)">编辑</ElButton><ElButton text type="danger" @click="removeActivity(scope.row)">删除</ElButton></template></ElTableColumn>
    </ElTable>
    <section class="source-images"><h3>来源页面图片</h3><ElSkeleton v-if="imagesLoading" :rows="4" animated /><div v-else-if="imageUrls.length" class="source-image-grid"><ElImage v-for="(url,index) in imageUrls" :key="url" :src="url" :preview-src-list="imageUrls" :initial-index="index" fit="cover" lazy /></div><ElEmpty v-else description="暂无来源图片" /></section>
  </ElDrawer>
  <ElDialog v-model="noteEditDialog" title="编辑推文" width="680px">
    <ElForm label-width="90px">
      <ElFormItem label="推文标题" required><ElInput v-model="noteForm.title" aria-label="推文标题" maxlength="512" /></ElFormItem>
      <ElFormItem label="推文正文"><ElInput v-model="noteForm.content" aria-label="推文正文" type="textarea" :rows="6" /></ElFormItem>
      <ElFormItem label="城市" required><ElSelect v-model="noteForm.city_code" aria-label="城市"><ElOption v-for="city in cities" :key="city.code" :label="city.name" :value="city.code" /></ElSelect></ElFormItem>
      <ElFormItem label="发布时间"><ElDatePicker v-model="noteForm.published_at" aria-label="发布时间" type="datetime" placeholder="待确认" /></ElFormItem>
      <ElFormItem label="原文链接"><ElInput v-model="noteForm.source_url" aria-label="原文链接" disabled /></ElFormItem>
    </ElForm>
    <template #footer><ElButton @click="noteEditDialog=false">取消</ElButton><ElButton type="primary" :loading="noteSaving" @click="saveNote">保存推文</ElButton></template>
  </ElDialog>
  <ElDialog v-model="editDialog" title="编辑识别活动" width="680"><ElForm label-width="90px"><ElFormItem label="名称"><ElInput v-model="form.name" aria-label="活动名称" /></ElFormItem><ElFormItem label="地点"><ElInput v-model="form.location" aria-label="活动地点" /></ElFormItem><ElFormItem label="摘要"><ElInput v-model="form.summary" aria-label="活动摘要" type="textarea" /></ElFormItem></ElForm><template #footer><ElButton @click="editDialog=false">取消</ElButton><ElButton type="primary" @click="saveActivity">保存</ElButton></template></ElDialog>
</template>

<style scoped>
.filters-toolbar{flex-wrap:wrap}.filter-item{width:180px}.row-actions{display:flex;align-items:center;white-space:nowrap}.detail-actions{display:flex;justify-content:flex-end;gap:8px;margin-bottom:16px}.source-images{margin-top:24px}.source-image-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}.source-image-grid :deep(.el-image){width:100%;height:220px;border-radius:var(--el-border-radius-base);background:var(--el-fill-color-light)}
</style>
