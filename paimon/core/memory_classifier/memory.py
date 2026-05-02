"""L1 记忆分类器 —— `/remember` 和草神面板"+ 新建记忆"共用。

一段自然语言 → LLM 分类为 (mem_type, title, subject)。失败降级规则见
classify_memory；subject 防路径注入走 sanitize_subject。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from loguru import logger

from ._common import _parse_reconcile_json, _repair_reconcile_json


# 单条记忆上限（memory 域设计值）；超了拒收，避免记忆域被单条挤爆
MAX_REMEMBER_CHARS = 2000


_CLASSIFY_PROMPT = """\
你是记忆分类器。用户用 /remember 命令告诉派蒙一段要记住的内容。
请把内容归入以下类型之一：
- user: 用户画像 / 偏好 / 角色（"我主要用 Go"、"偏好简洁"）
- feedback: 对派蒙行为的纠正 / 规范（"不要给总结"、"用中文"）
- project: 当前项目的持久事实（"这个项目在 /xxx"、"DB 是 PostgreSQL"）
- reference: 外部资源指针（"bugs 在 Linear INGEST"、"面板 grafana.xx"）

只输出 JSON 对象，严格格式：
{"type": "user|feedback|project|reference", "title": "短标题(<=20字)", "subject": "主题词(user/feedback 用 default, project 用项目名, reference 用简短关键词)"}

不要输出任何其他文字、不要 markdown 代码块。
"""


_SUBJECT_SAFE_RE = re.compile(r"^[\w一-鿿\-]+$")


def sanitize_subject(subject: str) -> str:
    """subject 必须是简单标识符（字母/数字/下划线/中文/短横）。

    含路径字符 / 空格 / 特殊字符的一律降级到 'default'，避免 resolve_safe 抛
    + 文件系统问题。
    """
    s = (subject or "").strip() or "default"
    if ".." in s or "/" in s or "\\" in s:
        return "default"
    if not _SUBJECT_SAFE_RE.match(s):
        return "default"
    return s[:80]


async def classify_memory(
    content: str, model,
) -> tuple[str | None, str | None, str | None]:
    """LLM 分类一段内容。返回 (type, title, subject)；三者全 None 表示失败。

    失败情境（调用方负责降级）：
    - LLM 调用异常
    - 返回非合法 JSON
    - 返回不是 dict
    - 返回 type 不在允许集合 / 缺 title
    """
    messages = [
        {"role": "system", "content": _CLASSIFY_PROMPT},
        {"role": "user", "content": f"内容：\n{content}"},
    ]
    try:
        raw, usage = await model._stream_text(
            messages, component="remember", purpose="记忆分类",
        )
        await model._record_primogem("", "remember", usage, purpose="记忆分类")
    except Exception as e:
        logger.warning("[记忆分类] LLM 调用失败: {}", e)
        return None, None, None

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()

    try:
        obj = json.loads(text)
    except Exception as e:
        logger.warning("[记忆分类] JSON 解析失败: {} 原始={}", e, text[:200])
        return None, None, None

    if not isinstance(obj, dict):
        logger.warning("[记忆分类] 输出非对象: {}", type(obj).__name__)
        return None, None, None

    mem_type = obj.get("type", "")
    title = (obj.get("title") or "").strip()
    subject = (obj.get("subject") or "").strip() or "default"
    if mem_type not in ("user", "feedback", "project", "reference") or not title:
        return None, None, None
    return mem_type, title[:80], subject[:80]


def default_title(content: str, max_len: int = 30) -> str:
    """LLM 分类失败时的兜底标题：用内容前 N 字（清理控制字符）。"""
    safe = content.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return safe[:max_len]


# ============================================================
# 冲突检测：新记忆 vs 同 type 已有记忆，LLM 判一种 action
# ============================================================

# 候选上限：实际不限制，把同 type 所有记忆都送去 reconcile（遗漏一条可能
# 让新条跟它并存产生矛盾）。用户记忆累积量远低于常见模型 context，足够容纳
# 上千条；当真超过此值时也仅影响本次判决降级为 new，不影响正确性
RECONCILE_CANDIDATE_LIMIT = 10000


@dataclass
class ReconcileDecision:
    """新记忆 vs 已有记忆的冲突判决结果。

    action:
      - 'new'       —— 直接写入新条目（不相关 / 无冲突）
      - 'merge'     —— 合并到 target_id；用 merged_body / merged_title 覆盖旧条
      - 'replace'   —— 矛盾/反义：删 target_id，再写新条
      - 'duplicate' —— 完全重复：什么都不做
    """
    action: str
    target_id: str | None = None
    merged_body: str | None = None
    merged_title: str | None = None
    reason: str = ""


_RECONCILE_PROMPT = """\
你在维护一个跨会话记忆库。用户刚提交了一段新记忆内容，该类型下已经有若干条记忆。
判断【新内容】和【已有每条记忆】的关系，选一种动作：

