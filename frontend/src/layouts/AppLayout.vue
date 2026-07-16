<script setup lang="ts">
import {
  Calendar,
  Connection,
  DataAnalysis,
  Document,
  List,
  Setting,
} from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <ElContainer class="app-shell">
    <ElAside class="app-sidebar" width="220px">
      <div class="brand">
        <ElIcon :size="22"><Connection /></ElIcon>
        <span>活动采集系统</span>
      </div>
      <ElMenu router :default-active="route.path" class="app-menu">
        <ElMenuItem index="/dashboard">
          <ElIcon><DataAnalysis /></ElIcon>
          <span>仪表盘</span>
        </ElMenuItem>
        <ElMenuItem index="/activities">
          <ElIcon><Calendar /></ElIcon>
          <span>活动管理</span>
        </ElMenuItem>
        <ElMenuItem index="/duplicates">
          <ElIcon><List /></ElIcon>
          <span>去重审核</span>
        </ElMenuItem>
        <ElMenuItem index="/tasks">
          <ElIcon><Connection /></ElIcon>
          <span>任务日志</span>
        </ElMenuItem>
        <ElMenuItem index="/reports">
          <ElIcon><Document /></ElIcon>
          <span>周报管理</span>
        </ElMenuItem>
        <ElMenuItem index="/settings">
          <ElIcon><Setting /></ElIcon>
          <span>配置中心</span>
        </ElMenuItem>
      </ElMenu>
    </ElAside>
    <ElContainer>
      <ElHeader class="app-header">
        <h1>{{ route.meta.title }}</h1>
        <ElTag type="success" effect="plain">本地轻量版</ElTag>
      </ElHeader>
      <ElMain class="app-main">
        <RouterView />
      </ElMain>
    </ElContainer>
  </ElContainer>
</template>
