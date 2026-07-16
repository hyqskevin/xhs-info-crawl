<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <ElCard shadow="never">
    <ElEmpty :description="`${String(route.meta.title)}模块将在对应业务阶段实现`" />
  </ElCard>
</template>
