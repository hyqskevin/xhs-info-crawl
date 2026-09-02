/** 安全 ElMessageBox.confirm：用户点取消不会冒 unhandled rejection。

Element Plus 的 ElMessageBox.confirm 在用户点取消时会 reject 一个 Error。
原代码大多 `await ElMessageBox.confirm(...)`，cancel 直接进 unhandled rejection，
既干扰日志也让 Promise 链路断裂。

使用 confirmSafe 替代直接 await，得到一个干净的 boolean：true 表示确认，false 表示取消。

```ts
if (!await confirmSafe('确认删除?')) return
await api.delete(...)
```
*/
import { ElMessageBox } from 'element-plus'

export async function confirmSafe(
  message: string,
  title = '确认',
  options: Record<string, unknown> = {},
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, options as Record<string, unknown> & { type?: string })
    return true
  } catch {
    return false
  }
}