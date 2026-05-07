"""天使·多视角讨论体系（docs/world_formula.md §3.4）。

天使体系 = 晨星（leader）+ 11 个协同天使。
- 晨星：天使中的 leader，负责调度（assemble 召集 → dispatch+speak loop → synthesize）
- 协同天使：11 个预定义角色（结构性 5 / 评估性 4 / 对抗性 2），由晨星按议题召集 3-5 个

(原 paimon/angels/ 已重命名为 paimon/skill_loader/，「天使」语义专属此模块。)
"""
from .council import CouncilResult, run_council
from .morningstar import run_agents
from .roles import ROLES, get_role

__all__ = ["run_agents", "run_council", "CouncilResult", "ROLES", "get_role"]
