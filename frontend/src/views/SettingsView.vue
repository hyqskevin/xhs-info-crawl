<script setup lang="ts">
import { Connection, Delete, Download, Edit, Loading, MagicStick, Plus, UploadFilled } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/api/client'
import KeywordGroupSettings from '@/components/KeywordGroupSettings.vue'

const tab = ref<'cities' | 'bloggers' | 'keyword-groups'>('cities')
const rows = ref<any[]>([])
const cities = ref<any[]>([])
const dialog = ref(false)
const editingId = ref<number | null>(null)
const testingOpenCLI = ref(false)
const enrichingId = ref<number | null>(null)
const importingBloggers = ref(false)
const form = reactive<any>({})
const recentFilters = ['不限', '一天内', '一周内', '半年内']

async function load() {
  rows.value = (await api.settings(tab.value)).data.data
  if (tab.value === 'cities') cities.value = rows.value
  else cities.value = (await api.settings('cities')).data.data
}

function resetForm() {
  Object.keys(form).forEach((key) => delete form[key])
  if (tab.value === 'cities') Object.assign(form, { name: '', keywords: [], recent_filter: '一周内', enabled: true })
  else Object.assign(form, { platform_user_id: '', username: '', profile_url: '', city_codes: [], enabled: true })
}

function open(row?: any) {
  editingId.value = row?.id ?? null
  resetForm()
  if (row) Object.assign(form, row, { keywords: [...(row.keywords || [])] })
  dialog.value = true
}

async function save() {
  if (tab.value === 'cities' && (!form.name?.trim() || !form.keywords?.length)) {
    ElMessage.warning('请填写城市名称并至少添加一个关键词')
    return
  }
  if (editingId.value) await api.updateSetting(tab.value, editingId.value, form)
  else await api.createSetting(tab.value, form)
  dialog.value = false
  ElMessage.success('保存成功')
  await load()
}

async function remove(row: any) {
  await ElMessageBox.confirm(`确认删除“${row.name || row.username}”？`, '删除确认', { type: 'warning' })
  await api.deleteSetting(tab.value, row.id)
  ElMessage.success('已删除')
  await load()
}

async function test() {
  testingOpenCLI.value = true
  try {
    await api.testOpenCLI()
    ElMessage.success('OpenCLI 登录与连接正常')
  } catch (error: any) {
    const reason = error.response?.data?.message || error.response?.data?.detail
    ElMessage.error(reason === 'AUTH_REQUIRED' ? '请在 Chrome 登录小红书' : (reason || '请在 Chrome 登录小红书'))
  } finally {
    testingOpenCLI.value = false
  }
}

async function enrich(row: any) {
  enrichingId.value = row.id
  try {
    await api.enrichBlogger(row.id)
    ElMessage.success(`已补充 ${row.username} 的主页与用户 ID`)
    await load()
  } catch (error: any) {
    const reason = error.response?.data?.message || error.response?.data?.detail
    ElMessage.error(reason || '补充博主信息失败')
  } finally {
    enrichingId.value = null
  }
}

async function downloadTemplate() {
  const response = await api.downloadBloggerTemplate()
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = 'blogger-import-template.xlsx'
  link.click()
  URL.revokeObjectURL(url)
}

async function importFile(uploadFile: any) {
  if (!uploadFile.raw) return
  importingBloggers.value = true
  try {
    const response = await api.importBloggers(uploadFile.raw)
    const result = response.data.data
    ElMessage.success(`导入成功：新增 ${result.created}，更新 ${result.updated}`)
    await load()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || error.response?.data?.detail || '批量导入失败')
  } finally {
    importingBloggers.value = false
  }
}

onMounted(load)
</script>

