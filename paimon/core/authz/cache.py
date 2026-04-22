"""授权本地缓存 —— 派蒙持有

启动时从世界树灌入；运行时写世界树后同步更新本机；
地脉 skill.loaded 事件触发 invalidate（冰神 AI 自举新 skill 时）。
遵守 docs/permissions.md "只存不推，派蒙不订阅世界树变更" 原则：
  这里的"订阅"订的是地脉事件，世界树本身仍然是被动存储。
"""
from __future__ import annotations

from loguru import logger

from paimon.foundation.irminsul import Irminsul


class AuthzCache:
    """(subject_type, subject_id) -> decision 的内存映射。

    decision ∈ {'permanent_allow', 'permanent_deny'}
    """

    def __init__(self):
        self._map: dict[tuple[str, str], str] = {}
        # 本次会话的临时放行/拒绝（不落盘，会话级）：(session_id, type, id) -> decision
        self._session_scope: dict[tuple[str, str, str], str] = {}

    async def load(self, irminsul: Irminsul, *, user_id: str = "default") -> None:
        self._map = await irminsul.authz_snapshot(user_id=user_id)
        logger.info("[派蒙·授权] 缓存灌入完成 共 {} 条永久记录", len(self._map))

    def get(self, subject_type: str, subject_id: str) -> str | None:
        """只查永久授权。本次会话临时决策走 get_session_scope。"""
        return self._map.get((subject_type, subject_id))

    def set(self, subject_type: str, subject_id: str, decision: str) -> None:
        """本地同步（派蒙写世界树后跟着调一次）。"""
        self._map[(subject_type, subject_id)] = decision

    def invalidate(
        self,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> None:
        """四影通知新 skill 注册时，让相关缓存失效。

        - 全清：两个参数都为 None
        - 局部清：仅命中的键被删，下次访问时回世界树读（或认未授权）
        """
        if subject_type is None and subject_id is None:
            self._map.clear()
            logger.info("[派蒙·授权] 缓存全量失效")
            return

        if subject_type is not None and subject_id is not None:
            self._map.pop((subject_type, subject_id), None)
        else:
            # 按类型批量清
            keys = [
                k for k in self._map
                if (subject_type is None or k[0] == subject_type)
                and (subject_id is None or k[1] == subject_id)
            ]
            for k in keys:
                self._map.pop(k, None)
        logger.debug("[派蒙·授权] 缓存失效 type={} id={}", subject_type, subject_id)

    def set_session_scope(
        self, session_id: str, subject_type: str, subject_id: str, decision: str,
    ) -> None:
        """本次会话临时决策（allow/deny），仅内存。"""
        self._session_scope[(session_id, subject_type, subject_id)] = decision

    def get_session_scope(
        self, session_id: str, subject_type: str, subject_id: str,
    ) -> str | None:
        return self._session_scope.get((session_id, subject_type, subject_id))

    def clear_session_scope(self, session_id: str) -> None:
        self._session_scope = {
            k: v for k, v in self._session_scope.items() if k[0] != session_id
        }

    def snapshot(self) -> dict[tuple[str, str], str]:
        """给面板等调用方读只读副本用。"""
        return dict(self._map)
