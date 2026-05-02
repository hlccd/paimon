"""派蒙运行时常量 + 状态守卫：state 校验、压缩阈值。被 chat 子包多模块共用。"""
from __future__ import annotations


def _require_runtime():
    """读取 cfg / session_mgr / model；任一未就绪 → RuntimeError 终止当前流程。"""
    from paimon.state import state
    cfg = state.cfg
    session_mgr = state.session_mgr
    model = state.model
    if not cfg or not session_mgr or not model:
        raise RuntimeError("运行时状态未初始化")
    return cfg, session_mgr, model


# 压缩 safety buffer（给压缩请求自己 + 各种重试留空间）
_COMPRESS_SAFETY_BUFFER_TOKENS = 8000


def _effective_compress_threshold_pct(cfg) -> float:
    """压缩阈值：取用户配置的百分比 和 "扣除 max_output + safety_buffer 后的安全百分比" 的更小值。

    参考 claude-code autoCompact：阈值必须给 summary 输出预留预算，
    否则压缩请求自己就 prompt_too_long。
    """
    percent = float(cfg.context_compress_threshold_pct)
    if cfg.context_window_tokens <= 0:
        return percent
    headroom = cfg.max_tokens + _COMPRESS_SAFETY_BUFFER_TOKENS
    safe_pct = 100.0 - (headroom / cfg.context_window_tokens * 100.0)
    return min(percent, max(safe_pct, 0.0))
