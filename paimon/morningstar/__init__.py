"""天使·多视角讨论体系（详见 docs/angels/angels.md）。

天使体系 = 晨星（leader）+ 11 个协同天使。
- 晨星：天使中的 leader，负责调度（assemble 召集 → dispatch+speak loop → synthesize）
- 协同天使：11 个预定义角色（结构性 5 / 评估性 4 / 对抗性 2），由晨星按议题召集 3-5 个

"""
from .council import CouncilResult, run_council
from .morningstar import run_agents
from .roles import ROLES

__all__ = ["run_agents", "run_council", "CouncilResult", "ROLES"]
