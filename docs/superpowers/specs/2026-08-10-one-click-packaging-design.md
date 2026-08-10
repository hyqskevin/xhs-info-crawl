# 一键打包分发方案设计

- 日期:2026-08-10
- 状态:已审核(持续授权,默认进入开发)
- 关联 TODO:docs/TODO.md "一键打包分发"

## 1. 目标

把当前只能 git clone 安装的工程,打包成最终用户双击即用的桌面程序,降低非开发者使用门槛。

## 2. 范围

### 2.1 两个产物

| 产物 | 接收者 | 内容 |
|---|---|---|
| `xhs-info-crawl-<ver>-<os>.zip` | 最终用户 | 便携运行时 + 应用代码 + 启动器 |
| `xhs-info-crawl-<ver>-src.zip` | 开发者 | 源代码(git archive 打包) |

### 2.2 用户约束(已对齐)

- 目标平台:macOS + Windows 双平台
- 用户自装:Chrome 浏览器、OpenCLI(官方桌面应用 OpenCLIApp)
- 程序内置:便携版 Python 3.11.9、后端依赖、前端构建产物、PyWebView 启动器
- OCR 作为可选增强包,启动器内一键下载安装
- 启动体验:PyWebView 桌面窗口 + 启动器面板 + 手动开网页

### 2.3 不在范围

- 不做 Linux 服务器版本
- 不做 Electron(体积过大)
- 不自动安装 Chrome(用户必须自装并登录小红书)
- 不自动安装 OpenCLI 桌面应用(用户自装,启动器提供下载链接和测试按钮)
- 不打包 Node.js 到最终用户包(后端是 Python,前端已构建为静态文件,OpenCLI 是独立桌面应用)

## 3. 整体架构与包结构

### 3.1 最终用户包结构(macOS 和 Windows 共用布局)

```
xhs-info-crawl/
├── runtime/                       # 便携运行时(平台相关)
│   ├── python/                    # python-build-standalone 3.11.9
│   │   └── (bin/python3 | python.exe)
│   └── venv/                      # 已装好 fastapi/celery/uvicorn/pywebview/...
├── app/                           # 应用代码(源代码子集,只保留运行所需)
│   ├── backend/                   # Python 后端源码
│   ├── frontend/dist/             # 前端已构建静态产物
│   └── migrations/
├── launcher/                      # PyWebView 启动器
│   ├── main.py
│   ├── status_server.py
│   ├── process_manager.py
│   ├── ocr_installer.py
│   ├── opencli_checker.py
│   ├── port_finder.py
│   ├── env_bootstrap.py
│   ├── requirements.txt
│   └── ui/                        # 启动器 UI(Vue 项目)
│       ├── src/
│       ├── package.json
│       └── dist/                  # 构建产物,PyWebView 加载这里
├── data/                          # 运行数据(空,首次启动初始化)
│   ├── logs/                      # 服务日志
│   ├── paddlex/                   # PaddleOCR 模型缓存(OCR 增强包安装后填充)
│   │   └── official_models/       # paddleocr 3.x 标准缓存目录
│   ├── huggingface/               # HuggingFace 缓存(若需要)
│   └── tmp/                       # 临时文件
├── .env                           # 首次启动时由 launcher 从 .env.example 生成
├── .env.example
└── README-USER.md                 # 用户使用说明(中文)
```

**注意**:不再有独立的 `ocr-addon/` 目录。OCR 增强包的内容(wheels + 模型)直接放到项目已有的目录结构中:
- wheels 安装到 `runtime/venv/`(pip install)
- 模型文件放到 `data/paddlex/official_models/`(paddleocr 标准缓存目录)
- 这样和项目现有的 `PADDLE_PDX_CACHE_HOME=./data/paddlex` 配置完全对齐,无路径冲突

### 3.2 关键约定

- **Python**:python-build-standalone 的 `cpython-3.11.9+<date>-<os>-<arch>-install_only.tar.gz`,在打包机上 `venv + pip install` 装好后端依赖和启动器依赖(pywebview),整个 venv 跟着分发。不装 paddleocr extra,OCR 走增强包
- **前端**:打包阶段 `npm run build` 出 `dist/`,后端 FastAPI 用 `StaticFiles` 挂载,不再跑 vite
- **启动器**:PyWebView 跨平台,同一份 Python + Vue 代码,macOS 套 `.app` bundle,Windows 出 `.exe` 启动器入口
- **OCR 增强包**:独立 zip,启动器内一键下载,模型解压到 `data/paddlex/official_models/`,wheel 装到 `runtime/venv/`,自动设 `OCR_ENABLED=true`

### 3.3 用户操作流程

```
1. 解压 xhs-info-crawl-<ver>-macos.zip
2. 双击 xhs-info-crawl.app(或 .exe)
3. 首次启动:
   - launcher 检测 .env 不存在 → 从 .env.example 复制
   - 检测 API_PORT 占用 → 自动选可用端口写入 .env
   - 执行 alembic upgrade head(用包内 Python)
4. 启动器面板显示三个进程状态、OpenCLI/OCR 状态
5. 用户点"下载 OpenCLI" → 浏览器打开 https://opencli.info/download
6. 装好 OpenCLIApp 后点"测试 OpenCLI 连接" → 显示绿色 ✓
7. (可选)点"下载安装 OCR" → 下载解压 pip 装 → 测试 OCR 通过
8. 点"打开网页" → 系统浏览器打开 http://127.0.0.1:<port>
```

## 4. 启动器架构(PyWebView)

### 4.1 进程模型

启动器是 Python 主进程,管理 3 个子进程 + 1 个本地状态服务 + 1 个 PyWebView 窗口:

```
launcher (Python 主进程)
├── PyWebView 窗口           — 加载本地 HTML(Vue 构建)
├── 本地状态 HTTP 服务       — Python 起小 FastAPI 给 UI 轮询状态(端口 = API_PORT + 1)
├── uvicorn (API 子进程)     — runtime/venv/bin/python -m uvicorn app.main:app
├── celery worker (子进程)   — runtime/venv/bin/python -m celery -A app.tasks.crawl_task worker
└── celery beat (子进程)     — runtime/venv/bin/python -m celery -A app.tasks.crawl_task beat
```

- 子进程用 `subprocess.Popen` 启动,stdout/stderr 重定向到 `data/logs/<service>.log`
- 启动器退出时,确保 3 个子进程都被 terminate(先 SIGTERM,5s 后 SIGKILL)
- macOS 用 .app bundle 包装,Windows 用 PyInstaller 出 .exe(只包启动器入口,不包后端)

