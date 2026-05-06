"""playwright 浏览器自动化封装：登录拿 cookies / headless 跑爬虫页面 / cookies 健康检查。

paimon 全项目共用。playwright 是必装依赖（pyproject.toml dependencies 里）。
chromium 二进制需手动一次：`playwright install chromium`。

主要 API：
- LoginSession 类：单次扫码登录的 stateful 会话（webui 扫码区用）
- is_cookies_valid()：headless 跑一次健康检查
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from loguru import logger

from .site_cookies import COOKIES_BASE, cookies_exists, cookies_path

# 各站登录配置：登录 URL + 登录成功 cookie 名 + 显示名 + QR 元素 selector 列表
# qr_selectors 按顺序试，命中第一个就只截那部分；全部 miss 才 fallback 整页
# 后续加新站点直接在这里追加；selector 不准确没关系，会回退到通用候选
_GENERIC_QR_SELECTORS = ["canvas", "img[src*='qr']", "img[alt*='二维码']", "img[alt*='扫码']"]

SITE_CONFIG: dict[str, dict] = {
    "zhihu": {
        "display_name": "知乎",
        "login_url": "https://www.zhihu.com/signin?next=%2F",
        "success_cookie": "z_c0",
        "qr_selectors": [".SignContainer-qrcode", "[class*='QrCode']", "[class*='Qrcode']"],
    },
    "weibo": {
        "display_name": "微博",
        "login_url": "https://weibo.com/login.php",
        "success_cookie": "SUB",
        "qr_selectors": [".qrcode_box", ".LoginCard_pic_3i6_M", ".qr-pic"],
    },
    "tieba": {
        "display_name": "贴吧",
        "login_url": "https://passport.baidu.com/v2/?login&u=https%3A%2F%2Ftieba.baidu.com%2F",
        "success_cookie": "BDUSS",
        "qr_selectors": [".tang-pass-userlogin-qrcode", "#TANGRAM__PSP_3__qrcodeImg", ".qrcode-img"],
    },
    "hupu": {
        "display_name": "虎扑",
        "login_url": "https://passport.hupu.com/pc/login",
        "success_cookie": "u",
        "qr_selectors": [".qr-code", ".qrcode", ".scan-login"],
    },
    "taptap": {
        "display_name": "TapTap",
        "login_url": "https://www.taptap.cn/login",
        "success_cookie": "_xsrf",
        "qr_selectors": [".tap-login-qr", ".qr-code", ".qrcode"],
    },
    "xhs": {
        "display_name": "小红书",
        "login_url": "https://www.xiaohongshu.com/explore",
        "success_cookie": "web_session",
        "qr_selectors": [".qrcode-img", ".login-qrcode", "[class*='qrcode']"],
        # explore 页登录浮层默认手机号 tab，需 click 切到扫码 tab；selector 候选试错命中第一个就 click
        "qr_tab_selectors": ["text=扫码登录", "text=二维码登录", "text=扫一扫", "[class*='qrcode-tab']", "[class*='qr-tab']"],
    },
}

# SMS 验证页常见 selector 候选（猜测，云端验证后回填）：
# - 表单出现判定：任一命中即视为进入 SMS 验证页
# - 「获取验证码」按钮：扫码后 best-effort click 一次，自动发短信场景下 click 无害
# - 验证码输入框：用户提交时 page.fill 写入
# - 提交按钮：fill 后 click
_SMS_FORM_DETECT_SELECTORS = [
    "input[placeholder*='验证码']",
    "input[placeholder*='短信']",
    "input[name*='verify']",
    "input[name*='code']",
]
_SMS_GET_BUTTON_SELECTORS = [
    "text=获取验证码",
    "text=发送验证码",
    "text=重新发送",
]
_SMS_CODE_INPUT_SELECTORS = [
    "input[placeholder*='验证码']",
    "input[placeholder*='短信']",
    "input[name*='verify']",
    "input[name*='code']",
]
_SMS_SUBMIT_SELECTORS = [
    "#login-btn",                  # 小红书登录浮层提交按钮的实测 ID（log 已确认）
    "button:has-text('登录')",
    "button:has-text('确定')",
    "button:has-text('提交')",
    "[type='submit']",
]


async def _capture_qr(page, qr_selectors: list[str]) -> bytes:
    """尽力只截 QR 区域；selector 全部 miss 才 fallback 到整页截图。

    selector 试 site 配置 → 通用候选 → 整页。
    """
    candidates = list(qr_selectors) + _GENERIC_QR_SELECTORS
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            count = await loc.count()
            if count == 0:
                continue
            # 等元素可见 + 渲染完
            try:
                await loc.wait_for(state="visible", timeout=2000)
            except Exception:
                pass
            shot = await loc.screenshot()
            if shot and len(shot) > 800:   # 太小（几十字节）肯定是空 canvas，跳过
                logger.debug("[浏览器·QR] 命中 selector: {}", sel)
                return shot
        except Exception as e:
            logger.debug("[浏览器·QR] selector {} 失败: {}", sel, e)
            continue
    logger.warning("[浏览器·QR] 所有 selector 未命中，fallback 整页截图")
    return await page.screenshot(full_page=False)


def _import_playwright():
    """playwright 是必装依赖；导入失败说明 chromium 二进制没 install。"""
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright 未就绪。在 paimon 根目录运行：\n"
            "  pip install -e .\n"
            "  playwright install chromium\n"
            "（国内：export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/）"
        ) from e


# ─────────────────────────────────────────────────────────────
# LoginSession：单次扫码登录的 stateful 会话
# ─────────────────────────────────────────────────────────────

class LoginSession:
    """单次扫码登录会话。

    生命周期：
        new → start() 起后台 task → status='baseline'（拍匿名 cookies 名集合做 baseline，避免用户抢跑把登录后 cookie 吃进 baseline）
            → status='qr_ready' + qr_image → 用户扫码
            ↳ 直接登录态：检测 success_cookie 出现且不在 baseline → status='success' + cookies 落盘
            ↳ 风控 SMS 路径（如云端 IP 登 xhs）：检测 SMS 表单 → status='awaiting_sms' + sms_form_image
                → 用户在 webui 输入验证码调 submit_sms() → status='sms_submitting'
                → 后端 fill+click → 5s 后再判 web_session：成功 success；失败回 awaiting_sms 让用户重试
            或 status='timeout' / 'failed'

    用法：
        sess = LoginSession('zhihu')
        await sess.start()
        # webui 轮询 sess.status / sess.qr_image
    """

    REFRESH_QR_EVERY_SEC = 5      # QR 截图刷新间隔
    DEFAULT_TIMEOUT = 300         # 等待用户扫码总超时（秒）

    def __init__(self, site: str, *, timeout_seconds: int | None = None):
        if site not in SITE_CONFIG:
            raise ValueError(f"未知站点 '{site}'，支持：{list(SITE_CONFIG.keys())}")
        cfg = SITE_CONFIG[site]
        self.session_id: str = uuid.uuid4().hex[:12]
        self.site: str = site
        self.display_name: str = cfg["display_name"]
        self.login_url: str = cfg["login_url"]
        self.success_cookie: str = cfg["success_cookie"]
        self.timeout_seconds: int = timeout_seconds or self.DEFAULT_TIMEOUT
        self.started_at: float = time.time()
        # pending / baseline / qr_ready / awaiting_sms / sms_submitting / success / timeout / failed
        self.status: str = "pending"
        self.qr_image: Optional[bytes] = None
        self.sms_form_image: Optional[bytes] = None  # SMS 验证页截图（前端在 awaiting_sms 时显示）
        self.error: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._sms_code: Optional[str] = None         # 用户提交的验证码，主循环 consume 后清空

    async def start(self) -> None:
        """启动后台 task，立即返回；调用方继续轮询 self.status。"""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """playwright 主流程：起 chromium → 截 QR → 轮询 cookies → 落盘。"""
        try:
            apw = _import_playwright()
        except RuntimeError as e:
            self.status = "failed"
            self.error = str(e)
            return

        COOKIES_BASE.mkdir(parents=True, exist_ok=True)
        try:
            async with apw() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={"width": 720, "height": 900},
                        user_agent=(
                            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        ),
                        locale="zh-CN",
                    )
                    # 反检测：navigator.webdriver
                    await context.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    )
                    page = await context.new_page()
                    await page.goto(self.login_url, wait_until="domcontentloaded", timeout=20_000)
                    # 等 JS 加载 QR：networkidle 等所有请求完成（最多 8s）
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8_000)
                    except Exception:
                        pass  # networkidle 等不到就拉倒，反正下面还会刷
                    # 再 buffer 1.5s 留给 QR 异步渲染
                    await asyncio.sleep(1.5)
                    qr_selectors = SITE_CONFIG[self.site].get("qr_selectors", [])

                    # 部分站点登录浮层默认非扫码 tab（如 xhs explore 默认手机号），先 click 切到扫码 tab
                    qr_tab_selectors = SITE_CONFIG[self.site].get("qr_tab_selectors", [])
                    for sel in qr_tab_selectors:
                        try:
                            loc = page.locator(sel).first
                            if await loc.count() > 0:
                                await loc.click(timeout=3000)
                                logger.info("[浏览器·登录] {} 切到扫码 tab selector={}", self.site, sel)
                                await asyncio.sleep(1.0)   # 等 tab 切换动画
                                break
                        except Exception as e:
                            logger.debug("[浏览器·登录] {} tab selector {} 失败: {}", self.site, sel, e)

                    # baseline 先拍稳：先把"匿名状态 cookies 名集合"拍下来再暴露 QR
                    # 顺序很关键：以前是先 status='qr_ready' → 再拍 baseline，前端立刻显示 QR
                    # 用户秒扫导致登录后产生的 z_c0/web_session 等关键 cookie 被吃进 baseline
                    # 现在改成先 baseline → 拍 QR → status='qr_ready'，前端在此之前显示 baseline 中间态
                    self.status = "baseline"
                    deadline = self.started_at + self.timeout_seconds
                    baseline_names: set[str] = set()
                    prev_set: frozenset = frozenset()
                    stable_count = 0
                    while time.time() < deadline:
                        cur_set = frozenset(c.get("name", "") for c in await context.cookies())
                        if cur_set == prev_set:
                            stable_count += 1
                            if stable_count >= 2:   # 连续 2 次（≥4s）相同 = 稳定
                                baseline_names = set(cur_set)
                                break
                        else:
                            stable_count = 0
                            prev_set = cur_set
                        await asyncio.sleep(2)
                    logger.info(
                        "[浏览器·登录] {} baseline 稳定 cookies 数={} 名={}",
                        self.site, len(baseline_names), sorted(baseline_names)[:8],
                    )

                    # baseline 已稳定，再拍 QR 暴露给前端
                    self.qr_image = await _capture_qr(page, qr_selectors)
                    self.status = "qr_ready"
                    logger.info(
                        "[浏览器·登录] {} QR 就绪 session={} success_cookie='{}' 在 baseline={}",
                        self.site, self.session_id, self.success_cookie,
                        self.success_cookie in baseline_names,
                    )

                    # 等用户扫码：双轨判定 + SMS 风控分支
                    # 登录态判定：
                    #   主：success_cookie 出现且不在 baseline → 真登录（精确，避免 baseline diff 把任意新 cookie 当成功）
                    #   兜底：success_cookie 已在 baseline（匿名占位场景，如 xhs 匿名 web_session）→ 退回 baseline diff
                    # SMS 风控分支：扫码后若小红书等站点跳到 SMS 验证页（云端异地 IP），状态切 awaiting_sms 等用户在
                    #   webui 提交验证码；代码 fill+click 后 5s 再判 cookies，成功落盘失败回 awaiting_sms 让用户重试
                    success_in_baseline = self.success_cookie in baseline_names
                    last_qr_refresh = time.time()
                    sms_get_button_attempted = False   # 「获取验证码」按钮 best-effort click 一次的标记
                    last_url_logged: Optional[str] = None
                    while time.time() < deadline:
                        # 诊断：page.url 变化时打日志 + dump DOM 头部 1KB（SMS 页 selector 没命中场景下的 fallback 观察点）
                        try:
                            cur_url = page.url
                            if cur_url != last_url_logged:
                                logger.info("[浏览器·登录] {} URL 变化 {} → {}",
                                            self.site, last_url_logged, cur_url)
                                last_url_logged = cur_url
                                try:
                                    content_head = (await page.content())[:1024].replace("\n", " ")
                                    logger.info("[浏览器·登录] {} URL 变化后 DOM 头部 1KB：{}",
                                                self.site, content_head)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # 判定 1：登录成功（仅在 qr_ready 阶段；进入 awaiting_sms / sms_submitting 后不再凭主循环 cookies 自动判，
                        # 否则 SMS 页打开时新增的匿名 cookies 会把 baseline diff 兜底误触发，把用户的 SMS 填写界面直接推到 success）
                        if self.status == "qr_ready":
                            cookies = await context.cookies()
                            current_names = {c.get("name", "") for c in cookies}
                            if success_in_baseline:
                                new_names = current_names - baseline_names
                                triggered = bool(new_names)
                                reason = f"baseline diff 新增 {sorted(new_names)[:5]}"
                            else:
                                triggered = self.success_cookie in current_names
                                reason = f"success_cookie '{self.success_cookie}' 出现"
                            if triggered:
                                await context.storage_state(path=str(cookies_path(self.site)))
                                self.status = "success"
                                logger.info("[浏览器·登录] {} 成功 cookies 落盘（{}）", self.site, reason)
                                return

                        # 判定 2：扫码后跳到 SMS 验证页（仅在 qr_ready 阶段检测，避免重复进入）
                        if self.status == "qr_ready":
                            sms_detected = False
                            for sel in _SMS_FORM_DETECT_SELECTORS:
                                try:
                                    if await page.locator(sel).count() > 0:
                                        sms_detected = True
                                        break
                                except Exception:
                                    pass
                            if sms_detected:
                                logger.info("[浏览器·登录] {} 检测到 SMS 验证页 url={}", self.site, page.url)
                                # DOM dump 前 2KB 进 paimon.log，云端遇到时把日志贴回来调 selector
                                try:
                                    content = await page.content()
                                    logger.info("[浏览器·登录] {} SMS 页 DOM dump（前 2KB）：{}",
                                                self.site, content[:2048].replace("\n", " "))
                                except Exception:
                                    pass
                                # best-effort click 「获取验证码」一次（自动发短信场景下找不到按钮也无所谓）
                                if not sms_get_button_attempted:
                                    sms_get_button_attempted = True
                                    for sel in _SMS_GET_BUTTON_SELECTORS:
                                        try:
                                            loc = page.locator(sel).first
                                            if await loc.count() > 0:
                                                await loc.click(timeout=3000)
                                                logger.info("[浏览器·登录] {} 已 click 获取验证码 selector={}",
                                                            self.site, sel)
                                                await asyncio.sleep(1.5)
                                                break
                                        except Exception as e:
                                            logger.debug("[浏览器·登录] {} 获取验证码 selector {} 失败: {}",
                                                         self.site, sel, e)
                                # 截图 SMS 表单给前端
                                try:
                                    self.sms_form_image = await page.screenshot(full_page=False)
                                except Exception as e:
                                    logger.warning("[浏览器·登录] {} SMS 截图失败: {}", self.site, e)
                                self.status = "awaiting_sms"

                        # 判定 3：用户已提交 SMS 验证码（submit_sms 把 _sms_code 置上、status 改 sms_submitting）
                        if self.status == "sms_submitting" and self._sms_code:
                            code = self._sms_code
                            self._sms_code = None   # consume
                            filled = False
                            code_input_loc = None   # 留给 Enter fallback 用
                            for sel in _SMS_CODE_INPUT_SELECTORS:
                                try:
                                    loc = page.locator(sel).first
                                    if await loc.count() > 0:
                                        await loc.fill(code, timeout=3000)
                                        filled = True
                                        code_input_loc = loc
                                        logger.info("[浏览器·登录] {} 已填验证码 selector={}", self.site, sel)
                                        break
                                except Exception as e:
                                    logger.debug("[浏览器·登录] {} 验证码 input selector {} 失败: {}",
                                                 self.site, sel, e)
                            if not filled:
                                logger.warning("[浏览器·登录] {} 未找到验证码输入框，回退 awaiting_sms", self.site)
                                self.status = "awaiting_sms"
                                try:
                                    self.sms_form_image = await page.screenshot(full_page=False)
                                except Exception:
                                    pass
                            else:
                                # fill 6 位验证码后小红书前端可能已自动触发提交（form input change → submit）；等 1s 让 JS 处理
                                # 之后尝试 click 提交按钮：force=True 跳过 visibility 检查（小红书 button 在 form 提交瞬间 not visible/被 detach）
                                # click 失败 fallback 到在 input 上 press Enter
                                # 不论 click/Enter 是否成功，都等 5s 看 cookies——fill 本身就可能已经触发提交
                                await asyncio.sleep(1)
                                clicked = False
                                for sel in _SMS_SUBMIT_SELECTORS:
                                    try:
                                        loc = page.locator(sel).first
                                        if await loc.count() > 0:
                                            await loc.click(timeout=2000, force=True)
                                            clicked = True
                                            logger.info("[浏览器·登录] {} 已 click 提交（force）selector={}",
                                                        self.site, sel)
                                            break
                                    except Exception as e:
                                        logger.debug("[浏览器·登录] {} 提交 selector {} 失败: {}",
                                                     self.site, sel, e)
                                if not clicked and code_input_loc is not None:
                                    try:
                                        await code_input_loc.press("Enter", timeout=2000)
                                        clicked = True
                                        logger.info("[浏览器·登录] {} fallback：input press Enter 触发提交",
                                                    self.site)
                                    except Exception as e:
                                        logger.debug("[浏览器·登录] {} press Enter 失败: {}", self.site, e)
                                # 等 5s 看 cookies（即使 click/Enter 都失败，fill 6 位也可能已自动提交）
                                await asyncio.sleep(5)
                                cookies_after = await context.cookies()
                                after_names = {c.get("name", "") for c in cookies_after}
                                after_ok = (
                                    bool(after_names - baseline_names) if success_in_baseline
                                    else (self.success_cookie in after_names)
                                )
                                if after_ok:
                                    await context.storage_state(path=str(cookies_path(self.site)))
                                    self.status = "success"
                                    logger.info("[浏览器·登录] {} SMS 提交后成功 cookies 落盘（click/Enter 触发={})",
                                                self.site, clicked)
                                    return
                                # 失败回 awaiting_sms 让用户重输（可能验证码错误/过期/风控加强）
                                logger.warning("[浏览器·登录] {} SMS 提交后未拿到登录态（click/Enter 触发={}），"
                                               "回退 awaiting_sms", self.site, clicked)
                                self.status = "awaiting_sms"
                                try:
                                    self.sms_form_image = await page.screenshot(full_page=False)
                                except Exception:
                                    pass

                        # QR 刷新仅在 qr_ready 阶段（awaiting_sms / sms_submitting 时 QR 已不重要）
                        if self.status == "qr_ready" and time.time() - last_qr_refresh >= self.REFRESH_QR_EVERY_SEC:
                            try:
                                self.qr_image = await _capture_qr(page, qr_selectors)
                                last_qr_refresh = time.time()
                            except Exception:
                                pass
                        await asyncio.sleep(2)
                    self.status = "timeout"
                    logger.warning("[浏览器·登录] {} 超时（{}s 内未检测到 {}）",
                                   self.site, self.timeout_seconds, self.success_cookie)
                finally:
                    await browser.close()
        except Exception as e:
            self.status = "failed"
            self.error = f"{type(e).__name__}: {e}"
            logger.warning("[浏览器·登录] {} 异常: {}", self.site, self.error)

    def to_status_dict(self) -> dict:
        """前端轮询用：不含二进制 qr_image / sms_form_image。error 截首行避免 ASCII 横幅撑爆 UI。"""
        err = self.error
        if err:
            # playwright "Executable doesn't exist..." 错误后面会带 60 行 banner，截掉
            first_line = err.split("\n", 1)[0]
            if "Executable doesn't exist" in first_line:
                err = "chromium 未安装；请在 paimon 根目录跑：playwright install chromium"
            else:
                err = first_line[:200]
        return {
            "session_id": self.session_id,
            "site": self.site,
            "display_name": self.display_name,
            "status": self.status,
            "error": err,
            "elapsed": int(time.time() - self.started_at),
            "timeout": self.timeout_seconds,
            "has_sms_form": self.sms_form_image is not None,
        }

    def submit_sms(self, code: str) -> dict:
        """webui 用户输入验证码后调；只接受在 awaiting_sms 状态下的提交，
        把 code 暂存到 _sms_code、状态切 sms_submitting，由后台 _run 主循环 consume。"""
        code = (code or "").strip()
        if not code:
            return {"ok": False, "error": "验证码不能为空"}
        if self.status != "awaiting_sms":
            return {"ok": False, "error": f"当前状态 {self.status} 不接受验证码提交"}
        self._sms_code = code
        self.status = "sms_submitting"
        return {"ok": True}


# ─────────────────────────────────────────────────────────────
# cookies 健康检查
# ─────────────────────────────────────────────────────────────

async def is_cookies_valid(
    site: str,
    probe_url: str,
    *,
    marker: str | None = None,
    expect_status: int = 200,
    timeout_seconds: float = 20.0,
) -> bool:
    """headless 跑一次请求，看是否仍是登录态。

    Args:
        site:        站点名（决定从 ~/.paimon/cookies/{site}.json 读 cookies）
        probe_url:   探测 URL（用站点的"我的主页"或登录态 API）
        marker:      返回内容里必须含的字符串（None 则只看状态码）
        expect_status: 期望 HTTP 状态码

    Returns:
        True = cookies 有效；False = 失效或文件不存在。
    """
    if not cookies_exists(site):
        return False
    apw = _import_playwright()

    try:
        async with apw() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(storage_state=str(cookies_path(site)))
                page = await context.new_page()
                response = await page.goto(probe_url, wait_until="domcontentloaded",
                                           timeout=int(timeout_seconds * 1000))
                if not response or response.status != expect_status:
                    return False
                if marker is None:
                    return True
                content = await page.content()
                return marker in content
            finally:
                await browser.close()
    except Exception as e:
        logger.warning("[浏览器·健康检查] {} 失败：{}", site, e)
        return False
