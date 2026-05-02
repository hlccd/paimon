"""三月·自检系统 —— 服务层

docs/foundation/march.md §自检体系

两档自检：
- Quick：秒级纯代码组件探针，零 LLM；每次写 audit + 归档到世界树域 12
- Deep ：调 check skill（参数模式 project-health）跑项目体检，产物 .check/report.md
         快照进归档目录供面板查看；独立 asyncio.Task，全局单例锁防并发

归档：元数据 → selfcheck_runs 表；原始产物（report.md / candidates.jsonl / state.json /
quick_snapshot.json）→ <paimon_home>/irminsul/selfcheck/{run_id}/

子模块：
- _helpers.py  —— 平台 shell 提示 + check 进度抽取 + 路径常量
- _models.py   —— ComponentProbe / QuickSnapshot dataclass
- _probes.py   —— 9 组件探针 + probe_all 并发收集
- _deep.py     —— Deep 实际执行流程（调 skill / watcher / 归档解析 / 推送）
- service.py   —— SelfCheckService 主类（薄入口 + 查询 API）
"""
from __future__ import annotations

from ._models import ComponentProbe, QuickSnapshot
from .service import SelfCheckService

__all__ = ["ComponentProbe", "QuickSnapshot", "SelfCheckService"]