### 4.2 启动顺序

```
1. 启动器启动
2. 加载 .env(不存在则从 .env.example 复制)
3. 检测 API_PORT 是否被占用 → 被占则自动递增找可用端口,写入 .env
4. 检测首次启动(data/app.db 不存在)→ 执行 alembic upgrade head
5. 启动 API 子进程,等待健康检查 /api/v1/health 返回 200(最多 30s)
6. API 健康后启动 Worker 子进程
7. Worker 启动后启动 Beat 子进程
8. UI 显示三个进程状态为 ● 运行中
9. 启动后台心跳线程,每 10s 检查三个子进程是否存活
   - 任一进程挂掉:UI 显示 ● 异常,日志尾部显示在面板下方
   - 用户可点 [重启] 单独重启某个进程
```

### 4.3 本地状态服务接口

启动器自己起的轻量服务(端口 = API_PORT + 1,仅本地,不对外):

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/status` | 返回三个进程状态、端口、版本号、OpenCLI/OCR 快照 |
| POST | `/service/{name}/restart` | 重启指定服务(api/worker/beat) |
| POST | `/service/all/stop` | 停止全部服务 |
| GET | `/opencli/test` | 测试 OpenCLI 连接 |
| GET | `/opencli/download-url` | 返回 OpenCLI 下载页 URL |
| GET | `/ocr/status` | OCR 安装状态 |
| POST | `/ocr/install` | 触发 OCR 下载安装(异步,后台线程) |
| GET | `/ocr/install-progress` | 查询 OCR 安装进度 |
| POST | `/ocr/test` | 测试 OCR(调后端 /api/v1/diagnostics/ocr) |
| GET | `/logs/tail?lines=50` | 获取最近日志 |

### 4.4 OpenCLI 测试逻辑

启动器直接调 `opencli doctor`(subprocess,超时 10s),解析输出:

- exit 0 + 输出含 "daemon: ok" / "extension: connected" → 绿色 ✓ + 版本号
- exit 非 0 → 红色 ✗,根据 stderr 分类:
  - `command not found` → "未安装 OpenCLI,点 [下载 OpenCLI]"
  - `daemon not running` → "OpenCLIApp 未启动,请打开 OpenCLIApp 应用"
  - `extension not connected` → "未装 Chrome 扩展,在 OpenCLIApp 里点 [安装扩展]"
  - 其他 → 显示原始 stderr

### 4.5 端口探测逻辑

```python
def find_available_port(start: int = 8000, end: int = 8020) -> int:
    """从 start 开始找可用端口,上限 end"""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"端口 {start}-{end} 全部被占用,请手动在 .env 中配置 API_PORT")
```

- 启动器启动时调用,找到可用端口后写入 `.env`
- 如果用户手动在 .env 配了端口,优先用配置值;若该端口被占则自动找下一个并提示
- CORS_ORIGINS 自动加入对应端口

### 4.6 UI 设计(基于 Google Material Design 3)

启动器 UI 遵循 [Material Design 3](https://m3.material.io/) 设计语言,确保视觉专业、信息层次清晰、状态反馈明确。

#### 4.6.1 设计原则(来自 M3)

| M3 原则 | 在启动器中的应用 |
|---|---|
| **颜色角色**(primary/on-primary/surface/on-surface/container) | 用语义化 CSS 变量,不用硬编码颜色 |
| **三层对比**(高/中/低强调) | 服务状态用高强调;日志用中强调;辅助文字用低强调 |
| **排版五角色**(Display/Headline/Title/Body/Label) | 应用名用 Headline;区块标题用 Title;状态文字用 Body;按钮用 Label |
| **Elevation 表达层次** | 卡片用阴影区分;日志区域用更低 elevation |
| **暗色主题优先** | 启动器默认暗色(减少眩光,适合长时间运行的工具面板) |
| **状态色语义** | 运行中=primary(绿);停止=on-surface 变体(灰);异常=error(红) |

#### 4.6.2 颜色方案(M3 Dark Theme baseline + 品牌色定制)

```css
:root {
  /* M3 Dark Surface 层级(用深灰而非纯黑,表达 elevation) */
  --md-sys-color-background: #121212;
  --md-sys-color-surface: #1C1C1E;
  --md-sys-color-surface-variant: #2C2C2E;
  --md-sys-color-surface-container-high: #3A3A3C;

  /* M3 On-Surface 文字色 */
  --md-sys-color-on-surface: #E6E6E6;
  --md-sys-color-on-surface-variant: #9B9B9D;

  /* 品牌主色(primary = 小红书红,降饱和度适配暗色) */
  --md-sys-color-primary: #FF5C5C;
  --md-sys-color-on-primary: #FFFFFF;
  --md-sys-color-primary-container: #4D1A1A;

  /* 状态语义色 */
  --md-sys-color-success: #4ADE80;    /* 运行中 */
  --md-sys-color-on-success: #003314;
  --md-sys-color-error: #F87171;      /* 异常/失败 */
  --md-sys-color-on-error: #4D0000;
  --md-sys-color-warning: #FBBF24;    /* 安装中/等待 */
  --md-sys-color-on-warning: #4D3500;

  /* M3 Elevation 阴影(暗色主题用表面色叠加而非阴影) */
  --md-sys-elevation-1: 0px 1px 2px rgba(0,0,0,0.3), 0px 1px 3px 1px rgba(0,0,0,0.15);
  --md-sys-elevation-2: 0px 2px 6px 2px rgba(0,0,0,0.15), 0px 1px 2px rgba(0,0,0,0.3);
}
```

#### 4.6.3 排版(M3 Type Scale)

```css
:root {
  /* M3 Type Scale - 网页用 line-height + padding 模式 */
  --md-sys-typescale-headline-large: 600 28px/36px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-headline-medium: 600 24px/32px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-title-large: 500 20px/28px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-title-medium: 500 16px/24px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-body-large: 400 16px/24px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-body-medium: 400 14px/20px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-label-large: 500 14px/20px 'Inter', 'PingFang SC', sans-serif;
  --md-sys-typescale-label-medium: 500 12px/16px 'Inter', 'PingFang SC', sans-serif;
}
```

#### 4.6.4 布局(M3 卡片 + 分区)

```
┌─────────────────────────────────────────────────────────────┐
│ ┌─ Top App Bar (surface, elevation-2) ───────────────────┐ │
│ │  小红书活动信息抓取系统              v0.1.0    [⚙ 设置] │ │
│ │  (headline-medium)                       (label-medium)│ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─ 服务状态 Card (surface, elevation-1) ─────────────────┐  │
│ │  服务状态 (title-large)                                │  │
│ │  ┌──────────────────────────────────────────────────┐  │  │
│ │  │ ● API     运行中    http://127.0.0.1:8000 [重启] │  │  │
│ │  │ (success) (body-med) (label-med)         [FAB]   │  │  │
│ │  ├──────────────────────────────────────────────────┤  │  │
│ │  │ ● Worker  运行中                          [重启] │  │  │
│ │  ├──────────────────────────────────────────────────┤  │  │
│ │  │ ● Beat    运行中                          [重启] │  │  │
│ │  └──────────────────────────────────────────────────┘  │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ OpenCLI Card (surface, elevation-1) ──────────────────┐  │
│ │  OpenCLI 连接 (title-large)             [未检测]       │  │
│ │                                          (warning chip)│  │
│ │  [测试连接]  [下载 OpenCLI]                            │  │
│ │  (outlined-btn)  (filled-btn)                          │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ OCR 增强 Card (surface, elevation-1) ─────────────────┐  │
│ │  OCR 增强 (title-large)                  [未安装]      │  │
│ │  PaddleOCR 图片本地识别                   (warning chip)│  │
│ │  (body-medium, on-surface-variant)                     │  │
│ │  [下载安装 OCR]  [测试 OCR]                            │  │
│ │  (filled-btn)     (outlined-btn)                       │  │
│ │  [━━━━━━━━━━━━━━━━━━━━━━━━━━] 45%  (进度条,安装中显示)│  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 日志 Card (surface-variant, elevation-0) ─────────────┐  │
│ │  日志 (title-medium)                   [打开日志目录]  │  │
│ │  ┌──────────────────────────────────────────────────┐  │  │
│ │  │ 14:30:01  API     启动成功,端口 8000            │  │  │
│ │  │ 14:30:03  Worker  启动成功                       │  │  │
│ │  │ 14:35:12  System  OpenCLI 测试:✓ v1.8.6         │  │  │
│ │  │ (body-medium, on-surface-variant, 等宽字体时间戳)│  │  │
│ │  └──────────────────────────────────────────────────┘  │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 底部操作栏 (surface-container-high) ──────────────────┐  │
│ │  [打开网页]              [停止全部]      [退出]        │  │
│ │  (filled-btn, primary)   (outlined-btn)  (text-btn)    │  │
│ └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### 4.6.5 M3 组件映射