<template>
  <ElCard shadow="never" class="page-card">
    <div class="toolbar">
      <ElRadioGroup v-model="tab" @change="load">
        <ElRadioButton value="cities">城市抓取配置</ElRadioButton>
        <ElRadioButton value="bloggers">博主白名单</ElRadioButton>
        <ElRadioButton value="keyword-groups">关键词组</ElRadioButton>
      </ElRadioGroup>
      <ElButton type="primary" :icon="Plus" @click="open()">{{ tab === 'cities' ? '新增城市' : '新增博主' }}</ElButton>
      <ElButton v-if="tab === 'bloggers'" :icon="Download" @click="downloadTemplate">下载模板</ElButton>
      <ElUpload v-if="tab === 'bloggers'" :show-file-list="false" :auto-upload="false" accept=".xlsx,.csv" :on-change="importFile">
        <ElButton :icon="UploadFilled" :loading="importingBloggers">批量导入</ElButton>
      </ElUpload>
      <ElButton :icon="Connection" :disabled="testingOpenCLI" @click="test">测试 OpenCLI</ElButton>
      <ElIcon v-if="testingOpenCLI" class="opencli-testing-icon is-loading" aria-label="OpenCLI 测试中"><Loading /></ElIcon>
    </div>

    <ElTable v-if="tab === 'cities'" :data="rows">
      <ElTableColumn prop="name" label="城市" min-width="140" />
      <ElTableColumn label="关键词" min-width="320">
        <template #default="scope"><ElTag v-for="word in scope.row.keywords" :key="word" class="keyword-tag">{{ word }}</ElTag></template>
      </ElTableColumn>
      <ElTableColumn prop="recent_filter" label="抓取时间范围" width="150" />
      <ElTableColumn label="状态" width="100"><template #default="scope"><ElTag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '已启用' : '已停用' }}</ElTag></template></ElTableColumn>
      <ElTableColumn label="操作" min-width="200" class-name="action-column">
        <template #default="scope">
          <ElButton text type="primary" :icon="Edit" @click="open(scope.row)">编辑</ElButton>
          <ElButton text type="danger" :icon="Delete" @click="remove(scope.row)">删除</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <ElTable v-else :data="rows">
      <ElTableColumn prop="username" label="博主" />
      <ElTableColumn prop="profile_url" label="主页" min-width="280" show-overflow-tooltip />
      <ElTableColumn label="城市" min-width="200"><template #default="scope">
        <template v-if="(scope.row.city_codes || []).length">
          <ElTag v-for="code in scope.row.city_codes" :key="code" class="keyword-tag">{{ cities.find((city) => city.code === code)?.name || code }}</ElTag>
        </template>
        <span v-else>未关联</span>
      </template></ElTableColumn>
      <ElTableColumn label="状态" width="100"><template #default="scope"><ElTag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '已启用' : '已停用' }}</ElTag></template></ElTableColumn>
      <ElTableColumn label="操作" min-width="280" class-name="action-column"><template #default="scope">
        <ElButton v-if="!scope.row.profile_url" text type="warning" :icon="MagicStick" :loading="enrichingId === scope.row.id" @click="enrich(scope.row)">补充博主信息</ElButton>
        <ElButton text type="primary" :icon="Edit" @click="open(scope.row)">编辑</ElButton>
        <ElButton text type="danger" :icon="Delete" @click="remove(scope.row)">删除</ElButton>
      </template></ElTableColumn>
    </ElTable>

    <KeywordGroupSettings v-if="tab === 'keyword-groups'" :cities="cities" />
  </ElCard>

  <ElDialog v-model="dialog" :title="`${editingId ? '编辑' : '新增'}${tab === 'cities' ? '城市' : '博主'}`" width="620">
    <ElForm label-width="110px">
      <template v-if="tab === 'cities'">
        <ElFormItem label="城市名称"><ElInput v-model="form.name" placeholder="例如：宁波" /></ElFormItem>
        <ElFormItem label="关键词"><ElInputTag v-model="form.keywords" aria-label="关键词" placeholder="输入关键词后按回车添加" style="width: 100%" /></ElFormItem>
        <ElFormItem label="抓取时间范围"><ElSelect v-model="form.recent_filter" style="width: 100%"><ElOption v-for="item in recentFilters" :key="item" :label="item" :value="item" /></ElSelect></ElFormItem>
        <ElFormItem label="启用"><ElSwitch v-model="form.enabled" /></ElFormItem>
      </template>
      <template v-else>
        <ElFormItem label="小红书用户 ID"><ElInput v-model="form.platform_user_id" placeholder="可选；留空后续可补" /></ElFormItem>
        <ElFormItem label="博主名称"><ElInput v-model="form.username" /></ElFormItem>
        <ElFormItem label="主页地址"><ElInput v-model="form.profile_url" placeholder="可选；后续可补" /></ElFormItem>
        <ElFormItem label="关联城市">
          <ElSelect v-model="form.city_codes" multiple collapse-tags collapse-tags-tooltip placeholder="选择 1 个或多个城市" style="width: 100%">
            <ElOption v-for="city in cities" :key="city.code" :label="city.name" :value="city.code" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="启用"><ElSwitch v-model="form.enabled" /></ElFormItem>
      </template>
    </ElForm>
    <template #footer><ElButton @click="dialog = false">取消</ElButton><ElButton type="primary" @click="save">保存</ElButton></template>
  </ElDialog>
</template>

<style scoped>
.keyword-tag { margin: 3px 6px 3px 0; }
</style>
