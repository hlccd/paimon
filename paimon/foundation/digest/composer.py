"""DigestSpec + 三个 render 函数。

各神调用方式：
    from paimon.foundation.digest import DigestSpec, render_cluster_prompt, ...

    SPEC = DigestSpec(actor="风神·巴巴托斯", domain="舆情新闻", ...)
    cluster_system = render_cluster_prompt(SPEC)        # 聚类 LLM 的 system
    analyze_system = render_analyze_prompt(SPEC)        # 事件分析 LLM 的 system
    digest_system  = render_digest_prompt(SPEC)         # 日报合成 LLM 的 system

注意 DIGEST_TEMPLATE 里有两组花括号占位符：
- spec 的 {actor}/{domain}/{digest_focus}/{regular_examples}/{advice_examples} 在 render 时一次性 .format 解决
- {{query}} / {{n}}（双花括号转义）保留给调用方在生成具体一份日报时再 .format 注入
"""
from __future__ import annotations

from dataclasses import dataclass

from .prompts import ANALYZE_TEMPLATE, CLUSTER_TEMPLATE, DIGEST_TEMPLATE


# 默认 severity 方案（风神舆情用）；其他神可在 spec.severity_scheme 覆写
DEFAULT_SEVERITY_SCHEME = """\
  * p0 = 立即推送（重大违法 / 大规模事故 / 行业级冲击 / 涉及生命安全）
  * p1 = 当日重要（行业争议焦点 / 重要发布 / 政策变更 / 重大财务事件）
  * p2 = 常规关注（产品更新 / 一般报道 / 例行声明）
  * p3 = 背景信息（综述 / 历史复盘 / 边角条目）"""


@dataclass(frozen=True)
class DigestSpec:
    """各神领域适配规格。

    必填字段（高频差异，必须各神自己写）：
      actor             "风神·巴巴托斯" / "岩神·钟离" / "水神·芙宁娜" / "草神·纳西妲"
      domain            "舆情新闻" / "理财金融" / "游戏娱乐" / "科技前沿"
      item_kind         "新闻条目" / "股票变化记录" / "游戏资讯" / "论文摘要"
      entity_kinds      "人物 / 公司 / 产品 / 地点" / "股票代码 / 行业 / 公司" 等
      cluster_examples  聚类合并示例（领域具体；3-5 行）
      digest_focus      日报关注点（"事件影响 + 整体情感倾向" / "按行业聚合 + 仓位建议"）
      regular_examples  P2/P3 折叠归纳示例文本（如"产品迭代 / 例行公告"）
      advice_examples   "关注建议"段示例（如"明日看哪个 benchmark"）

    可选字段（低频差异，默认沿用风神方案）：
      severity_scheme   严重度判定标准；岩神可改为"涨跌幅 ≥ X% 为 P0"等
    """

    actor: str
    domain: str
    item_kind: str
    entity_kinds: str
    cluster_examples: str
    digest_focus: str
    regular_examples: str
    advice_examples: str
    severity_scheme: str = DEFAULT_SEVERITY_SCHEME


def render_cluster_prompt(spec: DigestSpec) -> str:
    """渲染聚类 system prompt。"""
    return CLUSTER_TEMPLATE.format(
        actor=spec.actor,
        domain=spec.domain,
        item_kind=spec.item_kind,
        entity_kinds=spec.entity_kinds,
        cluster_examples=spec.cluster_examples,
    )


def render_analyze_prompt(spec: DigestSpec) -> str:
    """渲染事件分析 system prompt。"""
    return ANALYZE_TEMPLATE.format(
        actor=spec.actor,
        domain=spec.domain,
        digest_focus=spec.digest_focus,
        entity_kinds=spec.entity_kinds,
        severity_scheme=spec.severity_scheme,
    )


def render_digest_prompt(spec: DigestSpec) -> str:
    """渲染日报合成 system prompt。

    返回的字符串还含 `{query}` / `{n}` 两个占位符，调用方需再 .format 注入：
        digest_system = render_digest_prompt(spec)
        actual_system = digest_system.format(query=sub.query, n=len(events))
    """
    return DIGEST_TEMPLATE.format(
        actor=spec.actor,
        domain=spec.domain,
        digest_focus=spec.digest_focus,
        regular_examples=spec.regular_examples,
        advice_examples=spec.advice_examples,
    )
