import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import DashboardView from '@/views/DashboardView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AppLayout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', component: DashboardView, meta: { title: '仪表盘' } },
        { path: 'activities', component: PlaceholderView, meta: { title: '活动管理' } },
        { path: 'duplicates', component: PlaceholderView, meta: { title: '去重审核' } },
        { path: 'tasks', component: PlaceholderView, meta: { title: '任务日志' } },
        { path: 'reports', component: PlaceholderView, meta: { title: '周报管理' } },
        { path: 'settings', component: PlaceholderView, meta: { title: '配置中心' } },
      ],
    },
  ],
})

export default router
