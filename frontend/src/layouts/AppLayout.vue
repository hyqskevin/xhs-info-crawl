<script setup lang="ts">
import {
  Calendar,
  Connection,
  DataAnalysis,
  Document,
  Expand,
  Fold,
  List,
  Setting,
  SwitchButton,
  Timer,
} from '@element-plus/icons-vue'
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const isCollapse = ref(localStorage.getItem('sidebar_collapsed') === '1')
const userStore = useUserStore()

function toggleCollapse() {
  isCollapse.value = !isCollapse.value
  localStorage.setItem('sidebar_collapsed', isCollapse.value ? '1' : '0')
}

function logout(){localStorage.removeItem('token');userStore.clear();location.href='/login'}
</script>

<template>
  <ElContainer class="app-shell">
    <ElAside class="app-sidebar" :width="isCollapse ? '64px' : '220px'">
      <div class="brand">
        <ElIcon :size="22"><Connection /></ElIcon>
        <span v-if="!isCollapse">活动采集系统</span>
      </div>
      <ElMenu router :default-active="route.fullPath" :collapse="isCollapse" :collapse-transition="false" class="app-menu">
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
        <ElSubMenu index="/schedules">
          <template #title>
            <ElIcon><Timer /></ElIcon>
            <span>定时任务</span>
          </template>
          <ElMenuItem index="/schedules?tab=schedules">定时任务列表</ElMenuItem>
          <ElMenuItem index="/schedules?tab=batch">抓取批次配置</ElMenuItem>
        </ElSubMenu>
        <ElMenuItem index="/reports">
          <ElIcon><Document /></ElIcon>
          <span>周报管理</span>
        </ElMenuItem>
        <ElSubMenu index="/settings">
          <template #title>
            <ElIcon><Setting /></ElIcon>
            <span>配置中心</span>
          </template>
          <ElMenuItem index="/settings?tab=cities">城市抓取配置</ElMenuItem>
          <ElMenuItem index="/settings?tab=bloggers">博主白名单</ElMenuItem>
          <ElMenuItem index="/settings?tab=keyword-groups">关键词组</ElMenuItem>
          <ElMenuItem index="/settings?tab=blogger-groups">博主组</ElMenuItem>
          <ElMenuItem index="/settings?tab=xhs-accounts">小红书账号配置</ElMenuItem>
          <ElMenuItem index="/settings?tab=system-config">系统配置</ElMenuItem>
        </ElSubMenu>
        <!-- 海报制作功能未完备，暂隐藏 -->
        <!-- <ElMenuItem index="/posters">
          <ElIcon><Film /></ElIcon>
          <span>海报制作</span>
        </ElMenuItem> -->
      </ElMenu>
    </ElAside>
    <ElContainer>
      <ElHeader class="app-header">
        <ElButton class="collapse-toggle" :icon="isCollapse ? Expand : Fold" text @click="toggleCollapse" />
        <h1>{{ route.meta.title }}</h1>
        <div><ElTag type="success" effect="plain">本地轻量版</ElTag><ElButton text :icon="SwitchButton" @click="logout">退出</ElButton></div>
      </ElHeader>
      <ElMain class="app-main">
        <RouterView />
      </ElMain>
    </ElContainer>
  </ElContainer>
</template>

<style scoped>
.app-sidebar { transition: width 0.3s; }
</style>
