/** 判断当前是否在登录页（hash 路由模式）。 */
export function isLoginPage(): boolean {
  return location.hash === '#/login'
}

/** 跳转到登录页（hash 路由模式）。 */
export function goLogin(): void {
  location.hash = '#/login'
}