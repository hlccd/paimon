"""水神·芙宁娜 — 评审 archon 子包（service.py）

⚠️ 当前状态（2026-05 解耦后）：

水神跟四影解耦后**整体保留游戏功能**：
- 保留：水神·游戏（FurinaGameService，详 archons/furina_game/）— /game 面板 + 2 cron + 1 sub type
- 移除：水神·评审 archon 本体（review_spec / review_design / review_code）
  - `_review.py` 删除（420 行）
  - 已搬到：`paimon/shades/jonova/review.py`

archon 本体（FurinaArchon）当前是 namespace 壳：
- 移除：execute() 内部评审路由 + ReviewMixin
- 保留：class + name + description

待用户后续安排：是否给 archon 本体挂新职能（详见 docs/archons/furina.md）。
"""
from __future__ import annotations

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model


class FurinaArchon(Archon):
    name = "水神"
    description = "戏剧·评审（archon 本体：解耦后暂无具体职能 / namespace 保留；游戏服务在 furina_game/）"
    allowed_tools: set[str] = set()

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        return f"[{self.name}] execute 路径已解耦（v6），请参考 docs/archons/furina.md"
