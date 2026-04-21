from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from loguru import logger


@dataclass
class Session:
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


class SessionManager:
    def __init__(self, home: Path):
        self.home = home
        self.sessions: dict[str, Session] = {}
        self.bindings: dict[str, str] = {}
        self._sessions_dir = home / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, s: Session):
        s.updated_at = time.time()
        path = self._sessions_dir / f"{s.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2))
        tmp.replace(path)
        logger.trace("[派蒙·会话] 会话已保存: {}", s.id)

    def _save_state(self):
        data = {
            "bindings": self.bindings,
            "session_ids": list(self.sessions.keys()),
        }
        path = self.home / "state.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(path)
        logger.trace("[派蒙·会话] 状态已保存")

    @classmethod
    def load(cls, home: Path) -> SessionManager:
        mgr = cls(home)
        state_path = home / "state.json"
        if not state_path.exists():
            logger.info("[派蒙·会话] 未找到历史状态，全新启动")
            return mgr

        data = json.loads(state_path.read_text())
        for sid in data.get("session_ids", []):
            sp = mgr._sessions_dir / f"{sid}.json"
            if sp.exists():
                sd = json.loads(sp.read_text())
                sd.setdefault("response_status", "idle")
                mgr.sessions[sid] = Session(**sd)

        mgr.bindings = data.get("bindings", {})

        for s in mgr.sessions.values():
            if s.response_status == "generating":
                s.response_status = "interrupted"
                mgr.save_session(s)

        logger.info(
            "[派蒙·会话] 恢复{}个会话，{}个绑定",
            len(mgr.sessions),
            len(mgr.bindings),
        )
        return mgr

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
        self._save_state()
        logger.info("[派蒙·会话] 新建会话: {}", sid)
        return s

    def switch(self, channel_key: str, sid: str) -> Session | None:
        s = self.sessions.get(sid)
        if not s:
            return None
        self.bindings[channel_key] = sid
        self._save_state()
        logger.debug("[派蒙·会话] 绑定: {} → 会话 {}", channel_key, sid)
        return s

    def get_current(self, channel_key: str) -> Session | None:
        sid = self.bindings.get(channel_key)
        return self.sessions.get(sid) if sid else None

    def delete(self, sid: str):
        if sid in self.sessions:
            del self.sessions[sid]
        to_del = [k for k, v in self.bindings.items() if v == sid]
        for k in to_del:
            del self.bindings[k]
        path = self._sessions_dir / f"{sid}.json"
        if path.exists():
            path.unlink()
        self._save_state()
        logger.info("[派蒙·会话] 已删除会话: {}", sid)
