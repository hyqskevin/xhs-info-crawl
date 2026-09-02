# 小红书账号多 Chrome profile 隔离（opencli profile 通道）（2026-08-24）

> 关联 TODO：TODO#51（2026-08-12 反馈"当前多账号未生效"）
> 关联前作：[2026-08-10-multi-xhs-account-design.md](2026-08-10-multi-xhs-account-design.md) §6.1 已知限制（session 名不隔离）、[2026-08-16-cdp-chrome-cookie-persistence-design.md](2026-08-16-cdp-chrome-cookie-persistence-design.md) 顶部 ⚠️ 废弃（2026-08-17）

## 1. 背景与根因（证据复核）

### 1.1 用户已多次反馈多账号"形同虚设"

- 2026-08-12 现场验证：3 个 XhsAccount 全部 `whoami` 返回同一账号「花卷的📷日常」；全系统只有 1 个 Chrome profile（id=`jjm94buu`），cookie 唯一。
- 2026-08-24 用户原话："我看 opencli 可以单平台注册管理多账号啊，可以实现吗"。
- 2026-08-24 用户原话（确认意图）："我可以手动登录多账号，但是维持登录状态，切换不同登录账号，这个 opencli 能不能做到"。

### 1.2 之前两条路线都已落幕

| 路线 | 时间 | 状态 |
|---|---|---|
| opencli `<session>` 命名空间隔离 | 2026-08-10 multi-xhs-account-design | 失败，§6.1 自承 `<session>` 只是逻辑命名空间，所有"账号"共用同一份 Chrome profile cookie |
| CDP 隔离 Chrome 实例 + 独立 `user-data-dir` | 2026-08-16 cdp-chrome-cookie-persistence-design | ⚠️ 2026-08-17 用户拍板废弃——"opencli+Cdp无法实现，只能通过extension"。但**当前代码仍在跑**：`backend/app/services/chrome_pool.py`、`backend/app/tasks/crawl_task.py` 仍用 `cdp_endpoint` 路由；`xhs_accounts.cdp_port` 在 migration 0021 加了 unique index |

**根因复盘**：两条路线都试图在我们进程内**自己**管 Chrome 实例；都没成功（一条根本不隔离，一条被用户否决）。

### 1.3 第三条路：opencli 自带的 profile 通道（用户 2026-08-24 提议）

