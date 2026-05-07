"""晨星·多视角讨论体系（docs/world_formula.md §3.4）。

晨星 = 多视角讨论的 leader / orchestrator（不是天使）。
天使 = 11 个预定义角色（结构性 5 / 评估性 4 / 对抗性 2），由晨星按议题召集 3-5 个。

注意：跟 paimon/angels/（旧 skill 代理）命名重叠是过渡期；按 docs 规划，
后续会把旧 paimon/angels/ 体系处理掉，「天使」最终归属此模块。
"""
from .council import CouncilResult, run_council
from .morningstar import run_agents
from .roles import ROLES, get_role

__all__ = ["run_agents", "run_council", "CouncilResult", "ROLES", "get_role"]
