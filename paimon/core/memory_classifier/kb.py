"""知识库（knowledge 域）自然语言入库：一段话 → LLM 判 category/topic/body → 冲突检测。

入口 remember_knowledge_with_reconcile：分类 → 查同 category 已有条目 → reconcile → 落库。
失败降级：分类失败用 misc/前 20 字 topic；reconcile 失败降级 new。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from loguru import logger

from ._common import _parse_reconcile_json, _repair_reconcile_json
from .memory import default_title


_KB_CATEGORY_SAFE_RE = re.compile(r"^[\w一-鿿\-]+$")


def sanitize_kb_segment(seg: str) -> str:
    """category / topic 的安全清洗：只保留字母数字/中文/下划线/短横。

    含 `/` `..` `\\` 或其他字符 → 降级为 'default'。
    """
    s = (seg or "").strip()
    if not s:
        return "default"
    if ".." in s or "/" in s or "\\" in s or "\x00" in s:
        return "default"
    if not _KB_CATEGORY_SAFE_RE.match(s):
        return "default"
    return s[:80]


_CLASSIFY_KB_PROMPT = """\
你是知识库分类器。用户提交了一段知识内容；你需要判定它的分类和主题。

【知识库结构】按 category / topic 两级组织：
- category: 大类（如 architecture / tech / project / api / ops / ...），**必须用英文短小标识符**（小写字母+短横）
- topic: 具体主题（可以中英混用但短小，如 claude-rate-limit / paimon-memory-domain），**不含空格**

输出严格 JSON，不要 markdown：
{"category": "<英文小分类>", "topic": "<具体主题>", "title": "<供列表展示的短标题 ≤30 字>"}

示例：
- 输入「Claude API 每分钟限流 50 次」 → {"category":"api","topic":"claude-rate-limit","title":"Claude API 限流"}
- 输入「paimon 的 memory 域跟 knowledge 域区别」 → {"category":"architecture","topic":"paimon-memory-vs-knowledge","title":"memory vs knowledge"}

【JSON 引号规则】string value 里绝对不能有未转义双引号。
"""


async def classify_knowledge(
    content: str, model,
) -> tuple[str | None, str | None, str | None]:
    """LLM 判一段知识的 (category, topic, title)。三者全 None 表示失败。"""
    messages = [
        {"role": "system", "content": _CLASSIFY_KB_PROMPT},
        {"role": "user", "content": f"内容：\n{content}"},
    ]
    try:
        raw, usage = await model._stream_text(
            messages, component="kb_remember", purpose="知识分类",
        )
        await model._record_primogem("", "kb_remember", usage, purpose="知识分类")
    except Exception as e:
        logger.warning("[知识分类] LLM 失败: {}", e)
        return None, None, None

    obj = _parse_reconcile_json(raw)
    if obj is None:
        obj = await _repair_reconcile_json(raw, model)
    if obj is None or not isinstance(obj, dict):
        return None, None, None

    category = sanitize_kb_segment(obj.get("category", ""))
    topic = sanitize_kb_segment(obj.get("topic", ""))
    title = (obj.get("title") or "").strip()[:80]
    if category == "default" and topic == "default":
        return None, None, None
    return category, topic, (title or topic)


_RECONCILE_KB_PROMPT = """\
你在维护一个知识库。用户刚提交了一段新知识，该分类下已经有若干条。
判断【新内容】和【已有每条】的关系，选一种动作：

- new       : 新内容独立；作为新条目加入
- merge     : 新内容跟【某一条】语义互补/展开；合并为一条更完整的
- replace   : 新内容跟【某一条】矛盾/覆盖式更新；删旧写新
- duplicate : 完全重复；不必再记

【JSON 引号硬性】string value 里绝对不能有未转义双引号；引用片段用 中文【xxx】

