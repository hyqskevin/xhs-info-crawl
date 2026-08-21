<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'
import {
  getSystemConfig,
  saveSystemConfig,
  type SystemConfig,
  type SystemConfigSaveResponse,
} from '@/api/client'

interface Props {}

const props = defineProps<Props>()
const emit = defineEmits<{
  saved: [response: SystemConfigSaveResponse]
}>()

const loading = ref(false)
const saving = ref(false)
const config = ref<SystemConfig | null>(null)
const apiKeyVisible = ref(false)
// 默认展开 LLM 面板(用户最常改的就是 API key + model)
const activeNames = ref<string[]>(['llm'])

async function loadConfig() {
  loading.value = true
  try {
    config.value = await getSystemConfig()
  } catch (e) {
    ElMessage.warning(`加载系统配置失败: ${e}`)
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (!config.value) return
  saving.value = true
  try {
    // 只提交非空字段,后端按字段 missing = null 跳过
    const payload: Record<string, string> = {}
    for (const [k, v] of Object.entries(config.value)) {
      if (v !== null && v !== undefined && String(v).trim() !== '') {
        payload[k] = String(v).trim()
      }
    }
    const resp = await saveSystemConfig(payload as Partial<SystemConfig>)
    ElMessage.success(
      `配置已保存(${resp.saved_keys.length} 项),api/worker 已自动重启；`
      + `用户配置已写入 DATA_DIR/.env,迁移时跟着 DATA_DIR 一起拷贝`,
    )
    emit('saved', resp)
    await loadConfig()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail || (e as Error).message
    ElMessage.error(`保存失败: ${detail}`)
  } finally {
    saving.value = false
  }
}

// 改动 5:OCR 开关实时同步(无需用户点保存)。
// 关联 spec: docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 5
// 关联设计: docs/packaging-design.md §3.7
// 用户多次反馈"拨了 OCR 开关但 .env 不更新",是因为旧实现只改前端 v-model,
// 必须点保存按钮才 PUT。本回调在 @change 触发瞬间就 PUT 单字段,
// 把 OCR 开关变成"实时同步"控件,避免误操作导致开关与 .env 不一致。
async function handleOcrEnabledChange(val: string | number | boolean) {
  try {
    await saveSystemConfig({ ocr_enabled: String(val) } as Partial<SystemConfig>)
    ElMessage.success(val === 'true' ? 'OCR 已启用' : 'OCR 已停用')
    await loadConfig()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    const detail = err?.response?.data?.detail || (e as Error).message
    ElMessage.error(`OCR 状态同步失败: ${detail}`)
  }
}

function handleReset() {
  loadConfig()
}

// 通过 PyWebView 注入的 API 在 Finder 中打开目录(launcher 端处理 ~/expanduser)
function openDir(path: string) {
  const pywebview = (window as unknown as { pywebview?: { api?: { open_dir: (p: string) => Promise<string> } } }).pywebview
  if (pywebview?.api?.open_dir) {
    pywebview.api.open_dir(path).catch((err: unknown) => {
      ElMessage.error(`打开目录失败: ${err};请确认路径存在且有权限`)
    })
  } else {
    ElMessage.warning('该功能仅在桌面启动器中可用')
  }
}

// ─── 存储路径:子目录派生预览 ───
// 关联 spec: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
// base dir 模式:用户只设 config.data_dir,所有子目录从这里推导(同 backend Settings._sync_storage_subdirs_from_data_dir)
function joinDataDir(subdir: string): string {
  // config 是 Ref<SystemConfig | null>,JS 访问需要 .value(template 里 Vue auto-unwraps)
  // 关联: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
  const dataDir = config.value?.data_dir
  if (!dataDir) return `~/xhs-info-crawl/${subdir}`
  const base = dataDir.endsWith('/') ? dataDir.slice(0, -1) : dataDir
  return `${base}/${subdir}`
}

const derivedImageDir = computed(() => joinDataDir('images'))
const derivedExportDir = computed(() => joinDataDir('exports'))
const derivedArchiveDir = computed(() => joinDataDir('archive'))
const derivedPaddleDir = computed(() => joinDataDir('paddlex'))
const derivedHfDir = computed(() => joinDataDir('huggingface'))
const derivedDatabaseUrl = computed(() => `sqlite:///${joinDataDir('app.db')}`)

onMounted(loadConfig)
</script>

<template>
  <el-card class="llm-card" data-test="llm-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <span class="card-title">LLM 与系统配置</span>
        <span class="card-hint">保存后自动重启 api + worker,新配置立即生效</span>
      </div>
    </template>

    <div v-if="config" class="form-area" data-test="llm-form">
      <el-form label-position="top" :model="config">
        <el-collapse v-model="activeNames">
          <el-collapse-item title="LLM" name="llm">
            <el-form-item label="API Key">
              <el-input
                v-model="config.minimax_api_key"
                :type="apiKeyVisible ? 'text' : 'password'"
                placeholder="LLM API 密钥(留空保持不变)"
                data-test="llm-api-key"
              >
                <template #append>
                  <el-button
                    text
                    @click="apiKeyVisible = !apiKeyVisible"
                    :title="apiKeyVisible ? '隐藏' : '显示'"
                  >
                    {{ apiKeyVisible ? '隐藏' : '显示' }}
                  </el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="Base URL">
              <el-input
                v-model="config.minimax_base_url"
                placeholder="https://api.openai.com/v1"
                data-test="llm-base-url"
              />
            </el-form-item>
            <el-form-item label="Model">
              <el-input
                v-model="config.minimax_model"
                placeholder="如 gpt-4o-mini / deepseek-chat / 自定义模型名"
                data-test="llm-model"
              />
            </el-form-item>
            <el-form-item label="Vision Model(可选)">
              <el-input
                v-model="config.minimax_vision_model"
                placeholder="留空表示不支持视觉模型"
              />
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="超时 (秒)">
                  <el-input-number
                    v-model="config.minimax_timeout_seconds"
                    :min="30"
                    :max="600"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="并发数">
                  <el-input-number
                    v-model="config.minimax_concurrency"
                    :min="1"
                    :max="4"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </el-collapse-item>

          <el-collapse-item title="OCR" name="ocr">
            <el-form-item label="启用 OCR">
              <el-switch
                v-model="config.ocr_enabled"
                active-value="true"
                inactive-value="false"
                @change="handleOcrEnabledChange"
                data-test="ocr-enabled"
              />
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="语言">
                  <el-select v-model="config.ocr_language">
                    <el-option label="中文 (ch)" value="ch" />
                    <el-option label="英文 (en)" value="en" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="最低置信度">
                  <el-input-number
                    v-model="config.ocr_min_confidence"
                    :min="0"
                    :max="1"
                    :step="0.1"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="并行 worker 数">
              <el-input-number
                v-model="config.ocr_parallel_workers"
                :min="1"
                :max="4"
              />
            </el-form-item>
          </el-collapse-item>

          <el-collapse-item title="存储路径" name="storage">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              data-test="storage-hint"
              style="margin-bottom: var(--md-sys-spacing-3);"
            >
              只需设置一个 <strong>数据根目录</strong>,所有子目录(图片/导出/归档/OCR 模型/数据库)会自动从它推导。
              推荐用 .app 外部的绝对路径(默认 ~/Library/Application Support/com.xhs-info-crawl.local)，
              避免升级 .app 时数据被覆盖,且 Time Machine 自动备份。
            </el-alert>
            <el-form-item label="数据根目录">
              <el-input
                v-model="config.data_dir"
                placeholder="~/Library/Application Support/com.xhs-info-crawl.local"
                data-test="data-dir"
              >
                <template #append>
                  <el-button
                    text
                    @click="openDir(config.data_dir)"
                    :disabled="!config.data_dir"
                    title="在 Finder 中打开"
                  >
                    打开
                  </el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="日志目录">
              <el-input
                v-model="config.log_dir"
                placeholder="同 data_dir/logs"
                data-test="log-dir"
              >
                <template #append>
                  <el-button
                    text
                    :icon="FolderOpened"
                    @click="openDir(config.log_dir)"
                    :disabled="!config.log_dir"
                    title="在 Finder 中打开日志目录"
                  >
                    打开
                  </el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-divider content-position="left">子目录预览(自动从数据根目录推导)</el-divider>
            <el-descriptions
              :column="1"
              size="small"
              border
              data-test="storage-preview"
            >
              <el-descriptions-item label="图片 (IMAGE_DIR)">
                <div class="path-row">
                  <span class="path-text">{{ derivedImageDir }}</span>
                  <el-button
                    link
                    size="small"
                    :icon="FolderOpened"
                    @click="openDir(derivedImageDir)"
                    title="在 Finder 中打开"
                  >
                    打开
                  </el-button>
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="导出 (EXPORT_DIR)">
                <div class="path-row">
                  <span class="path-text">{{ derivedExportDir }}</span>
                  <el-button
                    link
                    size="small"
                    :icon="FolderOpened"
                    @click="openDir(derivedExportDir)"
                    title="在 Finder 中打开"
                  >
                    打开
                  </el-button>
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="归档 (ARCHIVE_DIR)">
                <div class="path-row">
                  <span class="path-text">{{ derivedArchiveDir }}</span>
                  <el-button
                    link
                    size="small"
                    :icon="FolderOpened"
                    @click="openDir(derivedArchiveDir)"
                    title="在 Finder 中打开"
                  >
                    打开
                  </el-button>
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="OCR 模型 (PADDLE_PDX_CACHE_HOME)">
                <div class="path-row">
                  <span class="path-text">{{ derivedPaddleDir }}</span>
                  <el-button
                    link
                    size="small"
                    :icon="FolderOpened"
                    @click="openDir(derivedPaddleDir)"
                    title="在 Finder 中打开"
                  >
                    打开
                  </el-button>
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="HF 缓存 (HF_HOME)">
                <div class="path-row">
                  <span class="path-text">{{ derivedHfDir }}</span>
                  <el-button
                    link
                    size="small"
                    :icon="FolderOpened"
                    @click="openDir(derivedHfDir)"
                    title="在 Finder 中打开"
                  >
                    打开
                  </el-button>
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="数据库 (DATABASE_URL)">
                <div class="path-row">
                  <span class="path-text">{{ derivedDatabaseUrl }}</span>
                  <!-- 数据库是文件不是目录,不显示"打开"按钮(Finder 打开 sqlite 文件无意义) -->
                </div>
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>

          <el-collapse-item title="OpenCLI / Chrome 路径" name="paths">
            <el-form-item label="opencli 二进制">
              <el-input
                v-model="config.opencli_bin"
                placeholder="opencli 或绝对路径"
              />
            </el-form-item>
            <el-form-item label="Chrome 路径">
              <el-input
                v-model="config.chrome_bin"
                placeholder="/Applications/Google Chrome.app"
              />
            </el-form-item>
            <el-form-item label="Chrome user-data-dir">
              <el-input
                v-model="config.chrome_user_data_dir"
                placeholder="data/chrome-pool"
              />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <div class="actions">
        <el-button
          type="primary"
          :loading="saving"
          :icon="undefined as never"
          data-test="llm-save-btn"
          @click="handleSave"
        >
          保存配置
        </el-button>
        <el-button :disabled="saving" @click="handleReset">重置</el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.llm-card {
  background: var(--md-sys-color-surface);
  color: var(--md-sys-color-on-surface);
  border: none;
  box-shadow: var(--md-sys-elevation-1);
  border-radius: var(--md-sys-shape-corner-medium);
  margin-bottom: var(--md-sys-spacing-4);
}
.card-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.card-title {
  font: var(--md-sys-typescale-title-large);
}
.card-hint {
  font: var(--md-sys-typescale-body-small);
  color: var(--md-sys-color-on-surface-variant);
}
.form-area {
  margin-bottom: var(--md-sys-spacing-3);
}
.actions {
  display: flex;
  gap: var(--md-sys-spacing-2);
  margin-top: var(--md-sys-spacing-3);
}

/* 子目录预览:长路径必须 wrap,避免被卡片宽度截断成 ~/xhs-info-crawl/...
   el-descriptions 默认 grid 模板会截断超长内容;
   强制 word-break + overflow-wrap + 等宽字体让路径完整显示。
   关联: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
*/
:deep(.storage-preview) {
  /* label 列固定 180px,content 列占满剩余空间 */
  --el-descriptions-table-columns: 180px 1fr;
}
:deep(.storage-preview .el-descriptions__content) {
  font-size: var(--md-sys-typescale-body-small, 13px);
  line-height: 1.45;
  padding: 6px 10px;
}
:deep(.storage-preview .el-descriptions__label) {
  white-space: nowrap;
  font-size: var(--md-sys-typescale-body-small, 13px);
  padding: 6px 10px;
}
.path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.path-text {
  flex: 1;
  min-width: 0;
  word-break: break-all;
  overflow-wrap: anywhere;
  font-family: var(--md-sys-font-family-mono, 'SF Mono', 'Menlo', 'Consolas', monospace);
  font-size: var(--md-sys-typescale-body-small, 13px);
}
.path-row .el-button {
  flex-shrink: 0;
  font-size: var(--md-sys-typescale-label-small, 12px);
}
</style>