| UI 元素 | M3 组件 | 实现方式(Element Plus 对应) |
|---|---|---|
| 应用顶栏 | M3 Top App Bar | 自定义 div + elevation-2 |
| 状态卡片 | M3 Card (filled) | el-card + surface 色 |
| 服务行 | M3 List Item | 自定义 flex 行 |
| 状态指示点 | M3 Badge (dot) | 自定义圆点 + success/error/warning 色 |
| 状态标签 | M3 Chip (assisted) | el-tag + 对应语义色 |
| 主操作按钮 | M3 Filled Button | el-button type="primary" |
| 次要按钮 | M3 Outlined Button | el-button type="default" + border |
| 文本按钮 | M3 Text Button | el-button type="text" |
| 进度条 | M3 Linear Progress Indicator | el-progress + 自定义颜色 |
| 日志区 | M3 Container(surface-variant) | el-card + 暗色背景 |
| 设置入口 | M3 IconButton | el-button circle + icon |

#### 4.6.6 间距与圆角(M3 规范)

```css
:root {
  /* M3 Spacing(4dp 网格) */
  --md-sys-spacing-1: 4px;
  --md-sys-spacing-2: 8px;
  --md-sys-spacing-3: 12px;
  --md-sys-spacing-4: 16px;
  --md-sys-spacing-5: 20px;
  --md-sys-spacing-6: 24px;
  --md-sys-spacing-8: 32px;

  /* M3 Shape(圆角) */
  --md-sys-shape-corner-small: 8px;    /* 按钮、chip */
  --md-sys-shape-corner-medium: 12px;  /* 卡片 */
  --md-sys-shape-corner-large: 16px;   /* 大卡片 */
  --md-sys-shape-corner-full: 9999px;  /* 圆形(FAB) */
}
```

#### 4.6.7 状态反馈动效(M3 Motion)

- 服务状态变化:圆点 200ms 淡入淡出(M3 standard easing)
- 按钮点击:M3 Ripple 效果(Element Plus 自带)
- 进度条:M3 Linear Progress 平滑过渡
- 卡片出现:150ms 淡入 + 4dp 上移

### 4.7 PyWebView 窗口配置

- 窗口标题:`小红书活动信息抓取系统 v<version>`
- 窗口尺寸:`900 × 700`,可调整,最小 `720 × 600`
- 加载 URL:`file:///.../launcher/ui/dist/index.html?statusPort=<port>`
- 关闭窗口 = 退出程序(触发停止全部服务)
- 背景色:`#121212`(M3 dark background,避免启动白闪)
- 窗口图标:打包时嵌入应用图标(macOS .icns / Windows .ico)

## 5. OCR 增强包一键安装

### 5.1 下载安装流程

OCR 增强包版本号独立于主程序,采用 `paddleocr-<paddleocr_version>` 格式(如 `paddleocr-3.7.0`)。

**关键技术约束**:paddleocr 3.x 的模型加载机制是:
- 默认缓存到 `~/.paddlex/official_models/`(用户 home 目录,违反项目"不污染外部目录"硬约束)
- 通过环境变量 `PADDLE_PDX_CACHE_HOME` 重定向缓存目录
- `PaddleOCR()` 构造函数不接受 `model_dir` 参数作为整体模型目录
- 因此项目现有的 `paddleocr_model_dir` 配置是死配置(见 7.3 节代码改动,本次一并修复)

1. 用户点 **"下载安装 OCR"** 按钮
2. 启动器根据当前 OS/架构自动选对应包:
   - macOS arm64 → `paddleocr-addon-3.7.0-macos-arm64.zip`
   - macOS x86_64 → `paddleocr-addon-3.7.0-macos-x86_64.zip`
   - Windows x64 → `paddleocr-addon-3.7.0-windows-x64.zip`
