import { createRouter, createWebHashHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import DashboardView from '@/views/DashboardView.vue'
import LoginView from '@/views/LoginView.vue'
import ActivitiesView from '@/views/ActivitiesView.vue'
import TasksView from '@/views/TasksView.vue'
import SchedulesView from '@/views/SchedulesView.vue'
import DuplicatesView from '@/views/DuplicatesView.vue'
import ReportsView from '@/views/ReportsView.vue'
import SettingsView from '@/views/SettingsView.vue'
import PostersListView from '@/views/PostersListView.vue'
import PosterWizardView from '@/views/PosterWizardView.vue'
import SystemAdminView from '@/views/SystemAdminView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {path:'/login',component:LoginView,meta:{public:true,title:'登录'}},
    {
      path: '/',
      component: AppLayout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', component: DashboardView, meta: { title: '仪表盘' } },
        { path: 'activities', component: ActivitiesView, meta: { title: '活动管理' } },
        { path: 'duplicates', component: DuplicatesView, meta: { title: '去重审核' } },
        { path: 'tasks', component: TasksView, meta: { title: '任务日志' } },
        { path: 'schedules', component: SchedulesView, meta: { title: '定时任务' } },
        { path: 'reports', component: ReportsView, meta: { title: '周报管理' } },
        { path: 'settings', component: SettingsView, meta: { title: '配置中心' } },
        { path: 'posters', component: PostersListView, meta: { title: '海报制作' } },
        { path: 'posters/new', component: PosterWizardView, meta: { title: '新建海报' } },
        { path: 'system-admin', component: SystemAdminView, meta: { title: '系统管理', permissions: ['system:admin'] } },
      ],
    },
  ],
})
router.beforeEach(async (to) => {
  // 动态 import 避免循环依赖（stores/user 不应在 router 文件顶层 import）
  const { useUserStore } = await import('@/stores/user')
  const user = useUserStore()
  if (!to.meta.public && !user.isAuthenticated) return '/login'
  if (to.path === '/login' && user.isAuthenticated) return '/dashboard'
  // 权限校验：to.meta.permissions 是 AND 关系（全部满足才放行），
  // 与后端 require_permission 单个 code 的语义对齐用 .every。
  const required = (to.meta as { permissions?: string[] }).permissions ?? []
  if (required.length && !required.every((p) => user.hasPermission(p))) return '/dashboard'
})

export default router