- new       : 新内容跟已有记忆都无关；直接加入为新条目
- merge     : 新内容跟【某一条】已有记忆语义互补，【可合并成一条更完整的记忆】
              （如【喜欢蓝色】+【喜欢紫色】→【喜欢蓝色、紫色】）
- replace   : 新内容跟【某一条】已有记忆【矛盾 / 反义 / 覆盖式更新】
              （如已有【喜欢蓝色】+ 新【不喜欢蓝色】→ 删旧写新）
- duplicate : 新内容跟【某一条】已有记忆【完全重复】；不必再记

判定原则：
- 只跟【一条】已有记忆发生关系；若同时跟多条有关，挑最相关的那条
- 非【同一主题轴】上的内容都判 new（不要强行合并不相关的条目）
- merge 时，merged_body 要【整合新旧信息】，保留原意、加入新表述；不要只拼接
- merge 时，merged_title 给一个覆盖新旧的短标题（≤20 字）
- 保守倾向：拿不准是 merge 还是 new 时判 new；拿不准是 replace 还是 merge 时判 merge

【JSON 引号硬性规则 · 极其重要】
输出的 JSON string 值里【绝对不能】出现未转义的双引号 "。
若要在 reason / merged_body / merged_title 里引用记忆片段：
- 用中文方括号【xxx】、书名号《xxx》或单引号 'xxx' 包裹
- 不要写成 "xxx"（这会破坏 JSON 使整个判决被丢弃）