3. 从 GitHub Releases 下载(地址形如 `https://github.com/hyqskevin/xhs-info-crawl/releases/download/ocr-addon-3.7.0/paddleocr-addon-3.7.0-<os>-<arch>.zip`,OCR 增强包用独立 tag `ocr-addon-<version>` 发布,不和主程序版本绑定)
4. 下载进度条显示(包体 1-2 GB,必须有进度反馈)
5. 下载完成校验 SHA256
6. 解压到 `data/paddlex/`(与项目现有 `PADDLE_PDX_CACHE_HOME` 重定向路径一致):
   ```
   data/paddlex/
   └── official_models/      # paddleocr 3.x 标准缓存目录结构
       ├── PP-OCRv4_chinese_det/
       │   ├── inference.yml
       │   ├── inference.pdiparams
       │   └── inference.json
       ├── PP-OCRv4_chinese_rec/
       │   └── ...
       └── PP-OCRv4_chinese_cls/
           └── ...
   ```
   说明:增强包里的模型文件直接放到 `data/paddlex/official_models/`,这样 paddleocr 启动时通过 `PADDLE_PDX_CACHE_HOME=./data/paddlex` 自动找到,无需额外配置路径。
7. 启动器调包内 Python 的 pip 安装 `wheels/` 下的 wheel 到 `runtime/venv/`(不污染系统 Python)
8. 自动写入 `.env`:`OCR_ENABLED=true`
   - 不需要写 `PADDLEOCR_MODEL_DIR`(该配置项将被废弃,见 7.3 节)
   - `PADDLE_PDX_CACHE_HOME=./data/paddlex` 由启动器启动时设置(见 13.1 节),已包含在 `env_bootstrap.py` 逻辑中
9. 提示用户重启服务(API/Worker/Beat 需重启才能加载 OCR)

### 5.2 "测试 OCR" 按钮

调后端 `POST /api/v1/diagnostics/ocr`(新增接口):
- 后端加载 paddleocr,对一张测试图片做识别
- 成功:绿色 ✓ + 显示识别到的文字片段 + 耗时
- 失败:红色 ✗ + 错误原因 + 解决建议

### 5.3 状态显示

- **未安装**:`OCR_ENABLED=false` 且 `data/paddlex/official_models/` 不存在或为空
- **已安装**:检测 `data/paddlex/official_models/` 下有模型目录(如 `PP-OCRv4_chinese_det`)+ paddleocr 可导入
- **安装中**:按钮变灰 + 进度条 + 取消按钮
- **安装失败**:红色 + 错误原因 + 重试按钮

### 5.4 异常处理

- 下载失败/网络中断:可重试,支持断点续传(用 HTTP Range)
- 磁盘空间不足:下载前先检测,提示需要至少 3 GB 可用空间
- pip 安装失败:回滚(删除已解压文件,恢复 .env)
- 用户在安装过程中关闭启动器:下次启动检测到半成品 `data/paddlex/.installing` 标记,提示清理后重装

## 6. 打包构建流程

### 6.1 打包机准备

打包在 GitHub Actions 上跑(免费且可复现),也可本地手动跑。

- GitHub Actions 提供 `macos-latest`(arm64)和 `windows-latest`(x64)runner
- **不能交叉打包**:python-build-standalone 和 PyInstaller 都要原生运行

### 6.2 GitHub Actions 工作流

两个独立工作流文件,对应主程序和 OCR 增强包的独立发布节奏。

#### 主程序工作流 `.github/workflows/release.yml`

触发条件:推送 `v*.*.*` tag。

jobs:
- `build-macos`:出 macOS 用户包
- `build-windows`:出 Windows 用户包
- `release`:汇总产物 + 源码 zip 创建 GitHub Release(tag `v<version>`)

每个 build job 的步骤:
1. checkout 代码
2. setup Node.js 18.20.4 + Python 3.11.9(用于跑构建脚本,不打包进用户包)
3. 构建前端:`cd frontend && npm ci && npm run build`
4. 构建启动器 UI:`cd launcher/ui && npm ci && npm run build`
5. 跑打包脚本:`./scripts/package-macos.sh` 或 `./scripts/package-windows.ps1`
6. upload-artifact

#### OCR 增强包工作流 `.github/workflows/release-ocr-addon.yml`

触发条件:推送 `ocr-addon-*` tag(如 `ocr-addon-3.7.0`)。

jobs:
- `build-ocr-addon-macos-arm64`:出 macOS arm64 OCR 增强包
- `build-ocr-addon-macos-x86_64`:出 macOS x86_64 OCR 增强包
- `build-ocr-addon-windows-x64`:出 Windows x64 OCR 增强包
- `release`:汇总产物创建 GitHub Release(tag `ocr-addon-<version>`)

OCR 增强包 build job 只需下载 wheel + 模型 + 打包,不需要构建前端。

### 6.3 macOS 打包脚本 `scripts/package-macos.sh` 主要步骤

```bash
#!/bin/bash
set -e

VERSION=$1
ROOT_DIR=$(pwd)
BUILD_DIR=$ROOT_DIR/dist/build
PKG_DIR=$BUILD_DIR/xhs-info-crawl

rm -rf $BUILD_DIR
mkdir -p $PKG_DIR

# 1. 下载便携版 Python 3.11.9(python-build-standalone)
curl -L https://github.com/astral-sh/python-build-standalone/releases/download/20240415/cpython-3.11.9+20240415-darwin-arm64-install_only.tar.gz \
  | tar xz -C $BUILD_DIR
mv $BUILD_DIR/python $PKG_DIR/runtime/python

# 2. 创建 venv 并安装依赖(不含 ocr extra)
$PKG_DIR/runtime/python/bin/python3 -m venv $PKG_DIR/runtime/venv
$PKG_DIR/runtime/venv/bin/pip install --upgrade pip
$PKG_DIR/runtime/venv/bin/pip install -r backend/requirements-runtime.txt
$PKG_DIR/runtime/venv/bin/pip install -r launcher/requirements.txt
# backend/requirements-runtime.txt 是 pyproject.toml 的 dependencies 转出(不含 ocr extra)

# 3. 复制后端源码
cp -r backend $PKG_DIR/app/backend

# 4. 复制前端构建产物
mkdir -p $PKG_DIR/app/frontend/dist
cp -r frontend/dist/* $PKG_DIR/app/frontend/dist/

# 5. 复制启动器(不含 ui/src 和 node_modules)
mkdir -p $PKG_DIR/launcher/ui/dist
cp -r launcher/*.py launcher/requirements.txt $PKG_DIR/launcher/
cp -r launcher/ui/dist/* $PKG_DIR/launcher/ui/dist/

# 6. 复制 .env.example
cp .env.example $PKG_DIR/.env.example

# 7. 创建空 data 目录(含 paddlex 占位,OCR 增强包安装后填充)
mkdir -p $PKG_DIR/data/logs $PKG_DIR/data/images $PKG_DIR/data/exports $PKG_DIR/data/celery
mkdir -p $PKG_DIR/data/paddlex/official_models
mkdir -p $PKG_DIR/data/huggingface
mkdir -p $PKG_DIR/data/tmp

# 8. 打 .app bundle
mkdir -p $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS
cat > $BUILD_DIR/xhs-info-crawl.app/Contents/Info.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>小红书活动信息抓取系统</string>
  <key>CFBundleExecutable</key><string>start.sh</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
</dict>
</plist>
EOF
cat > $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS/start.sh <<'EOF'
#!/bin/bash
DIR="$(dirname "$(dirname "$(dirname "$0")")")"
exec "$DIR/xhs-info-crawl/runtime/venv/bin/python" "$DIR/xhs-info-crawl/launcher/main.py"
EOF
chmod +x $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS/start.sh

# 9. 压缩
cd $BUILD_DIR
zip -r xhs-info-crawl-$VERSION-macos.zip xhs-info-crawl xhs-info-crawl.app
```

