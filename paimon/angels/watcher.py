"""Skill 目录文件系统监听 —— 冰神 B-2 热加载

参考 openclaw agents/skills/refresh.ts 的 chokidar watcher 设计：
- 只关心 `<skills_dir>/*/SKILL.md` 事件（避免 FD 耗尽 + 无关文件打扰）
- debounce 300ms（合并 IDE 多次保存）
- 事件落回 asyncio event loop 调 `SkillRegistry.reload_one` / `remove_one`
- watcher 的 observer 跑在独立 daemon 线程（watchdog 默认模式）

注意：watchdog 的 Observer 是线程模型，不是 asyncio 原生；
事件发生在 watchdog 线程，用 `loop.call_soon_threadsafe` 回投到 asyncio 事件循环。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from loguru import logger

try:
    from watchdog.events import (
        FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent,
        FileDeletedEvent, FileMovedEvent,
    )
    from watchdog.observers import Observer
    _WATCHDOG_OK = True
except ImportError:
    _WATCHDOG_OK = False

if TYPE_CHECKING:
    from paimon.angels.registry import SkillRegistry
    from paimon.foundation.irminsul import Irminsul
    from paimon.llm.model import Model


# 事件合并窗口（毫秒）
_DEBOUNCE_MS = 300


class _SkillEventHandler(FileSystemEventHandler):
    """只关心 `<skills_dir>/<skill_name>/SKILL.md` 这一级。

    其他深度、其他文件名的事件直接忽略。
    """

    def __init__(
        self,
        skills_dir: Path,
        loop: asyncio.AbstractEventLoop,
        schedule_cb: Callable[[str, str], None],
    ):
        super().__init__()
        self._skills_dir = skills_dir.resolve()
        self._loop = loop
        # schedule_cb(skill_dir_name, event_type) 由 HotLoader 实现
        self._schedule = schedule_cb

    def _parse_skill_dir(self, raw_path: str) -> str | None:
        """把一个 event path 解析成 skill_dir_name；不匹配则返回 None。

        只认 `<skills_dir>/<skill_dir>/SKILL.md` 这种两层结构。
        """
        try:
            p = Path(raw_path).resolve()
        except Exception:
            return None
        if p.name != "SKILL.md":
            return None
        try:
            rel = p.relative_to(self._skills_dir)
        except ValueError:
            return None
        # rel 应该是 `<skill_dir>/SKILL.md`
        if len(rel.parts) != 2:
            return None
        return rel.parts[0]

    def _emit(self, skill_dir: str, event_type: str) -> None:
        try:
            self._loop.call_soon_threadsafe(self._schedule, skill_dir, event_type)
        except RuntimeError:
            # event loop 已关闭
            pass

    def on_created(self, event):
        if event.is_directory:
            return
        sd = self._parse_skill_dir(event.src_path)
        if sd:
            self._emit(sd, "create")

    def on_modified(self, event):
        if event.is_directory:
            return
        sd = self._parse_skill_dir(event.src_path)
        if sd:
            self._emit(sd, "modify")

    def on_deleted(self, event):
        if event.is_directory:
            return
        sd = self._parse_skill_dir(event.src_path)
        if sd:
            self._emit(sd, "delete")

    def on_moved(self, event):
        """rename = 删旧 + 建新。"""
        if event.is_directory:
            return
        old = self._parse_skill_dir(event.src_path)
        new = self._parse_skill_dir(event.dest_path)
        if old:
            self._emit(old, "delete")
        if new:
            self._emit(new, "create")


class SkillHotLoader:
    """串联 watcher → debounce → registry.reload_one/remove_one。"""

    def __init__(
        self,
        registry: "SkillRegistry",
        irminsul: "Irminsul",
        model: "Model",
    ):
        self._registry = registry
        self._irminsul = irminsul
        self._model = model
        self._observer = None
        # skill_dir → (event_type, asyncio.TimerHandle)
        self._pending: dict[str, tuple[str, asyncio.TimerHandle]] = {}

    def start(self) -> bool:
        """启动 watcher。返回 True 表示成功启动。"""
        if not _WATCHDOG_OK:
            logger.warning("[冰神·watcher] watchdog 未安装，热加载不可用")
            return False

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[冰神·watcher] 无运行中事件循环，热加载不可用")
            return False

        handler = _SkillEventHandler(
            self._registry.skills_dir, loop, self._schedule,
        )
        observer = Observer()
        observer.schedule(
            handler,
            str(self._registry.skills_dir),
            recursive=True,  # 需要 recursive=True 才能监听 <skills_dir>/<skill>/SKILL.md
        )
        observer.daemon = True
        observer.start()
        self._observer = observer
        logger.info("[冰神·watcher] 已启动监听 {}", self._registry.skills_dir)
        return True

    def stop(self) -> None:
        """停止 watcher + 清理挂起任务。"""
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception as e:
                logger.debug("[冰神·watcher] stop 异常: {}", e)
            self._observer = None

        for _, (_, timer) in list(self._pending.items()):
            try:
                timer.cancel()
            except Exception:
                pass
        self._pending.clear()

    def _schedule(self, skill_dir: str, event_type: str) -> None:
        """在 asyncio 线程调用：为 skill_dir 排期 300ms 后执行 dispatch。"""
        # 同 skill_dir 有挂起事件：取消旧 timer，用新 event_type 覆盖
        if skill_dir in self._pending:
            _, old_timer = self._pending[skill_dir]
            old_timer.cancel()

        from paimon.foundation.bg import bg
        loop = asyncio.get_running_loop()
        # delete 事件即使之前有 create/modify 挂起，也优先 delete（文件没了）
        timer = loop.call_later(
            _DEBOUNCE_MS / 1000.0,
            lambda: bg(
                self._dispatch(skill_dir, event_type),
                label=f"watcher·{event_type}·{skill_dir}",
            ),
        )
        self._pending[skill_dir] = (event_type, timer)

    async def _dispatch(self, skill_dir: str, event_type: str) -> None:
        self._pending.pop(skill_dir, None)
        try:
            if event_type == "delete":
                await self._registry.remove_one(
                    skill_dir, irminsul=self._irminsul,
                )
            else:
                # create / modify 都走 reload_one
                await self._registry.reload_one(
                    skill_dir, irminsul=self._irminsul, model=self._model,
                )
        except Exception as e:
            logger.error(
                "[冰神·watcher] dispatch {} ({}) 异常: {}",
                skill_dir, event_type, e,
            )