输出严格 JSON，不要 markdown、不要解释：
{
  "action": "new | merge | replace | duplicate",
  "target_topic": "<merge/replace/duplicate 时必填：已有列表里的 topic>",
  "merged_body": "<merge 时必填：合并后完整内容>",
  "reason": "<一句话理由>"
}
"""


@dataclass
class KbReconcileDecision:
    """KB 域 reconcile 判决；语义同 ReconcileDecision 但用 topic 而非 id。"""
    action: str
    target_topic: str | None = None
    merged_body: str | None = None
    reason: str = ""


async def reconcile_knowledge(
    category: str, new_body: str, existing: list[tuple[str, str]], model,
) -> KbReconcileDecision:
    """existing: list of (topic, body)。全在同一 category 下。"""
    if not existing:
        return KbReconcileDecision(action="new", reason="该分类下无已有条目，新建")

    def _fmt(t, b):
        b = (b or "").strip().replace("\n", " ").replace("\r", " ")
        if len(b) > 400:
            b = b[:400] + "..."
        return {"topic": t, "body": b}

    listing = json.dumps([_fmt(t, b) for t, b in existing], ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": _RECONCILE_KB_PROMPT},
        {"role": "user", "content": (
            f"分类：{category}\n"
            f"新内容：{new_body}\n\n"
            f"已有条目（共 {len(existing)} 条）：\n{listing}"
        )},
    ]

    try:
        raw, usage = await model._stream_text(
            messages, component="kb_remember", purpose="知识冲突检测",
        )
        await model._record_primogem("", "kb_remember", usage, purpose="知识冲突检测")
    except Exception as e:
        logger.warning("[知识冲突] LLM 失败，降级为 new: {}", e)
        return KbReconcileDecision(action="new", reason=f"冲突检测失败：{e}")

    obj = _parse_reconcile_json(raw)
    if obj is None:
        obj = await _repair_reconcile_json(raw, model)
    if obj is None or not isinstance(obj, dict):
        return KbReconcileDecision(action="new", reason="LLM 输出解析失败，降级新建")

    action = obj.get("action", "")
    if action not in ("new", "merge", "replace", "duplicate"):
        return KbReconcileDecision(action="new", reason=f"未知 {action}，降级新建")

    valid_topics = {t for t, _ in existing}
    target_topic = (obj.get("target_topic") or "").strip() or None
    if action in ("merge", "replace", "duplicate"):
        if not target_topic or target_topic not in valid_topics:
            return KbReconcileDecision(
                action="new",
                reason=f"LLM 给了 {action} 但 target_topic 非法，降级新建",
            )

    merged_body = None
    if action == "merge":
        merged_body = (obj.get("merged_body") or "").strip()
        if not merged_body:
            return KbReconcileDecision(action="new", reason="merge 缺 merged_body，降级新建")

    return KbReconcileDecision(
        action=action,
        target_topic=target_topic,
        merged_body=merged_body,
        reason=(obj.get("reason") or "").strip()[:200],
    )


@dataclass
class KbRememberOutcome:
    """KB 域 remember 结果；面板/CLI 据此渲染反馈消息。"""
    ok: bool
    action: str  # 'new' | 'merge' | 'replace' | 'duplicate' | 'failed'
    category: str = ""
    topic: str = ""
    title: str = ""
    target_topic: str = ""
    reason: str = ""
    error: str = ""


async def remember_knowledge_with_reconcile(
    content: str, irminsul, model, *, actor: str = "草神面板",
) -> KbRememberOutcome:
    """知识库一段话入库：LLM 判 category/topic → 查该 category 已有条目 → reconcile → 执行。

    失败降级：分类失败 → category='misc' topic=<前 20 字>；reconcile 失败 → new
    """
    category, topic, title = await classify_knowledge(content, model)
    if category is None:
        category = "misc"
        topic = sanitize_kb_segment(default_title(content, 20)) or "untitled"
        title = default_title(content, 30)

    # 拉同 category 下所有 topic + body
    try:
        pairs = await irminsul.knowledge_list(category)
    except Exception as e:
        logger.warning("[知识录入] 查候选失败: {}", e)
        pairs = []

    existing: list[tuple[str, str]] = []
    for cat, tp in pairs:
        try:
            body = await irminsul.knowledge_read(cat, tp)
        except Exception:
            continue
        if body is not None:
            existing.append((tp, body))

    decision = await reconcile_knowledge(category, content, existing, model)

    try:
        if decision.action == "new":
            # 若新 topic 跟已有同 topic 冲突（LLM 判 new 但却给了现存 topic）：改 topic 加后缀
            if topic in {t for t, _ in existing}:
                topic = f"{topic}-{int(len(existing)) + 1}"
            await irminsul.knowledge_write(category, topic, content, actor=actor)
            return KbRememberOutcome(
                ok=True, action="new",
                category=category, topic=topic, title=title,
                reason=decision.reason or "作为新条目加入",
            )

        elif decision.action == "merge":
            # 写入合并内容到 target_topic；新 topic 不再新建
            await irminsul.knowledge_write(
                category, decision.target_topic,
                decision.merged_body, actor=actor,
            )
            return KbRememberOutcome(
                ok=True, action="merge",
                category=category, topic=decision.target_topic,
                title=decision.target_topic,
                target_topic=decision.target_topic,
                reason=decision.reason or "与原条合并",
            )

        elif decision.action == "replace":
            # 删 target_topic，写新内容到分类下（新 topic）
            await irminsul.knowledge_delete(
                category, decision.target_topic, actor=actor,
            )
            if topic == decision.target_topic:
                topic = f"{topic}-new"  # 避免重写同名
            await irminsul.knowledge_write(category, topic, content, actor=actor)
            return KbRememberOutcome(
                ok=True, action="replace",
                category=category, topic=topic, title=title,
                target_topic=decision.target_topic,
                reason=decision.reason or "与原条矛盾，已替换",
            )

        elif decision.action == "duplicate":
            return KbRememberOutcome(
                ok=True, action="duplicate",
                category=category, topic=decision.target_topic,
                title=decision.target_topic,
                target_topic=decision.target_topic,
                reason=decision.reason or "与现有条目重复，未重复写入",
            )

    except Exception as e:
        logger.error("[知识录入] 写入失败: {}", e)
        return KbRememberOutcome(ok=False, action="failed", error=str(e))

    return KbRememberOutcome(ok=False, action="failed", error="未知流程错误")
