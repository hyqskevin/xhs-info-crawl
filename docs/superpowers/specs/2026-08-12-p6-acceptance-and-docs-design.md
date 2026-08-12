# P6 端到端验收 + 文档 设计

- 日期:2026-08-12
- 状态:已审核(持续授权,默认进入开发)
- 关联 TODO:docs/TODO.md "P6 端到端验收 + 文档"
- 关联 spec:`docs/superpowers/specs/2026-08-10-one-click-packaging-design.md`

## 1. 目标

为打包分发流程补齐最终用户文档、开发者文档和 E2E 验收测试案例,确保非开发者用户能根据文档完成"解压 → 双击 → 装 OpenCLI → 测试 → 打开网页"完整流程,开发者能根据文档在干净环境复现打包版本。

## 2. 范围

### 2.1 可在本机完成的产物

| 产物 | 路径 | 接收者 |
|---|---|---|
| 用户使用说明 | `README-USER.md` | 最终用户 |
| 安装文档(含打包版) | `INSTALL.md` | 开发者 + 用户 |
| 部署文档(含打包版章节) | `docs/deployment.md` | 开发者 |
| E2E 测试案例:启动器启动 | `tests/test-launcher-startup.md` | QA / 开发者 |
| E2E 测试案例:OpenCLI 连接 | `tests/test-opencli-connection.md` | QA / 开发者 |
| E2E 测试案例:OCR 一键安装 | `tests/test-ocr-install.md` | QA / 开发者 |

### 2.2 需要真实环境验证的验收项(推 tag 后)

- macOS 解压双击 → 三进程运行
- 装 OpenCLI → 测试通过 → 打开网页
- OCR 一键安装流程
- 端口冲突自动处理

这部分由用户在 GitHub Actions 产出 zip 后,本机下载验证。本 spec 只产出测试案例文档,不实际执行。

## 3. 文档内容设计

### 3.1 README-USER.md(新文件,项目根)

面向最终用户的中文使用说明,内容大纲:

1. **程序简介**:一句话说明程序用途
2. **系统要求**:macOS 12+ / Windows 10+,Chrome 浏览器,OpenCLI 桌面应用
3. **安装步骤**:
   - 下载 `xhs-info-crawl-<version>-macos.zip` 或 `xhs-info-crawl-<version>-windows.zip`
   - 解压到任意目录
   - macOS:双击 `xhs-info-crawl.app`(首次需右键 → 打开,绕过 Gatekeeper)
   - Windows:双击 `start.bat`(或解压目录内的 `xhs-info-crawl.exe` 若将来有)
4. **首次启动流程**:
   - 启动器窗口出现,显示三个服务状态(初始化中 → 运行中)
   - 首次启动自动初始化数据库(约 5-10 秒)
5. **配置 OpenCLI**:
   - 点"下载 OpenCLI"按钮 → 浏览器打开下载页
   - 安装 OpenCLIApp 桌面应用
   - 在 OpenCLIApp 中安装 Chrome 扩展
   - 回到启动器点"测试连接" → 显示绿色 ✓
6. **(可选)安装 OCR 增强**:
   - 点"下载安装 OCR"按钮
   - 等待进度条完成(约 200-500MB 下载)
   - 点"测试 OCR" → 显示绿色 ✓
7. **打开网页使用**:
   - 点"打开网页"按钮 → 系统浏览器打开 `http://127.0.0.1:<port>`
   - 用户名 `admin`,密码见启动器日志或 `.env` 中的 `INITIAL_ADMIN_PASSWORD`
8. **端口冲突处理**:启动器自动递增找可用端口(8000-8020),无需手动配置
9. **退出程序**:点"退出"按钮,或关闭启动器窗口,所有服务自动停止
10. **常见问题**:Gatekeeper 拦截、OpenCLI 未连接、OCR 安装失败、端口全占用

### 3.2 INSTALL.md(更新,增加打包版章节)

