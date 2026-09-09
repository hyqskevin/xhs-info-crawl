import json
import logging
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from app.core.config import Settings
from app.services.crawler import AuthenticationRequired, OpenCLITimeout, OpenCLIError, VerificationRequired, is_verification_required

logger = logging.getLogger(__name__)


class OpenCLIAdapter:
    def __init__(
        self,
        settings: Settings,
        session: str = "xhs-crawler",
        cdp_endpoint: str | None = None,
        profile_alias: str | None = None,
    ) -> None:
        """opencli 子进程适配器。

        Args:
            settings: 全局配置
            session: opencli browser session 名（逻辑命名空间；也是 opencli profile alias）
            cdp_endpoint: 可选 CDP 端点 URL（如 http://127.0.0.1:9223）。传了后
                所有子进程通过环境变量 OPENCLI_CDP_ENDPOINT=<endpoint> 路由到对应
                Chrome 实例，实现账号级 cookie 隔离。
                None = 用当前 Chrome Browser Bridge 默认 profile（向后兼容）。
            profile_alias: opencli --profile <alias> 路由通道（2026-08-24 加入）。
                设置后所有 run() 调用会在 cmd 前缀插入 ['--profile', <alias>]，
                路由到该 Chrome profile 的 Browser Bridge 扩展实例。
                实测 profile_alias 与 cdp_endpoint 互斥：profile_alias 已能完美隔离，
                不依赖独立 Chrome 实例（spec 2026-08-24 §3.1）。
                默认从 settings.opencli_default_profile 读取，可被 XhsAccount.session_name 覆盖。
        """
        self.settings = settings
        self.session = session
        self.cdp_endpoint = cdp_endpoint
        # 优先用显式传入的 profile_alias；否则用 settings.opencli_default_profile；
        # 都没有 → None（向后兼容：不注入 --profile）
        self.profile_alias = (
            profile_alias
            if profile_alias is not None
            else getattr(settings, "opencli_default_profile", None)
        )
        self._bin = (settings.opencli_bin or "opencli").strip() or "opencli"
        self._current_task_id: int | None = None
        self._current_run_token: str | None = None
        self._execution_guard: Callable[[], None] | None = None
        self._warning_sink: Callable[[str], None] | None = None
        self._preserve_browser_tab = False

    def bind_task(
        self,
        task_id: int,
        run_token: str | None = None,
        execution_guard: Callable[[], None] | None = None,
        warning_sink: Callable[[str], None] | None = None,
    ) -> None:
        """绑定当前抓取任务 ID；所有后续 run() 调用都会注册到 task_registry。

        用法：
            adapter.bind_task(task.id)
            ... # 所有 run() 调用都会带 task_id
        """
        self._current_task_id = task_id
        self._current_run_token = run_token
        self._execution_guard = execution_guard
        self._warning_sink = warning_sink

    def _assert_execution_active(self, enforce_execution: bool) -> None:
        if enforce_execution and self._execution_guard is not None:
            self._execution_guard()

    def _warn(self, message: str) -> None:
        try:
            if self._warning_sink is not None:
                self._warning_sink(message)
            else:
                logger.warning(message)
        except Exception:
            logger.exception("OpenCLI warning sink failed")

    def _close_browser_tab(self) -> None:
        if self._preserve_browser_tab:
            return
        try:
            self.run(
                ["browser", self.session, "close"],
                enforce_execution=False,
                timeout=10,
            )
        except Exception as exc:
            self._warn(f"浏览器标签页清理失败: {exc}")

    def _sweep_tabs(self) -> int | None:
        """关闭本会话 Chrome 实例里的所有残留标签页，保留 1 个常驻页。

        保留策略：第一个 xiaohongshu.com 页 → 无则 active 页 → 再无则第 0 个。
        保留页让下个任务的 check_login eval 直接命中（快路径），也避免
        Chrome 零页面 → No current window 循环（2026-09-04 事故）。

        Returns:
            成功关闭的标签页数量；tab list 失败或返回异常时 None（调用方回退关当前页）。
        """
        try:
            tabs = self.run(
                ["browser", self.session, "tab", "list"],
                enforce_execution=False,
                timeout=10,
            )
        except Exception as exc:
            self._warn(f"标签页清理失败（tab list 不可用，回退关闭当前页）: {exc}")
            return None
        if not isinstance(tabs, list) or not tabs:
            return None

        def _is_xhs(t: dict) -> bool:
            return "xiaohongshu.com" in str(t.get("url") or "")

        keep = next((t for t in tabs if _is_xhs(t)), None)
        if keep is None:
            keep = next((t for t in tabs if t.get("active")), tabs[0])
        keep_page = keep.get("page")

        closed = 0
        for t in tabs:
            page = t.get("page")
            if page is None or page == keep_page:
                continue
            try:
                self.run(
                    ["browser", self.session, "tab", "close", str(page)],
                    enforce_execution=False,
                    timeout=10,
                )
                closed += 1
            except Exception as exc:
                self._warn(f"关闭标签页 {page} 失败（继续清理其余）: {exc}")
        return closed

    def close_session(self) -> int | None:
        """任务结束清理：sweep 掉所有残留标签页（保留 1 个常驻页）。

        安全验证保留页（_preserve_browser_tab=True）跳过 sweep 走原关闭路径。
        tab list 不可用时回退关闭当前页。返回关闭数量（回退时 None）。
        """
        preserve = self._preserve_browser_tab
        self._preserve_browser_tab = False
        if not preserve:
            closed = self._sweep_tabs()
            if closed is not None:
                return closed
        self._close_browser_tab()
        return None

    def logout(self) -> bool:
        """登出当前账号：经 opencli browser <session> eval 清 localStorage + 全部 cookie。

        Args:
            None

        Returns:
            True 登出成功；opencli/CDP 不可用时报错被捕获，返回 False 且不抛（切换流程可安全继续）。

        经 ``run(..., enforce_execution=False)`` 执行，避免任务停止 guard 中断登出。
        """
        script = (
            "(function(){try{"
            "localStorage.clear();"
            "document.cookie.split(';').forEach(function(c){"
            "var n=c.split('=')[0].trim();"
            "document.cookie=n+'=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';"
            "});return true;}catch(e){return false;}})()"
        )
        try:
            raw = self.run(
                ["browser", self.session, "eval", script],
                enforce_execution=False,
                timeout=10,
            )
            return raw is not False and raw is not None
        except (OpenCLITimeout, OpenCLIError, AuthenticationRequired, VerificationRequired):
            logger.info("logout 失败（session=%s），忽略", self.session)
            return False
        except Exception:  # noqa: BLE001 - 登出失败不阻断切换流程
            logger.warning("logout 异常（session=%s），忽略", self.session)
            return False

    @staticmethod
    def _kill_and_reap(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()

    def _command_timeout(self) -> int:
        # Python 层超时 = opencli 内部超时 + 30 秒缓冲，缩短超时让 worker 能及时响应停止信号
        try:
            inner = int(os.environ.get('OPENCLI_BROWSER_COMMAND_TIMEOUT', '30'))
        except (TypeError, ValueError):
            inner = 30
        return max(inner + 30, 60)
    def run(
        self,
        args:list[str],
        *,
        task_id: int | None = None,
        run_token: str | None = None,
        enforce_execution: bool = True,
        timeout: int | None = None,
    ) -> Any:
        """执行 opencli 子进程命令。

        Args:
            args: opencli 子命令及参数
            task_id: 当前抓取任务 ID；如果传了，会把子进程 PID 注册到 task_registry，
                让用户点"停止抓取"时能立即 SIGTERM 当前 note。
                如果没传，使用 adapter._current_task_id（由 bind_task 设置）。
        """
        effective_task_id = task_id if task_id is not None else self._current_task_id
        effective_run_token = run_token if run_token is not None else self._current_run_token
        self._assert_execution_active(enforce_execution)
        effective_timeout = timeout if timeout is not None else self._command_timeout()
        # 构造完整命令：profile_alias 已设 → 在子命令前插 ['--profile', <alias>]
        cmd: list[str] = [self._bin]
        if self.profile_alias:
            cmd += ["--profile", self.profile_alias]
        cmd += list(args)
        # 注入 OPENCLI_CDP_ENDPOINT（如有）让 opencli 路由到指定 Chrome 实例。
        # profile_alias 通道已能完美隔离,所以 profile_alias 已设时不强制再写 CDP env;
        # 但保留二者都设的可能性（向后兼容）→ 只要 cdp_endpoint 存在就仍写 env。
        proc_env = None
        if self.cdp_endpoint:
            proc_env = {**os.environ, "OPENCLI_CDP_ENDPOINT": self.cdp_endpoint}
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=proc_env,
            )
        except FileNotFoundError:
            raise OpenCLIError(
                f"opencli 不可用：未找到命令 {self._bin!r}"
                "（请运行 npm install -g @jackwener/opencli 或在 .env 配置 OPENCLI_BIN 指向其绝对路径）"
            )
        if effective_task_id is not None:
            from app.services.task_registry import register, unregister
            register(effective_task_id, proc.pid, run_token=effective_run_token)
        try:
            try:
                self._assert_execution_active(enforce_execution)
            except Exception:
                self._kill_and_reap(proc)
                raise
            try:
                stdout, stderr = proc.communicate(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                raise OpenCLITimeout(f'opencli 命令执行超过 {effective_timeout}s 被强制终止: {args}')
        finally:
            if effective_task_id is not None:
                from app.services.task_registry import unregister
                unregister(effective_task_id, run_token=effective_run_token)
        # 子进程可能由停止接口在另一进程中 kill。此时 -9 只是停止动作的结果，
        # 必须先重新读取任务所有权，避免把正常停止误写成 OpenCLIError/FAILED。
        self._assert_execution_active(enforce_execution)
        output = (stdout or "").strip()
        error_output = (stderr or "").strip() or output
        if proc.returncode and is_verification_required(f"{output}\n{error_output}"):
            self._preserve_browser_tab = True
            raise VerificationRequired("检测到小红书安全验证，请在 Chrome 完成后点击检测登录并继续")
        if proc.returncode == 77:
            raise AuthenticationRequired('请在 Chrome 登录小红书后重试')
        if proc.returncode == 75:
            # opencli 内部命令超时；提示用户调大 OPENCLI_BROWSER_COMMAND_TIMEOUT
            stderr_str = error_output
            raise OpenCLITimeout(
                f'opencli 内部命令超时（exit 75）：{stderr_str}；可调大 .env 中的 OPENCLI_BROWSER_COMMAND_TIMEOUT'
            )
        if proc.returncode:
            stderr_str = error_output
            # opencli 在 url/参数为空时返回 "✖ Missing url"
            if 'Missing url' in stderr_str:
                raise OpenCLIError(
                    f'opencli 缺少 url 参数：{args}；请检查笔记/博主链接是否为空'
                )
            raise OpenCLIError(stderr_str)
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    def check_login(self, foreground: bool = False, timeout: int | None = None):
        """登录预检：经 browser <session> eval 读 localStorage.RWP_LOGIN_TOKEN.uid（2026-08-24 改）。

        之前用 ``xiaohongshu whoami`` 实测返回**硬编码假账号**「花卷的📷日常」(spec
        2026-08-24 §1.3 踩坑)。改读 ``RWP_LOGIN_TOKEN.uid`` —— 真小红书 SPA 的
        localStorage key,登出后被清空。

        Args:
            foreground: True 时拉起前台可见窗口,让用户扫码（API check-login 用）。
                       仅当 RWP_LOGIN_TOKEN 不存在时才有意义（提示用户去扫码）,
                       这里不强制拉前台——eval 是只读探测,不阻塞。
            timeout: 单次命令超时（秒）。诊断探测必须传短超时（≤10s），
                    否则 snapshot 会拖到 45s+ 超过前端 axios 10s 超时。
                    None = 用默认 _command_timeout()（150s）。
        """
        # RWP_LOGIN_TOKEN 是小红书 SPA 启动后才写入 localStorage 的 key,
        # 页面打开未加载完时拿不到。脚本直接读,失败由调用方决定是否重试。
        # 顺手探 hasRlt/hasAlt → 反风控能力指标（弱账号会有 hasRlt=false）
        eval_script = (
            "(function(){try{"
            "var raw=localStorage.getItem('RWP_LOGIN_TOKEN');"
            "if(!raw) return JSON.stringify({logged_in:false,reason:'no_token'});"
            "var p=JSON.parse(raw);"
            "return JSON.stringify({logged_in:true,uid:p.uid,expiredAt:p.expiredAt,"
            "hasAlt:!!localStorage.getItem('alt'),hasRlt:!!localStorage.getItem('rlt')});"
            "}catch(e){return JSON.stringify({logged_in:false,reason:'parse_err',err:String(e)});"
            "}})()"
        )
        # eval-first 设计（2026-09-03 简化）：直接 eval 读 localStorage，
        # - 返回 logged_in → 完事（1 条命令，1-2s，最快路径）
        # - 返回 parse_err（about:blank 等非小红书源，SecurityError 被 eval 内部 catch）
        #   → open 页面 + wait + 重 eval + close 我们开的 tab
        # - 返回 no_token（页面对但 SPA 未挂载完）→ 等 2s 重 eval
        # - 抛 OpenCLIError（如 No current window：所有 tab 已关，无页面上下文）
        #   → 同 parse_err，open 页面重 eval
        # 不再用 state 预检（省 1-3s，且少一条命令）。
        # open 的 tab **保留不关**：作为账号常驻小红书页，后续检测 eval 直接命中，
        # 避免反复开关 tab（2026-09-04 现场：close 导致 Chrome 零页面 → No current window 循环）。
        eval_timeout = max(1, (timeout or 8) - 3) if timeout is not None else None
        # 诊断探测（timeout≤8）时 wait 缩短到 1s；抓取任务用默认 2s
        wait_seconds = "1" if timeout is not None and timeout <= 8 else "2"

        def _open_page_and_wait() -> None:
            # foreground：确保有活动窗口（No current window 场景需要建立页面上下文），
            # 且用户本就要在登录页扫码
            # 打开账号 session 的页面（不是默认 session），foreground=True 时拉前台
            window_mode = "foreground" if foreground else "background"
            self.run(["browser", self.session, "open", self.settings.xhs_login_url, "--window", window_mode], timeout=timeout)
            self.run(["browser", self.session, "wait", "time", wait_seconds], timeout=timeout)

        try:
            try:
                raw = self.run(["browser", self.session, "eval", eval_script], timeout=eval_timeout)
                # parse_err = 页面不在小红书源（about:blank 或其他）→ 打开页面再读
                if isinstance(raw, dict) and raw.get("reason") == "parse_err":
                    _open_page_and_wait()
                    raw = self.run(["browser", self.session, "eval", eval_script], timeout=eval_timeout)
                elif isinstance(raw, dict) and raw.get("reason") == "no_token":
                    # no_token = 页面对但 SPA 未挂载完 → 等 2s 重 eval 一次
                    self.run(["browser", self.session, "wait", "time", "2"], timeout=timeout)
                    raw = self.run(["browser", self.session, "eval", eval_script], timeout=eval_timeout)
            except OpenCLIError as exc:
                # No current window（所有 tab 已关 / 零窗口坏实例）→ open 也不可靠，
                # 转为登录异常，让用户点「扫码登录」走 open_login 的健康检查+重启链路
                raise AuthenticationRequired(
                    '浏览器实例状态异常（无可用页面），请点「扫码登录」重启 Chrome 实例后重新登录'
                ) from exc
        except OpenCLITimeout as exc:
            # 扩展未响应 / 页面未打开过 SPA → 同归为未登录
            raise AuthenticationRequired(
                '小红书登录检查超时：可能未登录或 session 未打开小红书页面,'
                '请打开小红书并完成扫码后点击「继续抓取」'
            ) from exc
        # run() 解析失败时返字符串,解析成功时返 dict
        if isinstance(raw, dict):
            # 兼容:把 uid 映射成 user_id（与 fetch_my_user_id 输出同名,调用方少一层 .get("uid")）
            if "uid" in raw and "user_id" not in raw:
                raw = {**raw, "user_id": raw["uid"]}
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    if "uid" in parsed and "user_id" not in parsed:
                        parsed = {**parsed, "user_id": parsed["uid"]}
                    return parsed
                return {"logged_in": False, "reason": "eval_unexpected_type"}
            except Exception:
                return {"logged_in": False, "reason": "eval_unparseable"}
        return {"logged_in": False, "reason": "unexpected_payload"}

    def fetch_my_user_id(self) -> str | None:
        """从浏览器 localStorage.RWP_LOGIN_TOKEN.uid 提取当前登录账号的 user_id。

        2026-08-24 改:从 USER_INFO.userId（实测不存在于真实小红书 SPA）改为
        RWP_LOGIN_TOKEN.uid —— 小红书 SPA 登录挂载后写入 localStorage 的真实 key,
        登出后被清空。24 位 hex。

        行为：
        - 成功 → 返回 user_id 字符串
        - RWP_LOGIN_TOKEN 不存在 / 未登录 / CDP 关闭 / 解析失败 → 返回 None（不抛错）
        """
        # RWP_LOGIN_TOKEN.uid 直接是字符串,不加 JSON.stringify → opencli 把 stdout
        # 当 JSON 解析,字符串会被 json.loads 成 Python str。
        eval_script = (
            "(function(){try{"
            "var raw=localStorage.getItem('RWP_LOGIN_TOKEN');"
            "if(!raw) return '';"
            "return (JSON.parse(raw)||{}).uid||'';"
            "}catch(e){return '';}"
            "})()"
        )
        try:
            raw = self.run(["browser", self.session, "eval", eval_script])
        except (OpenCLITimeout, OpenCLIError) as exc:
            logger.info("fetch_my_user_id eval 失败,跳过 user_id 落库: %s", exc)
            return None
        if raw is None or raw == "":
            return None
        if isinstance(raw, str):
            user_id = raw.strip().strip('"').strip()
        else:
            user_id = str(raw).strip()
        if not user_id:
            return None
        # 启发式:小红书 user_id 是 24 位 hex;允许 hex / 字母数字 / 长度 16~64
        if not (16 <= len(user_id) <= 64) or not re.match(r"^[A-Za-z0-9]+$", user_id):
            logger.info("fetch_my_user_id 拿到非用户 ID 格式 (%r),跳过", user_id)
            return None
        return user_id
    @staticmethod
    def normalize_note(value:Any)->dict[str,Any]:
        if isinstance(value,dict): return value
        if isinstance(value,list) and all(isinstance(row,dict) and 'field' in row for row in value):
            return {str(row['field']):row.get('value') for row in value}
        raise OpenCLIError(f'unexpected note response: {type(value).__name__}')
    def _click_filter_option(self,text:str) -> None:
        target=json.dumps(text,ensure_ascii=False)
        script=f"""(() => {{ const targetText={target}; const span=[...document.querySelectorAll('.filter .tags span')].find(e=>e.textContent?.trim()===targetText); const option=span?.closest('.tags'); if(!option) return false; option.click(); return true }})()"""
        if not self.run(['browser',self.session,'eval',script]): raise OpenCLIError(f'filter option not found: {text}')
    def _open_filter_panel(self) -> None:
        probe="""(() => { const optionExists=[...document.querySelectorAll('.filter .tags span')].some(e=>e.textContent?.trim()==='最新'); return optionExists })()"""
        for _ in range(3):
            self.run(['browser',self.session,'click','.search-layout__top .filter'])
            self.run(['browser',self.session,'wait','time','1'])
            if self.run(['browser',self.session,'eval',probe]): return
        raise OpenCLIError('filter option not found: 最新')
    def search_recent(self,query:str,recent_filter:str='一周内')->list[dict[str,Any]]:
        if not query or not query.strip():
            raise OpenCLIError(f'search_recent: 查询关键词为空（query={query!r}）')
        # 前端文案 "当天" 对应小红书的 "一天内"（搜索面板无"当天"按钮）
        _FILTER_ALIAS = {'当天': '一天内'}
        actual_filter = _FILTER_ALIAS.get(recent_filter, recent_filter)
        self.check_login(); url=f'https://www.xiaohongshu.com/search_result?keyword={quote_plus(query)}'
        try:
            self.run(['browser',self.session,'open',url,'--window','background'])
            self.run(['browser',self.session,'wait','time','2'])
            self._open_filter_panel(); self._click_filter_option('最新')
            if recent_filter != '不限': self._click_filter_option(actual_filter)
            self.run(['browser',self.session,'wait','time','2'])
            script=r"""(() => Array.from(document.querySelectorAll('section')).map(s => { const links=[...s.querySelectorAll('a[href*="/search_result/"]')]; const title=s.querySelector('a[href*="/search_result/"] span')?.textContent?.trim(); const time=[...s.querySelectorAll('div')].map(x=>x.textContent?.trim()).find(x=>/^(\d+分钟前|\d+小时前|\d+天前|\d{2}-\d{2})$/.test(x||'')); return title&&links[0]?{title,url:new URL(links[0].getAttribute('href'),location.origin).href,published_text:time||''}:null }).filter(Boolean))()"""
            previous=0; stagnant=0; items=[]
            for _ in range(self.settings.xhs_search_scroll_max_rounds+1):
                items=self.run(['browser',self.session,'eval',script]) or []
                if len(items)>=self.settings.xhs_search_target_count: break
                stagnant=stagnant+1 if len(items)<=previous else 0
                if stagnant>=self.settings.xhs_scroll_stagnant_rounds: break
                previous=len(items); self.run(['browser',self.session,'scroll','down','--amount',str(self.settings.xhs_scroll_pixels)]); self.run(['browser',self.session,'wait','time','1'])
            return items[:self.settings.xhs_search_target_count]
        finally:
            self._close_browser_tab()
    def note(self,url:str)->dict[str,Any]:
        if not url or not url.strip():
            raise OpenCLIError(f'note: 笔记 url 为空，无法抓取详情')
        self.check_login()
        try:
            self.run(['browser',self.session,'open',url,'--window','background'])
            self.run(['browser',self.session,'wait','time','2'])
            previous=0; stagnant=0
            for _ in range(self.settings.xhs_detail_scroll_max_rounds):
                height=int(self.run(['browser',self.session,'eval','document.documentElement.scrollHeight']) or 0)
                stagnant=stagnant+1 if height<=previous else 0
                if stagnant>=self.settings.xhs_scroll_stagnant_rounds: break
                previous=height
                self.run(['browser',self.session,'scroll','down','--amount',str(self.settings.xhs_scroll_pixels)])
                self.run(['browser',self.session,'wait','time','1'])
            return self.normalize_note(self.run(['xiaohongshu','note',url,'-f','json','--window','background']))
        finally:
            self._close_browser_tab()
    def blogger_notes(self, username: str, profile_url: str = "") -> list[dict[str,Any]]:
        """博主笔记抓取：通过 user 命令拿带 xsec_token 的完整 URL。

        Args:
            username: 博主的用户名（返回结果中使用）
            profile_url: 博主主页 URL，从中提取 user-id（必填）

        Returns:
            list of {"title": str, "url": str, "author": str}，url 必须带 xsec_token

        Raises:
            OpenCLIError: xsec_token 注入失败（重试 3 次仍全缺）时抛错，避免静默返 0。
        """
        if not profile_url or not profile_url.strip():
            raise OpenCLIError(f'blogger_notes: profile_url 为空，跳过该博主')
        match = re.search(r'/user/profile/([^/?]+)', profile_url)
        if not match:
            raise OpenCLIError(f'blogger_notes: 无法从 profile_url 提取 user-id: {profile_url}')
        user_id = match.group(1)
        self.check_login()
        # 先打开博主主页（about:blank 状态下 xiaohongshu user 会被小红书风控拒绝）
        self.run(['browser', self.session, 'open', profile_url, '--window', 'background'])
        self.run(['browser', self.session, 'wait', 'time', '2'])

        notes: list[dict[str, Any]] = []
        last_total = 0
        last_without_token = 0
        # 最多重试 3 次（首次 + 2 次重试），让 opencli 有机会在 tab 暖好后注入 xsec_token
        for attempt in range(1, 4):
            results = self.run(['xiaohongshu', 'user', user_id, '-f', 'json', '--window', 'background']) or []
            notes = []
            without_token = 0
            for item in results:
                url = (item.get('url') or '').strip()
                if not url:
                    continue
                if 'xsec_token' not in url:
                    without_token += 1
                    continue
                notes.append({
                    'title': (item.get('title') or '博主笔记').strip(),
                    'url': url,
                    'author': username.strip() if username else '',
                })
            last_total = len(results)
            last_without_token = without_token
            logger.warning(
                "blogger_notes user_id=%s attempt=%d total=%d with_token=%d without_token=%d",
                user_id, attempt, last_total, len(notes), without_token,
            )
            if notes:
                break
            # 0 条带 token：可能是风控 / token 未注入 → 等长一点再重试
            if attempt < 3:
                self.run(['browser', self.session, 'wait', 'time', '3'])

        if not notes:
            # 区分"博主真没笔记"和"抓不到"：opencli 返回 0 条时不报错；返回 N 条但全没 token 视为抓取失败
            if last_total > 0 and last_without_token == last_total:
                raise OpenCLIError(
                    f'blogger_notes: opencli 返回 {last_total} 条但全部缺少 xsec_token，'
                    f'user_id={user_id} profile_url={profile_url}。'
                    f'可能是被风控拒绝 / xsec_token 注入失败。'
                )
            # opencli 真的返回 0 条 —— 博主本身可能没笔记，正常返回空
            return []
        return notes[:self.settings.xhs_search_target_count]
    def download(self,url:str,output_dir:Path)->list[Path]:
        if not url or not url.strip():
            raise OpenCLIError(f'download: 笔记 url 为空，无法下载图片')
        self.check_login(); output_dir.mkdir(parents=True,exist_ok=True)
        before={path.resolve() for path in output_dir.rglob('*') if path.is_file()}
        self.run(['xiaohongshu','download',url,'--output',str(output_dir),'-f','json','--window','background'])
        suffixes={'.jpg','.jpeg','.png','.webp','.bmp'}
        return sorted(path for path in output_dir.rglob('*') if path.is_file() and path.resolve() not in before and path.suffix.lower() in suffixes)