### 6.4 Windows 打包脚本 `scripts/package-windows.ps1`

逻辑对应 macOS 版,差异点:
- 下载 `cpython-3.11.9+20240415-x86_64-pc-windows-msvc-install_only.tar.gz`
- venv 在 `runtime\venv\Scripts\python.exe`
- PyInstaller 出 `xhs-info-crawl.exe` 启动器入口(只包 launcher/main.py,不包后端)
- 压缩成 zip

### 6.5 OCR 增强包构建 `scripts/package-ocr-addon.sh`

```bash
#!/bin/bash
OS=$1      # macos / windows
ARCH=$2    # arm64 / x86_64 / x64
VERSION=$3

BUILD_DIR=dist/ocr-addon-build
rm -rf $BUILD_DIR && mkdir -p $BUILD_DIR/wheels $BUILD_DIR/data/paddlex/official_models

# 1. 下载 paddleocr + paddlepaddle wheel(对应平台)
pip download paddleocr==3.7.0 paddlepaddle==3.3.1 \
  --platform $WHEEL_PLATFORM_TAG \
  --only-binary=:all: \
  -d $BUILD_DIR/wheels/

# 2. 下载 OCR 模型文件到 paddleocr 标准缓存目录结构
# 触发 paddleocr 自动下载,然后把 ~/.paddlex/official_models/ 复制过来
# 或用 paddleocr 提供的模型下载 API
python -c "
import os
os.environ['PADDLE_PDX_CACHE_HOME'] = '$BUILD_DIR/data/paddlex'
from paddleocr import PaddleOCR
# 初始化触发模型下载到指定目录
ocr = PaddleOCR(lang='ch', use_doc_orientation_classify=False,
                use_doc_unwarping=False, use_textline_orientation=False)
"

# 3. 写 VERSION(放在 wheels/ 旁边,启动器用它判断增强包版本)
echo "version: 3.7.0" > $BUILD_DIR/VERSION
echo "built_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> $BUILD_DIR/VERSION

# 4. 压缩
cd dist
zip -r paddleocr-addon-$VERSION-$OS-$ARCH.zip ocr-addon-build
```

**安装时**:启动器把 zip 解压到项目根:
- `wheels/` → 临时目录,pip install 后可删
- `data/paddlex/official_models/` → 直接放到项目 `data/paddlex/official_models/`(与 `PADDLE_PDX_CACHE_HOME=./data/paddlex` 对齐)
- `VERSION` → 放到 `data/paddlex/.ocr_addon_version`(启动器用它判断已安装版本)

### 6.6 源码 zip 包

```bash
git archive --format=zip --prefix=xhs-info-crawl/ HEAD \
  > xhs-info-crawl-$VERSION-src.zip
```

`.gitattributes` 配置排除:

```
.venv/ export-ignore
node_modules/ export-ignore
data/*.db export-ignore
data/images/ export-ignore
data/exports/ export-ignore
```

### 6.7 Release 产物清单

主程序 Release(tag `v<version>`):

| 文件 | 大小(估计) | 用途 |
|---|---|---|
| `xhs-info-crawl-v<version>-macos.zip` | ~180 MB | macOS 用户包 |
| `xhs-info-crawl-v<version>-windows.zip` | ~180 MB | Windows 用户包 |
| `xhs-info-crawl-v<version>-src.zip` | ~2 MB | 开发者源码 |

OCR 增强包 Release(独立 tag `ocr-addon-<paddleocr_version>`):

| 文件 | 大小(估计) | 用途 |
|---|---|---|
| `paddleocr-addon-3.7.0-macos-arm64.zip` | ~1.5 GB | macOS Apple Silicon |
| `paddleocr-addon-3.7.0-macos-x86_64.zip` | ~1.5 GB | macOS Intel |
| `paddleocr-addon-3.7.0-windows-x64.zip` | ~1.5 GB | Windows |

OCR 增强包版本独立于主程序,可单独升级(如 paddleocr 出 3.8.0 时只发 OCR Release,不用发主程序 Release)。

## 7. 后端代码改动

### 7.1 静态文件挂载(让后端直接服务前端)

`backend/app/main.py` 启动时挂载 `frontend/dist`:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# 启动时检测 frontend/dist 是否存在(打包版有,开发版无)
# 开发模式:backend/app/main.py → parents[2] = 项目根 → frontend/dist
# 打包模式:app/backend/app/main.py → parents[2] = app/ → app/frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not FRONTEND_DIST.is_dir():
    # 打包模式 fallback:尝试 app/frontend/dist
    FRONTEND_DIST = Path(__file__).resolve().parents[2] / "app" / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
```

- 用户访问 `http://127.0.0.1:<port>/` 直接看到前端
- `/api/v1/*` 路由优先级高于静态挂载,不冲突
- 开发模式下 `frontend/dist` 不存在,不影响 `make dev-web`

### 7.2 OCR 诊断接口

新增 `backend/app/api/v1/diagnostics.py` 接口:

