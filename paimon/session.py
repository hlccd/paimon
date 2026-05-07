"""派蒙会话管理 —— 服务层

存储落盘走世界树 session 域，本模块只持有运行时缓存 + 业务逻辑（切换 / 绑定 / 新建）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul


@dataclass
class Session:
    """和旧 Session 字段保持一致（新增 channel_key 内部字段；archived_at 不对 app 层暴露）。"""
    id: str
    name: str
    messages: list[dict] = field(default_factory=list)
    session_memory: list[str] = field(default_factory=list)
    last_context_tokens: int = 0
    last_context_ratio: float = 0.0
    last_compressed_at: float = 0.0
    compressed_rounds: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    response_status: str = "idle"
    # 内部字段：当前绑定的 channel_key；随 switch 更新
    _channel_key: str = ""
    # 时执压缩熔断相关（docs/shades/istaroth.md §压缩失败熔断）
    compression_failures: int = 0
    auto_compact_disabled: bool = False
    # 临时执行容器标记：天使路径 skill 调用时 create_ephemeral() 建一个，跑完丢弃
    # 不入 SessionManager.sessions、不落世界树、不绑 channel_key，save 入口 short-circuit
    # 仅内存字段，不写 SessionRecord
    ephemeral: bool = False


class SessionManager:
    """会话管理器：内存缓存 + 委托世界树落盘。"""

    def __init__(self, irminsul: Irminsul):
        self._irminsul = irminsul
        self.sessions: dict[str, Session] = {}
        # channel_key -> session_id 绑定（从 session._channel_key 字段派生）
        self.bindings: dict[str, str] = {}

    @classmethod
    async def load(cls, irminsul: Irminsul) -> SessionManager:
        """启动时从世界树恢复所有活跃会话 + 绑定。"""
        mgr = cls(irminsul)
        records = await irminsul.session_list_all_full()

        for rec in records:
            s = Session(
                id=rec.id, name=rec.name,
                messages=rec.messages,
                session_memory=rec.session_memory,
                last_context_tokens=rec.last_context_tokens,
                last_context_ratio=rec.last_context_ratio,
                last_compressed_at=rec.last_compressed_at,
                compressed_rounds=rec.compressed_rounds,
                response_status=rec.response_status,
                created_at=rec.created_at,
                updated_at=rec.updated_at,
                _channel_key=rec.channel_key,
                compression_failures=rec.compression_failures,
                auto_compact_disabled=rec.auto_compact_disabled,
            )
            # 审计 REL-012 P2：异常中断的 generating 改回 interrupted
            if s.response_status == "generating":
                s.response_status = "interrupted"
                await mgr._save(s)

            mgr.sessions[s.id] = s
            if rec.channel_key:
                mgr.bindings[rec.channel_key] = s.id

        logger.info(
            "[派蒙·会话] 恢复 {} 个会话，{} 个绑定",
            len(mgr.sessions), len(mgr.bindings),
        )
        return mgr

    async def _save(self, s: Session) -> None:
        """落盘：转成 SessionRecord 调世界树。"""
        from paimon.foundation.irminsul import SessionRecord
        s.updated_at = time.time()
        rec = SessionRecord(
            id=s.id, name=s.name,
            channel_key=s._channel_key,
            messages=s.messages,
            session_memory=s.session_memory,
            last_context_tokens=s.last_context_tokens,
            last_context_ratio=s.last_context_ratio,
            last_compressed_at=s.last_compressed_at,
            compressed_rounds=s.compressed_rounds,
            response_status=s.response_status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            compression_failures=s.compression_failures,
            auto_compact_disabled=s.auto_compact_disabled,
        )
        await self._irminsul.session_upsert(rec, actor="派蒙")

    # ---------- 对外 API（保持原同名同语义）----------
    def save_session(self, s: Session) -> None:
        """同步入口：旧代码大量使用。内部 schedule 异步落盘任务。

        ephemeral session（天使 skill 路径用）入口拦截，全局 short-circuit：
        不落盘 / 不入 self.sessions / 不绑 channel_key —— handle_chat 内部多处
        save_session 不必散点判 ephemeral。
        """
        if s.ephemeral:
            return
        import asyncio
        from paimon.foundation.bg import bg
        s.updated_at = time.time()
        # 先更新内存
        self.sessions[s.id] = s
        # 异步触发落盘（不阻塞调用方）
        try:
            asyncio.get_running_loop()
            bg(self._save(s), label=f"session·save·{s.id[:8]}")
        except RuntimeError:
            # 无运行中事件循环（不应该发生在派蒙业务代码中）
            asyncio.run(self._save(s))
        logger.trace("[派蒙·会话] 会话已保存: {}", s.id)

    async def save_session_async(self, s: Session) -> None:
        """显式异步入口，供新代码使用。"""
        if s.ephemeral:
            return
        s.updated_at = time.time()
        self.sessions[s.id] = s
        await self._save(s)

    def create(self) -> Session:
        sid = uuid4().hex[:8]
        now = time.time()
        s = Session(
            id=sid,
            name=f"s-{sid}",
            created_at=now,
            updated_at=now,
        )
        self.sessions[sid] = s
        self.save_session(s)
        logger.info("[派蒙·会话] 新建会话: {}", sid)
        return s

    def create_ephemeral(self) -> Session:
        """建一个临时执行容器：天使 skill 调用用 —— 不入 self.sessions、不落世界树、
        不绑 channel_key。跑完直接丢弃，handle_chat 在它身上跑工具循环不污染主 session。

        UI 看见的「指令记录」由调用方跑完后单独 append 两条带 meta=skip_llm 的条目
        到主 session（user 文本 + final assistant 文本），中间工具循环产物丢弃。
        """
        sid = "eph-" + uuid4().hex[:8]
        now = time.time()
        s = Session(
            id=sid,
            name=f"ephemeral-{sid}",
            created_at=now,
            updated_at=now,
            ephemeral=True,
        )
        # 故意不入 self.sessions / 不调 save_session（save 入口也会 short-circuit）
        logger.debug("[派蒙·会话] 新建临时容器: {}", sid)
        return s

    def switch(self, channel_key: str, sid: str) -> Session | None:
        s = self.sessions.get(sid)
        if not s:
            return None

        # 清理同 channel 其他会话的绑定（保持一 channel 一活跃会话）
        for other_sid, other in list(self.sessions.items()):
            if other_sid != sid and other._channel_key == channel_key:
                other._channel_key = ""
                self.save_session(other)

        s._channel_key = channel_key
        self.bindings[channel_key] = sid
        self.save_session(s)
        logger.debug("[派蒙·会话] 绑定: {} → 会话 {}", channel_key, sid)
        return s

    def get_current(self, channel_key: str) -> Session | None:
        sid = self.bindings.get(channel_key)
        return self.sessions.get(sid) if sid else None

    def delete(self, sid: str) -> None:
        import asyncio
        from paimon.foundation.bg import bg
        if sid in self.sessions:
            s = self.sessions.pop(sid)
            # 清除绑定
            to_del = [k for k, v in self.bindings.items() if v == sid]
            for k in to_del:
                del self.bindings[k]
            # 异步落盘：从世界树删除
            try:
                asyncio.get_running_loop()
                bg(self._irminsul.session_delete(sid, actor="派蒙"), label=f"session·delete·{sid[:8]}")
            except RuntimeError:
                asyncio.run(self._irminsul.session_delete(sid, actor="派蒙"))
            logger.info("[派蒙·会话] 已删除会话: {}", sid)

    def invalidate_removed(self, sids: list[str]) -> None:
        """时执生命周期清扫物理删除了会话后调，同步内存缓存。

        仅清内存 dict / bindings；DB 已由时执删除。不触发二次落盘。
        """
        if not sids:
            return
        removed_count = 0
        for sid in sids:
            if sid in self.sessions:
                self.sessions.pop(sid, None)
                removed_count += 1
            to_del = [k for k, v in self.bindings.items() if v == sid]
            for k in to_del:
                del self.bindings[k]
        if removed_count:
            logger.info(
                "[派蒙·会话] 生命周期清扫同步内存：移除 {} 个缓存会话",
                removed_count,
            )
