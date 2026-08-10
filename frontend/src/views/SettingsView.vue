<script setup lang="ts">
import { Delete, Download, Edit, MagicStick, Plus, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '@/api/client'
import KeywordGroupSettings from '@/components/KeywordGroupSettings.vue'
import BloggerGroupSettings from '@/components/BloggerGroupSettings.vue'

const route = useRoute()
const tab = ref<'cities' | 'bloggers' | 'keyword-groups' | 'blogger-groups' | 'xhs-accounts' | 'system-config'>(
  (route.query.tab as any) || 'cities',
)
watch(() => route.query.tab, (newTab) => {
  if (newTab) {
    tab.value = newTab as any
    load()
  }
})
const systemConfig = ref<Record<string, any>>({})
const systemConfigLoading = ref(false)
const systemConfigSaving = ref(false)
const rows = ref<any[]>([])
const cities = ref<any[]>([])
const dialog = ref(false)
const editingId = ref<number | null>(null)
const enrichingId = ref<number | null>(null)
const importingBloggers = ref(false)
const checkingLoginId = ref<number | null>(null)
const form = reactive<any>({})
const recentFilters = ['不限', '一天内', '一周内', '半年内']

const loginStatusMeta: Record<string, { type: string; label: string }> = {
  logged_in: { type: 'success', label: '已登录' },
  logged_out: { type: 'danger', label: '未登录' },
  unknown: { type: 'info', label: '未知' },
}
const loginStatusOf = (status: string) => loginStatusMeta[status] || { type: 'info', label: status || '未知' }

async function load() {
  try {
    if (tab.value === 'system-config') {
      await loadSystemConfig()
      return
    }
    if (tab.value === 'keyword-groups' || tab.value === 'blogger-groups') {
      return
    }
    if (tab.value === 'xhs-accounts') {
      try {
        rows.value = (await api.xhsAccounts()).data.data || []
      } catch {
        rows.value = []
      }
      return
    }
    try {
      rows.value = (await api.settings(tab.value)).data.data || []
    } catch {
      rows.value = []
    }
    if (tab.value === 'cities') {
      cities.value = rows.value
    } else {
      try {
        cities.value = (await api.settings('cities')).data.data || []
      } catch {
        cities.value = []
      }
    }
  } catch {
    // 顶层兜底，防止异常阻断 tab 切换
  }
}

function resetForm() {
  Object.keys(form).forEach((key) => delete form[key])
  if (tab.value === 'cities') Object.assign(form, { name: '', recent_filter: '一周内', enabled: true })
  else if (tab.value === 'xhs-accounts') Object.assign(form, { name: '', remark: '', session_name: '', enabled: true, priority: 0 })
  else Object.assign(form, { platform_user_id: '', username: '', profile_url: '', city_codes: [], enabled: true, max_notes_per_crawl: 0 })
}

function open(row?: any) {
  editingId.value = row?.id ?? null
  resetForm()
  if (row) Object.assign(form, row)
  dialog.value = true
}

async function save() {
  if (tab.value === 'cities' && !form.name?.trim()) {
    ElMessage.warning('请填写城市名称')
    return
  }
  if (tab.value === 'xhs-accounts') {
    if (!form.name?.trim()) {
      ElMessage.warning('请填写账号名称')
      return
    }
    if (editingId.value) await api.updateXhsAccount(editingId.value, form)
    else await api.createXhsAccount(form)
    dialog.value = false
    ElMessage.success('保存成功')
    await load()
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
  if (tab.value === 'xhs-accounts') {
    await api.deleteXhsAccount(row.id)
  } else {
    await api.deleteSetting(tab.value, row.id)
  }
  ElMessage.success('已删除')
  await load()
}

async function checkLogin(row: any) {
  checkingLoginId.value = row.id
  try {
    const res = await api.checkXhsAccountLogin(row.id)
    const data = res.data.data || {}
    const idx = rows.value.findIndex((r) => r.id === row.id)
    if (idx !== -1) {
      rows.value[idx] = { ...rows.value[idx], ...data }
    }
    const meta = loginStatusOf(data.login_status || row.login_status)
    ElMessage.success(`「${row.name}」${meta.label}`)
  } catch (error: any) {
    const reason = error.response?.data?.message || error.response?.data?.detail || '检测登录失败'
    ElMessage.error(reason)
  } finally {
    checkingLoginId.value = null
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

async function loadSystemConfig() {
  systemConfigLoading.value = true
  try {
    const res = await api.systemConfig()
    systemConfig.value = res.data.data || {}
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '加载系统配置失败')
  } finally {
    systemConfigLoading.value = false
  }
}

async function saveSystemConfig() {
  systemConfigSaving.value = true
  try {
    await api.updateSystemConfig(systemConfig.value)
    ElMessage.success('系统配置已保存，重启服务后生效')
    await loadSystemConfig()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '保存系统配置失败')
  } finally {
    systemConfigSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <ElCard shadow="never" class="page-card">
    <div class="toolbar">
      <ElButton v-if="tab === 'cities' || tab === 'bloggers'" type="primary" :icon="Plus" @click="open()">{{ tab === 'cities' ? '新增城市' : '新增博主' }}</ElButton>
      <ElButton v-if="tab === 'xhs-accounts'" type="primary" :icon="Plus" @click="open()">新增账号</ElButton>
      <ElButton v-if="tab === 'bloggers'" :icon="Download" @click="downloadTemplate">下载模板</ElButton>
      <ElUpload v-if="tab === 'bloggers'" :show-file-list="false" :auto-upload="false" accept=".xlsx,.csv" :on-change="importFile">
        <ElButton :icon="UploadFilled" :loading="importingBloggers">批量导入</ElButton>
      </ElUpload>
    </div>

    <ElTable v-if="tab === 'cities'" :data="rows">
      <ElTableColumn prop="name" label="城市" min-width="140" />
      <ElTableColumn prop="recent_filter" label="抓取时间范围" width="150" />
      <ElTableColumn label="状态" width="100"><template #default="scope"><ElTag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '已启用' : '已停用' }}</ElTag></template></ElTableColumn>
      <ElTableColumn label="操作" min-width="200" class-name="action-column">
        <template #default="scope">
          <ElButton text type="primary" :icon="Edit" @click="open(scope.row)">编辑</ElButton>
          <ElButton text type="danger" :icon="Delete" @click="remove(scope.row)">删除</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <ElTable v-else-if="tab === 'bloggers'" :data="rows">
      <ElTableColumn prop="username" label="博主" />
      <ElTableColumn prop="profile_url" label="主页" min-width="280" show-overflow-tooltip />
      <ElTableColumn label="城市" min-width="200"><template #default="scope">
        <template v-if="(scope.row.city_codes || []).length">
          <ElTag v-for="code in scope.row.city_codes" :key="code" class="keyword-tag">{{ cities.find((city) => city.code === code)?.name || code }}</ElTag>
        </template>
        <span v-else>未关联</span>
      </template></ElTableColumn>
      <ElTableColumn label="状态" width="100"><template #default="scope"><ElTag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '已启用' : '已停用' }}</ElTag></template></ElTableColumn>
      <ElTableColumn label="抓取上限" width="120"><template #default="scope">{{ scope.row.max_notes_per_crawl ? scope.row.max_notes_per_crawl + ' 篇' : '不限制' }}</template></ElTableColumn>
      <ElTableColumn label="操作" min-width="280" class-name="action-column"><template #default="scope">
        <ElButton v-if="!scope.row.profile_url" text type="warning" :icon="MagicStick" :loading="enrichingId === scope.row.id" @click="enrich(scope.row)">补充博主信息</ElButton>
        <ElButton text type="primary" :icon="Edit" @click="open(scope.row)">编辑</ElButton>
        <ElButton text type="danger" :icon="Delete" @click="remove(scope.row)">删除</ElButton>
      </template></ElTableColumn>
    </ElTable>

    <ElTable v-else-if="tab === 'xhs-accounts'" :data="rows">
      <ElTableColumn prop="name" label="账号名称" min-width="140" />
      <ElTableColumn prop="remark" label="备注" min-width="120" show-overflow-tooltip />
      <ElTableColumn prop="session_name" label="Session 名" min-width="140" />
      <ElTableColumn label="登录状态" width="120">
        <template #default="scope">
          <ElTag :type="loginStatusOf(scope.row.login_status).type as any">{{ loginStatusOf(scope.row.login_status).label }}</ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="启用" width="90">
        <template #default="scope">
          <ElTag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '已启用' : '已停用' }}</ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn prop="priority" label="优先级" width="90" />
      <ElTableColumn label="操作" min-width="280" class-name="action-column">
        <template #default="scope">
          <ElButton text type="primary" :loading="checkingLoginId === scope.row.id" @click="checkLogin(scope.row)">检测登录</ElButton>
          <ElButton text type="primary" :icon="Edit" @click="open(scope.row)">编辑</ElButton>
          <ElButton text type="danger" :icon="Delete" @click="remove(scope.row)">删除</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <KeywordGroupSettings v-if="tab === 'keyword-groups'" :cities="cities" />

    <BloggerGroupSettings v-if="tab === 'blogger-groups'" />

    <ElCard v-if="tab === 'system-config'" v-loading="systemConfigLoading" shadow="never" class="config-card">
      <template #header>系统配置 <span class="config-hint">修改后需重启服务生效</span></template>

      <ElForm label-width="180px" label-position="left">
        <div class="config-group">
          <h4 class="config-group-title">活动识别模型</h4>
          <ElFormItem label="API Key">
            <ElInput v-model="systemConfig.minimax_api_key" type="password" show-password placeholder="MiniMax API 密钥" />
          </ElFormItem>
          <ElFormItem label="API 地址">
            <ElInput v-model="systemConfig.minimax_base_url" placeholder="https://api.minimaxi.com/v1" />
          </ElFormItem>
          <ElFormItem label="模型名称">
            <ElInput v-model="systemConfig.minimax_model" placeholder="MiniMax-M3" />
          </ElFormItem>
          <ElFormItem label="超时时间（秒）">
            <ElInputNumber v-model="systemConfig.minimax_timeout_seconds" :min="10" :step="30" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="并发调用数">
            <ElInputNumber v-model="systemConfig.minimax_concurrency" :min="1" :max="4" :step="1" style="width: 100%" />
          </ElFormItem>
        </div>

        <div class="config-group">
          <h4 class="config-group-title">PaddleOCR</h4>
          <ElFormItem label="启用 OCR">
            <ElSwitch v-model="systemConfig.ocr_enabled" />
          </ElFormItem>
          <ElFormItem label="识别语言">
            <ElSelect v-model="systemConfig.ocr_language" style="width: 100%">
              <ElOption label="中英文 (ch)" value="ch" />
              <ElOption label="英文 (en)" value="en" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="最低置信度">
            <ElInputNumber v-model="systemConfig.ocr_min_confidence" :min="0" :max="1" :step="0.1" :precision="1" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="并行线程数">
            <ElInputNumber v-model="systemConfig.ocr_parallel_workers" :min="1" :max="4" :step="1" style="width: 100%" />
          </ElFormItem>
        </div>

        <div class="config-group">
          <h4 class="config-group-title">单笔记流水线重试</h4>
          <ElFormItem label="最大重试次数">
            <ElInputNumber v-model="systemConfig.pipeline_stage_max_retries" :min="1" :max="10" :step="1" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="重试间隔（秒）">
            <ElInputNumber v-model="systemConfig.pipeline_stage_retry_delay_seconds" :min="0.5" :max="60" :step="0.5" :precision="1" style="width: 100%" />
          </ElFormItem>
        </div>

        <div class="config-group">
          <h4 class="config-group-title">小红书滚动策略</h4>
          <ElFormItem label="目标笔记数">
            <ElInputNumber v-model="systemConfig.xhs_search_target_count" :min="10" :max="200" :step="10" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="最大滚动轮数">
            <ElInputNumber v-model="systemConfig.xhs_search_scroll_max_rounds" :min="1" :max="30" :step="1" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="滚动像素">
            <ElInputNumber v-model="systemConfig.xhs_scroll_pixels" :min="200" :max="2000" :step="100" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="停滞轮数阈值">
            <ElInputNumber v-model="systemConfig.xhs_scroll_stagnant_rounds" :min="1" :max="10" :step="1" style="width: 100%" />
          </ElFormItem>
        </div>

        <div class="config-group">
          <h4 class="config-group-title">抓取工具</h4>
          <ElFormItem label="opencli 路径">
            <ElInput
              v-model="systemConfig.opencli_bin"
              placeholder="opencli"
              clearable
            >
              <template #append>
                <ElTooltip content="支持绝对路径，留空回退 PATH 解析" placement="top">
                  <ElIcon><QuestionFilled /></ElIcon>
                </ElTooltip>
              </template>
            </ElInput>
          </ElFormItem>
        </div>

        <div class="config-group">
          <h4 class="config-group-title">抓取数量</h4>
          <ElFormItem label="单次搜索上限">
            <ElInputNumber v-model="systemConfig.search_limit" :min="10" :max="500" :step="10" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="每周搜索上限">
            <ElInputNumber v-model="systemConfig.weekly_search_limit" :min="0" :max="5000" :step="50" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="连续失败熔断阈值">
            <ElInputNumber v-model="systemConfig.consecutive_note_failure_limit" :min="1" :max="20" :step="1" style="width: 100%" />
          </ElFormItem>
          <ElFormItem label="活动有效窗口（天）">
            <ElInputNumber v-model="systemConfig.activity_future_window_days" :min="7" :max="365" :step="7" style="width: 100%" />
          </ElFormItem>
        </div>

        <ElFormItem>
          <ElButton type="primary" :loading="systemConfigSaving" @click="saveSystemConfig">保存配置</ElButton>
          <ElButton @click="loadSystemConfig">重置</ElButton>
        </ElFormItem>
      </ElForm>
    </ElCard>
  </ElCard>

  <ElDialog v-model="dialog" :title="`${editingId ? '编辑' : '新增'}${tab === 'cities' ? '城市' : tab === 'xhs-accounts' ? '账号' : '博主'}`" width="620">
    <ElForm label-width="110px">
      <template v-if="tab === 'cities'">
        <ElFormItem label="城市名称"><ElInput v-model="form.name" placeholder="例如：宁波" /></ElFormItem>
        <ElFormItem label="抓取时间范围"><ElSelect v-model="form.recent_filter" style="width: 100%"><ElOption v-for="item in recentFilters" :key="item" :label="item" :value="item" /></ElSelect></ElFormItem>
        <ElFormItem label="启用"><ElSwitch v-model="form.enabled" /></ElFormItem>
      </template>
      <template v-else-if="tab === 'xhs-accounts'">
        <ElFormItem label="账号名称"><ElInput v-model="form.name" placeholder="例如：主账号" /></ElFormItem>
        <ElFormItem label="备注"><ElInput v-model="form.remark" placeholder="可选；用于区分账号用途" /></ElFormItem>
        <ElFormItem label="Session 名"><ElInput v-model="form.session_name" placeholder="opencli --session 参数值" /></ElFormItem>
        <ElFormItem label="启用"><ElSwitch v-model="form.enabled" /></ElFormItem>
        <ElFormItem label="优先级"><ElInputNumber v-model="form.priority" :min="0" :step="1" style="width: 100%" /></ElFormItem>
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
        <ElFormItem label="抓取上限"><ElInputNumber v-model="form.max_notes_per_crawl" :min="0" :step="5" placeholder="0 表示不限制" style="width: 100%" /></ElFormItem>
      </template>
    </ElForm>
    <template #footer><ElButton @click="dialog = false">取消</ElButton><ElButton type="primary" @click="save">保存</ElButton></template>
  </ElDialog>
</template>

<style scoped>
.keyword-tag { margin: 3px 6px 3px 0; }
.config-card { margin-top: 16px; }
.config-hint { font-size: 13px; color: #909399; font-weight: normal; margin-left: 8px; }
.config-group { margin-bottom: 8px; }
.config-group-title { font-size: 15px; font-weight: 600; color: #303133; margin: 0 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid #ebeef5; }
</style>
