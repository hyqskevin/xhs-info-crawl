<script setup lang="ts">
import { Delete, Edit } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/api/client'

const props = defineProps<{ cities: any[] }>()
const rows = ref<any[]>([])
const dialog = ref(false)
const editingId = ref<number | null>(null)
const form = reactive<any>({ name: '', description: '', city_codes: [], words: [], enabled: true })

async function load() {
  const resp = await api.keywordGroups()
  rows.value = resp.data.data.items || []
}

function resetForm() {
  Object.keys(form).forEach((key) => delete form[key])
  Object.assign(form, { name: '', description: '', city_codes: [], words: [], enabled: true })
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialog.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  resetForm()
  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    city_codes: [...(row.city_codes || [])],
    words: [...(row.words || [])],
    enabled: row.enabled,
  })
  dialog.value = true
}

async function save() {
  if (!form.name?.trim()) {
    ElMessage.warning('请填写关键词组名称')
    return
  }
  if (editingId.value) {
    await api.updateKeywordGroupCities(editingId.value, form.city_codes)
    await api.updateKeywordGroupWords(editingId.value, form.words)
    ElMessage.success('已更新')
  } else {
    await api.createKeywordGroup({
      name: form.name.trim(),
      description: form.description?.trim() || null,
      city_codes: form.city_codes,
      words: form.words,
      enabled: form.enabled,
    })
    ElMessage.success('已创建')
  }
  dialog.value = false
  await load()
}

async function remove(row: any) {
  await ElMessageBox.confirm(`确认删除关键词组 "${row.name}"？`, '删除确认', { type: 'warning' })
  await api.deleteKeywordGroup(row.id)
  ElMessage.success('已删除')
  await load()
}

function addWord(value: string) {
  const w = value.trim()
  if (!w || form.words.includes(w)) return false
  form.words.push(w)
  return true
}

function removeWord(value: string) {
  form.words = form.words.filter((w: string) => w !== value)
}

function addCity(code: string) {
  if (!code || form.city_codes.includes(code)) return
  form.city_codes.push(code)
}

function removeCity(code: string) {
  form.city_codes = form.city_codes.filter((c: string) => c !== code)
}

onMounted(load)
</script>

<template>
  <div class="keyword-group-settings">
    <div class="toolbar">
      <ElButton type="primary" :icon="Edit" @click="openCreate">新增关键词组</ElButton>
    </div>

    <ElTable :data="rows">
      <ElTableColumn prop="name" label="名称" min-width="160" />
      <ElTableColumn prop="description" label="说明" min-width="220" show-overflow-tooltip />
      <ElTableColumn label="挂载城市" min-width="200">
        <template #default="scope">
          <template v-if="(scope.row.city_codes || []).length">
            <ElTag v-for="code in scope.row.city_codes" :key="code" type="primary" class="keyword-tag">
              {{ props.cities.find((c: any) => c.code === code)?.name || code }}
            </ElTag>
          </template>
          <span v-else>未挂载</span>
        </template>
      </ElTableColumn>
      <ElTableColumn label="关键词" min-width="240">
        <template #default="scope">
          <ElTag v-for="word in scope.row.words" :key="word" class="keyword-tag">{{ word }}</ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="状态" width="100">
        <template #default="scope">
          <ElTag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '启用' : '停用' }}</ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="操作" min-width="200" class-name="action-column">
        <template #default="scope">
          <ElButton text type="primary" :icon="Edit" @click="openEdit(scope.row)">编辑</ElButton>
          <ElButton text type="danger" :icon="Delete" @click="remove(scope.row)">删除</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <ElDialog v-model="dialog" :title="editingId ? '编辑关键词组' : '新增关键词组'" width="640">
      <ElForm label-width="90px">
        <ElFormItem label="名称">
          <ElInput v-model="form.name" :disabled="!!editingId" placeholder="例如：展览" aria-label="关键词组名称" />
        </ElFormItem>
        <ElFormItem label="说明">
          <ElInput v-model="form.description" placeholder="可选" aria-label="说明" />
        </ElFormItem>
        <ElFormItem label="关键词">
          <div class="chips">
            <ElTag v-for="word in form.words" :key="word" closable @close="removeWord(word)">{{ word }}</ElTag>
          </div>
          <ElInput
            :model-value="''"
            placeholder="回车添加"
            @keyup.enter="(e: any) => { if (addWord(e.target.value)) e.target.value = '' }"
          />
        </ElFormItem>
        <ElFormItem label="挂载城市">
          <div class="chips">
            <ElTag v-for="code in form.city_codes" :key="code" type="primary" closable @close="removeCity(code)">
              {{ props.cities.find((c: any) => c.code === code)?.name || code }}
            </ElTag>
          </div>
          <ElSelect
            :model-value="''"
            placeholder="添加城市"
            @change="(v: any) => { addCity(v); form.city_codes = [...form.city_codes] }"
          >
            <ElOption v-for="city in props.cities" :key="city.code" :label="city.name" :value="city.code" />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialog = false">取消</ElButton>
        <ElButton type="primary" @click="save">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.keyword-group-settings { padding-top: 16px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 8px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; min-height: 24px; }
.chips:empty { display: none; }
.keyword-tag { margin-right: 4px; }
</style>
