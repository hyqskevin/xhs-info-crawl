# E2E 测试案例:OpenCLI 连接测试

> 测试 OpenCLI 下载、安装、连接、异常处理全流程。
>
> 关联 spec:`docs/superpowers/specs/2026-08-12-p6-acceptance-and-docs-design.md` § 3.4.2

## 前置条件

- 启动器已启动,三个服务运行中(API/Worker/Beat 绿色)
- Google Chrome 已安装并登录小红书(https://www.xiaohongshu.com)
- 网络连接正常

## 测试步骤

### 步骤 1:点击下载 OpenCLI

**操作**:在启动器面板"OpenCLI 连接"卡片中,点"下载 OpenCLI"按钮

**预期**:
- 系统浏览器打开 OpenCLI 官方下载页(https://opencli.info/download 或类似地址)
- 启动器面板 OpenCLI 状态显示"未检测,请安装后点测试连接"

### 步骤 2:安装 OpenCLIApp

**操作**:
1. 在浏览器中下载 OpenCLIApp 安装包
2. 安装 OpenCLIApp(macOS 拖到 Applications;Windows 运行安装程序)
3. 打开 OpenCLIApp 应用

**预期**:
- OpenCLIApp 应用启动,显示主界面
- OpenCLIApp 显示 daemon 运行中
- OpenCLIApp 显示"Chrome 扩展:未连接"

### 步骤 3:安装 Chrome 扩展

**操作**:在 OpenCLIApp 中点"安装 Chrome 扩展"按钮

**预期**:
- Chrome 自动打开扩展商店页面(或下载 .crx 文件)
- 安装扩展后,OpenCLIApp 显示"Chrome 扩展:已连接"
- OpenCLIApp 显示当前连接的 Chrome 版本

### 步骤 4:测试连接

**操作**:回到启动器面板,点"测试连接"按钮

**预期**:
- 按钮变为 loading 状态(约 5-10 秒)
- OpenCLI 状态变绿色 ✓ + 显示版本号(如 "v1.8.6")
- 日志卡片新增:"OpenCLI 测试:✓ v<版本号>"
- "下载 OpenCLI"按钮变为灰色(已安装)

### 步骤 5:验证抓取功能

**操作**:
1. 点"打开网页"进入仪表盘
2. 配置一个城市和关键词组
3. 发起一次小范围抓取(如 5 篇)

**预期**:
- 抓取任务进入运行中状态
- 任务列表显示进度
- 抓取完成后,推文列表有数据
- OpenCLI 在抓取过程中保持连接状态

## 异常案例

### 异常 1:未安装 OpenCLIApp

**前置**:未安装 OpenCLIApp

**操作**:点"测试连接"

**预期**:
- 状态显示红色 ✗
- 提示:"未安装 OpenCLI,点 [下载 OpenCLI]"
- 日志显示:"opencli: command not found"
- "下载 OpenCLI"按钮高亮

### 异常 2:OpenCLIApp 未启动

**前置**:已安装 OpenCLIApp 但未打开

**操作**:点"测试连接"

**预期**:
- 状态显示红色 ✗
- 提示:"OpenCLIApp 未启动,请打开 OpenCLIApp 应用"
- 日志显示:"daemon not running" 或类似
- 不显示版本号

### 异常 3:未装 Chrome 扩展

**前置**:OpenCLIApp 已启动,但未装 Chrome 扩展

**操作**:点"测试连接"

**预期**:
- 状态显示红色 ✗
- 提示:"未装 Chrome 扩展,在 OpenCLIApp 里点 [安装扩展]"
- 日志显示:"extension not connected" 或类似

### 异常 4:测试连接超时

**前置**:OpenCLIApp 已启动但响应异常

**操作**:点"测试连接"

**预期**:
- 按钮保持 loading 状态 10 秒后恢复
- 状态显示红色 ✗
- 提示:"连接超时,请检查 OpenCLIApp 是否正常运行"
- 日志显示:"opencli doctor 超时(10s)"

### 异常 5:Chrome 未登录小红书

**前置**:OpenCLI 已连接,但 Chrome 未登录小红书

**操作**:发起抓取

**预期**:
- 抓取任务进入"已暂停"状态
- 任务错误信息:"小红书未登录,请在 Chrome 中登录后重试"
- 仪表盘显示登录提示
- OpenCLI 连接状态保持绿色(连接正常,只是未登录)

## 验收标准

- [x] 步骤 1-5 全部通过
- [x] 异常 1-5 全部按预期处理
- [x] 测试连接响应时间 < 10 秒
- [x] 连接状态在启动器面板明确显示(绿色 ✓ 或红色 ✗)
- [x] 错误提示给出具体解决方案(不只是错误码)