```python
# POST /api/v1/diagnostics/ocr
# 响应:
# {
#   "ok": true,
#   "text": "识别到的文字片段",
#   "latency_ms": 1234
# }
# 或
# {
#   "ok": false,
#   "reason": "ocr_disabled" | "paddleocr_not_installed" | "model_not_found" | "inference_failed",
#   "detail": "..."
# }
```

实现逻辑:
- 检测 `OCR_ENABLED` 环境变量,`false` 直接返回 `ocr_disabled`
- `try import paddleocr`,失败返回 `paddleocr_not_installed`
- 检测 `PADDLE_PDX_CACHE_HOME` 指向的 `official_models/` 目录存在且有模型子目录,失败返回 `model_not_found`
- 对包内测试图 `app/backend/tests/fixtures/ocr_test.png` 做识别
- 成功返回识别文字 + 耗时,失败返回 `inference_failed`

### 7.3 废弃死配置 `paddleocr_model_dir` 并修复 OCR 路径机制

**问题(审计确认)**:项目存在一个长期死配置 + 一个环境变量设置缺失:

1. **死配置**:`backend/app/core/config.py:60` 的 `paddleocr_model_dir: Path = Path("./data/models/paddleocr")`
   - `backend/app/services/paddleocr_adapter.py:15` 的 `PaddleOCR(...)` 构造函数完全没传这个参数
   - `.env.example:83`、`backend/tests/test_scaffold_contract.py:51`、`backend/tests/conftest.py:65`、`docs/paddleocr-setup.md:64` 都引用了它
   - **从项目一开始就没生效过**,只是挂着误导开发者

2. **环境变量设置缺失**:`PADDLE_PDX_CACHE_HOME` 只在 `scripts/dev-worker.sh:16` 里 `export`,Python 代码完全没设置
   - 用户直接跑 `uvicorn app.main:app` 或 `celery worker`(不走 dev-worker.sh)时,环境变量没设置
   - paddleocr 3.x 会默认用 `~/.paddlex/official_models/`,**污染用户 home 目录,违反 AGENTS.md 硬约束**
   - `HF_HOME` 同样只在 dev-worker.sh 里设置,Python 代码缺失

3. **paddleocr 3.x 实际机制**:
   - `PaddleOCR()` 构造函数不接受 `model_dir` 参数
   - 模型缓存目录由环境变量 `PADDLE_PDX_CACHE_HOME` 决定
   - 设置后模型在 `$PADDLE_PDX_CACHE_HOME/official_models/` 下

**修复(分 3 步)**:

#### 步骤 1:废弃死配置

1. 删除 `backend/app/core/config.py:60` 的 `paddleocr_model_dir` 字段
2. 删除 `.env.example:82-83` 的 `PADDLEOCR_MODEL_DIR` 配置项及注释
3. 删除 `backend/tests/test_scaffold_contract.py:51` 对 `PADDLEOCR_MODEL_DIR` 的引用
4. 删除 `backend/tests/conftest.py:65` 对 `PADDLEOCR_MODEL_DIR` 的引用
5. 更新 `docs/paddleocr-setup.md:64`,把 `PADDLEOCR_MODEL_DIR=./data/models/paddleocr` 改为说明实际机制(用 `PADDLE_PDX_CACHE_HOME`)

#### 步骤 2:在 Python 代码里设置环境变量(关键修复)

在 `backend/app/core/config.py` 的 `get_settings()` 函数里,Settings 实例化后立即设置环境变量:

```python
import os

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # 关键:在 Python 进程启动时设置环境变量,确保 paddleocr/huggingface 不污染用户 home
    # 这之前只靠 scripts/dev-worker.sh 的 export,直接跑 uvicorn/celery 时会缺失
    cache_home = str(settings.paddle_pdx_cache_home.resolve())
    hf_home = str(settings.huggingface_cache_home.resolve())
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", cache_home)
    os.environ.setdefault("HF_HOME", hf_home)
    # 确保目录存在
    settings.paddle_pdx_cache_home.mkdir(parents=True, exist_ok=True)
    settings.huggingface_cache_home.mkdir(parents=True, exist_ok=True)
    return settings
```

#### 步骤 3:新增配置字段

在 `backend/app/core/config.py` 的 `Settings` 类新增两个字段(替代死配置):

```python
# PaddleOCR 3.x 模型缓存目录(通过环境变量 PADDLE_PDX_CACHE_HOME 生效)
paddle_pdx_cache_home: Path = Field(
    Path("./data/paddlex"),
    validation_alias="PADDLE_PDX_CACHE_HOME"
)
# HuggingFace 缓存目录(paddlex 传递依赖,通过环境变量 HF_HOME 生效)
huggingface_cache_home: Path = Field(
    Path("./data/huggingface"),
    validation_alias="HF_HOME"
)
```

并在 `ensure_runtime_directories()` 方法里加入这两个目录:

```python
def ensure_runtime_directories(self) -> None:
    for path in (
        self.sqlite_path.parent,
        self.image_dir,
        self.export_dir,
        self.archive_dir,
        self.celery_folder / "queue",
        self.celery_folder / "processed",
        self.task_registry_file.parent,
        self.tmp_dir,
        self.paddle_pdx_cache_home,      # 新增
        self.huggingface_cache_home,     # 新增
    ):
        path.mkdir(parents=True, exist_ok=True)
```

#### 步骤 4:更新 .env.example

在 `PADDLEOCR_MODEL_DIR` 的位置替换为:

```env
# PADDLE_PDX_CACHE_HOME:PaddleOCR 3.x 模型缓存目录(paddleocr 通过此环境变量决定模型下载/加载位置)。
PADDLE_PDX_CACHE_HOME=./data/paddlex

# HF_HOME:HuggingFace 缓存目录(paddlex 传递依赖,预防写 ~/.cache/huggingface)。
HF_HOME=./data/huggingface
```

#### 步骤 5:paddleocr_adapter.py 不需要改

`backend/app/services/paddleocr_adapter.py` 不需要改——它本来就没用死配置,环境变量在 `get_settings()` 里设置后,`paddleocr` 库会自动读取。

