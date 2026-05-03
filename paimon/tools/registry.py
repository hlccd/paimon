from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from paimon.tools.base import BaseTool, ToolContext


class ExternalTool(BaseTool):
    def __init__(self, name: str, description: str, parameters: dict, module):
        self.name = name
        self.description = description
        self.parameters = parameters
        self._module = module

    async def execute(self, ctx: ToolContext, **kwargs) -> str:
        return await self._module.execute(**kwargs)


@dataclass
class ToolRegistry:
    tools_dir: Path
    _tools: dict[str, BaseTool] = field(default_factory=dict)

    @classmethod
    def load(cls, tools_dir: Path) -> ToolRegistry:
        reg = cls(tools_dir=tools_dir)
        reg.refresh()
        return reg

    def refresh(self) -> None:
        self._tools.clear()

        from paimon.tools.builtin import BUILTIN_TOOLS
        for t in BUILTIN_TOOLS:
            self._tools[t.name] = t

        if not self.tools_dir.exists():
            logger.info("[天使·工具] 工具目录不存在: {}", self.tools_dir)
            return

        for py in sorted(self.tools_dir.glob("*.py")):
            try:
                self._load_external(py)
            except Exception as e:
                logger.error("[天使·工具] 加载外部工具失败 {}: {}", py.name, e)

        logger.info("[天使·工具] 已加载: {}", list(self._tools.keys()))

    def _load_external(self, path: Path) -> None:
        # SEC-002 路径白名单：path 必须是 tools_dir 的直系子文件（不允许 ..）
        # exec_module 等价于跑任意 .py 代码，目录可写即 RCE；强制限定加载源
        try:
            tools_dir = self.tools_dir.resolve()
            real_path = path.resolve()
            if real_path.parent != tools_dir:
                logger.error(
                    "[天使·工具] 拒绝加载外部工具（不在 tools_dir 直系子文件）: {}",
                    real_path,
                )
                return
            if real_path.suffix != ".py":
                logger.error("[天使·工具] 拒绝非 .py 文件: {}", real_path)
                return
        except (OSError, ValueError) as e:
            logger.error("[天使·工具] 路径校验失败 {}: {}", path, e)
            return

        spec = importlib.util.spec_from_file_location(path.stem, path)
        if not spec or not spec.loader:
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # 校验外部 module 必填字段（防 ExternalTool 字段缺失/恶意类型）
        required = ("name", "description", "parameters")
        missing = [k for k in required if not hasattr(mod, k)]
        if missing:
            logger.error(
                "[天使·工具] 外部工具缺字段 {} 拒绝加载: {}", missing, path,
            )
            return
        if not isinstance(mod.name, str) or not mod.name:
            logger.error("[天使·工具] 外部工具 name 非合法字符串: {}", path)
            return

        self._tools[mod.name] = ExternalTool(
            name=mod.name,
            description=mod.description,
            parameters=mod.parameters,
            module=mod,
        )
        logger.debug("[天使·工具] 外部工具: {}", mod.name)

    async def execute(self, name: str, arguments: str, ctx: ToolContext) -> str:
        kwargs = json.loads(arguments) if arguments else {}
        tool = self._tools.get(name)
        if not tool:
            return f"错误: 未知工具 '{name}'"
        try:
            return await tool.execute(ctx, **kwargs)
        except Exception as e:
            logger.error("[天使·工具] {} 执行失败: {}", name, e)
            return f"工具执行错误: {e}"

    def to_openai_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]
