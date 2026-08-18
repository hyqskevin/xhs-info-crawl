<script setup lang="ts">
import type { OpencliTestResult } from '@/api/client'

interface Props {
  result: OpencliTestResult | null
  loading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  test: []
  download: []
}>()

function chipType(value: boolean | undefined): 'success' | 'danger' | 'info' {
  if (value === true) return 'success'
  if (value === false) return 'danger'
  return 'info'
}

function chipText(value: boolean | undefined, fallback: string): string {
  if (value === true) return '已就绪'
  if (value === false) return '未就绪'
  return fallback
}

function overallText(): string {
  if (props.loading) return '测试中'
  if (!props.result) return '未检测'
  return props.result.ok ? '全部就绪' : '未就绪'
}

function overallType(): 'success' | 'danger' | 'info' {
  if (!props.result) return 'info'
  return props.result.ok ? 'success' : 'danger'
}
</script>

<template>
  <el-card class="opencli-card" data-test="opencli-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">OpenCLI 连接</span>
        <el-tag :type="overallType()" data-test="opencli-overall-chip">
          {{ overallText() }}<span v-if="result && result.version"> · v{{ result.version }}</span>
        </el-tag>
      </div>
    </template>

    <div class="sub-chips" data-test="opencli-sub-chips">
      <!-- Daemon chip -->
      <div class="sub-chip-row">
        <el-tag
          :type="chipType(result?.daemon.running)"
          data-test="opencli-daemon-chip"
        >
          {{ chipText(result?.daemon.running, '未检测') }} · Daemon
        </el-tag>
        <span v-if="result?.daemon.port" class="chip-detail">
          端口 {{ result.daemon.port }}
        </span>
      </div>

      <!-- Chrome chip -->
      <div class="sub-chip-row">
        <el-tag
          :type="chipType(result?.chrome.running)"
          data-test="opencli-chrome-chip"
        >
          {{ chipText(result?.chrome.running, '未检测') }} · Chrome
        </el-tag>
        <span v-if="result?.chrome.path" class="chip-detail">
          {{ result.chrome.path }}
        </span>
      </div>

      <!-- Extension chip -->
      <div class="sub-chip-row">
        <el-tag
          :type="chipType(result?.extension.connected)"
          data-test="opencli-extension-chip"
        >
          {{ chipText(result?.extension.connected, '未检测') }} · 扩展
        </el-tag>
        <span v-if="result?.extension.profile" class="chip-detail">
          profile: {{ result.extension.profile }}
        </span>
      </div>
    </div>

    <p v-if="result && !result.ok" class="result-error" data-test="opencli-result-error">
      ✗ {{ result.message }}
    </p>
    <p v-else-if="result && result.ok" class="result-success" data-test="opencli-result-success">
      ✓ OpenCLI 全链路就绪
    </p>

    <div class="actions">
      <el-button
        :disabled="loading"
        data-test="test-opencli-btn"
        @click="emit('test')"
      >
        {{ loading ? '测试中...' : '测试连接' }}
      </el-button>
      <el-button type="primary" data-test="download-opencli-btn" @click="emit('download')">
        下载 OpenCLI
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.opencli-card {
  background: var(--md-sys-color-surface);
  color: var(--md-sys-color-on-surface);
  border: none;
  box-shadow: var(--md-sys-elevation-1);
  border-radius: var(--md-sys-shape-corner-medium);
  margin-bottom: var(--md-sys-spacing-4);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title {
  font: var(--md-sys-typescale-title-large);
}
.sub-chips {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: var(--md-sys-spacing-3);
}
.sub-chip-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.chip-detail {
  font: var(--md-sys-typescale-body-small);
  color: var(--md-sys-color-on-surface-variant);
}
.result-success {
  color: var(--md-sys-color-success);
  font: var(--md-sys-typescale-body-medium);
  margin: 0 0 8px;
}
.result-error {
  color: var(--md-sys-color-error);
  font: var(--md-sys-typescale-body-medium);
  margin: 0 0 8px;
}
.actions {
  display: flex;
  gap: var(--md-sys-spacing-2);
}
</style>