**测试**:
- `backend/tests/test_config.py` 验证 `paddleocr_model_dir` 字段已删除
- `backend/tests/test_config.py` 验证 `paddle_pdx_cache_home` 和 `huggingface_cache_home` 字段存在且默认值正确
- `backend/tests/test_paddleocr_cache_env.py` 验证 `get_settings()` 调用后 `os.environ["PADDLE_PDX_CACHE_HOME"]` 和 `os.environ["HF_HOME"]` 已设置
- `backend/tests/test_scaffold_contract.py` 更新:移除 `PADDLEOCR_MODEL_DIR`,加入 `PADDLE_PDX_CACHE_HOME` 和 `HF_HOME`
- `backend/tests/test_project_internal_writes.py` 确认无新增外部路径引用

### 7.4 启动器依赖文件

新增 `launcher/requirements.txt`:

```
pywebview>=5.0,<6
fastapi>=0.115,<1
uvicorn>=0.34,<1
python-dotenv>=1.0,<2
httpx>=0.28,<1
```

启动器用便携 Python 的 venv 跑,和后端共用同一个 venv。

## 8. 测试策略

### 8.1 后端测试

| 测试文件 | 测试内容 |
|---|---|
| `backend/tests/test_static_frontend_mount.py` | 静态文件挂载:dist 存在时挂载;不存在时不影响开发模式 |
| `backend/tests/test_diagnostics_ocr_api.py` | OCR 诊断接口:OCR_ENABLED=false 返回 ocr_disabled;paddleocr 未装返回 paddleocr_not_installed;模型目录不存在返回 model_not_found;正常返回识别文字 |
| `backend/tests/test_config.py`(扩展) | `paddleocr_model_dir` 字段已删除;`paddle_pdx_cache_home` 字段存在且默认 `./data/paddlex` |
| `backend/tests/test_paddleocr_cache_env.py` | Settings 初始化后 `os.environ["PADDLE_PDX_CACHE_HOME"]` 已设置为项目内路径 |

### 8.2 启动器单元测试

| 测试文件 | 测试内容 |
|---|---|
| `launcher/tests/test_port_finder.py` | 端口探测:端口可用返回原值;被占返回下一个;全占抛异常 |
| `launcher/tests/test_env_bootstrap.py` | .env 初始化:不存在从 example 复制;端口写入;CORS 追加;SECRET_KEY 自动生成;INITIAL_ADMIN_PASSWORD 自动生成;API_HOST 强制 127.0.0.1;PADDLE_PDX_CACHE_HOME/HF_HOME 设置 |
| `launcher/tests/test_process_manager.py` | 子进程启停:mock subprocess,验证启动顺序、环境变量传递和清理 |
| `launcher/tests/test_ocr_installer.py` | OCR 安装:URL 选择按 OS/arch;磁盘不足报错;SHA256 校验失败回滚;pip install 用 --no-deps --find-links;模型解压到 `data/paddlex/official_models/` 而非 `ocr-addon/` |
| `launcher/tests/test_opencli_checker.py` | OpenCLI 测试:各种 exit code 和 stderr 分类;不记录完整 stderr |
| `launcher/tests/test_status_server.py` | 状态服务接口:各 endpoint 返回正确;不暴露密钥明文 |
| `launcher/tests/test_security.py` | 安全专项:状态服务只监听 127.0.0.1;.env 中无默认占位密钥残留;日志无 cookie/密码明文 |

### 8.3 启动器 UI 组件测试

| 测试文件 | 测试内容 |
|---|---|
| `launcher/ui/src/components/ServiceStatus.spec.ts` | 状态显示/重启按钮交互;M3 状态色(运行中=success/停止=on-surface-variant/异常=error) |
| `launcher/ui/src/components/OpenCLIPanel.spec.ts` | OpenCLI 状态 chip 显示;测试/下载按钮交互 |
| `launcher/ui/src/components/OcrPanel.spec.ts` | 安装进度显示/测试按钮;进度条 M3 Linear Progress 样式 |
| `launcher/ui/src/components/LogViewer.spec.ts` | 日志列表显示;等宽时间戳;自动滚动 |
| `launcher/ui/src/App.spec.ts` | 轮询状态/日志显示;M3 暗色主题 CSS 变量加载 |
| `launcher/ui/src/__tests__/design-tokens.spec.ts` | M3 设计令牌存在性:CSS 变量(primary/surface/on-surface/success/error/warning)已定义;间距/圆角变量已定义 |

### 8.4 E2E 测试

| 测试文件 | 测试内容 |
|---|---|
| `tests/test-launcher-startup.md` | 启动器启动 → 三个进程运行 → 打开网页 → 登录 → 看到主界面 |
| `tests/test-ocr-install-flow.md` | 启动器点安装 OCR → 下载 → 解压 → pip 装 → 测试 OCR 通过 |
| `tests/test-opencli-test-flow.md` | 启动器点测试 OpenCLI → 显示绿色 ✓ |

## 9. 文档改动

| 文件 | 改动 |
|---|---|
| `INSTALL.md` | 增加"打包版安装"章节,指向 GitHub Releases |
| `docs/deployment.md` | 增加"阶段 1.5:打包分发"章节 |
| `README-USER.md`(新建,只在打包版里) | 用户使用说明:解压→双击→装 OpenCLI→测试→打开网页 |
| `docs/TODO.md` | 增加"一键打包分发"TODO 项 |

## 10. 验收标准

1. **macOS 包**:在干净 macOS(无 Python/Node)上解压双击,启动器打开,三个进程运行,可访问前端
2. **Windows 包**:同上,在 Windows 11 上验证
3. **端口冲突**:占用 8000 后启动,自动用 8001,前端可访问
4. **OpenCLI 测试**:装好 OpenCLIApp 后点测试,显示绿色 ✓ 和版本号
5. **OCR 一键安装**:点下载安装,进度条走完,测试 OCR 显示绿色 ✓
6. **源码包**:解压后 `make init && make dev-api` 可正常开发
7. **退出清理**:关闭启动器窗口,三个子进程都被清理(pgrep 无残留)
8. **TDD 测试全通过**:`make test` + `launcher/` 下测试全绿
9. **配置独立性**:在干净系统(无 ~/.paddlex、~/.cache、~/.huggingface)上运行,这些目录不被创建;所有数据在包内 `data/` 下
10. **安全配置自动生成**:首次启动后 `.env` 中 SECRET_KEY 不为占位值;INITIAL_ADMIN_PASSWORD 不为空;首次启动弹窗显示生成的 admin 密码
11. **API 不对外暴露**:`API_HOST` 被强制为 127.0.0.1,即使 .env 被改也不生效
12. **业务配置在 Chrome 页面**:MiniMax API Key 等在主应用配置中心输入,不要求用户改 .env
13. **状态服务不泄露密钥**:`GET /status` 等接口返回的 JSON 中无 SECRET_KEY/MINIMAX_API_KEY 等明文

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| python-build-standalone 在某平台缺包 | 打包脚本先跑后端测试套件验证 |
| PyWebView 在 Windows 依赖 WebView2 Runtime | Windows 11 自带;Win10 用户提示安装 WebView2 Evergreen |
| PaddleOCR 原生库在某 OS 加载失败 | OCR 作为可选包,失败不影响主功能;启动器测试按钮给清晰错误 |
| GitHub Release 单文件 2GB 限制 | OCR 增强包约 1.5GB,在限制内;若超限则分卷 |
| 用户网络差下载 OCR 慢 | 支持断点续传;显示下载速度和预计剩余时间 |
| 启动器退出子进程残留 | 先 SIGTERM 等 5s,再 SIGKILL;启动器启动时清理上次残留 PID |