在现有开发者安装说明后,增加"打包版安装(非开发者)"章节:

- 下载 Release 中的对应平台 zip
- 解压并双击启动
- 与开发者版的差异(无需 Python/Node.js,内置运行时)
- 升级方法(下载新版 zip 替换,数据目录 `data/` 保留)

### 3.3 docs/deployment.md(更新,增加打包版部署章节)

增加"打包版部署"章节:

- 打包版架构图(便携 Python + venv + 应用代码 + 启动器)
- GitHub Actions 构建流程(推 tag 触发)
- 本地复现打包(`./scripts/package-macos.sh <version>`)
- OCR 增强包分发(独立 zip,启动器内一键安装)
- 数据目录布局(`data/` 下各子目录用途)
- 升级与迁移策略

### 3.4 E2E 测试案例(3 个文件)

#### 3.4.1 tests/test-launcher-startup.md

测试启动器从双击到三进程运行的完整流程:

- 前置:干净 macOS/Windows,已解压 zip
- 步骤1:双击 .app/start.bat
- 步骤2:启动器窗口出现,显示版本号
- 步骤3:等待 5-10 秒,API 状态变绿
- 步骤4:Worker 状态变绿
- 步骤5:Beat 状态变绿
- 步骤6:点"打开网页" → 浏览器打开 http://127.0.0.1:<port>
- 步骤7:登录页显示,输入 admin/密码 → 进入仪表盘
- 步骤8:点"退出" → 窗口关闭,进程结束
- 验收:任务管理器无残留 python 进程

#### 3.4.2 tests/test-opencli-connection.md

测试 OpenCLI 下载、安装、连接全流程:

- 前置:启动器已启动,三进程运行
- 步骤1:点"下载 OpenCLI" → 浏览器打开下载页
- 步骤2:下载并安装 OpenCLIApp
- 步骤3:打开 OpenCLIApp,安装 Chrome 扩展
- 步骤4:回到启动器,点"测试连接"
- 步骤5:等待 5-10 秒,显示绿色 ✓ + 版本号
- 异常案例1:未装 OpenCLIApp → 显示"未安装,点下载"
- 异常案例2:OpenCLIApp 未启动 → 显示"请打开 OpenCLIApp"
- 异常案例3:未装 Chrome 扩展 → 显示"请安装扩展"

#### 3.4.3 tests/test-ocr-install.md

测试 OCR 增强包一键安装:

- 前置:启动器已启动,OpenCLI 已连接
- 步骤1:点"下载安装 OCR" → 进度条出现
- 步骤2:等待下载完成(约 200-500MB)
- 步骤3:进度条到 100%,状态变"已安装"
- 步骤4:点"测试 OCR" → 显示绿色 ✓
- 步骤5:在网页端发起抓取,验证 OCR 真实工作
- 异常案例1:网络中断 → 进度条停止,显示错误
- 异常案例2:磁盘空间不足 → 安装前检查,显示警告
- 异常案例3:重复安装 → 检测已安装,跳过

## 4. 验收

### 4.1 文档验收(本机可完成)

- `README-USER.md` 存在,含 10 个章节
- `INSTALL.md` 含"打包版安装"章节
- `docs/deployment.md` 含"打包版部署"章节
- `tests/test-launcher-startup.md` 存在,含 8 步骤 + 验收
- `tests/test-opencli-connection.md` 存在,含 5 步骤 + 3 异常案例
- `tests/test-ocr-install.md` 存在,含 5 步骤 + 3 异常案例

### 4.2 真实环境验收(推 tag 后)

- macOS 解压双击 → 三进程运行 ✓
- 装 OpenCLI → 测试通过 → 打开网页 ✓
- OCR 一键安装流程 ✓
- 端口冲突自动处理 ✓

## 5. 不在范围

- 不实际执行真实环境验收(需推 tag + 下载 zip)
- 不修改打包脚本和工作流(P5 已完成)
- 不增加新的打包平台(Linux 仍不支持)
