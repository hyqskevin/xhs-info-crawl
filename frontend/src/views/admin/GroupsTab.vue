<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'

interface GroupOut {
  id: number
  name: string
  description: string | null
  is_builtin: boolean
  permission_codes: string[]
}

interface PermissionOut {
  id: number
  code: string
  description: string | null
  is_builtin: boolean
}

const groups = ref<GroupOut[]>([])
const permissions = ref<PermissionOut[]>([])
const selectedId = ref<number | null>(null)
const selectedCodes = ref<string[]>([])

const selectedGroup = computed(() => groups.value.find((g) => g.id === selectedId.value) ?? null)

async function load() {
  const [g, p] = await Promise.all([api.listGroups(), api.listPermissions()])
  // 后端 list_groups / list_permissions 返回裸数组，从 axios 响应里取 .data
  groups.value = (g as any).data as GroupOut[]
  permissions.value = (p as any).data as PermissionOut[]
  if (!selectedId.value && groups.value.length) {
    selectedId.value = groups.value[0].id
    selectedCodes.value = [...groups.value[0].permission_codes]
  }
}

function selectGroup(g: GroupOut) {
  selectedId.value = g.id
  selectedCodes.value = [...g.permission_codes]
}

async function savePermissions() {
  if (!selectedGroup.value) return
  await api.updateGroupPermissions(selectedGroup.value.id, selectedCodes.value)
  ElMessage.success('已保存')
  await load()
}

onMounted(load)
</script>

<template>
  <div class="groups-tab">
    <div class="layout">
      <div class="left">
        <div class="left-header">分组列表</div>
        <div
          v-for="g in groups"
          :key="g.id"
          :class="['item', { active: g.id === selectedId }]"
          @click="selectGroup(g)"
        >
          {{ g.name }}
          <ElTag v-if="g.is_builtin" size="small" type="info">内置</ElTag>
        </div>
      </div>
      <div class="right">
        <template v-if="selectedGroup">
          <h3>{{ selectedGroup.name }}</h3>
          <p>{{ selectedGroup.description || '—' }}</p>
          <ElCheckboxGroup v-model="selectedCodes">
            <div v-for="p in permissions" :key="p.code" class="permission-row">
              <ElCheckbox :value="p.code">
                <strong>{{ p.code }}</strong> — {{ p.description }}
              </ElCheckbox>
            </div>
          </ElCheckboxGroup>
          <ElButton type="primary" @click="savePermissions">保存</ElButton>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.layout { display: flex; gap: 16px; }
.left { width: 220px; }
.left-header { font-weight: bold; margin-bottom: 8px; }
.item { padding: 8px; cursor: pointer; border-radius: 4px; }
.item.active { background: #ecf5ff; color: #409eff; }
.right { flex: 1; }
.permission-row { margin-bottom: 4px; }
</style>