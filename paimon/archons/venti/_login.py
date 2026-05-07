"""风神·站点登录管理 mixin：扫码会话 + cookies 状态总览。

风神主管 topic / 各登录态 collector，所以站点 cookies 归风神管：
- WebUI 的 `/feed` 面板通过 API 调风神：login_start / login_status / login_qr
- LoginSession 的实例字典放在 archon 上（跨请求保留）
- 后台 GC：超过 600s 的 stale 会话清掉
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger

from paimon.foundation.browser import LoginSession, SITE_CONFIG
from paimon.foundation.site_cookies import cookies_age_days, cookies_exists

if TYPE_CHECKING:
    pass

_GC_INTERVAL = 60       # GC 周期（秒）
_GC_STALE_AFTER = 600   # 会话超过此时长视为 stale 可清


class _LoginMixin:
    """注入到 VentiArchon。需配合 __init__ 里 self._pending_login = {} self._login_gc_task = None。"""

    def _ensure_login_attrs(self) -> None:
        """惰性初始化（避免破坏既有 __init__ 顺序）。"""
        if not hasattr(self, "_pending_login"):
            self._pending_login: dict[str, LoginSession] = {}
        if not hasattr(self, "_login_gc_task"):
            self._login_gc_task: asyncio.Task | None = None

    def _ensure_login_gc(self) -> None:
        self._ensure_login_attrs()
        if self._login_gc_task is not None and not self._login_gc_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._login_gc_task = loop.create_task(self._login_gc_loop())

    async def _login_gc_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(_GC_INTERVAL)
                now = time.time()
                stale = [
                    sid for sid, s in self._pending_login.items()
                    if now - s.started_at > _GC_STALE_AFTER
                ]
                for sid in stale:
                    self._pending_login.pop(sid, None)
                if stale:
                    logger.info("[风神·登录] GC 清理 {} 个 stale 会话", len(stale))
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[风神·登录·GC] 异常: {}", e)

    # ─────────────── 对外 API（webui 调） ───────────────

    async def login_start(self, site: str) -> dict:
        """启动一次扫码登录会话；返回 status dict（含 session_id）。"""
        self._ensure_login_attrs()
        self._ensure_login_gc()
        if site not in SITE_CONFIG:
            return {"ok": False, "error": f"未知站点：{site}"}
        try:
            sess = LoginSession(site)
            await sess.start()
        except Exception as e:
            logger.warning("[风神·登录] 启动失败 site={}: {}", site, e)
            return {"ok": False, "error": str(e)}
        self._pending_login[sess.session_id] = sess
        logger.info("[风神·登录] 启动 {} session={}", site, sess.session_id)
        return {"ok": True, **sess.to_status_dict()}

    def login_status(self, session_id: str) -> dict:
        """轮询一次会话状态。"""
        self._ensure_login_attrs()
        sess = self._pending_login.get(session_id)
        if not sess:
            return {"ok": False, "error": "session 不存在或已过期", "status": "not_found"}
        return {"ok": True, **sess.to_status_dict()}

    def login_qr(self, session_id: str) -> bytes | None:
        """拿当前 QR PNG bytes（前端 <img> src 用）。"""
        self._ensure_login_attrs()
        sess = self._pending_login.get(session_id)
        return sess.qr_image if sess else None

    def login_sms_form(self, session_id: str) -> bytes | None:
        """SMS 风控分支：扫码后被站点跳到验证码页，前端展示这张表单截图给用户参考。"""
        self._ensure_login_attrs()
        sess = self._pending_login.get(session_id)
        return sess.sms_form_image if sess else None

    def login_submit_sms(self, session_id: str, code: str) -> dict:
        """webui 用户填了验证码后调：交给 LoginSession 的后台 task 去 fill+click。"""
        self._ensure_login_attrs()
        sess = self._pending_login.get(session_id)
        if not sess:
            return {"ok": False, "error": "session 不存在或已过期"}
        return sess.submit_sms(code)

    def login_overview(self) -> list[dict]:
        """所有支持站点的 cookies 状态总览（前端登录区表格用）。

        免登录站点（requires_login=False，如 B 站）也列出，前端按字段渲染：
        - requires_login=True：显示 cookies 状态 + 扫码登录按钮
        - requires_login=False：标"无需 cookies"，无按钮
        """
        result: list[dict] = []
        for site, cfg in SITE_CONFIG.items():
            requires_login = cfg.get("requires_login", True)
            row: dict = {
                "site": site,
                "display_name": cfg["display_name"],
                "requires_login": requires_login,
                "configured": cookies_exists(site) if requires_login else None,
            }
            if requires_login and row["configured"]:
                age = cookies_age_days(site)
                row["age_days"] = round(age, 1) if age is not None else None
            result.append(row)
        return result
