"""L1 记忆分类器 —— `/remember` 和草神面板"+ 新建记忆"共用。

一段自然语言 → LLM 分类为 (mem_type, title, subject)。失败降级规则见
classify_memory；subject 防路径注入走 sanitize_subject。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from loguru import logger


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


def _parse_reconcile_json(raw: str) -> dict | None:
    """从 LLM 原始输出抠出 JSON；含 ``` 代码块时剥壳。失败返回 None。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError as e:
        logger.debug("[记忆冲突] 首次 JSON 解析失败（尝试修复）: {} 原始={}", e, text[:200])
        return None


_REPAIR_PROMPT = """\
你刚输出的 JSON 无法解析。常见错误是 string value 里含未转义双引号。
请重新输出**严格合法**的 JSON，同样的字段结构。

要求：
- 不要 markdown 代码块、不要解释
- string value 里的双引号必须改为中文【】或《》或单引号 'xxx'
- 只输出 JSON 本身
"""


async def _repair_reconcile_json(raw: str, model) -> dict | None:
    """LLM 自修复：原输出 + 错误信息扔回去，让 LLM 重新生成合法 JSON。

    失败场景才触发，不影响正常路径开销。失败就 None，调用方降级 new。
    """
    messages = [
        {"role": "system", "content": _REPAIR_PROMPT},
        {"role": "user", "content": f"原输出（需修复）：\n{raw[:2000]}"},
    ]
    try:
        fixed_raw, usage = await model._stream_text(
            messages, component="reconcile", purpose="JSON 修复",
        )
        await model._record_primogem("", "reconcile", usage, purpose="JSON 修复")
    except Exception as e:
        logger.warning("[记忆冲突] JSON 修复 LLM 调用失败: {}", e)
        return None
    return _parse_reconcile_json(fixed_raw)


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


# ============================================================
# 周期聚合（记忆整理）：批量重整一个 type 的所有记忆
# ============================================================

# 全局重入 flag：cron + 面板按钮共用，避免并发双跑
_HYGIENE_RUNNING = False


def is_hygiene_running() -> bool:
    return _HYGIENE_RUNNING


@dataclass
class HygieneStats:
    mem_type: str
    before: int = 0
    after: int = 0
    merged: int = 0
    deleted: int = 0
    skipped: int = 0  # LLM 未动的（keep）
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class HygieneReport:
    started_at: float
    finished_at: float
    trigger: str  # 'cron' | 'manual'
    stats: list  # list[HygieneStats]
    aborted: str = ""  # 非空 = 整体异常跳过

    @property
    def total_merged(self) -> int:
        return sum(s.merged for s in self.stats)

    @property
    def total_deleted(self) -> int:
        return sum(s.deleted for s in self.stats)


_HYGIENE_PROMPT = """\
你在重整一个【{mem_type}】类跨会话记忆库。下面列出了全部 N 条记忆，
请分析并生成整理操作计划：找出可合并的、矛盾/过时的、完全重复的。

动作类型：
- merge  : 多条（2 条及以上）讲同一件事或互补 → 合并成一条；保留 ids 列表
- delete : 这条是冗余的（跟其他某条完全重复，或明显过时矛盾）→ 删除

原则：
- 保守：拿不准就不动（不出现在计划里即为 keep）
- merge 要保留所有原意，不要丢信息；merged_body 要是一条流畅完整的记忆
- delete 必须有明确理由（冗余或矛盾），不要删独立意义的条目
- 不要处理同一条 id 两次（不要让一条 id 同时出现在 merge 和 delete）

【JSON 引号规则】string value 里绝对不能有未转义双引号；引用片段用 中文【xxx】

输出严格 JSON，不要 markdown / 解释：
{{
  "operations": [
    {{
      "action": "merge",
      "ids": ["<id1>", "<id2>", ...],
      "merged_title": "<整合后标题 ≤20 字>",
      "merged_body": "<整合后完整内容>",
      "reason": "<一句说明>"
    }},
    {{
      "action": "delete",
      "ids": ["<id>"],
      "reason": "<一句说明>"
    }}
  ]
}}

如果当前记忆都健康无需整理，输出 {{"operations": []}}。
"""


async def _analyze_hygiene(
    mem_type: str, memories: list, model,
) -> list[dict]:
    """LLM 批量分析记忆，返回操作计划（list of dict）。失败返回空列表。"""
    if len(memories) < 2:
        return []

    def _fmt(m):
        b = (m.body or "").strip().replace("\n", " ").replace("\r", " ")
        if len(b) > 300:
            b = b[:300] + "..."
        return {"id": m.id, "title": (m.title or "").strip(), "body": b}

    listing = json.dumps([_fmt(m) for m in memories], ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": _HYGIENE_PROMPT.format(mem_type=mem_type)},
        {"role": "user", "content": f"全部 {len(memories)} 条记忆：\n{listing}"},
    ]

    try:
        raw, usage = await model._stream_text(
            messages, component="hygiene", purpose="记忆批量整理",
        )
        await model._record_primogem("", "hygiene", usage, purpose="记忆批量整理")
    except Exception as e:
        logger.warning("[记忆整理] LLM 失败 type={}: {}", mem_type, e)
        return []

    obj = _parse_reconcile_json(raw)
    if obj is None:
        # 复用修复流程
        obj = await _repair_reconcile_json(raw, model)
    if obj is None or not isinstance(obj, dict):
        logger.warning("[记忆整理] 解析失败 type={}", mem_type)
        return []

    ops = obj.get("operations")
    if not isinstance(ops, list):
        return []
    return ops


async def _apply_hygiene_plan(
    mem_type: str,
    memories: list,
    ops: list[dict],
    irminsul,
    actor: str = "草神·记忆整理",
) -> HygieneStats:
    """按操作计划执行：merge → update 第一条 + 删剩余；delete → 删。

    已处理过的 id 登记到 touched 集合，避免多动作冲突。
    """
    stats = HygieneStats(mem_type=mem_type, before=len(memories))
    by_id = {m.id: m for m in memories}
    touched: set[str] = set()

    for op in ops:
        action = op.get("action", "")
        ids = op.get("ids") or []
        if not isinstance(ids, list) or not ids:
            stats.skipped += 1
            continue
        # id 必须在候选集内且未被动过
        valid_ids = [i for i in ids if i in by_id and i not in touched]
        if not valid_ids:
            stats.errors.append(f"op {action} ids 全无效或已动过: {ids}")
            continue

        try:
            if action == "merge":
                if len(valid_ids) < 2:
                    stats.skipped += 1
                    continue
                merged_title = (op.get("merged_title") or "").strip()[:80]
                merged_body = (op.get("merged_body") or "").strip()
                if not merged_title or not merged_body:
                    stats.errors.append("merge 缺 merged_title/body，跳过")
                    continue
                keeper_id = valid_ids[0]
                await irminsul.memory_update(
                    keeper_id,
                    title=merged_title, body=merged_body,
                    actor=actor,
                )
                touched.add(keeper_id)
                for drop_id in valid_ids[1:]:
                    await irminsul.memory_delete(drop_id, actor=actor)
                    touched.add(drop_id)
                stats.merged += 1
                stats.deleted += len(valid_ids) - 1

            elif action == "delete":
                for drop_id in valid_ids:
                    await irminsul.memory_delete(drop_id, actor=actor)
                    touched.add(drop_id)
                    stats.deleted += 1
            else:
                stats.errors.append(f"未知 action: {action}")
        except Exception as e:
            stats.errors.append(f"{action} {valid_ids}: {e}")
            logger.warning("[记忆整理] 操作失败 action={} ids={} err={}", action, valid_ids, e)

    stats.after = stats.before - stats.deleted
    return stats


async def run_hygiene(
    irminsul, model, *, trigger: str = "manual",
) -> HygieneReport:
    """对全部 4 种 mem_type 跑一轮记忆整理。写 push_archive 审计。

    trigger: 'cron' | 'manual'，仅记录用。
    重入保护：并发调用只第一个生效，其余立即返回 aborted 报告。
    """
    global _HYGIENE_RUNNING
    import time as _time

    if _HYGIENE_RUNNING:
        return HygieneReport(
            started_at=_time.time(), finished_at=_time.time(),
            trigger=trigger, stats=[],
            aborted="已有整理任务在跑，本次跳过",
        )

    _HYGIENE_RUNNING = True
    started = _time.time()
    all_stats: list[HygieneStats] = []

    try:
        for mem_type in ("user", "feedback", "project", "reference"):
            try:
                metas = await irminsul.memory_list(
                    mem_type=mem_type, limit=RECONCILE_CANDIDATE_LIMIT,
                )
            except Exception as e:
                logger.warning("[记忆整理] 查 {} 失败: {}", mem_type, e)
                continue
            if len(metas) < 2:
                all_stats.append(HygieneStats(mem_type=mem_type, before=len(metas), after=len(metas)))
                continue

            full = []
            for meta in metas:
                try:
                    m = await irminsul.memory_get(meta.id)
                except Exception:
                    continue
                if m is not None:
                    full.append(m)

            ops = await _analyze_hygiene(mem_type, full, model)
            stats = await _apply_hygiene_plan(mem_type, full, ops, irminsul)
            all_stats.append(stats)
            logger.info(
                "[记忆整理] type={} before={} after={} merged={} deleted={} errors={}",
                mem_type, stats.before, stats.after,
                stats.merged, stats.deleted, len(stats.errors),
            )

    finally:
        _HYGIENE_RUNNING = False

    finished = _time.time()
    report = HygieneReport(
        started_at=started, finished_at=finished,
        trigger=trigger, stats=all_stats,
    )

    # 审计：写 push_archive 供面板查看
    try:
        duration = finished - started
        lines = [
            f"# 🧹 记忆整理 · {trigger}",
            "",
            f"**耗时**：{duration:.1f}s · **合并**：{report.total_merged} 次 · **删除**：{report.total_deleted} 条",
            "",
        ]
        for s in all_stats:
            lines.append(
                f"- **{s.mem_type}**：{s.before} → {s.after} 条"
                + (f"（合并 {s.merged}、删除 {s.deleted}）" if (s.merged or s.deleted) else "（无变化）")
            )
            for err in s.errors[:3]:
                lines.append(f"  - ⚠️ {err}")
        await irminsul.push_archive_create(
            source=f"草神·记忆整理·{trigger}",
            actor="草神",
            message_md="\n".join(lines),
            channel_name="webui", chat_id="webui-push",
            extra={"merged": report.total_merged, "deleted": report.total_deleted},
        )
    except Exception as e:
        logger.warning("[记忆整理] 写 push_archive 失败（不影响整理结果）: {}", e)

    return report


# ============================================================
# 方案 D：注册 memory_hygiene 周期任务类型
# ============================================================


# ============================================================
# 知识库（knowledge 域）自然语言入库：一段话 → LLM 判 category/topic/body → 冲突检测
# ============================================================


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


# ============================================================
# 知识库整理（knowledge 域批量聚合/去重）—— 跟 memory hygiene 平行
# ============================================================

_HYGIENE_KB_RUNNING = False


def is_kb_hygiene_running() -> bool:
    return _HYGIENE_KB_RUNNING


_HYGIENE_KB_PROMPT = """\
你在重整一个知识库的一个分类（category）下的全部条目。找出可合并 / 冗余 / 矛盾的。

动作：
- merge  : 多条（≥2）讲同一主题或互补 → 合并为一条；保留 topics 列表
- delete : 这条已冗余（跟其他某条重复 / 明显过时）→ 删除

原则：
- 保守：拿不准不动（不列入操作即为 keep）
- merge 合并要保留全部原意，merged_body 是一条流畅完整的文本
- merged_topic 是一个简洁新主题名（英文小写 + 短横），若跟某旧 topic 一样那就沿用
- 不要一条 topic 同时出现在多个操作里

【JSON 引号】string value 里不能有未转义双引号；引用片段用【xxx】

输出严格 JSON：
{{
  "operations": [
    {{"action":"merge","topics":["<t1>","<t2>",...],"merged_topic":"<新/旧 topic>","merged_body":"<完整内容>","reason":"..."}},
    {{"action":"delete","topics":["<t>"],"reason":"..."}}
  ]
}}

若该分类已经干净无需整理，输出 {{"operations": []}}。
"""


async def _analyze_kb_hygiene(category, entries, model):
    if len(entries) < 2:
        return []
    def _fmt(t, b):
        b = (b or "").strip().replace("\n", " ").replace("\r", " ")
        if len(b) > 400:
            b = b[:400] + "..."
        return {"topic": t, "body": b}
    listing = json.dumps([_fmt(t, b) for t, b in entries], ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": _HYGIENE_KB_PROMPT},
        {"role": "user", "content": f"分类：{category}\n该分类下全部 {len(entries)} 条：\n{listing}"},
    ]
    try:
        raw, usage = await model._stream_text(messages, component="kb_hygiene", purpose="知识批量整理")
        await model._record_primogem("", "kb_hygiene", usage, purpose="知识批量整理")
    except Exception as e:
        logger.warning("[知识整理] LLM 失败 category={}: {}", category, e)
        return []
    obj = _parse_reconcile_json(raw)
    if obj is None:
        obj = await _repair_reconcile_json(raw, model)
    if obj is None or not isinstance(obj, dict):
        return []
    ops = obj.get("operations")
    return ops if isinstance(ops, list) else []


async def _apply_kb_hygiene_plan(category, entries, ops, irminsul, actor="草神·知识整理"):
    stats = HygieneStats(mem_type=f"kb/{category}", before=len(entries))
    existing_topics = {t for t, _ in entries}
    touched: set[str] = set()
    for op in ops:
        action = op.get("action", "")
        topics = op.get("topics") or []
        if not isinstance(topics, list) or not topics:
            stats.skipped += 1
            continue
        valid = [t for t in topics if t in existing_topics and t not in touched]
        if not valid:
            stats.errors.append(f"op {action} topics 全无效或已动过: {topics}")
            continue
        try:
            if action == "merge":
                if len(valid) < 2:
                    stats.skipped += 1
                    continue
                merged_topic = sanitize_kb_segment((op.get("merged_topic") or "").strip())
                merged_body = (op.get("merged_body") or "").strip()
                if not merged_body:
                    stats.errors.append("merge 缺 merged_body，跳过")
                    continue
                if merged_topic == "default":
                    merged_topic = valid[0]
                await irminsul.knowledge_write(category, merged_topic, merged_body, actor=actor)
                touched.add(merged_topic)
                for drop in valid:
                    if drop == merged_topic:
                        continue
                    await irminsul.knowledge_delete(category, drop, actor=actor)
                    touched.add(drop)
                stats.merged += 1
                stats.deleted += len([t for t in valid if t != merged_topic])
            elif action == "delete":
                for drop in valid:
                    await irminsul.knowledge_delete(category, drop, actor=actor)
                    touched.add(drop)
                    stats.deleted += 1
            else:
                stats.errors.append(f"未知 action: {action}")
        except Exception as e:
            stats.errors.append(f"{action} {valid}: {e}")
            logger.warning("[知识整理] 失败 action={} topics={} err={}", action, valid, e)
    stats.after = stats.before - stats.deleted
    return stats


async def run_kb_hygiene(irminsul, model, *, trigger="manual"):
    """知识库按 category 分别跑整理；独立于 memory hygiene 的重入 flag。"""
    global _HYGIENE_KB_RUNNING
    import time as _time

    if _HYGIENE_KB_RUNNING:
        return HygieneReport(
            started_at=_time.time(), finished_at=_time.time(),
            trigger=trigger, stats=[],
            aborted="已有知识整理任务在跑，本次跳过",
        )

    _HYGIENE_KB_RUNNING = True
    started = _time.time()
    all_stats: list[HygieneStats] = []

    try:
        try:
            pairs = await irminsul.knowledge_list()
        except Exception as e:
            logger.warning("[知识整理] 列目录失败: {}", e)
            pairs = []
        by_cat: dict[str, list[str]] = {}
        for cat, tp in pairs:
            by_cat.setdefault(cat, []).append(tp)

        for cat, topics in sorted(by_cat.items()):
            if len(topics) < 2:
                all_stats.append(HygieneStats(mem_type=f"kb/{cat}", before=len(topics), after=len(topics)))
                continue
            entries = []
            for tp in topics:
                try:
                    body = await irminsul.knowledge_read(cat, tp)
                except Exception:
                    continue
                if body is not None:
                    entries.append((tp, body))
            ops = await _analyze_kb_hygiene(cat, entries, model)
            stats = await _apply_kb_hygiene_plan(cat, entries, ops, irminsul)
            all_stats.append(stats)
            logger.info(
                "[知识整理] category={} before={} after={} merged={} deleted={} errors={}",
                cat, stats.before, stats.after,
                stats.merged, stats.deleted, len(stats.errors),
            )
    finally:
        _HYGIENE_KB_RUNNING = False

    finished = _time.time()
    report = HygieneReport(started_at=started, finished_at=finished, trigger=trigger, stats=all_stats)

    try:
        duration = finished - started
        lines = [
            f"# 🧹 知识库整理 · {trigger}",
            "",
            f"**耗时**：{duration:.1f}s · **合并**：{report.total_merged} 次 · **删除**：{report.total_deleted} 条",
            "",
        ]
        for s in all_stats:
            lines.append(
                f"- **{s.mem_type}**：{s.before} → {s.after} 条"
                + (f"（合并 {s.merged}、删除 {s.deleted}）" if (s.merged or s.deleted) else "（无变化）")
            )
            for err in s.errors[:3]:
                lines.append(f"  - ⚠️ {err}")
        await irminsul.push_archive_create(
            source=f"草神·知识整理·{trigger}",
            actor="草神",
            message_md="\n".join(lines),
            channel_name="webui", chat_id="webui-push",
            extra={"merged": report.total_merged, "deleted": report.total_deleted},
        )
    except Exception as e:
        logger.warning("[知识整理] 写 push_archive 失败: {}", e)

    return report


# ============================================================
# 方案 D：注册两个 hygiene 周期任务类型
# ============================================================


def register_task_types() -> None:
    """由 bootstrap 启动时调一次：memory_hygiene + kb_hygiene。"""
    from paimon.foundation import task_types

    async def _desc_mem(_sid, _irm) -> str:
        return "记忆整理（批量合并/去重）"

    async def _dispatch_mem(task, state) -> None:
        if not state.irminsul or not state.model:
            logger.error("[草神·记忆整理] irminsul / model 未就绪，跳过")
            return
        await run_hygiene(state.irminsul, state.model, trigger="cron")

    task_types.register(task_types.TaskTypeMeta(
        task_type="memory_hygiene",
        display_label="草神·记忆整理",
        manager_panel="/knowledge",
        icon="broom",
        description_builder=_desc_mem,
        anchor_builder=None,
        dispatcher=_dispatch_mem,
    ))

    async def _desc_kb(_sid, _irm) -> str:
        return "知识库整理（按分类合并/去重）"

    async def _dispatch_kb(task, state) -> None:
        if not state.irminsul or not state.model:
            logger.error("[草神·知识整理] irminsul / model 未就绪，跳过")
            return
        await run_kb_hygiene(state.irminsul, state.model, trigger="cron")

    task_types.register(task_types.TaskTypeMeta(
        task_type="kb_hygiene",
        display_label="草神·知识整理",
        manager_panel="/knowledge",
        icon="broom",
        description_builder=_desc_kb,
        anchor_builder=None,
        dispatcher=_dispatch_kb,
    ))
