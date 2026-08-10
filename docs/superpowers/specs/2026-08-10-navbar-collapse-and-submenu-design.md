# 侧边 navbar 折叠 + 子页面 tab 改二级目录

## 1. 背景

用户 2026-08-10 反馈：
- 侧边 navbar 固定 220px 不可折叠，占用空间
- 配置中心和定时任务的子页面通过页面内 RadioButton tab 切换，层级不清，期望改为 navbar 一级目录下的二级目录

## 2. 目标

1. 侧边 navbar 支持向左折叠收拢（Element Plus `ElMenu :collapse` 自带能力）
2. 配置中心 5 个 tab 改为 navbar 二级目录
3. 定时任务 2 个 tab 改为 navbar 二级目录
4. 路由配置同步更新，URL 直接定位子页面

## 3. 设计

### 3.1 侧边栏折叠

**AppLayout.vue** 改动：
```vue
<script setup>
const isCollapse = ref(localStorage.getItem('sidebar_collapsed') === '1')
function toggleCollapse() {
  isCollapse.value = !isCollapse.value
  localStorage.setItem('sidebar_collapsed', isCollapse.value ? '1' : '0')
}
</script>

<template>
  <ElContainer>
    <ElAside :width="isCollapse ? '64px' : '220px'">
      <div class="brand">
        <ElIcon :size="22"><Connection /></ElIcon>
        <span v-if="!isCollapse">活动采集系统</span>
      </div>
      <ElMenu router :default-active="route.path" :collapse="isCollapse" :collapse-transition="false">
        <!-- 菜单项 -->
      </ElMenu>
    </ElAside>
    <ElContainer>
      <ElHeader>
        <ElButton :icon="isCollapse ? Expand : Fold" text @click="toggleCollapse" />
        <h1>{{ route.meta.title }}</h1>
        <!-- ... -->
      </ElHeader>
    </ElContainer>
  </ElContainer>
</template>
```

**折叠状态持久化**：localStorage key `sidebar_collapsed`，值为 `'1'`/`'0'`

### 3.2 配置中心改为二级目录

**路由**（`router/index.ts`）：
```ts
// 旧：{ path: 'settings', component: SettingsView }
// 新：保持单一路由，但用 query 参数区分子页面
{ path: 'settings', component: SettingsView, meta: { title: '配置中心' } }
// URL: /settings?tab=cities / /settings?tab=bloggers / ...
```

**AppLayout.vue 菜单**：
```vue
<ElSubMenu index="/settings">
  <template #title>
    <ElIcon><Setting /></ElIcon>
    <span>配置中心</span>
  </template>
  <ElMenuItem index="/settings?tab=cities">城市抓取配置</ElMenuItem>
  <ElMenuItem index="/settings?tab=bloggers">博主白名单</ElMenuItem>
  <ElMenuItem index="/settings?tab=keyword-groups">关键词组</ElMenuItem>
  <ElMenuItem index="/settings?tab=blogger-groups">博主组</ElMenuItem>
  <ElMenuItem index="/settings?tab=system-config">系统配置</ElMenuItem>
</ElSubMenu>
```

**SettingsView.vue**：
- 移除顶部 `<ElRadioGroup>` RadioButton
- `tab` 改为从 `route.query.tab` 读取，默认 `'cities'`
- 监听 `route.query.tab` 变化触发 `load()`
- 点击二级菜单导航时用 `router.push('/settings?tab=xxx')` 或依赖 `ElMenu router` 模式

### 3.3 定时任务改为二级目录

**路由**：保持 `/schedules`，query 参数 `tab=schedules|batch`

**AppLayout.vue 菜单**：
```vue
<ElSubMenu index="/schedules">
  <template #title>
    <ElIcon><Timer /></ElIcon>
    <span>定时任务</span>
  </template>
  <ElMenuItem index="/schedules?tab=schedules">定时任务列表</ElMenuItem>
  <ElMenuItem index="/schedules?tab=batch">抓取批次配置</ElMenuItem>
</ElSubMenu>
```

**SchedulesView.vue**：
- 移除顶部 RadioButton
- `tab` 从 `route.query.tab` 读取，默认 `'schedules'`
- 监听 query 变化

### 3.4 其他一级菜单保持不变

仪表盘/活动管理/去重审核/任务日志/周报管理/海报制作 保持 `<ElMenuItem>` 一级菜单。

### 3.5 样式调整

- 折叠时 brand 区域只显示图标，文字隐藏
- `ElAside` 过渡动画 `transition: width 0.3s`
- `ElMenu` 折叠时 tooltip 显示文字（Element Plus 自带）

## 4. 验收

- [ ] 侧边栏有折叠按钮（Header 左侧），点击切换 64px/220px
- [ ] 折叠状态刷新页面后保持（localStorage）
- [ ] 折叠时只显示图标，hover 显示 tooltip
- [ ] 配置中心 navbar 二级目录：城市/博主/关键词组/博主组/系统配置
- [ ] 定时任务 navbar 二级目录：定时任务列表/抓取批次配置
- [ ] 点击二级菜单直接路由到对应子页面（URL 带 `?tab=xxx`）
- [ ] 页面内移除 RadioButton tab
- [ ] 直接访问 `/settings?tab=bloggers` 能正确展示博主白名单
- [ ] `AppLayout.spec.ts` 新增折叠按钮测试
- [ ] `SettingsView.spec.ts` / `SchedulesView.spec.ts` 适配新结构
- [ ] 前端全量测试通过，build 通过

## 5. 部署

- 纯前端改动，dev server 自动刷新
- 无后端改动，无 worker 重启