## 12. 不做的事(YAGNI)

- 不做自动更新(下个版本再加)
- 不做多语言(只中文)
- 不做安装包签名(下个版本再加,macOS notarization + Windows code signing)
- 不做 32 位 Windows 支持
- 不做 Linux 桌面包

## 13. 安全与配置独立性

### 13.1 配置独立性原则

打包版必须**完全不依赖开发环境原有的项目和工具**:

- 所有配置通过 `.env` 文件管理(已有机制,无需新增)
- 所有运行时数据(数据库、图片、导出、日志、Celery 队列)都在包内 `data/` 目录(已有机制)
- 所有临时文件在 `data/tmp/`(已有机制,`test_project_internal_writes.py` 静态扫描强制)
- PaddleOCR 缓存通过 `PADDLE_PDX_CACHE_HOME` 重定向到 `data/paddlex/`(已有机制)
- HuggingFace 缓存通过 `HF_HOME` 重定向到 `data/huggingface/`(已有机制)
- 启动器 `env_bootstrap.py` 启动时必须显式设置上述两个环境变量,确保便携 Python 运行时不污染用户 home 目录:
  ```python
  os.environ["PADDLE_PDX_CACHE_HOME"] = str(root_dir / "data" / "paddlex")
  os.environ["HF_HOME"] = str(root_dir / "data" / "huggingface")
  ```
- 启动器启动子进程时,这两个环境变量必须传递给 API/Worker/Beat 子进程(通过 `subprocess.Popen` 的 `env=` 参数)

### 13.2 敏感配置首次启动自动生成

打包版用户不会手动改 `.env`,默认值不安全。启动器首次启动(`env_bootstrap.py`)必须:

1. **SECRET_KEY**:从 `.env.example` 复制后,若值为 `replace-with-a-random-local-secret` 则自动生成 32 字节随机字符串替换
   ```python
   import secrets
   new_key = secrets.token_urlsafe(32)
   _update_env(env_path, "SECRET_KEY", new_key)
   ```

2. **INITIAL_ADMIN_PASSWORD**:若 `.env` 里为空,自动生成 12 位随机密码,写入 `.env`,并在启动器首次启动时弹窗显示给用户(仅显示一次,用户需记下)
   ```python
   import secrets, string
   alphabet = string.ascii_letters + string.digits + "!@#$%"
   password = ''.join(secrets.choice(alphabet) for _ in range(12))
   _update_env(env_path, "INITIAL_ADMIN_PASSWORD", password)
   # 启动器 UI 首次启动弹窗显示
   ```

3. **API_HOST 强制 127.0.0.1**:打包版不允许对外暴露,启动器检测 `API_HOST` 若非 `127.0.0.1` 则强制改回(防止用户误改导致局域网暴露)

### 13.3 用户在 Chrome 页面配置的项(不要求改 .env)

以下配置必须在主应用前端配置页完成,**不要求用户改 `.env`**:

| 配置项 | 配置位置 | 是否已有 |
|---|---|---|
| MiniMax API Key | 配置中心 → 系统配置 | 已有,前端有输入框 |
| 城市信息 | 配置中心 → 城市 | 已有 |
| 博主信息 | 配置中心 → 博主 | 已有 |
| 关键词组 | 配置中心 → 关键词组 | 已有 |
| 博主组 | 配置中心 → 博主组 | 已有 |
| 定时任务 | 定时任务页 | 已有 |
| 抓取参数(搜索间隔/上限等) | 配置中心 → 系统配置 | 已有 |

**启动器只管运行时配置**(端口、进程管理、OCR/OpenCLI 测试),**业务配置全在前端页面**。

### 13.4 OCR 增强包安装的安全约束

- wheel 安装用 `--no-deps --find-links <本地 wheels 目录>`,不从 PyPI 下载,避免供应链风险
- SHA256 校验失败则回滚,不执行 pip install
- pip install 目标是包内 `runtime/venv/`,不污染系统 Python

### 13.5 升级时的数据保留

- 用户解压新版包时,`data/` 目录必须保留(用户已有抓取数据)
- 启动器启动时检测 `data/app.db` 存在则跳过 `alembic upgrade head` 的 seed_admin,只跑 schema 迁移
- 启动器检测到版本号变化时(对比 `data/.app_version` 和当前版本),提示用户"数据已保留,如遇问题可查看迁移日志"

### 13.6 OpenCLI 命令兜底

- `OPENCLI_BIN` 默认 `opencli`,依赖 PATH
- 启动器测试 OpenCLI 失败且错误为 `command not found` 时,提示用户:
  > "未找到 opencli 命令。请打开已安装的 OpenCLIApp 应用,在 System 页面点击 [Install/Repair opencli command]。"
- 不在启动器里自动改 `OPENCLI_BIN`,避免猜错路径;用户可在 `.env` 手动配置绝对路径

### 13.7 启动器状态服务的访问限制

- 状态服务只监听 `127.0.0.1`,不对外暴露
- 状态服务端口(`API_PORT + 1`)不写入 CORS,仅本机 PyWebView 窗口访问
- 状态服务不要求认证(本地无敏感数据),但接口不暴露任何密钥明文(MiniMax API Key 等不返回)

### 13.8 日志脱敏

- 启动器日志面板和 `data/logs/*.log` 不能记录敏感信息
- 已有机制:`test_cookie_log_redaction.py` 强制 cookie/密码脱敏
- 启动器新增:OpenCLI 测试结果不记录完整 stderr(可能含 cookie),只记录分类结果
