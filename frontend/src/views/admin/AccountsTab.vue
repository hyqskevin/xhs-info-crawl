<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { api } from '@/api/client'

interface UserRow {
  id: number
  username: string
  display_name: string | null
  enabled: boolean
  role: string
  groups: string[]
}

interface GroupRow {
  id: number
  name: string
}

const users = ref<UserRow[]>([])
const groups = ref<GroupRow[]>([])
const dialogVisible = ref(false)
const form = ref({
  username: '',
  password: '',
  display_name: '',
  is_admin: true,
  group_ids: [] as number[],
})

async function load() {
  const [u, g] = await Promise.all([api.listUsers(), api.listGroups()])
  // 后端 list_users / list_groups 返回裸数组（response_model=list[...])，需要从 axios 响应里取 .data
  users.value = (u as any).data as UserRow[]
  groups.value = (g as any).data as GroupRow[]
}

async function submit() {
  const payload = {
    username: form.value.username,
    password: form.value.password,
    display_name: form.value.display_name || null,
    is_admin: form.value.is_admin,
    group_ids: form.value.is_admin ? [] : form.value.group_ids,
  }
  await api.createUser(payload)
  ElMessage.success('创建成功')
  dialogVisible.value = false
  await load()
}

async function remove(u: UserRow) {
  try {
    await ElMessageBox.confirm(`确认删除账号 ${u.username}？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  await api.deleteUser(u.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<template>
  <div class="accounts-tab">
    <div class="toolbar">
      <ElButton type="primary" :icon="Plus" @click="dialogVisible = true">新建账号</ElButton>
    </div>
    <ElTable :data="users" stripe>
      <ElTableColumn prop="username" label="用户名" />
      <ElTableColumn prop="display_name" label="显示名" />
      <ElTableColumn label="启用">
        <template #default="{ row }">
          <ElTag :type="row.enabled ? 'success' : 'danger'">
            {{ row.enabled ? '是' : '否' }}
          </ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="分组">
        <template #default="{ row }">
          <ElTag v-for="g in row.groups" :key="g" size="small" style="margin-right: 4px;">{{ g }}</ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="180">
        <template #default="{ row }">
          <ElButton size="small" :disabled="row.username === 'admin'" @click="remove(row)">删除</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <ElDialog v-model="dialogVisible" title="新建账号" width="480">
      <ElForm :model="form" label-width="100">
        <ElFormItem label="用户名"><ElInput v-model="form.username" /></ElFormItem>
        <ElFormItem label="初始密码"><ElInput v-model="form.password" type="password" show-password /></ElFormItem>
        <ElFormItem label="显示名"><ElInput v-model="form.display_name" /></ElFormItem>
        <ElFormItem label="管理员账号">
          <ElSwitch v-model="form.is_admin" />
          <span style="margin-left: 8px; color: #909399;">开启后自动加入 Administrators 组</span>
        </ElFormItem>
        <ElFormItem v-if="!form.is_admin" label="所属分组">
          <ElSelect v-model="form.group_ids" multiple style="width: 100%;">
            <ElOption v-for="g in groups" :key="g.id" :value="g.id" :label="g.name" />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" @click="submit">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>