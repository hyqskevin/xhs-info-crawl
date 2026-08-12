<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const isAdmin = computed(() => userStore.isAdmin)
const isAuthenticated = computed(() => userStore.isAuthenticated)

onMounted(() => {
  if (isAuthenticated.value && !isAdmin.value) {
    ElMessage.error('无权限访问系统管理')
    router.push('/dashboard')
  }
})
</script>

<template>
  <slot v-if="isAdmin" />
</template>