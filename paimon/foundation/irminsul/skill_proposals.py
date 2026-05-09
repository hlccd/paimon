"""Skill 自进化提案域 —— 世界树域 16

唯一写入者：四影（生执 propose / 死执 review_proposal / 派蒙审批与空执落盘）。

承载：四影从一次任务复盘里凝练出的 skill 草案 + 死执质量审 + 等用户审。
**空执**才是真正的 skill 写盘者；此域只是「提案 → 审批」中转，apply 后由空执
读 approved 提案、落 `skills/<name>/SKILL.md`、注册 skill_declarations。

存储：纯 SQLite 单表（草案文本量小 ≤ 4KB，不外置文件）。
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field

import aiosqlite
from loguru import logger


# 状态机常量（避免散字符串）
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_APPLIED = "applied"

VERDICT_PASS = "pass"
VERDICT_NEEDS_REVISE = "needs_revise"
VERDICT_REJECT = "reject"

# 未落盘 pending 队列上限：超过即移除最早的（LRU），防 LLM 失控刷 spam 占满表
MAX_PENDING_QUEUE = 25


@dataclass
class SkillProposal:
    id: str
    name: str
    kind: str = "new"                          # 'new' | 'improve'
    target_skill: str = ""                     # improve 时指向已存在 skill 名
    description: str = ""
    triggers: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    rationale: str = ""
    proposed_by_session: str = ""
    proposed_by_task: str = ""
    review_verdict: str = ""                   # '' | 'pass' | 'needs_revise' | 'reject'
    review_notes: str = ""
    status: str = STATUS_PENDING
    decided_by: str = ""
    decision_notes: str = ""
    decided_at: float | None = None
    applied_at: float | None = None
    user_feedback: str = ""                    # 用户最近一次给草案的建议（驱动 revise）
    revision_count: int = 0                    # 被用户提建议重写过的次数
    revising_at: float | None = None           # 正在生执 revise 中的开始时间戳；None = 空闲
    created_at: float = 0.0
    updated_at: float = 0.0


class SkillProposalRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def create(
        self, *,
        name: str,
        kind: str = "new",
        target_skill: str = "",
        description: str = "",
        triggers: str = "",
        system_prompt: str = "",
        allowed_tools: list[str] | None = None,
        rationale: str = "",
        proposed_by_session: str = "",
        proposed_by_task: str = "",
        actor: str,
    ) -> str:
        """新建提案，返回 proposal id。

        校验：
        - name / system_prompt 非空
        - kind ∈ {'new', 'improve'}；'improve' 时 target_skill 必填
        - **去重**：同 name + 同 kind 已存在 status=pending 提案 → 返该 id 不新建
          （避免模型在多轮反思里反复 propose 同一个 skill 形成 spam）
        """
        if not name.strip():
            raise ValueError("skill 提案 name 不能为空")
        if not system_prompt.strip():
            raise ValueError("skill 提案 system_prompt 不能为空")
        if kind not in ("new", "improve"):
            raise ValueError(f"非法 kind: {kind!r}（仅允许 new / improve）")
        if kind == "improve" and not target_skill.strip():
            raise ValueError("kind='improve' 时 target_skill 必填")

        # 去重：已有 pending 同名同 kind → 直接返已存在 id（不算新增，不占队列名额）
        async with self._db.execute(
            "SELECT id FROM skill_proposals "
            "WHERE name = ? AND kind = ? AND status = ? LIMIT 1",
            (name, kind, STATUS_PENDING),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            logger.info(
                "[世界树] {}·Skill 提案已存在 pending 同名  {} → 复用 {}",
                actor, name, existing[0],
            )
            return existing[0]

        # 队列上限：pending 提案数 ≥ MAX_PENDING_QUEUE → 删最早的，腾出 1 个名额。
        # 严格按 created_at ASC LRU 删，不区分 verdict 状态（用户原始诉求）。
        async with self._db.execute(
            "SELECT COUNT(*) FROM skill_proposals WHERE status = ?",
            (STATUS_PENDING,),
        ) as cur:
            n_pending_row = await cur.fetchone()
        n_pending = (n_pending_row[0] if n_pending_row else 0) or 0
        if n_pending >= MAX_PENDING_QUEUE:
            # 一次可能要删多条（防 schema 历史遗留超额），保证插入新条后 ≤ MAX
            n_to_evict = n_pending - MAX_PENDING_QUEUE + 1
            async with self._db.execute(
                "SELECT id, name FROM skill_proposals WHERE status = ? "
                "ORDER BY created_at ASC LIMIT ?",
                (STATUS_PENDING, n_to_evict),
            ) as cur:
                evict_rows = await cur.fetchall()
            for eid, ename in evict_rows:
                await self._db.execute(
                    "DELETE FROM skill_proposals WHERE id = ?", (eid,),
                )
                logger.info(
                    "[世界树] {}·Skill 提案队列满（{}/{}），LRU 移除最早 {} ({})",
                    actor, n_pending, MAX_PENDING_QUEUE, ename, eid,
                )

        prop_id = uuid.uuid4().hex[:12]
        now = time.time()
        await self._db.execute(
            "INSERT INTO skill_proposals "
            "(id, name, kind, target_skill, description, triggers, system_prompt, "
            " allowed_tools, rationale, proposed_by_session, proposed_by_task, "
            " status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                prop_id, name, kind, target_skill, description, triggers, system_prompt,
                json.dumps(allowed_tools or [], ensure_ascii=False),
                rationale, proposed_by_session, proposed_by_task,
                STATUS_PENDING, now, now,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·Skill 提案落档  {} ({}, kind={})",
            actor, name, prop_id, kind,
        )
        return prop_id

    async def get(self, prop_id: str) -> SkillProposal | None:
        async with self._db.execute(
            _SELECT_SQL + " WHERE id = ?", (prop_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_proposal(row) if row else None

    async def list(
        self, *,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[SkillProposal]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"{_SELECT_SQL} {where} "
            "ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_proposal(r) for r in rows]

    async def set_review_verdict(
        self, prop_id: str, verdict: str, notes: str = "", *, actor: str,
    ) -> bool:
        """死执质量审写 verdict + notes。verdict='reject' 时同步把 status 设 rejected。"""
        if verdict not in (VERDICT_PASS, VERDICT_NEEDS_REVISE, VERDICT_REJECT):
            raise ValueError(f"非法 verdict: {verdict!r}")
        now = time.time()
        if verdict == VERDICT_REJECT:
            # 死执直拒 → status 也置 rejected
            await self._db.execute(
                "UPDATE skill_proposals "
                "SET review_verdict = ?, review_notes = ?, status = ?, "
                "    decided_by = ?, decided_at = ?, updated_at = ? "
                "WHERE id = ?",
                (verdict, notes, STATUS_REJECTED, "auto", now, now, prop_id),
            )
        else:
            await self._db.execute(
                "UPDATE skill_proposals "
                "SET review_verdict = ?, review_notes = ?, updated_at = ? "
                "WHERE id = ?",
                (verdict, notes, now, prop_id),
            )
        await self._db.commit()
        logger.info(
            "[世界树] {}·Skill 提案审  {} verdict={}", actor, prop_id, verdict,
        )
        return True

    async def approve(
        self, prop_id: str, *, decided_by: str = "user", actor: str,
    ) -> bool:
        """用户同意 → status=approved（等空执 apply）。

        质量门保护：
        - 仅 status=pending 可 approve（已 rejected/applied 不可回流）
        - 死执 review_verdict='needs_revise' 时**不允许** approve
          （死执说要修，必须重产再审；用户硬批等于绕过质量门）
        - review_verdict='reject' 走 set_review_verdict 已联动 status=rejected，
          自然被 status=pending 卡住
        """
        now = time.time()
        cur = await self._db.execute(
            "UPDATE skill_proposals "
            "SET status = ?, decided_by = ?, decided_at = ?, updated_at = ? "
            "WHERE id = ? AND status = ? AND review_verdict != ? "
            "AND revising_at IS NULL",
            (
                STATUS_APPROVED, decided_by, now, now,
                prop_id, STATUS_PENDING, VERDICT_NEEDS_REVISE,
            ),
        )
        await self._db.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.info("[世界树] {}·Skill 提案 approve  {}", actor, prop_id)
        else:
            logger.warning(
                "[世界树] {}·Skill 提案 approve 被拒  {}（已非 pending / 死执要求修订 / 正在重写中）",
                actor, prop_id,
            )
        return ok

    async def reject(
        self, prop_id: str, notes: str = "", *,
        decided_by: str = "user", actor: str,
    ) -> bool:
        """拒绝（用户主动 / 死执直拒复用）。

        保护：仅 status=pending 时可拒。已 applied 提案是已落盘 skill 的依据，
        不允许打回 rejected（防误操作清空历史）。
        """
        now = time.time()
        cur = await self._db.execute(
            "UPDATE skill_proposals "
            "SET status = ?, decided_by = ?, decision_notes = ?, "
            "    decided_at = ?, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (STATUS_REJECTED, decided_by, notes, now, now, prop_id, STATUS_PENDING),
        )
        await self._db.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.info("[世界树] {}·Skill 提案 reject  {}", actor, prop_id)
        else:
            logger.warning(
                "[世界树] {}·Skill 提案 reject 被拒  {}（已非 pending）",
                actor, prop_id,
            )
        return ok

    async def submit_user_feedback(
        self, prop_id: str, feedback: str, *, actor: str = "用户",
    ) -> bool:
        """记录用户对草案的建议 + 标记 revising_at（不立即重写，仅入库 + 占用）。

        重写动作由 shades.naberius.revise.revise_proposal 异步处理；本方法只把
        feedback 写入、reset review_verdict（让死执下次重审）、并把 revising_at
        设为现在（前端据此禁用同意/再提建议按钮，仅保留拒绝兜底）。

        保护：
        - 仅 status=pending 提案能接受 feedback（已 approved/rejected/applied 不允许）
        - revising_at 已经非空（正在改）→ 拒绝（避免重复触发链路）
        """
        if not feedback.strip():
            # 空 feedback 也允许：等价于"按原内容重审"，让卡在 needs_revise 的提案
            # 走一遍重审通道。这样用户面板不需要为"重审"另开一个按钮。
            feedback = ""
        now = time.time()
        cur = await self._db.execute(
            "UPDATE skill_proposals "
            "SET user_feedback = ?, review_verdict = '', review_notes = '', "
            "    revising_at = ?, updated_at = ? "
            "WHERE id = ? AND status = ? AND revising_at IS NULL",
            (feedback, now, now, prop_id, STATUS_PENDING),
        )
        await self._db.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.info(
                "[世界树] {}·Skill 提案收到反馈  {} feedback_len={} ",
                actor, prop_id, len(feedback),
            )
        else:
            logger.warning(
                "[世界树] {}·Skill 提案反馈被拒  {}（已非 pending 或正在重写中）",
                actor, prop_id,
            )
        return ok

    async def mark_revising_done(self, prop_id: str) -> None:
        """生执 revise + 死执 re-review 链路完成后清空 revising_at（前端解锁按钮）。

        无论链路成功/失败/异常都该调一次（finally 兜底）；幂等不抛异常。
        """
        try:
            now = time.time()
            await self._db.execute(
                "UPDATE skill_proposals "
                "SET revising_at = NULL, updated_at = ? WHERE id = ?",
                (now, prop_id),
            )
            await self._db.commit()
        except Exception as e:
            logger.warning("[世界树] mark_revising_done 异常 {}: {}", prop_id, e)

    async def clear_stale_revising(self, *, timeout_seconds: float = 600) -> int:
        """启动时清扫僵尸 revising_at（fire-and-forget chain 因服务重启 / 异常永
        不返回时，revising_at 永远不会被清空，前端按钮永久 disabled）。

        策略：revising_at 距今超过 timeout_seconds（默认 10 分钟）视作僵尸，清空。
        实际链路 1-2 分钟跑完，10 分钟阈值给足容差。
        """
        cutoff = time.time() - timeout_seconds
        cur = await self._db.execute(
            "UPDATE skill_proposals "
            "SET revising_at = NULL "
            "WHERE revising_at IS NOT NULL AND revising_at < ?",
            (cutoff,),
        )
        await self._db.commit()
        n = cur.rowcount
        if n:
            logger.info("[世界树] 启动清扫僵尸 revising_at 提案 {} 条", n)
        return n

    async def update_content(
        self, prop_id: str, *,
        description: str | None = None,
        triggers: str | None = None,
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        rationale: str | None = None,
        bump_revision: bool = True,
        actor: str,
    ) -> bool:
        """生执 revise_proposal 重写后写回 in-place。

        仅传入需要更新的字段（None 跳过）；bump_revision=True 时 revision_count += 1。
        同时 reset review_verdict（让死执重审）。仅 pending 提案可改。
        """
        sets: list[str] = []
        params: list = []
        if description is not None:
            sets.append("description = ?"); params.append(description)
        if triggers is not None:
            sets.append("triggers = ?"); params.append(triggers)
        if system_prompt is not None:
            sets.append("system_prompt = ?"); params.append(system_prompt)
        if allowed_tools is not None:
            sets.append("allowed_tools = ?")
            params.append(json.dumps(allowed_tools, ensure_ascii=False))
        if rationale is not None:
            sets.append("rationale = ?"); params.append(rationale)
        if not sets:
            return False
        sets.append("review_verdict = ''")
        sets.append("review_notes = ''")
        if bump_revision:
            sets.append("revision_count = revision_count + 1")
        now = time.time()
        sets.append("updated_at = ?"); params.append(now)
        params.append(prop_id)
        sql = (
            f"UPDATE skill_proposals SET {', '.join(sets)} "
            f"WHERE id = ? AND status = ?"
        )
        params.append(STATUS_PENDING)
        cur = await self._db.execute(sql, tuple(params))
        await self._db.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.info(
                "[世界树] {}·Skill 提案内容更新  {} fields={}",
                actor, prop_id, len(sets) - (3 if bump_revision else 2),
            )
        return ok

    async def mark_applied(self, prop_id: str, *, actor: str) -> bool:
        """空执落盘 + skill_declarations 注册完毕后调。"""
        now = time.time()
        cur = await self._db.execute(
            "UPDATE skill_proposals "
            "SET status = ?, applied_at = ?, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (STATUS_APPLIED, now, now, prop_id, STATUS_APPROVED),
        )
        await self._db.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.info("[世界树] {}·Skill 提案 applied  {}", actor, prop_id)
        return ok

    async def delete(self, prop_id: str, *, actor: str) -> bool:
        """彻底删除提案（仅允许 rejected 清理，applied 是已落盘 skill 的依据，禁删）。"""
        # 先查状态保护
        async with self._db.execute(
            "SELECT status FROM skill_proposals WHERE id = ?", (prop_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        if row[0] == STATUS_APPLIED:
            logger.warning(
                "[世界树] {}·Skill 提案删除被拒  {}（status=applied，是 skill 落盘依据）",
                actor, prop_id,
            )
            return False
        cur = await self._db.execute(
            "DELETE FROM skill_proposals WHERE id = ?", (prop_id,),
        )
        await self._db.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.info("[世界树] {}·Skill 提案删除  {}", actor, prop_id)
        return ok

    async def count_by_status(self) -> dict[str, int]:
        """各 status 的提案数（用于面板角标）。SQL COUNT GROUP BY 一次 query 搞定。"""
        out = {STATUS_PENDING: 0, STATUS_APPROVED: 0, STATUS_REJECTED: 0, STATUS_APPLIED: 0}
        async with self._db.execute(
            "SELECT status, COUNT(*) FROM skill_proposals GROUP BY status",
        ) as cur:
            async for row in cur:
                out[row[0]] = row[1]
        return out

    async def prune_old(
        self, *, before_ts: float, statuses: tuple[str, ...] = (STATUS_REJECTED,),
        actor: str,
    ) -> int:
        """清理历史提案（默认仅清 rejected；applied 永不清，作为 skill 起源审计）。

        三月 cron 周期调，传 before_ts=N 天前，控制表大小。
        """
        if not statuses:
            return 0
        # 防呆：禁止把 applied 列入清理
        statuses = tuple(s for s in statuses if s != STATUS_APPLIED)
        if not statuses:
            return 0
        placeholders = ",".join("?" * len(statuses))
        cur = await self._db.execute(
            f"DELETE FROM skill_proposals "
            f"WHERE status IN ({placeholders}) AND updated_at < ?",
            (*statuses, before_ts),
        )
        await self._db.commit()
        n = cur.rowcount
        if n:
            logger.info(
                "[世界树] {}·Skill 提案清理  共 {} 条（status={}）", actor, n, statuses,
            )
        return n


_SELECT_SQL = (
    "SELECT id, name, kind, target_skill, description, triggers, system_prompt, "
    "allowed_tools, rationale, proposed_by_session, proposed_by_task, "
    "review_verdict, review_notes, status, decided_by, decision_notes, "
    "decided_at, applied_at, user_feedback, revision_count, revising_at, "
    "created_at, updated_at "
    "FROM skill_proposals"
)


def _row_to_proposal(row) -> SkillProposal:
    def _safe_json(raw, default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return SkillProposal(
        id=row[0], name=row[1], kind=row[2], target_skill=row[3],
        description=row[4], triggers=row[5], system_prompt=row[6],
        allowed_tools=_safe_json(row[7], []),
        rationale=row[8], proposed_by_session=row[9], proposed_by_task=row[10],
        review_verdict=row[11], review_notes=row[12],
        status=row[13], decided_by=row[14], decision_notes=row[15],
        decided_at=row[16], applied_at=row[17],
        user_feedback=row[18] or "",
        revision_count=row[19] or 0,
        revising_at=row[20],
        created_at=row[21], updated_at=row[22],
    )
