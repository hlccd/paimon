"""四影闭环 · Plan 数据模型与 DAG 图算法

docs/aimon.md §2.3 典型复杂任务流的"草水雷多轮循环"要求：
  - 子任务以 DAG 表达（不是平铺列表）
  - 生执可以多轮修订（每轮产生新的 Plan 版本）
  - 空执按拓扑分层并发执行
  - 检测依赖环并降级

本模块仅持内存对象 + 纯函数；落盘仍走 `task_subtasks` 表。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from paimon.foundation.irminsul.task import Subtask


@dataclass
class Plan:
    """某轮次的 DAG 工作副本。

    - subtasks: 当轮的节点（含新建 + 复用的旧节点）
    - round: 轮次编号（1 起）
    - reason: 本轮生成/修订的理由（初始编排时为空；修订时为评审意见）
    """
    task_id: str
    round: int
    subtasks: list[Subtask]
    reason: str = ""

    @property
    def by_id(self) -> dict[str, Subtask]:
        return {s.id: s for s in self.subtasks}


def detect_cycle(subtasks: list[Subtask]) -> list[str] | None:
    """DFS 三色标记找环。返回环上的节点 id 列表（任一），无环返回 None。

    只考虑 subtasks 内部的 deps；对外部不存在的 dep id 静默忽略（由上层过滤）。
    """
    ids = {s.id for s in subtasks}
    adj: dict[str, list[str]] = {
        s.id: [d for d in (s.deps or []) if d in ids] for s in subtasks
    }

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in ids}
    parent: dict[str, str | None] = {sid: None for sid in ids}

    def _dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                # 回溯抽环
                cycle = [v, u]
                p = parent[u]
                while p is not None and p != v:
                    cycle.append(p)
                    p = parent[p]
                return list(reversed(cycle))
            if color[v] == WHITE:
                parent[v] = u
                found = _dfs(v)
                if found:
                    return found
        color[u] = BLACK
        return None

    for sid in ids:
        if color[sid] == WHITE:
            cycle = _dfs(sid)
            if cycle:
                return cycle
    return None


def topological_layers(subtasks: list[Subtask]) -> list[list[Subtask]]:
    """Kahn 算法分层。每层内可并发执行。

    前提：subtasks 已无环（调用方保证）。
    无效 dep（引用不存在的 id）在入度计算时被忽略。
    """
    ids = {s.id for s in subtasks}
    by_id = {s.id: s for s in subtasks}

    indeg: dict[str, int] = {sid: 0 for sid in ids}
    rev_adj: dict[str, list[str]] = {sid: [] for sid in ids}

    for s in subtasks:
        for d in (s.deps or []):
            if d in ids:
                indeg[s.id] += 1
                rev_adj[d].append(s.id)

    layers: list[list[Subtask]] = []
    current = [sid for sid in ids if indeg[sid] == 0]

    while current:
        # 按 created_at 排序，保留编排直觉顺序
        current.sort(key=lambda x: by_id[x].created_at)
        layers.append([by_id[sid] for sid in current])
        next_layer: list[str] = []
        for u in current:
            for v in rev_adj[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    next_layer.append(v)
        current = next_layer

    # 防御：若仍有节点剩余（无环前提下不应发生），兜底把剩余节点放最后一层
    visited = {s.id for layer in layers for s in layer}
    leftover = [by_id[sid] for sid in ids if sid not in visited]
    if leftover:
        logger.warning("[四影·plan] topo 兜底：{} 个节点未入层，追加末层", len(leftover))
        layers.append(leftover)

    return layers


def linearize(subtasks: list[Subtask], cycle_nodes: list[str] | None = None) -> list[Subtask]:
    """降级：把 DAG 压平为线性链（按 created_at 顺序，去除所有 deps）。

    用于依赖环检测失败后的兜底。会修改每个 Subtask 的 deps 为 []（原地）。
    cycle_nodes 仅用于日志展示，不影响结果。
    """
    logger.warning(
        "[四影·plan] 检测到依赖环 {} → 降级为线性链（{} 个节点）",
        cycle_nodes or "?", len(subtasks),
    )
    sorted_subs = sorted(subtasks, key=lambda s: s.created_at)
    # 顺序化：第 i 个依赖第 i-1 个；这样至少保留"有先后"的语义
    for i, s in enumerate(sorted_subs):
        s.deps = [sorted_subs[i - 1].id] if i > 0 else []
    return sorted_subs


def filter_invalid_deps(subtasks: list[Subtask]) -> int:
    """原地清洗：移除引用不存在 id 的 dep。返回清洗掉的 dep 总数。"""
    ids = {s.id for s in subtasks}
    cleaned = 0
    for s in subtasks:
        if not s.deps:
            continue
        valid = [d for d in s.deps if d in ids]
        cleaned += len(s.deps) - len(valid)
        s.deps = valid
    return cleaned


def collect_prior_results(
    subtask: Subtask,
    results: dict[str, str],
    by_id: dict[str, Subtask],
) -> list[str]:
    """给某节点收集其依赖节点的产物列表（按 deps 顺序）。

    跳过失败/跳过的节点（产物为空字符串也跳）；archon 的 prior_results
    参数签名保持 `list[str]` 兼容。
    """
    prior: list[str] = []
    for dep_id in (subtask.deps or []):
        r = results.get(dep_id, "")
        if r:
            sub = by_id.get(dep_id)
            tag = (
                f"【{sub.assignee}·subtask_id={dep_id}·{sub.description[:60]}】\n"
                if sub else f"【subtask_id={dep_id}】\n"
            )
            prior.append(f"{tag}{r}")
    return prior


def mark_downstream_skipped(
    failed_id: str,
    subtasks: list[Subtask],
    results: dict[str, str],
) -> list[str]:
    """传递性标记：任何（直接或间接）依赖失败节点的后继节点打 skipped。

    仅修改内存视图，持久化由 asmoday 在 dispatch 中负责。
    返回被标 skipped 的节点 id 列表。
    """
    ids = {s.id for s in subtasks}
    reverse: dict[str, list[str]] = {sid: [] for sid in ids}
    for s in subtasks:
        for d in (s.deps or []):
            if d in ids:
                reverse[d].append(s.id)

    skipped: list[str] = []
    stack = [failed_id]
    visited = {failed_id}
    while stack:
        u = stack.pop()
        for v in reverse.get(u, []):
            if v in visited:
                continue
            visited.add(v)
            skipped.append(v)
            results[v] = ""
            stack.append(v)
    return skipped
