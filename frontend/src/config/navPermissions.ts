/** 菜单 ↔ 权限码静态映射。
 *
 * 与后端 Permission.code / require_permission 一致。`*` 通配视为具备所有权限码。
 *
 * 顶级菜单可见 = 该顶级菜单下任一子项可见；若顶级自身指定了 `topLevelPermission` 则要求该码存在。
 * 子项不可见 = 该子项声明的 permission 用户不具备。
 *
 * 关联 TODO: navbar 按权限过滤（2026-08-13）
 */
export interface SubItem {
  /** Element Plus `index` 值（路由或带 query 的路径） */
  index: string
  /** 标签 */
  label: string
  /** 所需权限码。null 表示对所有已登录用户可见 */
  permission: string | null
}

export interface TopItem {
  /** Element Plus `index` 值（路由或带 query 的路径） */
  index: string
  /** 标签 */
  label: string
  /** 是否为顶级菜单（带子项）；false 时当作 leaf item */
  hasChildren?: boolean
  /** 顶级菜单可见需要该权限码；null 表示不强制（由子项决定） */
  topLevelPermission?: string | null
  /** 子项；顶级菜单时必须提供 */
  children?: SubItem[]
}

/** null = 对所有已登录用户可见 */
export const NAV_ITEMS: TopItem[] = [
  { index: '/dashboard', label: '仪表盘', hasChildren: false, topLevelPermission: null },
  { index: '/activities', label: '活动管理', hasChildren: false, topLevelPermission: null },
  { index: '/duplicates', label: '去重审核', hasChildren: false, topLevelPermission: 'duplicates:resolve' },
  { index: '/tasks', label: '任务日志', hasChildren: false, topLevelPermission: 'tasks:crawl' },
  {
    index: '/schedules',
    label: '定时任务',
    hasChildren: true,
    topLevelPermission: 'tasks:crawl',
    children: [
      { index: '/schedules?tab=schedules', label: '定时任务列表', permission: 'tasks:crawl' },
      { index: '/schedules?tab=batch', label: '抓取批次配置', permission: 'settings:write' },
    ],
  },
  { index: '/reports', label: '周报管理', hasChildren: false, topLevelPermission: 'reports:generate' },
  {
    index: '/settings',
    label: '配置中心',
    hasChildren: true,
    topLevelPermission: 'settings:write',
    children: [
      { index: '/settings?tab=cities', label: '城市抓取配置', permission: 'settings:write' },
      { index: '/settings?tab=bloggers', label: '博主白名单', permission: 'settings:write' },
      { index: '/settings?tab=keyword-groups', label: '关键词组', permission: 'settings:write' },
      { index: '/settings?tab=blogger-groups', label: '博主组', permission: 'settings:write' },
      { index: '/settings?tab=xhs-accounts', label: '账号配置', permission: 'settings:write' },
      { index: '/settings?tab=system-config', label: '系统配置', permission: 'settings:write' },
    ],
  },
  {
    index: '/system-admin',
    label: '系统管理',
    hasChildren: true,
    topLevelPermission: 'users:read',
    children: [
      { index: '/system-admin?tab=accounts', label: '操作账号', permission: 'users:manage' },
      { index: '/system-admin?tab=groups', label: '账号分组', permission: 'users:read' },
      { index: '/system-admin?tab=permissions', label: '权限配置', permission: 'users:read' },
      { index: '/system-admin?tab=audit', label: '操作日志', permission: 'users:manage' },
    ],
  },
]