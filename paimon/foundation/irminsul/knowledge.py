"""知识库域 —— 世界树域 3

唯一写入者 / 读取者：草神（业务接口层）
存储介质：文件系统 .paimon/irminsul/knowledge/{category}/{topic}.md

路径安全由 resolve_safe 承担，调用方只传 (category, topic) 语义参数。
首版不建 index 表；未来加 tags / FTS 时再引入。
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from ._paths import resolve_safe


class KnowledgeRepo:
    def __init__(self, root: Path):
        """root = paimon_home/irminsul/knowledge"""
        self._root = root

    def _topic_path(self, category: str, topic: str) -> Path:
        if not category or not topic:
            raise ValueError("category / topic 不能为空")
        # 加 .md 后缀
        filename = f"{topic}.md"
        return resolve_safe(self._root, category, filename)

    async def read(self, category: str, topic: str) -> str | None:
        try:
            path = self._topic_path(category, topic)
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    async def write(
        self, category: str, topic: str, body: str, *, actor: str,
    ) -> None:
        path = self._topic_path(category, topic)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        logger.info("[世界树] {}·知识写入  {}/{}", actor, category, topic)

    async def list(self, category: str = "") -> list[tuple[str, str]]:
        """返回 [(category, topic), ...]"""
        if not self._root.exists():
            return []
        result: list[tuple[str, str]] = []
        if category:
            # 只列某个类别
            try:
                cat_dir = resolve_safe(self._root, category)
            except ValueError:
                return []
            if not cat_dir.is_dir():
                return []
            for md in sorted(cat_dir.glob("*.md")):
                result.append((category, md.stem))
        else:
            # 列全部
            for cat_dir in sorted(self._root.iterdir()):
                if not cat_dir.is_dir():
                    continue
                for md in sorted(cat_dir.glob("*.md")):
                    result.append((cat_dir.name, md.stem))
        return result

    async def delete(self, category: str, topic: str, *, actor: str) -> bool:
        try:
            path = self._topic_path(category, topic)
        except ValueError:
            return False
        if not path.is_file():
            return False
        path.unlink()
        logger.info("[世界树] {}·知识删除  {}/{}", actor, category, topic)
        return True
