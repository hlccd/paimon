"""工人 Worker — 四影内部的无人格化执行单元。

按 stage tag 选 skill workflow / tool-loop，替代原七神 archon 在四影 execute 路径
扮演的角色。工人无中文神名，日志 / 审计用 stage 名标识（"工人·spec" 等）。

9 个预定义 stage（详见 _stages.py）：
- spec / design / code：调 requirement-spec / architecture-design / code-implementation skill
- review_spec / review_design / review_code：light LLM 或 check skill
- simple_code：trivial 任务直接 LLM 写代码（无 skill 兜底）
- exec：通用执行（shell / 部署 / 重型工具）
- chat：普通 LLM 推理（默认兜底）

四影空执 asmoday 调 `run_stage(sub.stage, ...)` 派发到工人；工人不依赖 archons.* 代码。
"""
from .runner import run_stage

__all__ = ["run_stage"]
