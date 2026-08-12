<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SystemAdminGuard from '@/components/SystemAdminGuard.vue'
import AccountsTab from './admin/AccountsTab.vue'
import GroupsTab from './admin/GroupsTab.vue'
import PermissionsTab from './admin/PermissionsTab.vue'
import AuditLogsTab from './admin/AuditLogsTab.vue'

const route = useRoute()
const router = useRouter()

const tab = computed(() => (route.query.tab as string) || 'accounts')

function setTab(name: string) {
  router.push({ path: '/system-admin', query: { tab: name } })
}
</script>

<template>
  <SystemAdminGuard>
    <div class="system-admin">
      <h2>系统管理</h2>
      <ElRadioGroup :model-value="tab" @change="(v: string | number | boolean | undefined) => setTab(String(v))">
        <ElRadioButton value="accounts">操作账号</ElRadioButton>
        <ElRadioButton value="groups">账号分组</ElRadioButton>
        <ElRadioButton value="permissions">权限配置</ElRadioButton>
        <ElRadioButton value="audit">操作日志</ElRadioButton>
      </ElRadioGroup>
      <div class="tab-body" style="margin-top: 16px;">
        <AccountsTab v-if="tab === 'accounts'" />
        <GroupsTab v-else-if="tab === 'groups'" />
        <PermissionsTab v-else-if="tab === 'permissions'" />
        <AuditLogsTab v-else-if="tab === 'audit'" />
      </div>
    </div>
  </SystemAdminGuard>
</template>