输出严格 JSON，不要 markdown、不要解释：
{
  "action": "new | merge | replace | duplicate",
  "target_id": "<merge/replace/duplicate 时必填：来自已有记忆列表的 id>",
  "merged_body": "<merge 时必填：合并后的完整内容，保留原有表述并纳入新表述>",
  "merged_title": "<merge 时必填：整合后的短标题，≤20 字>",
  "reason": "<一句话说明判决依据，供用户看；不要含双引号>"
}
"""


async def reconcile_memory(
    new_type: str,
    new_title: str,
    new_body: str,
    existing,  # list of Memory（同 type 的已有记忆，含 body）
    model,
) -> ReconcileDecision:
    """LLM 判新记忆是否跟已有记忆冲突 / 可合并。失败降级为 action='new'。

    调用方负责：
    - 如果 existing 为空，**不要**调本函数，直接 action='new' 写入
    - 按 action 执行对应操作（这里只出决策，不做写操作）
    """
    if not existing:
        return ReconcileDecision(action="new", reason="无已有记忆，新建")

    # 按 updated_at DESC 排序，让"最近活跃"的记忆优先进入 LLM 视野；
    # 不截断（LIMIT 上游已处理）
    candidates = sorted(
        existing, key=lambda m: getattr(m, "updated_at", 0) or 0, reverse=True,
    )

    # 拼给 LLM 看的列表：id + title + body（body 截 300 字）
    def _fmt(m):
        b = (m.body or "").strip().replace("\n", " ").replace("\r", " ")
        if len(b) > 300:
            b = b[:300] + "..."
        return {
            "id": m.id,
            "title": (m.title or "").strip(),
            "body": b,
        }

    candidates_json = json.dumps(
        [_fmt(m) for m in candidates], ensure_ascii=False, indent=2,
    )
    user_payload = (
        f"新内容类型：{new_type}\n"
        f"新内容标题：{new_title}\n"
        f"新内容正文：{new_body}\n\n"
        f"已有记忆（同类型，共 {len(candidates)} 条）：\n{candidates_json}"
    )

    messages = [
        {"role": "system", "content": _RECONCILE_PROMPT},
        {"role": "user", "content": user_payload},
    ]

    try:
        raw, usage = await model._stream_text(
            messages, component="reconcile", purpose="记忆冲突检测",
        )
        await model._record_primogem("", "reconcile", usage, purpose="记忆冲突检测")
    except Exception as e:
        logger.warning("[记忆冲突] LLM 调用失败，降级为 new: {}", e)
        return ReconcileDecision(action="new", reason=f"冲突检测失败降级：{e}")

    obj = _parse_reconcile_json(raw)
    if obj is None:
        # 一次 LLM 自修复尝试（常见：LLM 在 string value 里塞了未转义双引号）
        obj = await _repair_reconcile_json(raw, model)

    if obj is None:
        return ReconcileDecision(action="new", reason="LLM 输出解析失败，降级新建")
    if not isinstance(obj, dict):
        return ReconcileDecision(action="new", reason="LLM 输出结构异常，降级新建")

    action = obj.get("action", "")
    if action not in ("new", "merge", "replace", "duplicate"):
        logger.warning("[记忆冲突] 未知 action={} 降级为 new", action)
        return ReconcileDecision(action="new", reason=f"未知决策 {action}，降级新建")

    # target_id 校验：必须来自 candidates
    valid_ids = {m.id for m in candidates}
    target_id = (obj.get("target_id") or "").strip() or None
    if action in ("merge", "replace", "duplicate"):
        if not target_id or target_id not in valid_ids:
            logger.warning(
                "[记忆冲突] action={} 但 target_id 非法（{}），降级为 new",
                action, target_id,
            )
            return ReconcileDecision(
                action="new",
                reason=f"LLM 给了 {action} 但 target_id 非法，降级新建",
            )

    merged_body = None
    merged_title = None
    if action == "merge":
        merged_body = (obj.get("merged_body") or "").strip()
        merged_title = (obj.get("merged_title") or "").strip()
        if not merged_body or not merged_title:
            logger.warning("[记忆冲突] merge 但缺 merged_body/title，降级为 new")
            return ReconcileDecision(
                action="new",
                reason="merge 缺合并文本，降级新建",
            )
        merged_title = merged_title[:80]

    return ReconcileDecision(
        action=action,
        target_id=target_id,
        merged_body=merged_body,
        merged_title=merged_title,
        reason=(obj.get("reason") or "").strip()[:200],
    )


# ============================================================
# 高阶 API：一句话 → 分类 → 冲突检测 → 写入 / 合并 / 替换 / 去重
# ============================================================


@dataclass
class RememberOutcome:
    """一次 remember 操作的结果，面板 / CLI 都据此生成反馈。"""
    ok: bool
    action: str  # 'new' | 'merge' | 'replace' | 'duplicate' | 'failed'
    mem_type: str = ""
    subject: str = ""
    title: str = ""
    mem_id: str = ""
    target_id: str = ""       # merge/replace/duplicate 时：被操作的旧记忆 id
    target_title: str = ""    # 同上：展示旧记忆标题供提示
    reason: str = ""
    error: str = ""


async def remember_with_reconcile(
    content: str, irminsul, model, *, source: str, actor: str,
) -> RememberOutcome:
    """记忆录入高阶入口：分类 → reconcile → 按 action 落库。

    失败路径（保证面板/CLI 不崩）：
    - 分类 LLM 失败 → 用兜底类型 (user/default/前30字)
    - reconcile LLM 失败 → 降级 action='new' 写入
    - 写入异常 → RememberOutcome(ok=False, error=...)
    """
    mem_type, title, subject = await classify_memory(content, model)
    if mem_type is None:
        mem_type, subject, title = "user", "default", default_title(content)
    subject = sanitize_subject(subject)

    # 查同 type 已有记忆（候选）
    try:
        existing_metas = await irminsul.memory_list(
            mem_type=mem_type, limit=RECONCILE_CANDIDATE_LIMIT,
        )
    except Exception as e:
        logger.warning("[记忆录入] 查候选失败，降级为简单写入: {}", e)
        existing_metas = []

    # 拿带 body 的完整 Memory（meta 不含 body）
    existing: list = []
    for meta in existing_metas:
        try:
            m = await irminsul.memory_get(meta.id)
        except Exception:
            continue
        if m is not None:
            existing.append(m)

    decision = await reconcile_memory(mem_type, title, content, existing, model)

    try:
        if decision.action == "new":
            mem_id = await irminsul.memory_write(
                mem_type=mem_type, subject=subject, title=title,
                body=content, source=source, actor=actor,
            )
            return RememberOutcome(
                ok=True, action="new", mem_type=mem_type, subject=subject,
                title=title, mem_id=mem_id,
                reason=decision.reason or "作为新条目加入",
            )

        elif decision.action == "merge":
            # 合并：更新 target 的 title/body；保留原 mem_type/subject
            target = next((m for m in existing if m.id == decision.target_id), None)
            ok = await irminsul.memory_update(
                decision.target_id,
                title=decision.merged_title,
                body=decision.merged_body,
                actor=actor,
            )
            if not ok:
                logger.warning("[记忆录入] merge 更新失败，回退为新建")
                mem_id = await irminsul.memory_write(
                    mem_type=mem_type, subject=subject, title=title,
                    body=content, source=source, actor=actor,
                )
                return RememberOutcome(
                    ok=True, action="new", mem_type=mem_type, subject=subject,
                    title=title, mem_id=mem_id,
                    reason="合并目标已失效，降级新建",
                )
            return RememberOutcome(
                ok=True, action="merge", mem_type=mem_type, subject=subject,
                title=decision.merged_title or title,
                mem_id=decision.target_id,
                target_id=decision.target_id,
                target_title=(target.title if target else ""),
                reason=decision.reason or "与原记忆合并",
            )

        elif decision.action == "replace":
            # 覆盖式更新：删旧写新
            target = next((m for m in existing if m.id == decision.target_id), None)
            target_title = target.title if target else ""
            await irminsul.memory_delete(decision.target_id, actor=actor)
            mem_id = await irminsul.memory_write(
                mem_type=mem_type, subject=subject, title=title,
                body=content, source=source, actor=actor,
            )
            return RememberOutcome(
                ok=True, action="replace", mem_type=mem_type, subject=subject,
                title=title, mem_id=mem_id,
                target_id=decision.target_id,
                target_title=target_title,
                reason=decision.reason or "与原记忆矛盾，已替换",
            )

        elif decision.action == "duplicate":
            target = next((m for m in existing if m.id == decision.target_id), None)
            # 重复命中也刷新 updated_at：等于"用户再次确认这条记忆"，
            # 面板按 updated_at DESC 排序会把它跳到前面
            try:
                await irminsul.memory_update(decision.target_id, actor=actor)
            except Exception as e:
                logger.debug("[记忆录入] duplicate 刷 updated_at 失败（忽略）: {}", e)
            return RememberOutcome(
                ok=True, action="duplicate", mem_type=mem_type, subject=subject,
                title=(target.title if target else title),
                mem_id=decision.target_id,
                target_id=decision.target_id,
                target_title=(target.title if target else ""),
                reason=decision.reason or "与现有记忆重复，未重复写入",
            )

    except ValueError as e:
        return RememberOutcome(ok=False, action="failed", error=f"参数无效: {e}")
    except Exception as e:
        logger.error("[记忆录入] 写入失败: {}", e)
        return RememberOutcome(ok=False, action="failed", error=str(e))

    # 不应到达
    return RememberOutcome(ok=False, action="failed", error="未知流程错误")
