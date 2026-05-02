"""三月自检通用 helper：平台 shell 提示 + check skill 进度抽取 + 路径常量。"""
from __future__ import annotations

import platform
import time
from typing import Any


# check skill 在 target 路径写 .check/ 目录；Deep selfcheck 的 target 是项目根
_CHECK_DIR_NAME = ".check"
_CHECK_FILES = ("report.md", "candidates.jsonl", "state.json")

# 进度 watcher 轮询间隔（秒）；check skill 每轮都会重写 state.json
_PROGRESS_POLL_INTERVAL = 5.0


def _platform_exec_hint() -> str:
    """按当前平台返回给 LLM 的 shell 使用提示。

    不同平台 LLM 默认偏好的命令不同：LLM 常用 Unix 风格（find/ls/grep），
    在 Windows 下这些要么不存在要么语义迥异 → 失败 → 无法列文件 → Deep 跑空。
    在 Linux/macOS 下 Unix 命令全可用，但仍建议优先 `file_ops(list)` 获得结构化输出。
    """
    sysname = platform.system()  # 'Windows' / 'Linux' / 'Darwin'
    if sysname == "Windows":
        return (
            "当前运行环境: **Windows**（shell = PowerShell 或 cmd）\n"
            "- **列目录用 `file_ops(action=\"list\", path=...)`，禁用 shell `find`/`ls`**\n"
            "  Windows 的 `find` 语义与 Unix 完全不同（`FIND: Parameter format not correct`），\n"
            "  `cmd` 没 `ls`，PowerShell 的 `ls -la` 语法也不对 → 只会返回错误文本\n"
            "- **避免 Unix-only 命令**：find / ls -la / mkdir -p / date -u / `&&`\n"
            "  需要链式用 `;`；需要时间戳直接取消（不重要）\n"
            "- **多行 Python 脚本用文件**：`python -c \"多行...\"` 在 PowerShell 下引号\n"
            "  转义易坏；复杂逻辑用 `file_ops(write)` 写临时 .py → `exec python xxx.py`"
        )
    # Linux / macOS / 其他 POSIX
    return (
        f"当前运行环境: **{sysname}**（POSIX shell）\n"
        "- Unix 命令全可用：find / ls / grep / rg / mkdir -p / && 等\n"
        "- **列目录仍优先 `file_ops(action=\"list\", path=...)`** —— 返回结构化数组\n"
        "  比解析 shell 输出更可靠；只有需要通配/递归时才走 `find`\n"
        "- 多行 `python -c` 在 POSIX shell 正常工作，可放心用\n"
        "- 能用 `file_ops` 的不要走 `exec`（跨平台一致 + 路径安全检查）"
    )


def _extract_progress(state: Any) -> dict[str, Any]:
    """从 check skill 的 state.json 抽面板展示需要的字段（容错：缺字段默认 0/空）。

    入参容错：若 state 不是 dict（LLM 可能错写成 list/str/null），返回空 dict，
    避免调用方 watcher 打出 AttributeError 噪音日志。

    关键字段：
    - current_iteration / max_iter：当前是第几大轮，上限几轮
    - consecutive_clean / clean_iter：连续 clean 数（达 clean_iter 即停止）
    - iterations_done：已完成迭代数（= iteration_state.iterations 长度）
    - total_candidates / total_confirmed：累计候选/确认
    - severity_counts：实时 P0-P3 计数
    - modules_processed：当前已扫过的 module 列表（进度颗粒度最细的信号）
    - engine_status：哪个引擎在活跃（discovery / alignment / opportunity）
    """
    if not isinstance(state, dict):
        return {}
    it = state.get("iteration_state") or {}
    cfg = state.get("iteration_config") or {}
    cum = state.get("cumulative") or {}
    sev = state.get("severity_counts") or {}
    engines = state.get("engines") or {}
    # 子字段也做 isinstance 兜底（LLM 可能把 iteration_state 写成 list 等）
    if not isinstance(it, dict): it = {}
    if not isinstance(cfg, dict): cfg = {}
    if not isinstance(cum, dict): cum = {}
    if not isinstance(sev, dict): sev = {}
    if not isinstance(engines, dict): engines = {}
    discovery = engines.get("discovery") or {}
    if not isinstance(discovery, dict): discovery = {}

    return {
        "skill_status": state.get("status", "unknown"),  # 不跟 SelfcheckRun.status 混名
        "current_iteration": int(it.get("current_iteration", 0) or 0),
        "consecutive_clean": int(it.get("consecutive_clean", 0) or 0),
        "iterations_done": len(it.get("iterations") or []),
        "max_iter": int(cfg.get("max_iter", 0) or 0),
        "clean_iter": int(cfg.get("clean_iter", 0) or 0),
        "discovery_rounds": int(cfg.get("discovery_rounds", 0) or 0),
        "validation_rounds": int(cfg.get("validation_rounds", 0) or 0),
        "total_candidates": int(cum.get("total_candidates", 0) or 0),
        "total_confirmed": int(cum.get("total_confirmed", 0) or 0),
        "total_rejected": int(cum.get("total_rejected", 0) or 0),
        "total_deferred": int(cum.get("total_deferred", 0) or 0),
        "p0": int(sev.get("p0", 0) or 0),
        "p1": int(sev.get("p1", 0) or 0),
        "p2": int(sev.get("p2", 0) or 0),
        "p3": int(sev.get("p3", 0) or 0),
        "modules_processed": list(discovery.get("modules_processed") or []),
        "updated_at": state.get("updated_at"),
        "polled_at": time.time(),
    }
