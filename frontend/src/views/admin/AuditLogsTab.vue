<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'

interface AuditLogOut {
  id: number
  actor_user_id: number | null
  actor_username: string
  action: string
  resource_type: string | null
  resource_id: number | null
  target_label: string | null
  method: string
  path: string
  status_code: number
  client_ip: string
  user_agent: string | null
  extra: string | null
  created_at: string
}

const items = ref<AuditLogOut[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const filter = ref({
  actor_username: '',
  action: [] as string[],
  date_from: '',
  date_to: '',
})
const actions = [
  'login_success', 'login_failed', 'user_created', 'user_updated',
  'user_deleted', 'group_created', 'group_permission_changed', 'user_group_changed',
]

async function load() {
  const data = await api.listAuditLogs({
    actor_username: filter.value.actor_username || undefined,
    action: filter.value.action.length ? filter.value.action : undefined,
    date_from: filter.value.date_from || undefined,
    date_to: filter.value.date_to || undefined,
    page: page.value,
    size: size.value,
  }) as { total: number; items: AuditLogOut[] }
  items.value = data.items
  total.value = data.total
}

onMounted(load)
</script>

<template>
  <div>
    <div class="filter" style="margin-bottom: 12px;">
      <ElInput v-model="filter.actor_username" placeholder="操作者用户名" clearable style="width: 200px;" @change="load" />
      <ElSelect v-model="filter.action" multiple collapse-tags collapse-tags-tooltip placeholder="动作" style="width: 240px; margin-left: 8px;" @change="load">
        <ElOption v-for="a in actions" :key="a" :value="a" :label="a" />
      </ElSelect>
      <ElButton style="margin-left: 8px;" @click="load">查询</ElButton>
    </div>
    <ElTable :data="items" stripe>
      <ElTableColumn prop="created_at" label="时间" width="180" />
      <ElTableColumn prop="actor_username" label="操作者" width="140" />
      <ElTableColumn prop="action" label="动作" width="200" />
      <ElTableColumn prop="target_label" label="目标" />
      <ElTableColumn prop="method" label="方法" width="80" />
      <ElTableColumn prop="path" label="路径" />
      <ElTableColumn prop="status_code" label="状态" width="80" />
      <ElTableColumn prop="client_ip" label="来源 IP" width="140" />
    </ElTable>
    <ElPagination
      :total="total"
      :page-size="size"
      :current-page="page"
      layout="prev, pager, next, total"
      style="margin-top: 12px;"
      @current-change="(p: number) => { page = p; load() }"
    />
  </div>
</template>