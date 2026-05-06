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
    },
}


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
        new → start() 起后台 task → status='qr_ready' + qr_image
            → 用户扫码 → 检测 success_cookie → status='success' + cookies 落盘
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
        self.status: str = "pending"   # pending / qr_ready / success / timeout / failed
        self.qr_image: Optional[bytes] = None
        self.error: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

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
                    self.qr_image = await _capture_qr(page, qr_selectors)
                    self.status = "qr_ready"
                    logger.info("[浏览器·登录] {} QR 就绪 session={}", self.site, self.session_id)

                    # 轮询 cookies
                    deadline = self.started_at + self.timeout_seconds
                    last_qr_refresh = time.time()
                    while time.time() < deadline:
                        cookies = await context.cookies()
                        if any(c.get("name") == self.success_cookie for c in cookies):
                            await context.storage_state(path=str(cookies_path(self.site)))
                            self.status = "success"
                            logger.info("[浏览器·登录] {} 成功 cookies 落盘", self.site)
                            return
                        # 每 N 秒刷一次 QR 截图（QR 在页面里会自动 rotate）
                        if time.time() - last_qr_refresh >= self.REFRESH_QR_EVERY_SEC:
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
        """前端轮询用：不含二进制 qr_image。error 截首行，避免 ASCII 横幅撑爆 UI。"""
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
        }


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
