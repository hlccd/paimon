"""Skill 自进化提案域 —— 世界树域 16

唯一写入者：四影（生执 propose / 死执 review_proposal / 派蒙审批与冰神落盘）。

承载：四影从一次任务复盘里凝练出的 skill 草案 + 死执质量审 + 等用户审。
**冰神**才是真正的 skill 写盘者；此域只是「提案 → 审批」中转，apply 后由冰神
读 approved 提案、落 `.claude/skills/<name>/SKILL.md`、注册 skill_declarations。

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

        # 去重：已有 pending 同名同 kind → 直接返已存在 id
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
        """用户同意 → status=approved（等冰神 apply）。

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
            "WHERE id = ? AND status = ? AND review_verdict != ?",
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
                "[世界树] {}·Skill 提案 approve 被拒  {}（已非 pending 或死执要求修订）",
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

    async def mark_applied(self, prop_id: str, *, actor: str) -> bool:
        """冰神落盘 + skill_declarations 注册完毕后调。"""
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
    "decided_at, applied_at, created_at, updated_at "
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
        created_at=row[18], updated_at=row[19],
    )