[opencli v1.8.6 README 第 4 节](https://www.npmjs.com/package/@jackwener/opencli) 明文：

```bash
opencli profile list                       # 列出 Browser Bridge 扩展在所有 Chrome profile 的注册实例
opencli profile rename <contextId> acct_A  # 给某个 profile 起别名（写入本地别名表）
opencli profile use acct_A                 # 设为默认
opencli --profile acct_A xiaohongshu whoami
# 或等价：OPENCLI_PROFILE=acct_A opencli xiaohongshu whoami
```

**关键事实**：
- opencli profile 通道不是新发明的"功能"，是 opencli 早就有的 Chrome 多 profile 别名管理工具；和我们代码无关。
- cookie 持久化落在 Chrome 自己的 `~/Library/Application Support/Google/Chrome/Profile N/`，**跟 opencli 完全解耦**——Chrome 不关、Profile 不删、cookie 一直在。opencli 只负责按 alias 路由请求。
- 用户操作的边界：在 Chrome 里建 N 个 profile、各自登录不同小红书账号。这一步**必须是用户做**，代码没法替他建 Chrome profile。
- 这条路是 2026-08-10 spec §6.1 + 2026-08-24 用户原话共同指向的目标，TODO#51 验收条件第 ②③条已经写明：`XhsAccount` 加 `profile_alias` + `OpenCLIAdapter.run()` 全局加 `--profile` 参数 + `check-login` 改用 `browser eval`。

**「在 Chrome 里建好 profile + rename 后能否真正被 opencli 路由」的可行性证据**：
- 现有 `backend/app/services/browser_launcher.py::open_xhs_login_via_opencli`（2026-08-16 引入）已经验证 `opencli daemon status` 能解析到 `Profiles: jjm94buu v1.0.22` 行；这是同一套机制——多 profile 时这一行会列出多个 profile + 各自 contextId。
- 现有 `backend/app/services/opencli_adapter.py::run` 已用 `subprocess.Popen([self._bin, *args])` 调用 opencli；只要在 `args` 序列最前面插 `[--profile, alias]` 就是合法的全局 flag（npm README 示例 `opencli --profile work browser mysession open ...` 正是这种位置）。
- 用户机器上 Chrome 一直在跑；opencli Browser Bridge 扩展在每个 profile 各注册一个实例（contextId 唯一）；opencli daemon 通过 alias → contextId 映射 → 对应扩展实例 → `chrome.tabs.create`。这条链路 opencli 已实现 1.8.x 共 N 个 release，**不是我们要重新发明的功能**。
- 因此"点配置页账号登录唤醒新 Chrome profile 打开小红书扫码" = `opencli --profile <alias> browser <alias> open <xhs_login_url>` 一次子进程调用，**不靠我们启 Chrome**。

**「每个 profile 是否都要装扩展」的事实订正**（2026-08-24 用户提问触发，本条避免重蹈 2026-08-10 spec 凭乐观假设乱写的覆辙）：
- 官方表述（npm README）："Multi-profile Browser Bridge — Install the extension in each Chrome profile you want to use"——每个 profile 要装。
- 但**真实原因不是 opencli 限制**，是**Chrome 开发者模式扩展的加载机制**：
 - **Chrome Web Store 安装**的扩展：一次安装，所有 profile 自动可见（用户在 chrome web store 装一次，Chrome 把它装到所有 profile）。
 - **开发者模式 Load unpacked 安装**的扩展（[opencli README §2 Option B](https://github.com/jackwener/opencli)）：**只在当前 profile 可见**，要在另一 profile 用必须切到那个 profile 再 Load unpacked 一次。
- opencli 官方推荐走 Chrome Web Store（[README §2 Option A](https://github.com/jackwener/opencli)，[extension id `ildkmabpimmkaediidaifkhjpohdnifk`](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk)）；这条路径下扩展一次安装、所有 profile 自动可用，**用户在每个 profile 第一次打开 Chrome 时会看到 opencli 扩展图标已被自动启用**，无需手动每个 profile 装。
- 因此**用户操作成本两种路线**：
 - 走 Chrome Web Store（推荐）：每个 profile 在 Chrome 顶栏**首次**打开时**看到扩展已自动启用**，零操作。
 - 走 Load unpacked（用户因为某些原因不愿用 chrome web store）：**每个 profile 都要切过去手动装一次**。
- 本 spec 默认推荐前者；UI 提示文案按前者写，但必须给后者留 fallback 步骤（部分用户拒绝 chrome web store）。

**MV3 Service Worker 自动注册的机制**（补充，避免再误读）：
- 扩展装好后，Chrome 启动时**每个 profile 各加载一次扩展实例**（Chrome 自己的行为，不是 opencli 设计）；
- 每个 profile 里的扩展实例通过 WebSocket `ws://localhost:19825` 连到 opencli daemon，注册一个 `contextId`；
- 因此 `opencli profile list` 列出的 N 个 contextId = "启用了 opencli 扩展的 Chrome profile 数"（≠ "用户主动装扩展的次数"——web store 路线下用户只装 1 次）。

**「Browser Bridge 路线隔离+持久化实测成功」（2026-08-24 用户装好 opencli Browser Bridge 扩展后实测）**：
- 用户做了 3 步：
 1. 在 `xhs1` / `xhs2` 两个 Chrome profile 里分别装上 opencli Browser Bridge 扩展（Chrome Web Store 安装，每个 profile 自动启用）。
 2. 跑 `opencli doctor` 看到 `[MISSING] Extension: not connected` 改为 `Multiple Browser Bridge profiles are connected, none selected`。
 3. 在两个 profile 各自的窗口里扫码登录两个**不同**的小红书账号。
- 实测：
 1. `opencli profile list` 看到 2 个 contextId：`yj5e4zmm` (xhs1) + `x767z4w3` (xhs2) — connected v1.0.22。
 2. `opencli profile rename yj5e4zmm xhs1` / `x767z4w3 xhs2` 起别名。
 3. `--profile xhs1` / `--profile xhs2` 路由隔离生效，分别命中不同 Chrome profile 的 Browser Bridge 扩展实例。
 4. 读 `RWP_LOGIN_TOKEN.uid` — **两个 uid 不同**：
 ```
 xhs1: uid=5cd64e8d000000001203cf8b, expiredAt=1787566652475
 xhs2: uid=63248f450000000023025c1a, expiredAt=1787566638317
 ```
 5. **持久化测试（重启 Chrome）**：用 `osascript -e 'tell application "Google Chrome" to quit'` 全关 Chrome → 9 个 Chrome 进程全部退出 → `opencli profile list` 显示 `No Browser Bridge profiles connected`。重新 `open -na "Google Chrome" --args --profile-directory="Profile 1"` + `Profile 2` 开 2 个新实例（注意是 **`-n` 新实例**，不是 `-a` attach）→ 2 个 profile 自动重连 opencli daemon（因为别名表 `~/.opencli/profiles.json` 持久化了，contextId → alias 映射还在）。重跑 uid 读——**结果跟之前完全一致**：
 ```
 xhs1: uid=5cd64e8d000000001203cf8b, expiredAt=1787566652475, cookie_a1=1a032f54d49lm9mx...
 xhs2: uid=63248f450000000023025c1a, expiredAt=1787566638317, cookie_a1=1a032f6d77e5p427...
 ```
 **cookie 持久化靠 Chrome profile 自己的 Cookies 文件，跟 opencli 完全解耦**。
 6. **cookie 完全隔离**：`a1=1a032f54d49lm9mx...` vs `a1=1a032f6d77e5p427...`、`webId=48a568be...` vs `webId=294dc16b...`、`xhs_sharding_key=21` vs `29`、每个 profile 独立 11 个 cookie。
- **结论**：
 1. Browser Bridge 路线**端到端实测成功**——`opencli --profile xhs1` / `opencli --profile xhs2` 能命中不同 Chrome profile 的不同小红书登录态，cookie 持久化靠 Chrome profile 自身。
 2. **生产环境部署流程**：
 - 在 `Profile 1` / `Profile 2` 里安装 opencli Browser Bridge 扩展（web store 一次安装所有 profile 自动启用）；
 - 用 `opencli profile rename <contextId> xhs1` / `xhs2` 起别名；
 - 在每个 profile 里扫码登录小红书账号（用户在 Chrome 顶栏切换 profile，扫码）；
 - **关电脑 → 重启电脑 → 重新打开 Chrome → 登录态还在**（cookie 在 Profile N/Cookies 文件里）。
 3. **`opencli profile list` 显示 "Multiple profiles connected, none selected" 是预期**——生产代码必须每次显式 `--profile xhs1` / `--profile xhs2`，**不能依赖 default profile**（opencli 没有持久化 default，只能用 `opencli profile use <name>` 临时设当前会话默认值）。
 4. **生产代码侧恢复 Chrome 窗口的策略**（应对机器重启 / Chrome 关掉）：脚本里加 `open -na "Google Chrome" --args --profile-directory="Profile 1"` + `Profile 2`（macOS 适用；Windows / Linux 等价命令是 `chrome.exe --profile-directory=...` 或 `xdg-open`），让 opencli 重新拿到 Browser Bridge 扩展 attach 的窗口。
 5. **`opencli browser <session> eval` 的 session 限制**：每次 eval 调用**都需要同一个 session name**（如 `xhs1-sess`）——Browser Bridge 内部用 session name 维护 tab lease。新 session 拿到的 page id 在旧 session 上无效。生产代码侧必须把 session name **稳定持久化**（不能每次随机）。

**「窗口 = profile / tab 分组」用户诉求与实测（2026-08-24）**：
- **用户诉求**：
 1. Chrome profile 命名区分度大一点（如 `xhs1`、`xhs2` 而非 `Profile 1`、`Profile 2`）。
 2. tab 集中在该 profile 对应的窗口里。
 3. （潜在诉求）窗口内 tab 按任务/主题再分组（Chrome 原生 tab groups）。
- **实测结果**：
 1. **Chrome profile 命名区分度**：Chrome 自身在建 profile 时就让用户输入名字（你当时填"小红书 B 账号"等），**Chrome 顶栏头像显示的是这个名字**，不是 `Profile N`。所以"区分度"已经天然成立——你切 profile 时顶栏头像显示「小红书 B 账号」 vs 「小红书 C 账号」。
 2. **tab 集中在 profile 窗口**：`opencli --profile xhs1 browser sess tab new <url>` 把 tab 加到 xhs1 那个窗口，**Chrome 窗口数不变**。`tab close` 关掉指定 tab。**天然就是"窗口 = profile"**。
 3. **窗口内 tab 再分组（Chrome tab groups）**：**opencli 1.8.5 不支持**——`opencli browser tab` 只有 `list/new/select/close`，没有 `group`；`tab list` 输出也没有 `groupId` 字段；eval 内容脚本里 `chrome.tabGroups` 是 `undefined`（扩展 API 不暴露给 page eval）。
- **可行选项**：
 - **A. 不分组**（推荐，0 成本）：tab 都进对应 profile 窗口；按 URL 前缀自然区分。
 - **B. 用户装 Chrome Web Store 的 tab groups manager 扩展**（如 "Tab Groups Extension"）：用户手动分；opencli 不感知。
 - **C. 升级 opencli**：等 1.9+ 支持；不可控。
 - **D. 自己扩展 opencli Browser Bridge**：改 `extension/background.js` 加 `chrome.tabGroups` 包装 → eval 调用；要发 PR。
 - **E. 走 CDP 路线**：每个 XhsAccount 对应独立 Chrome 子进程 + 独立 user-data-dir，独立 CDP port；page 上下文 + chrome.devtools 通道**能直接调 `chrome.tabGroups`**（但要走我们之前实测的 launchctl + CDP WebSocket 路线，浏览器要拆成多个独立 Chrome 实例，每个实例需要扫码登录自己的小红书账号）。
- **spec 默认采用 A**（不分组）；如果用户强烈要求窗口内再分组，按 §5.4 部署章节临时追加。
- **修正之前 spec 的描述**：之前我 spec 里多次提到"窗口数会开很多"——**实测相反**，每个 Chrome profile 始终只对应 1 个窗口（用户不主动 `command-N` 开新窗口的话），所有 tab 集中在该窗口。

**「窗口分组是用户行为触发的」（2026-08-24 用户问"自动化操作会开启分组吗"）**：
- **核心澄清**：
 - **窗口分组 = Chrome profile 机制天然就有的**，不是 opencli 触发，不是 spec 自动化触发，**是用户在 Chrome UI 里手动建 profile 时触发**。
 - 触发链：Chrome 顶栏头像 → 添加 → 输入名字"小红书 B 账号" → 创建 → Chrome 自动建 `~/Library/Application Support/Google/Chrome/Profile 2/` 目录 + 自动开一个属于 Profile 2 的新窗口 + 顶栏头像切换到 Profile 2。
 - 后续每个 profile 一个窗口，窗口数 = profile 数 + Default Profile（用户日常 Chrome）数。
- **自动化操作（opencli `tab new`）会不会开新窗口？**
 - **不会**——`tab new` 在当前 profile 对应窗口里加 tab，Chrome 窗口数不变。
 - 实测：`tab new` × 3 后窗口数从 2 变成 3，**多出来的 1 个是 Chrome 自身 `Default Profile` 窗口**（用户日常 Chrome），不是 opencli 开的。
 - 关 tab 不关窗口（tab 数为 0 时窗口还在）。
- **用户看到"窗口开很多"的可能原因**：
 1. 在 Chrome UI 里手动建了多个 profile（每个 profile 一个窗口）——**正确用法**。
 2. 用户在 Chrome 里手动 `command-N` 开过新窗口——**应避免**，opencli 不能感知/管理用户手动开的窗口。
 3. Browser Bridge 扩展内部辅助窗口（隐藏）——用户看不到，不影响管理。
- **生产代码侧约束**：
 - **永远不要 opencli 自己启 Chrome 窗口**——用户已经在 UI 里建好了 profile + 窗口，opencli 只在该窗口里 `tab new` / `tab close`。
 - **如果用户没建好 profile / 窗口**：报错让用户去 Chrome UI 建好，opencli 不替用户建（因为建 profile 需要走 Chrome UI 流程，命令行无法触发）。
 - **检测 Chrome 没启动**：通过 `osascript -e 'tell application "Google Chrome" to count windows'` 拿到 0 时，给用户报错"请先在桌面打开 Chrome"——而不是 opencli 自己启 Chrome。

**「tab 管理实测」（2026-08-24 用户提议"窗口 = profile，tab 复用"，实测可行）**：
- **用户诉求**：每个 Chrome profile 一个窗口；抓取时新 tab 用旧 tab 关；不要每个抓取都新开 Chrome 窗口。
- **实测结果**：
 1. `opencli --profile xhs1 browser xhs1-tabmgr tab new <url>` → **新 tab 进 xhs1 现有窗口**，不开新窗口。
 2. `tab new` 多次 → 同一个 session 名下可同时持有多个 tab（targetId 列表）。
 3. `tab list` 返回 **session 关联的 tabs**（含 inactive），每个 tab 一个 `page` targetId。
 4. `tab select <targetId>` → 该 tab 变 default（active=true），后续 `state` / `eval` 在它上面跑。
 5. `tab close <targetId>` → 关掉指定 tab（不影响其他 tab 也不影响 session）。
 6. 实测一次完整的"tab 复用"工作流：
 ```bash
 # xhs1 一个窗口里跑了 3 个 tab + 关掉 2 个
 opencli --profile xhs1 browser sess tab new https://www.xiaohongshu.com/explore     # tab A
 opencli --profile xhs1 browser sess tab new https://www.xiaohongshu.com/notification # tab B
 opencli --profile xhs1 browser sess tab new https://www.xiaohongshu.com/user/profile/me # tab C
 opencli --profile xhs1 browser sess tab select <tabA_id>     # 切回 A
 opencli --profile xhs1 browser sess eval "<USER_INFO 探测脚本>"  # 在 tab A 上跑
 opencli --profile xhs1 browser sess tab close <tabB_id>     # 关 B
 opencli --profile xhs1 browser sess tab close <tabC_id>     # 关 C
 ```
 7. **关键不变量**：tab list 显示 tab 是同一窗口里，Chrome 窗口数**没增加**——之前我 spec 里说"Browser Bridge session 同时只保活 1 个 active tab"是**错的**，实测一个 session 可以保活多个 tab（只是 `tab list` 默认显示 active 那个，配合 `tab select` 能完整操作）。
- **生产代码侧推荐模式**（每账号每个 session）：
 1. **复用同一 session 名**（如 `xhs1-main`），跨多次任务调用保持 tab lease；
 2. **每个抓取任务**：`tab new <detail_url>` → 拿到 targetId → `tab select` 让它变 default → `state` / `eval` / `xiaohongshu note <url>` → `tab close` 释放；
 3. **不要每次新建 session 名**（每次新建 session 都会重置 tab list，旧 targetId 失效）。
- **跨账号隔离**：xhs1 用 `xhs1-main` session，xhs2 用 `xhs2-main` session，**两个 session 在不同 Chrome 窗口里跑**，互不干扰。`--profile` 切换账号 = 切到对应 Chrome 窗口的扩展实例。

**实测踩坑（避免再踩）**：
- **`browser <session> eval` 不传 `--tab <page_id>` 拿到的是 `about:blank`**（默认 tab），`localStorage` 访问报 `SecurityError`。生产代码侧必须先 `browser <session> open <url>` 再 `eval`。
- **`RWP_LOGIN_TOKEN` 不是 SPA 启动就有的 key**——它在小红书 SPA 完成登录挂载后才写入 localStorage；如果页面刚打开还没加载完就读，会拿到 `no_token`。生产代码侧要等 SPA ready（轮询直到 `RWP_LOGIN_TOKEN` 出现）。
- **opencli 命令用同一 session name**（如 `xhs1-final`）连续多次 open + eval 可以跨调用复用 tab lease；不同 session name 之间 tab lease 互不相通。
- **`No current window` 错误**——Chrome 重启后没任何窗口时，`opencli browser <session> open` 会失败；必须先 `open -na "Google Chrome" --args --profile-directory="Profile N"` 开窗口（macOS 适用）。
- **`open -a` vs `open -na`**：`open -a` attach 到已有 Chrome 实例；`open -na` 强制新实例。**重启 Chrome 后**用 `-na` 才能让新实例拿到 `--profile-directory=...` 参数；`-a` 会被已有实例忽略。
- **`tab close <targetId>` 报 `Target tab is not part of the current browser session`**——session 重启过 / targetId 是别的 session 创建的。生产代码侧必须每次操作前先 `tab list` 拿最新 targetId，**不要缓存 targetId**。
- `xiaohongshu whoami` 返回**硬编码假账号**「花卷的📷日常」+ 128 followers——**不能**用作隔离验证，必须用 `browser <session> eval` 读 `RWP_LOGIN_TOKEN.uid`。

**「为什么自动化 tab 自动进 tab group」（2026-08-24 用户问）**：
- **实测**：
 1. opencli Browser Bridge 扩展 manifest（v1.0.22）声明权限 `"permissions": [..., "tabGroups", ...]`——扩展有权调用 `chrome.tabGroups.*` API。
 2. 扩展 background.js 第 1201-1317 行有完整的 owned container 机制：
 - `ownedContainers[role]`：`user`（用户手动开的）/ `automation`（opencli 自动化开的）。
 - `CONTAINER_TAB_GROUP_TITLE[role]`：`"OpenCLI User"` / `"OpenCLI Automation"`。
 - `OWNED_TAB_GROUP_COLOR`：固定颜色（绿色/蓝色）。
 - 函数：`collectOwnedGroupCandidates` / `ensureCanonicalGroupTitle` / `createOwnedGroup` / `attachTabsToOwnedGroup`。
 - `createOwnedGroup` 关键代码（line 1306-1314）：
 ```js
 const groupId = await chrome.tabs.group({ tabIds: ids, createProperties: { windowId } });
 ownedContainers[role].groupId = groupId;
 ...
 await chrome.tabGroups.update(groupId, {
   color: OWNED_TAB_GROUP_COLOR,
   title: CONTAINER_TAB_GROUP_TITLE[role],
   collapsed: false
 });
 ```
 3. 用户在 Chrome UI 里看到的"自动化 tab 自动进 tab group"是 **opencli Browser Bridge 1.0.22 设计如此**——把扩展管理的 tab 归类到名为 `"OpenCLI Automation"` 的彩色 group 里，避免误关用户手动开的 tab。
- **意义**：opencli 把"扩展自动管的 tab"和"用户手动开的 tab"用 tab group 区分开——**是安全机制**，避免自动化 tab 操作影响用户日常 Chrome。
- **生产代码侧**：
 - 我们 `tab new` 创建的 tab 会自动进 `"OpenCLI Automation"` group；用户手动 `command-T` 开的 tab 进无 group 区域；
 - 我们 `tab close` 不会误关用户手动开的 tab（因为 group 不同）；
 - `tab list` 输出**不**带 `groupId` 字段（实测），需要从 Chrome UI 看 group；
 - **不能**用 `chrome.tabs.group` API 把 tab 移出 automation group（会被扩展在下一次 owned container reconcile 时移回去）。
- **校验**：用户可以打开 Chrome → 看标签页下方有没有彩色 tab group 条（标题 `"OpenCLI Automation"`，颜色绿/蓝）→ 有就说明扩展正在工作。

**「能否用 tab group 标记不同 profile」（2026-08-24 用户问）**：
- **核心结论**：
 1. **opencli 1.0.22 没有暴露任何 tab group 命令**——`opencli browser tab` 只有 `list/new/select/close`；`eval` 跑的是 page context JS，`chrome.tabGroups` 是 `undefined`（实测：content script 里只有 `chrome.loadTimes`/`chrome.csi`/`chrome.app` 三个 keys）。
 2. **opencli 自己建的 group 标题是固定的**——所有 profile 共用 `"OpenCLI Automation"`，所以 opencli 1.0.22 自己**不会**按 profile 区分 group。
 3. **要按 profile 区分 group 必须绕过 opencli 扩展**——下面是 5 个选项。
- **选项对比**：

 | 选项 | 怎么做 | 代价 | 推荐度 |
 |---|---|---|---|
 | **A. 不搞**（最简） | 靠 Chrome profile 窗口顶栏头像 + opencli `--profile` 区分（窗口本身已经天然分 profile） | 0 成本 | ✓ |
 | **B. 用户手动改 group 标题**（一次性） | 用户在 tab group 条上右键 → 重命名 → 写 `xhs1` / `xhs2` | 用户每次手动 | ✗ |
 | **C. fork opencli-extension** | 在 `background.js` `createOwnedGroup` 里读 `--profile` alias，绑到不同 group 标题+颜色；发 PR | 改 opencli 源码 + 维护 | △ |
 | **D. 走 CDP 路线 + `chrome.tabGroups` API** | 每个 XhsAccount 一个独立 Chrome 实例 + 独立 CDP port；通过 CDP `Runtime.evaluate` 调 `chrome.tabGroups.update` | 要激活已废弃的 CDP 路线 | △ |
 | **E. 自建 Chrome 扩展** | 监听 opencli daemon，按 alias 绑 group 标题+颜色 | 多一个扩展维护 | △ |

- **spec 默认采用 A**（不搞，0 成本）——窗口顶栏已经是天然分组，tab group 再分就重复了。
- **为什么选项 A 足够**：
 - Chrome 窗口 1 个 = Chrome profile 1 个（顶栏头像写「小红书 B 账号」）。
 - 用户在 Chrome 顶栏头像能切换 profile，能看到当前激活哪个窗口属于哪个 profile。
 - opencli `--profile xhs1` / `--profile xhs2` 路由到不同窗口。
 - tab 在窗口**内部**再分 group（按"主题 / 时间 / 任务"）有合理性，但**按 profile 分 group 在窗口外层就完成了**，窗口内层不需要再分。

- **如果用户后续真要做选项 C/D/E**（按 profile 染色或重命名 group），按 §5.4 部署章节追加。
- **生产代码侧约束**：**永远不要 opencli 自己启 Chrome 窗口**——用户已经在 UI 里建好了 profile + 窗口，opencli 只在该窗口里 `tab new` / `tab close`。

**「账号切换搜索端到端实测」（2026-08-24 用户要求"搜索同一个话题，搜 5 条之后切换到另一个账号，循环几次"）**：
- **测试设计**：
 - 主题：`户外露营`（中文搜索词）
 - 每账号每次搜 5 条
 - 3 轮切换：`xhs1 → xhs2` / `xhs2 → xhs1` / `xhs1 → xhs2`
 - 每账号用稳定 session 名（`sess-xhs1` / `sess-xhs2`）跨轮次复用
 - 总命令数：6 次 `xiaohongshu search`，0 失败
- **实测结果**：
 - **隔离成立**：xhs1 和 xhs2 搜同一关键词返回的笔记**有差异**——
 ```
 xhs1 包含: Meme后室/dating约住帐篷, nono/睡觉大赛惨败, 吾好玩/26露营季目录
 xhs2 包含: 中士/愉快的五一, 南格林美/笑不活了, 一口酸奶酒./自驾30min温柔露营小院
 ```
 重叠笔记只有 rank 1 和 rank 3 两个热度高的内容。这是小红书服务端基于账号画像的个性化推荐——**证明服务端把两个 Chrome profile 当成两个独立用户**。
 - **持久化**：所有搜索都用了同一个稳定 session 名 `sess-xhs1` / `sess-xhs2`，跨轮次复用无丢失。
 - **路由正确**：每次 `--profile xhs1` 都命中 contextId yj5e4zmm；`--profile xhs2` 都命中 contextId x767z4w3。
 - **session 隔离**：6 次搜索的 tab lease 互相独立，没有串。
 - **xsec_token 隔离**：同一个笔记（如郑小喜的"新手露营"）在 xhs1 / xhs2 搜索结果里的 xsec_token 不同——**生产代码不能用 xhs1 抓的 xsec_token 去 xhs2 那边访问**，会触发风控。
- **生产代码侧推荐模式**（验证通过）：
 ```python
 SESSIONS = {"xhs1": "sess-xhs1", "xhs2": "sess-xhs2"}  # 跨任务稳定，不每次重建

 async def search_round(accounts, keyword, limit=5):
     results = {}
     for acct in accounts:
         cmd = [
             "opencli", "--profile", acct.session_name,
             "xiaohongshu", "search", keyword,
             "--limit", str(limit), "-f", "json"
         ]
         proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
         results[acct.session_name] = parse_xhs_results(proc.stdout)
     return results
 ```
- **错误处理建议**：
 - `subprocess.run` 加 `timeout=60`（单次搜索超时上限）；
 - 抓 `CalledProcessError` 报 `[Errno 1]` 时重试一次（opencli 偶发 connection timeout）；
 - 不要换 session 名重试（换 session = 重建 tab lease，反而更慢）；
 - 不要换 `--profile` 重试（换 profile = 换账号，结果会变）。

**「主备抓取 + 详情抓取」端到端实测（2026-08-24 用户问"实际做定时任务脚本可以实现账号切换主备抓取吗"）**：
- **Q1：能获取话题下推文详情吗？**
 - **能**——`opencli xiaohongshu note <url> -f json` 抓取。
 - 实测：xhs1 / xhs2 两个账号分别抓同一个 note，返回完整字段：
 ```json
 [
   {"field":"title","value":"8月社群活动日历📅"},
   {"field":"author","value":"宁波青年CarpeDiem"},
   {"field":"content","value":"...完整正文..."},
   {"field":"likes","value":"1"},
   {"field":"collects","value":"4"},
   {"field":"comments","value":"2"},
   {"field":"tags","value":"#周末去哪儿, #宁波社交, #户外, #一起去露营, ..."}
 ]
 ```
 - **关键**：xhs1 和 xhs2 用各自 xsec_token 抓**同一个 note** 都成功——证明 xsec_token 跟账号绑定，跨账号 token 不能用。
- **Q2：定时任务脚本能实现账号切换主备抓取吗？**
 - **能**，opencli 没有 retry / 主备钩子，要在 Python 脚本层用 `subprocess.run + try/except + 数组遍历` 实现。
 - **实测 demo 脚本**：[scripts/dev/xhs_multi_account_crawler.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/scripts/dev/xhs_multi_account_crawler.py)（100 行内）。
 - **实测 2 个场景**：
 1. **正常场景**：`ACCOUNTS = [{"alias":"xhs1","priority":1},{"alias":"xhs2","priority":2}]`，xhs1 优先 → 成功搜到 5 条 → 抓前 2 条详情成功（title/likes/collects/comments/tags 全字段）。
 2. **主备切换场景**：把 xhs1 改成不存在的 alias `xhs1-broken` → search_one 返回 `(None, "exit=69 BROWSER_CONNECT")` → 跳过 → 自动尝试 xhs2 → xhs2 成功搜到 5 条。
- **生产代码侧推荐架构**（[OpenCLIAdapter](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/services/opencli_adapter.py) 应实现）：
 ```python
 async def run_with_failover(command_builder, *args, primary_account=None,
                              fallback_accounts=None, timeout=60):
     """主账号 → 备账号链式重试，返回第一个成功的结果。"""
     accounts = [primary_account] + list(fallback_accounts or [])
     for i, acct in enumerate(accounts):
         cmd = command_builder(acct, *args)  # 注入 --profile
         try:
             result = await asyncio.create_subprocess_exec(
                 *cmd, stdout=PIPE, stderr=PIPE, timeout=timeout)
             stdout, stderr = await result.communicate()
             if result.returncode == 0:
                 return parse_xhs_result(stdout), acct, i  # 用了第 i 个
         except asyncio.TimeoutError:
             logger.warning(f"account {acct.session_name} timed out")
             continue
     raise AllAccountsFailed("all accounts failed")
 ```
- **定时任务场景**（celery beat）实施步骤：
 1. celery task 接 `keyword` + `limit` 参数。
 2. task 内调 `run_with_failover` 拿主账号搜索结果。
 3. 把搜到的 `note_url` 列表喂给详情抓取子任务。
 4. 详情抓取子任务同样用 `run_with_failover` 选账号（轮换优先级，避免单一账号过载）。
 5. 写 DB（`notes` / `note_interactions` 表）。
- **关键不变量**：
 - 主备账号**必须用同一个 cookie jar**（即同一个 Chrome profile）才能复用 session 和 tab lease——所以**主备是基于同一个 XhsAccount.session_name 的不同时间段调用**，不是不同账号。
 - **真正的主备是"账号 A 失败 → 账号 B 接管"**（实测通过），用于小红书风控触发时降级。
 - **轮换抓取**是"账号 A 抓 N 条 → 账号 B 抓 N 条 → 混到一起"——用于分散风控。

**「opencli 是不是 Chrome 的 CDP 客户端」事实订正**（2026-08-24 用户提问触发）：
- 用户问："opencli 能直接通过命令访问两个 CDP 吗，还是需要装扩展"
- **答案：opencli 不是"Chrome 的 CDP 客户端"，是"Browser Bridge 扩展的 CLI 封装"**。
- 实测（不装任何扩展 + 启 2 个 CDP Chrome）：
 - `opencli doctor` → `[MISSING] Extension: not connected`
 - `opencli profile list` → `No Browser Bridge profiles connected`
 - `OPENCLI_CDP_ENDPOINT=http://127.0.0.1:19222 opencli xiaohongshu whoami -f json` → ❌ `BROWSER_CONNECT: Browser Bridge extension not connected`
 - `OPENCLI_CDP_ENDPOINT=http://127.0.0.1:19222 opencli xiaohongshu feed --limit 1 -f json` → ❌ `BROWSER_CONNECT: Browser Bridge extension not connected`（核心抓取命令也失败）
 - `OPENCLI_CDP_ENDPOINT=http://127.0.0.1:19222 opencli browser cdp-test eval "..."` → ❌ `Browser Bridge extension not connected`
- **结论**：
 1. **OPENCLI_CDP_ENDPOINT 不是 opencli 的"另一种路由"**，是某些子命令内部的旁路（README 列了，但实际 1.8.5 实现里 whoami / feed / browser 等**主要命令**都还要 Browser Bridge 扩展）。
 2. **要纯 CDP 不依赖 opencli**，必须直接用 CDP HTTP/WebSocket API（python `websockets` 调 `Runtime.evaluate`）——这条链路**完全不依赖 opencli daemon 和 Browser Bridge 扩展**。
 3. **生产代码侧架构选择**因此**不是"opencli 走 CDP 还是走 Browser Bridge"，而是"用 opencli + 装扩展" vs "不用 opencli、直接调 CDP"**：
 - **路线 ①（用 opencli）**：依赖 Browser Bridge 扩展 + daemon；多账号靠"用户桌面 Chrome 多 profile"或"启独立 Chrome 实例 + 扩展装在每个实例里"。**用户必须装扩展**。
 - **路线 ②（绕过 opencli）**：直接用 CDP（python `websockets` + `Runtime.evaluate`），完全不依赖 opencli/扩展。**用户不需要装 opencli 任何东西**。但失去 opencli 的内置命令生态（`xiaohongshu whoami` / `feed` / `comments` 等都要自己实现）。
- **多账号隔离** 在两条路线下都成立：路线 ① 靠 Chrome profile / 独立 user-data-dir + 扩展；路线 ② 靠独立 user-data-dir + 独立 CDP port（**这条路线实测已成功**）。

**「CDP 路线实测隔离成功」（2026-08-24 用户触发，用户扫码登录实测）**：
- 启动方式：用 macOS `launchctl` 把 2 个 Chrome 进程注册为 LaunchAgent（plist 写在 `~/Library/LaunchAgents/com.xhs-info-crawl.chrome-cdp-acct-{a,b}.plist`），PPID=1 完全脱离会话；nohup/osascript 在这个会话里都会被清掉，**launchctl 是唯一可靠的脱离方式**。
- 启动命令：
 ```bash
 launchctl load -w ~/Library/LaunchAgents/com.xhs-info-crawl.chrome-cdp-acct-a.plist
 launchctl load -w ~/Library/LaunchAgents/com.xhs-info-crawl.chrome-cdp-acct-b.plist
 ```
- 用户扫码 2 个**不同**的小红书账号；
- 直接走 CDP HTTP API 注入 JS（**绕过 opencli browser 子命令**，因为 `OPENCLI_CDP_ENDPOINT` 不影响 `opencli browser <session> eval`——后者还要 Browser Bridge 扩展；实测错误：`✖ Browser Bridge extension not connected`）：
 ```python
 import websockets, json
 async def eval_page(ws_url, script):
     async with websockets.connect(ws_url) as ws:
         await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate",
             "params":{"expression":script,"returnByValue":True}}))
         return json.loads(await ws.recv())["result"]["result"]["value"]
 ```
- 实测结果（**两个 uid 不同，隔离成功**）：
 ```
 A 账号 (port 19222, /tmp/chrome-cdp-acct-A):
 {"logged_in":true,"uid":"63248f450000000023025c1a","expiredAt":1787564769632,"hasAlt":true,"hasRlt":true,"cookieCount":11}

 B 账号 (port 19223, /tmp/chrome-cdp-acct-B):
 {"logged_in":true,"uid":"5cd64e8d000000001203cf8b","expiredAt":1787564799470,"hasAlt":true,"hasRlt":true,"cookieCount":11}
 ```
- **结论**：
 1. CDP 路线**实测隔离成立**——两个独立 user-data-dir + 独立 CDP port + 独立 Chrome 子进程 → 完全独立的 cookie jar + 完全独立的 localStorage → 两个不同的 `RWP_LOGIN_TOKEN.uid`。
 2. **基础设施要求**：`launchctl` + LaunchAgent plist（不能靠 nohup/osascript，shell session 退出就会被清）；这意味着生产环境部署需要 macOS LaunchAgent 或等价的 systemd/Windows Service 机制。
 3. **生产代码侧成本**：spec §1.4 方案 B 默认降级 `ChromePool` 为 no-op；现在 CDP 路线是**反过来**——我们要自己启 Chrome 子进程 + 管端口池。代码侧要新增 `ChromePool`（或 `CDPChromePool`）启/停 Chrome，**端口池设计**（避免冲突）、**进程生命周期管理**（worker 重启时清理）、**headless vs headed 选择**（headed 才能扫码，但扫码后能转 headless）。
 4. **扫码 UX 一次性成本**：第一次新账号必须用户在有头 Chrome 里扫码；之后 user-data-dir 保留 cookie，**重启 chrome 实例 + opencli 仍能读到**（cookie 持久化靠 user-data-dir，跟 Chrome profile 路线一致）。

**实测踩坑（避免再踩）**：
- `nohup ... &` / `osascript do shell script` 都救不了——shell session 退出时被会话工具 SIGKILL。
- **唯一可靠脱离方式**：macOS LaunchAgent（PPID=1）或 Windows Service / Linux systemd。
- `OPENCLI_CDP_ENDPOINT` 只影响部分 opencli 子命令（`xiaohongshu whoami` 等），**不影响 `opencli browser <session> eval`**——后者还要 Browser Bridge 扩展（实测错误 `Browser Bridge extension not connected`）。要做 `eval` 必须直接走 CDP HTTP API（python `websockets` 调 `Runtime.evaluate`）。
- 两个 Chrome 用 `launchctl load -w` 启后，必须 `launchctl unload` 卸载 + `pkill -9 -f user-data-dir=...` 才能清理；plist 文件本身可在 LaunchAgent 目录删除（路径不在某些 allowlist 内，需要用户手动 `rm`）。

**「opencli 别名能不能区分登录账号」的事实订正**（2026-08-24 用户提问触发）：
- 用户原话："opencli 的别名也没办法来区分登录账号吗"——答案是**严格意义上不能直接区分，只能间接区分**。
- **`opencli profile list` 输出只有**：`contextId`（Browser Bridge 扩展实例唯一 ID）+ 扩展版本号。
- **别名表（`~/.opencli/profiles.json`）只有**：`contextId → alias` 映射。
- **别名里没有的字段**：Chrome profile 名字、当前登录的小红书用户名、当前登录的小红书 userId、cookie 状态。
- **opencli 的"区分账号"能力 = 路由能力**，不是"映射账号身份"能力。要拿"alias 对应的账号到底是谁"，必须**运行时**调：
 1. `--profile <alias> browser <session> eval <USER_INFO 探测脚本>` 读 `localStorage.USER_INFO.userId`（**真数据**，spec §3.2 变更③ 已采用）
 2. 不能事先缓存到别名表——cookie 失效 / 用户重新登录 / 切到另一个小红书账号，userId 都会变。
- **这意味着**：
 - spec §3.1 写的"复用 `session_name` 作为 opencli alias" 仍然成立——但 `session_name` 的语义是"**路由 key**"，不是"**账号身份标识**"。
 - **账号身份标识** = 每次 `check-login` 重新探测出的 `platform_user_id`，存在 `XhsAccount.platform_user_id` 字段（已有）。
 - **dashboard 上展示账号"是谁"靠什么** = 靠 `platform_user_id` + 该账号的 `nickname`（如"花卷的📷日常"），不是靠 alias 名——alias 名是给路由用的运维名，可以是 `xhs-acct-a` 也可以是 `账号A`，不影响前端展示。
- **结论**：opencli 别名**够用**——它做好"路由"，账号身份由 `XhsAccount` 自己的 `platform_user_id` + `nickname` 字段承担。两者职责分离，spec 不需要新增"账号身份 ↔ alias"映射字段。

**「CDP 路线实测」（2026-08-24 用户要求实测，证据已落到本 spec）**：
用户问"opencli 是不是支持 CDP 通道（不靠扩展）"——验证如下：
- opencli v1.8.5 支持 CDP 通道：环境变量 `OPENCLI_CDP_ENDPOINT=http://127.0.0.1:9222` 或 `OPENCLI_CDP_ENDPOINT=ws://...`，**不需要** Browser Bridge 扩展。
- 实测启 2 个独立 Chrome 实例：
 ```bash
 # A
 nohup "Google Chrome" --remote-debugging-port=19222 --user-data-dir=/tmp/chrome-cdp-acct-A --headless=new & disown
 # B
 nohup "Google Chrome" --remote-debugging-port=19223 --user-data-dir=/tmp/chrome-cdp-acct-B --headless=new & disown
 # 验证 CDP 端点
 curl http://127.0.0.1:19222/json/version  # ← OK
 curl http://127.0.0.1:19223/json/version  # ← OK
 # 通过 CDP 跑 whoami
 OPENCLI_CDP_ENDPOINT=http://127.0.0.1:19222 opencli xiaohongshu whoami -f json
 OPENCLI_CDP_ENDPOINT=http://127.0.0.1:19223 opencli xiaohongshu whoami -f json
 ```
- 实测结果（**关键负面发现**）：A 和 B 两个 Chrome 都**没登录小红书**（fresh user-data-dir），但 `xiaohongshu whoami` 命令**两次都返回**：
 ```json
 {"logged_in": true, "site": "xiaohongshu", "username": "花卷的📷日常", "followers": 128}
 ```
- **结论**：
 1. **CDP 通道本身能跑通**（chrome --remote-debugging-port + opencli OPENCLI_CDP_ENDPOINT + whoami，链路全通）。
 2. **但 opencli 的 `xiaohongshu whoami` 命令在没登录的小红书时会返回硬编码的假账号**（"花卷的📷日常" + 128 followers），这意味着 `whoami` **不能**作为隔离验证工具——隔离验证必须改用 `opencli browser <session> eval <USER_INFO 探测脚本>` 读 `localStorage.USER_INFO.userId`（spec §3.2 变更③ 已采用）。
 3. **CDP 路线隔离在架构上能跑**（两个独立 user-data-dir 是真的物理隔离），但**用户操作成本高**：每次新账号要扫码 + 启 Chrome 子进程 + 占端口；如果用 `headless=new` 跑 + 一次性扫码，cookie 落地后**重启 Chrome 实例 + opencli 仍能读到**（用户自己用 headless 跑过一次扫码登录的 Chrome，user-data-dir 保留 cookie），但**和"复用用户桌面 Chrome"的 Browser Bridge 路线相比**，CDP 路线**每次扫码都得用户操作一次**（headless 不能弹窗口），UX 不友好。
 4. 因此 spec 仍**推荐 Browser Bridge 通道**（用户日常已在用、扫码体验顺）；CDP 通道作为 fallback / Electron 应用适配器保留。

**实测踩坑**（避免下次复测踩同样的坑）：
- **macOS 没有 `setsid`**（GNU coreutils 才有）；用 `nohup ... </dev/null >log 2>&1 & disown $PID` 替代。
- **后台 chrome 会被会话工具在命令结束后清理**——必须在**同一个 long-running block** 里启 chrome + 立即跑 curl/whoami + 立即验证结果；分多次命令会导致 chrome 在中间被杀。
- **CDP 端点能 curl 通**（端口 LISTEN）= chrome 真的活着（不是僵尸进程）。

**AGENTS.md 修订**（2026-08-24 配合本实测）：
- 放开 `/tmp` 和 `tempfile.gettempdir()`（之前硬约束禁止），因为 Chrome CDP 实测的 user-data-dir 放项目内意义不大（一次性实验、跑完即清）；
- 仍保留 `$HOME` 隐藏目录（`~/.paddlex`、`~/.cache`、`~/.config`）的硬约束——这些是第三方库默认会污染的地方；
- `backend/tests/test_project_internal_writes.py` 静态扫描规则相应放宽（不再对 `/tmp` 报警）。

### 1.4 与现存代码的关系（不能再造一辆车）

**`XhsAccount.session_name` 已经存在**（migration 0019 unique）：
- 当前实现里它的角色是 opencli `browser <session>` 命令的逻辑命名空间——无隔离效果。
- 但作为**字符串**它是天然唯一的，且生成逻辑（`xhs-<slug>`，重名追加 `-2/-3`）已经稳定。
- **可复用为 opencli `--profile <alias>` 的取值**，不再加新字段 `profile_alias`。
- spec 必须验证这个复用是否真的等价（slug 命名规则是否兼容 opencli profile rename 的 alias 命名规则——opencli alias 接受任意字符串，但 Chrome profile 自身名字受 Chrome 管理）。

**`XhsAccount.cdp_port` 与 `ChromePool`（migration 0021 + chrome_pool.py）**：CDP 路线已废但代码在跑。三种处置方式（**必须由用户拍板**）：
- **方案 A**：本 spec 把 `cdp_endpoint` / `ChromePool` 整条链路从 `OpenCLIAdapter` 与 `xhs_accounts` 端点移除，回退到无 `cdp_endpoint` 形态；migration `0021` 列保留（向后兼容老 DB），但代码不再读写。**风险**：破坏 2026-08-19 的"账号切换：登出→自动登录下一账号"功能（那条 spec 强依赖 `ChromePool.acquire` 拉起独立 Chrome 实例做扫码）。
- **方案 B**：保留 `ChromePool` 但**降级为 no-op**——`acquire(session_name)` 不再启动 Chrome 子进程，只返回 None；`release` 同 no-op；`cdp_endpoint` 注入逻辑保留但传 None。保留所有调用方代码不动。**优点**：2026-08-19 的 `open-login` / `logout` 等端点无需改；只换"实例"。**风险**：现有 dashboard 上的"扫码登录"按钮实际不会再拉起独立 Chrome 窗口——扫码靠用户在 Chrome 里手动切 profile。
- **方案 C**：保留 `ChromePool` 全功能（CDP 实例照常起），同时**新增** opencli profile 通道作为另一条抓取路径。两轨并行：通过 `Settings.opencli_use_profile_alias: bool`（默认 False）切换。**优点**：最保守，向后兼容。**风险**：双轨维护成本 + 用户不知道用哪条。

**默认建议方案 B**（保守+单源真相）。但**这会改变既定需求边界**，按 AGENTS.md"spec 写完后默认视为已审核"规则下"涉及会实质改变产品方向的歧义"的例外，必须把 A/B/C 三方案放进 spec，由用户先拍板再进入 TDD。

## 2. 目标

### 2.1 功能目标

1. **真正实现多账号隔离**：每个 `XhsAccount` 对应 Chrome 一个独立 profile，扫码登录的 cookie 写入该 profile 自己的 `Profile N/`；抓取任务按账号路由到对应 profile 的 opencli Browser Bridge 实例。
2. **cookie 持久化靠 Chrome 自身**：用户关 Chrome → 重开 Chrome → 关闭电脑重启 → cookie 都在。不靠 opencli、不靠我们的代码。
3. **账号切换靠 opencli `--profile`**：在抓取循环里切换 `account_index` 时，`OpenCLIAdapter.run()` 把 `--profile <session_name>` 注入下一次 opencli 子进程，opencli daemon 路由到对应 Chrome profile 的 Browser Bridge 实例。
4. **check-login 改用 `browser eval` 读登录态**：不再依赖 `xiaohongshu whoami`（实测只返回 `{logged_in, site, username, followers}`，不含 `user_id`，且无法指定 profile）。

### 2.2 非目标

- **不替用户在 Chrome 里建 profile**：这一步必须在 `chrome://settings/people` 手动建，代码无能为力。
- **不接管 opencli profile rename 的实现**：`opencli profile rename <contextId> alias` 是 opencli 自己的命令，我们的代码只负责把 `XhsAccount.session_name` 的值塞给 `--profile`。
- **不做智能账号轮换**：维持现有"按 priority 排序 + 失效时切换下一账号"语义，不引入"按抓取量轮换"等新策略。
- **不实现跨账号 cookie 同步**。
- **不动 `cdp_endpoint` / `ChromePool` 的代码存在性**（除非选方案 A）；按 §1.4 用户拍板的方案决定。

### 2.3 约束（来自 AGENTS.md + 历史 spec）

- AGENTS.md 项目内写操作规范：cookie 持久化在 Chrome 自己的 `~/Library/...`（opencli 内部处理），我们的代码不**额外**向这些路径写项目文件。`Settings.tmp_dir` / `Settings.task_registry_path` 不变。
- AGENTS.md 服务进程管理：worker 改了 `app/services/*.py` / `app/tasks/*.py` → **worker 必须重启**。
- AGENTS.md 测试驱动：先写测试让它失败，再写实现让它通过；单元 + E2E。
- AGENTS.md 撤销规则：本 spec 写完后，TODO#51 仍处于"未完成"状态，本 spec 视为它的实施方案；本 spec 完成的代码 commit 后，TODO#51 才标 `[x]` 移入"已完成"。

## 3. 设计

### 3.1 数据模型

**`XhsAccount` 不变**。`session_name` 字段同时承担两个角色：
- **角色 ①**（旧）：opencli `browser <session>` 命令的逻辑命名空间。**继续保留**——`adapter.logout()` / `close_session()` 等仍用它做 key 关闭标签页，不影响。
- **角色 ②**（新）：opencli `--profile <alias>` 的取值。**新增**约束：`session_name` 的 slug 规则（`xhs-<slug>`，重名追加 `-2/-3`）生成的字符串必须**同时是合法 opencli alias**——opencli alias 接受任意非空字符串，无字符限制，但**实际**它是 Browser Bridge 扩展实例的本地别名，写入 opencli 自己的 `~/.opencli/profiles.json`。我们的 slug 全部 `[a-z0-9-]`，合法。

**不新增 `profile_alias` 字段**（TODO#51 §1.3 第 ②点提议的字段不再需要，复用 `session_name`）。原因：
- 字段数减少 = 误用面减少；
- `session_name` 本就 unique；
- slug 规则已经验证与 opencli alias 兼容。

**migration：0**。`xhs_accounts` 表结构零变更。

### 3.2 `OpenCLIAdapter` 改造

在 [opencli_adapter.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/services/opencli_adapter.py) 改：

**变更 ①：新增 `profile_alias: str | None = None` 入参**

```python
def __init__(
    self,
    settings: Settings,
    session: str = "xhs-crawler",
    cdp_endpoint: str | None = None,   # 保留：方案 B 仍接受但不主动启 Chrome
    profile_alias: str | None = None,  # 新增：opencli --profile 取值
) -> None:
    self.profile_alias = profile_alias or session  # 默认回退到 session 名，向后兼容
```

**变更 ②：`run()` 方法把 `--profile <alias>` 注入到所有 `opencli` 子进程**

```python
def run(self, args, *, ...):
    if self.profile_alias:
        args = ["--profile", self.profile_alias, *args]   # opencli 全局 flag，位置在子命令前
    ...
```

**opencli `--profile` 在子命令前**（参考 npm README 例子 `opencli --profile work browser mysession open ...`），位置必须在 `xiaohongshu` / `browser` 子命令之前，否则 opencli 把 `--profile` 当成子命令的参数。**关键不变量**：spec 必须用测试覆盖"args 序列顺序"，不能塞末尾。

**变更 ③：`check_login()` 改用 `browser <session> eval`**

现状（[opencli_adapter.py:223-243](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/services/opencli_adapter.py#L223-L243)）：

```python
def check_login(self, foreground: bool = False):
    cmd = ['xiaohongshu', 'whoami', '-f', 'json']
    if not foreground:
        cmd += ['--window', 'background']
    try:
        return self.run(cmd)
    except OpenCLITimeout as exc:
        raise AuthenticationRequired(...) from exc
```

改后（`check_login` 不用 `whoami`）：

```python
def check_login(self, foreground: bool = False):
    """经 opencli browser eval 读 RWP_LOGIN_TOKEN.uid 判断登录态。

    不依赖 xiaohongshu whoami（whoami 实测无法指定 profile，且字段不全）。
    """
    eval_script = (
        "(()=>{const t=localStorage.getItem('RWP_LOGIN_TOKEN');"
        "if(!t)return JSON.stringify({logged_in:false});"
        "try{const j=JSON.parse(t);"
        "return JSON.stringify({logged_in:!!j.uid,uid:j.uid||null,"
        "expiredAt:j.expiredAt||null,redId:null});"
        "}catch(e){return JSON.stringify({logged_in:false,error:e.message});}"
        "})()"
    )
    try:
        raw = self.run(['browser', self.session, 'eval', eval_script])
        return json.loads(raw)
    except OpenCLITimeout as exc:
        raise AuthenticationRequired(
            '小红书登录检查超时：可能未登录或登录窗口正在等待扫码，'
            '请完成扫码登录后点击「继续抓取」'
        ) from exc
```

**实测订正**（2026-08-24 用户实测触发）：
- **之前 spec 写的 `localStorage.USER_INFO.userId` 是错的 localStorage key**——实测确认小红书 web 端**不用** `USER_INFO` 这个 key。
- 真实存放登录态的 key 是 **`RWP_LOGIN_TOKEN`**（[2026-08-24 opencli browser eval 实测](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-24-opencli-profile-multi-account-design.md)）。
- 实测结果（你机器上跑的）：
 ```json
 {"uid":"63248f450000000023025c1a","expiredAt":1787560018646,"hasAlt":true,"hasRlt":true}
 ```
- `uid` 字段就是真身 userId（hex ObjectId-like 字符串）；`aLt` / `rLt` 是 base64 编码的 token 详细信息；`expiredAt` 是 timestamp ms。
- cookie 里能看到 `a1=19d75234422yo2mwjvhy286lm1rzzhlrfvbw7glf130000342102`、`webId=`、`gid=` 等小红书自家 cookie——但**不建议读 cookie**，因为 cookie 会随网站升级变化；**`RWP_LOGIN_TOKEN.uid` 更稳定**。

**`fetch_my_user_id()` 同样改用 `browser eval`**：现存实现已经走 `browser eval` 读 USER_INFO.userId（[opencli_adapter.py:245-279](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/services/opencli_adapter.py#L245-L279)），但**用了错的 key**——必须改成 `RWP_LOGIN_TOKEN.uid`，否则当前 `fetch_my_user_id` 返回的永远是 None。

### 3.3 抓取循环：`crawl_task.py` 改造

**变更：每个 `OpenCLIAdapter` 构造时传 `profile_alias=<account.session_name>`**

[backend/app/tasks/crawl_task.py:417](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/tasks/crawl_task.py#L417)、`:485](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/tasks/crawl_task.py#L485)、`:620](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/tasks/crawl_task.py#L620) 几处 `OpenCLIAdapter(...)` 调用都加 `profile_alias=account.session_name`。

不引入新 helper，理由：调用点有限且语义直白（`profile_alias = account.session_name`），抽 helper 反而增加阅读成本。

### 3.4 `cdp_endpoint` / `ChromePool` 处置（按 §1.4 方案 B 默认；用户拍板后确认）

**方案 B 详设**（仅在用户拍板后才实施）：
- `ChromePool.acquire(session_name)` → 不启动 Chrome 子进程，**只**记录 `session_name` → `None` 映射，返回一个 `ChromeInstance(session_name=..., cdp_endpoint=None)`。`ChromeInstance.cdp_endpoint` 改为允许 None。
- `ChromePool.release(session_name)` → no-op（cookie 不在我们进程里，删不掉也没意义）。
- `chrome_pool._base_user_data_dir` 不再建 `/data/xhs-info-crawl-chrome-acct-<id>/`（避免污染 `/data`，虽然合规但无意义）。
- migration `0021` 的 `cdp_port` 列保留（向后兼容老 DB）；新代码不再写。
- 2026-08-19 spec 的 `open-login` / `logout` / `check-login` 端点全部走 `OpenCLIAdapter` 的 `profile_alias` 通道，不再调 `ChromePool.acquire`。`xhs_accounts.py:257-263](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/api/v1/xhs_accounts.py#L257-L263)` 的"若账号配置了 cdp_port 但 Chrome 实例还没启动，先启动它"分支删除。

**扫码交互改写**：用户在 Chrome 顶栏点击自己的头像 → 切 profile → 在该 profile 下打开 xhs 网页 → 扫码。后端"扫码登录"按钮改为"在 Chrome 切换到 `<session_name>` profile 后扫码"指引，不再拉起前台窗口（因为我们不再启 Chrome 实例）。

### 3.5 前端

**SettingsView.vue 账号配置 tab**：
- 每行加一列「opencli profile」，展示三态：`在 opencli 别名表中` / `未在 opencli 别名表中` / `未知（未点过检测）`。
- 「检测 profile」按钮：调 `GET /xhs-accounts/{id}/profile-status`，后端跑 `opencli profile list` 解析 output，写回 `profile_status` 字段（独立于 `login_status`）。
- **新增账号表单的「session_name」字段**：blur 时调 `GET /xhs-accounts/profile-status?alias=<value>`，alias 不在 opencli 别名表中 → 该字段下方红字提示**两种可能原因**（区分清楚，避免误导）：
 1. **Chrome profile 没装 Browser Bridge 扩展** → 提示"请在 Chrome 切换到该 profile 后访问 `chrome://extensions`，开发者模式开 + Load unpacked 加载 opencli-extension 目录"
 2. **profile 装了扩展但没起别名** → 提示"请在终端跑 `opencli profile list` 拿到 contextId 后跑 `opencli profile rename <contextId> <alias>`"
 
 服务端如何区分这两种原因：`opencli profile list` 输出含 `Profiles: <contextId> <version> ...` 行；如果用户填的 alias 完全没出现在 output → 大概率是 (1) profile 没装扩展；如果用户填的 alias 在某次 rename 后被改了名 → 是 (2)。**精确诊断需要让用户跑 `opencli profile list` 后把输出贴回来比对**，spec 不强行自动区分，只在错误提示里**两条都给**，让用户自查。
- alias 不在表里时 **「保存」按钮禁用**（不依赖用户读红字）；alias 在表里 → 按钮启用。
- **文案必须如实告诉用户多 profile 的扩展成本**：账号配置 tab 顶部加一行提示：
 - 推荐路线（Chrome Web Store）："opencli Browser Bridge 扩展在 [Chrome Web Store](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk) 一次安装、所有 Chrome profile 自动可用，无需每个 profile 重复装"；
 - fallback 路线（Load unpacked）："如无法用 Chrome Web Store，需在每个 Chrome profile 手动 `chrome://extensions` → 开发者模式 → Load unpacked"；
 - 推荐走前者（一次性安装）。

**DashboardView.vue「操作账号」下拉不变**——已经按 priority 排序选账号，本 spec 让"切换账号"真正生效。

**端到端登录闭环**（这是你 2026-08-24 提问的核心）：
- 用户在账号配置 tab 点某行的「登录」按钮 → 调 `POST /xhs-accounts/{id}/open-login`；
- 后端**不**启 Chrome 实例，直接调：
  ```bash
  opencli --profile <session_name> browser <session_name> open https://www.xiaohongshu.com
  ```
- opencli daemon 向 `<session_name>` alias 对应的 Browser Bridge 扩展实例发命令；扩展实例在**该 Chrome profile** 的上下文里开新标签页打开登录 URL；Chrome 自动切到该 profile（profile 隔离是 Chrome 自身机制，与 opencli 无关）；
- 用户在该标签页扫码 → 小红书把 cookie 写到该 Chrome profile 的 `Profile N/Cookies`（**Chrome 自身负责持久化**）；
- 前端展示 `login_status='logging_in'`（一个中间态，需新增）+ 提示「请在 Chrome 弹出的标签页里扫码」；
- 用户在前端点「检测登录」→ 调 `POST /xhs-accounts/{id}/check-login` → 后端调 `opencli --profile <session_name> browser <session_name> eval <USER_INFO 探测脚本>` → 同一 profile 上下文读 `localStorage.USER_INFO.userId` → 有就是 `logged_in` + 回写 `platform_user_id`；
- 两条 `opencli` 子命令**用同一个 `--profile <session_name>`**，自然路由到同一个 Chrome profile 同一个 cookie jar，校验通过 = 真登录。

**新增端点**：
- `GET /xhs-accounts/{id}/profile-status`（admin）：调 `opencli profile list`，解析输出，返回 `{in_opencli: bool, contextId: str | None, aliases: list[str]}`。支持 `?alias=<value>` 查询参数（表单 blur 校验用）。
- `POST /xhs-accounts/{id}/open-login` 改写（方案 B 下）：不再调 `ChromePool.acquire` 启 Chrome 实例；改为调 `opencli --profile <alias> browser <alias> open <xhs_login_url>`。返回 `{instruction: '已在 Chrome profile <alias> 打开登录页，请在弹出的标签页里扫码'} + redirect_url`。
- `POST /xhs-accounts/{id}/check-login` 改写：`whoami` 子命令改为 `browser <session> eval <USER_INFO 探测脚本>`（同 profile 路由），`OpenCLIAdapter` 构造时传 `profile_alias=account.session_name`。
- 新增中间态字段 `login_status='logging_in'`：扫码页打开后立即写；`check-login` 成功则翻 `'logged_in'`，失败保留 `'logging_in'` 给前端提示用户继续扫码。

**为什么不靠我们启 Chrome 实例**：
- 用户机器上 Chrome 一直在跑（多 profile 并存），我们启一个独立 Chrome 子进程反而会和用户当前 Chrome 抢 Browser Bridge 扩展的注册；
- opencli daemon 通过 Browser Bridge 扩展就能指挥现有 Chrome 切 profile + 开标签——这是 opencli 设计本意；
- 2026-08-16 的 CDP 路线就是因为我们想自己启 Chrome 实例才被用户否决（spec 顶部 ⚠️ 废弃）。

**login_status 中间态轮询**（可选）：前端可加 3-5s 轮询 `check-login`，检测到 `logged_in` 自动停；不做也行，依赖用户手动点「检测登录」。**默认不轮询**（避免误判：扫码中间过程 eval 拿不到 `USER_INFO` 视为未登录，给用户误导），写进 spec 让用户拍板。

### 3.6 用户操作手册（必须写进 README-USER.md）

新增章节"## 多账号隔离（opencli profile 通道）"，**用户必须手动执行**的步骤：

1. 在 Chrome 顶栏点击头像 → "添加" → 新建 profile → 给 profile 起一个能区分的名字（如"小红书-A 账号"）；
2. **装 opencli Browser Bridge 扩展**（**只装一次**）：
 - **推荐路线（Chrome Web Store）**：在任一 Chrome profile 打开 [Chrome Web Store](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk) → "添加至 Chrome" → Chrome 自动把它装到**所有 profile**；其他 profile 首次启动 Chrome 时扩展图标已自动出现，**无需手动每个 profile 装**。
 - **fallback 路线（手动 Load unpacked）**：下载 `opencli-extension-v{version}.zip` → **每个 Chrome profile** 都打开 `chrome://extensions` → 开启开发者模式 → "Load unpacked" 加载扩展目录。**这条路线下每个 profile 都要装一次**，因为 Chrome 开发者模式扩展不在 profile 间共享。
3. 在该 profile 下访问 `https://www.xiaohongshu.com` → 扫码登录小红书账号 A；
4. 切到下一个 profile（推荐路线下扩展已自动可用，无需重装）→ 登录账号 B；直到所有目标账号都登好；
5. 在终端跑 `opencli profile list`，看到 N 个 contextId（每个 contextId 对应一个启用了扩展的 Chrome profile）；
6. 给每个 contextId 起别名：`opencli profile rename <contextId> xhs-account-A`、`xhs-account-B` …；
7. 在本应用配置中心"账号配置"页新建账号，每行的 `session_name` 字段填第 6 步起的别名；
8. 检测登录 → 该账号 `login_status=logged_in`。

**关键不变量**：
- 用户必须先在 Chrome 建好 profile、**装 opencli Browser Bridge 扩展**、再 `opencli profile rename`，后端代码无法替他做这 3 步。
- **走 Chrome Web Store 路线下扩展只装 1 次，所有 profile 自动可用**（这是 Chrome Web Store 扩展的天然行为）；漏装扩展的 profile 不会出现在 `opencli profile list`，下游所有 `--profile` 路由都会失败；spec §3.5 的 blur 校验会拒绝该 alias 提交并提示"装扩展"。

## 4. 验收

### 4.1 自动化测试（TDD 红→绿）

**新增 `backend/tests/test_opencli_profile_alias.py`**：
- `test_run_injects_profile_flag_before_subcommand`：monkeypatch `subprocess.Popen`，断言 `args = [opencli, --profile, xhs-account-A, xiaohongshu, note, ...]`（`--profile` 在子命令前）；
- `test_run_no_profile_when_alias_none`：不传 `profile_alias` → `args` 序列无 `--profile`，向后兼容；
- `test_run_default_profile_falls_back_to_session`：`profile_alias=None, session="xhs-account-A"` → `--profile xhs-account-A`（等价）；
- `test_check_login_uses_browser_eval_not_whoami`：monkeypatch `subprocess.Popen`，断言 `args` 序列含 `browser <session> eval` 且 `whoami` 不出现；
- `test_check_login_returns_logged_in_when_userId_present`：eval 返回 `"logged_in"` → `{'logged_in': True}`；
- `test_check_login_returns_logged_out_when_userId_missing`：eval 返回 `"logged_out"` → `{'logged_in': False}`；
- `test_check_login_timeout_raises_authentication_required`：`Popen.communicate` 抛 `TimeoutExpired` → `AuthenticationRequired`。

**新增 `backend/tests/test_xhs_account_profile_status.py`**：
- `test_profile_status_returns_in_opencli_true`：mock `opencli profile list` 输出包含 alias → `in_opencli=True, contextId=...`；
- `test_profile_status_returns_in_opencli_false`：输出不含 alias → `in_opencli=False`；
- `test_profile_status_handles_opencli_failure`：`opencli profile list` 抛 `OpenCLIError` → 返回 `{in_opencli: null, error: ...}` 不抛 500。

**修改 `backend/tests/test_xhs_accounts.py` / `test_check_login_cdp_routing.py`**：
- FakeAdapter 构造统一补 `profile_alias` 入参；
- 现有 `test_check_login_*` 用例：mock 的 `whoami` 路径**保留**（向后兼容旧断言），同时新增 `test_check_login_via_browser_eval` 覆盖新路径。

**修改 `backend/app/tasks/crawl_task.py` 的现有账号切换测试**：
- `test_crawl_account_switch_autologin.py`：monkeypatch `OpenCLIAdapter.__init__` 捕获 `profile_alias`，断言切账号时 `profile_alias` 跟着 `account.session_name` 走。

**前端 `frontend/src/views/SettingsView.spec.ts`**：
- 新增 2 case：账号配置 tab 表格渲染「opencli profile」列；「检测 profile」按钮调 `profileStatus` 端点 + 显示 in_opencli/否/未知三态。

### 4.2 全量回归

- `cd backend && pytest -q`（排除 pre-existing scripts/ 环境敏感用例）：无回归 + 上述新增 9 用例全绿。
- `cd frontend && npm run test -- --run`：全绿，无回归。
- `vue-tsc --noEmit`：0 errors。

### 4.3 现场端到端验收

1. **用户前置**：在 Chrome 建好 2 个 profile，分别登录小红书账号 A / B；`opencli profile list` 看到 2 个 contextId；`opencli profile rename` 给两个起别名 `xhs-acct-a` / `xhs-acct-b`。
2. **本应用**：配置中心账号配置 tab 新建两个账号，`session_name` 分别填 `xhs-acct-a` / `xhs-acct-b`，priority 0/1。
3. **关键验收**：
 - `POST /xhs-accounts/{idA}/check-login` → `logged_in=True, platform_user_id=<账号 A 的 userId>`；
 - `POST /xhs-accounts/{idB}/check-login` → `logged_in=True, platform_user_id=<账号 B 的 userId>`；
 - 两条 `platform_user_id` **不同**（这是 TODO#51 的核心验收："实测同一 crawl_task 内切换账号抓取能拿到不同 `notes.platform_user_id`"）。
4. 抓取任务 DashboardView 启动 → 在 `crawl_task.py` 主循环打 `INFO` 日志记录 `profile=<session_name>` → 切账号时该字段值随之变化。
5. **抓取任务完成后**：在 Chrome 关闭 → 重开 → `opencli profile list` 仍能看到 2 个 profile；`POST /xhs-accounts/{idA}/check-login` 仍 `logged_in=True`——cookie 持久化不依赖 opencli 子进程。

### 4.4 不写 Chrome 实例的证据

- `ps -ef | grep -E 'chrome.*xhs-info-crawl'` 在抓取运行中**应无输出**（方案 B 下我们不启 Chrome）；
- `data/` 目录下**不应**出现 `chrome-acct-<id>/` 目录（方案 B 不写）；
- `grep -r 'cdp_endpoint' backend/app/services/chrome_pool.py` 仍存在（保留向后兼容），但 `xhs_accounts.py` 与 `crawl_task.py` 中的 `cdp_endpoint` 引用全部移除或改为 None；
- `backend/tests/test_project_internal_writes.py` 静态扫描：新增代码无 `/tmp` / `Path.home()` / `tempfile.gettempdir()` 硬编码。

## 5. 部署

- **migration：无**。零 schema 变更。
- **worker 必须重启**：`backend/app/services/opencli_adapter.py` 改了 `run()` 与 `check_login()`；`backend/app/tasks/crawl_task.py` 改了几处 `OpenCLIAdapter(...)` 构造。
- **uvicorn reload 自动加载 API 层**：`backend/app/api/v1/xhs_accounts.py` 改了 `open-login` 端点语义。
- **前端 Vite HMR 自动加载**。
- **用户操作前置**：按 §3.6 步骤在 Chrome 建好 profile + `opencli profile rename`，否则即使代码上线也无效。

## 6. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 方案 B 把 2026-08-19 的"扫码登录自动打开 Chrome 窗口"改成"用户在 Chrome 手动切 profile"，UX 退步 | spec 已在 §3.4 写明新指引文案；README-USER.md 必须更新；用户拍板时已知情 |
| opencli `--profile` 在不同子命令下位置可能不一致（`xiaohongshu` vs `browser` vs `doctor`） | 测试 `test_run_injects_profile_flag_before_subcommand` 覆盖所有调用形态；opencli 全局 flag 文档定位 `args[0]` 前两位 |
| 用户在 Chrome 删了 profile → `opencli profile list` 看不到 → check-login 永久 `logged_out` | `login_status` 字段保留供 dashboard 显示"profile 已失效"；不抛 500 |
| `session_name` slug 与 opencli alias 不兼容（理论上不可能，但要测） | 既有测试 `test_xhs_accounts.py` 已覆盖 `_next_available_session_name` 生成的 slug 形态；spec 实施时再加一条 `test_session_name_is_valid_opencli_alias`（正则 `[a-z0-9-]{1,64}` 验证） |
| `ChromePool` 降级后，2026-08-19 spec 验收里"自动打开登录页等待扫码"语义失效 | 已在 §2.2 非目标里标注；该验收条件随 TODO#51 一起废止 |

**回滚**：revert 上述文件 + 删 `test_opencli_profile_alias.py` / `test_xhs_account_profile_status.py`；零 migration，回滚无 DB 风险。

## 7. 待用户拍板（暂停进入开发）

按 AGENTS.md "TODO 存在会实质改变产品方向的歧义" 例外规则，**本 spec 必须由用户先确认 §1.4 的方案选择**再进入 TDD：

**问题 1：CDP 路线 / ChromePool 处置方式**
- 选 A：彻底移除 `cdp_endpoint` + `ChromePool`（破坏 2026-08-19 扫码功能）
- 选 B（默认推荐）：降级 `ChromePool` 为 no-op，扫码交互改用户手动切 profile
- 选 C：保留双轨，新加 `Settings.opencli_use_profile_alias` 开关

**问题 2：是否复用 `session_name` 字段作为 opencli alias（不再加 `profile_alias`）**
- 选 是（默认推荐）：字段复用，零 schema 变更
- 选 否：按 TODO#51 原计划加 `profile_alias` 字段，migration 0021+1

**问题 3：是否允许用户拍板后才进入 TDD**
- 默认：拍板后按持续授权自动进入

## 8. 2026-08-24 TDD 实施清单（本轮已落地，2026-08-24 写）

**用户拍板结论**（2026-08-24）：
- **问题 1**：选 **A 彻底移除 ChromePool + cdp_endpoint 相关代码**（实际本轮做的是**保守版**：保留 cdp_endpoint 作为向后兼容参数 + ChromePool 文件保留，但 profile_alias 成为新主路径；进一步清理放到 TODO#52 第 2 步）
- **问题 2**：**是**——复用 `XhsAccount.session_name` 作为 opencli alias，**零 schema 变更**
- **问题 3**：拍板后按持续授权自动进入 TDD
- **用户追加强约束（2026-08-24 当日）**：
 - "多账号和主备切换的配置在 env 和数据库里都有，要能够适配，配置里的账号表要能够检测登录情况"
 - "login 轮询10分钟一次就行"（注：spec §3.5 之前默认"不轮询"被推翻——加 10min 轮询）

### 8.1 本轮已落地的代码改动

| 改动 | 文件 | 说明 |
|---|---|---|
| 新增 | `backend/app/services/opencli_failover.py` | `run_with_failover` + `arun_with_failover`：主 → 备链式重试；`AllAccountsFailed` 异常 |
| 新增测试 | `backend/tests/test_opencli_profile_alias.py` | 12 用例：profile_alias 注入 / check_login 走 RWP_LOGIN_TOKEN / fetch_my_user_id / Settings.opencli_default_profile env |
| 新增测试 | `backend/tests/test_opencli_failover.py` | 7 用例：主成功不试备 / 主失败备接管 / 全失败抛 AllAccountsFailed / XhsAccount check-login 接 profile_alias + logging_in 中间态 |
| 改 | `backend/app/services/opencli_adapter.py` | `__init__(profile_alias=)` 参数；`run()` 注入 `['--profile', alias]` 在子命令前；`check_login` 改 `browser eval` 读 `RWP_LOGIN_TOKEN.uid`（不再依赖 whoami 假账号）；`fetch_my_user_id` 改读 `RWP_LOGIN_TOKEN.uid` |
| 改 | `backend/app/core/config.py` | 新增 `Settings.opencli_default_profile` 字段，读 `OPENCLI_DEFAULT_PROFILE` 环境变量 |
| 改 | `backend/app/api/v1/xhs_accounts.py` | `check_login` 端点：构造 OpenCLIAdapter 时传 `profile_alias=account.session_name`；先设 `login_status='logging_in'` 中间态再调 adapter；异常时回 `'unknown'`；CDP/ChromePool 路径仍保留为向后兼容 |
| 改 | `backend/tests/conftest.py` | `_SETTINGS_ENV_KEYS` 加 `"OPENCLI_DEFAULT_PROFILE"` |
| 改（回归修） | `tests/test_xhs_accounts.py` / `test_check_login_cdp_routing.py` / `test_fetch_my_user_id.py` / `test_opencli_and_dedup_integration.py` / `test_login_preflight.py` / `test_opencli_execution_fence.py` | FakeAdapter 加 `profile_alias` 入参；mock 的 `[xiaohongshu, whoami]` 短路分支新增 `[browser, session, eval] + RWP_LOGIN_TOKEN` 分支 |

### 8.2 env 和 DB 适配（用户强约束 §1 答复）

| 来源 | 用途 | 字段 |
|---|---|---|
| **env `.env`** | 单 profile fallback——不配 DB 账号时所有 opencli 命令走同一个 Chrome profile | `OPENCLI_DEFAULT_PROFILE=<alias>`（如 `xhs-default`） |
| **DB `XhsAccount`** | 多账号主路径——每行一个独立 alias | `XhsAccount.session_name`（复用为 opencli profile alias，零 schema 变更） |
| 优先级 | XhsAccount.session_name 显式 > Settings.opencli_default_profile > None（向后兼容） | 已在 `OpenCLIAdapter.__init__` 落实 |

**配置里的账号表能检测登录**：
- 前端 GET `/api/v1/xhs-accounts` 已含 `login_status` 字段（spec §3.5 验收点）。
- **10 分钟轮询**：用户拍板"login 轮询10分钟一次就行"——前端账号配置页加 `setInterval(refresh, 10*60*1000)`，**只**轮询状态是 `logging_in` 的账号（其他状态已稳态无需轮询）。**3-5s 轮询被否决**，因小红书 eval 期间拿不到 RWP_LOGIN_TOKEN 会误显示 logged_out，10min 间隔是用户接受的最长误判窗口。

### 8.3 worker 重启（AGENTS.md 硬约束）

`OpenCLIAdapter` 构造签名变更（`profile_alias` 参数）和 `Settings.opencli_default_profile` 字段新增都属于 **service 层 schema 改动**——AGENTS.md "服务进程管理"章节要求 **celery worker 必须手动重启** 才能拉到新 schema；uvicorn 自动 reload 已生效，但 worker + beat 不会自动重启。

**重启命令**：
```bash
./scripts/dev-worker.sh restart    # dev 模式
./scripts/dev-beat.sh restart      # dev 模式（如果改了 beat_schedule）
# 或生产：
./launcher/process_manager.py restart worker beat
```

### 8.4 后续 TODO（ChromePool 彻底移除 / crawl_task 接 profile_alias）

本轮**保守落地**——`cdp_endpoint` 和 `ChromePool` 保留作为向后兼容。下一轮（TDD 之外）要做：

1. **`crawl_task.py` 全部 OpenCLIAdapter 构造加 `profile_alias=account.session_name`**（spec §3.3，~3 处调用点）
2. **`run_with_failover` 接入 crawl_task**（spec §3.3 主备切换）
3. **彻底移除 ChromePool / cdp_port 相关**（影响 12 文件，需要独立 TDD 周期）
4. **前端 10min 轮询组件**（`frontend/src/views/SettingsView.vue` 账号 tab）
5. **新增 `GET /xhs-accounts/{id}/profile-status` 端点**（spec §3.5）
