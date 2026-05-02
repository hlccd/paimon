"""世界树主门面 Irminsul：__init__ / initialize / close + mixin 组合。

对外暴露扁平 `<域>_<动作>` 方法（共 9 个域 ~120 个方法），实际方法实现按域拆到 4 个 mixin：
- _basics.py        —— authz/skill/knowledge/memory/task/token/audit
- _finance.py       —— dividend/user_watch/mihoyo
- _runtime.py       —— session/schedule/subscription/feed_event
- _observability.py —— selfcheck/push_archive/llm_profile/llm_route
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite
from loguru import logger

from .._db import init_db
from ..audit import AuditRepo
from ..authz import AuthzRepo
from ..dividend import DividendRepo
from ..dividend_event import DividendEventRepo
from ..feed_event import FeedEventRepo
from ..knowledge import KnowledgeRepo
from ..llm_profile import LLMProfileRepo
from ..llm_route import LLMRouteRepo
from ..memory import MemoryRepo
from ..mihoyo import MihoyoRepo
from ..push_archive import PushArchiveRepo
from ..schedule import ScheduleRepo
from ..selfcheck import SelfcheckRepo
from ..session import SessionRepo
from ..skills import SkillRepo
from ..subscription import SubscriptionRepo
from ..task import TaskRepo
from ..token import TokenRepo
from ..user_watchlist import UserWatchlistRepo
from ._basics import _BasicsMixin
from ._finance import _FinanceMixin
from ._observability import _ObservabilityMixin
from ._runtime import _RuntimeMixin


class Irminsul(
    _BasicsMixin, _FinanceMixin, _RuntimeMixin, _ObservabilityMixin,
):
    """世界树：全系统唯一存储层。

    对外按 9 个数据域提供读/写/快照/列表接口。所有写/删方法必传 actor（服务方中文名），
    内部统一打 `[世界树] <actor>·<动作> <对象>` INFO 日志。
    """

    def __init__(self, home: Path):
        self._home = home
        self._db_path = home / "irminsul.db"
        self._fs_root = home / "irminsul"
        self._knowledge_root = self._fs_root / "knowledge"
        self._memory_root = self._fs_root / "memory"
        self._selfcheck_root = self._fs_root / "selfcheck"
        self._db: aiosqlite.Connection | None = None
        # Repo 延迟到 initialize
        self._authz: AuthzRepo | None = None
        self._skill: SkillRepo | None = None
        self._knowledge: KnowledgeRepo | None = None
        self._memory: MemoryRepo | None = None
        self._task: TaskRepo | None = None
        self._token: TokenRepo | None = None
        self._audit: AuditRepo | None = None
        self._dividend: DividendRepo | None = None
        self._dividend_event: DividendEventRepo | None = None
        self._user_watchlist: UserWatchlistRepo | None = None
        self._mihoyo: MihoyoRepo | None = None
        self._session: SessionRepo | None = None
        self._schedule: ScheduleRepo | None = None
        self._subscription: SubscriptionRepo | None = None
        self._feed_event: FeedEventRepo | None = None
        self._push_archive: PushArchiveRepo | None = None
        self._selfcheck: SelfcheckRepo | None = None
        self._llm_profile: LLMProfileRepo | None = None
        self._llm_route: LLMRouteRepo | None = None

    async def initialize(self) -> None:
        """打开 DB / 建目录 / 实例化 19 个 Repo / 跑历史迁移；幂等。"""
        self._home.mkdir(parents=True, exist_ok=True)
        self._fs_root.mkdir(parents=True, exist_ok=True)
        self._knowledge_root.mkdir(parents=True, exist_ok=True)
        self._memory_root.mkdir(parents=True, exist_ok=True)
        self._selfcheck_root.mkdir(parents=True, exist_ok=True)

        self._db = await init_db(self._db_path)

        self._authz = AuthzRepo(self._db)
        self._skill = SkillRepo(self._db)
        self._knowledge = KnowledgeRepo(self._knowledge_root)
        self._memory = MemoryRepo(self._db, self._memory_root)
        self._task = TaskRepo(self._db)
        self._token = TokenRepo(self._db)
        self._audit = AuditRepo(self._db)
        self._dividend = DividendRepo(self._db)
        self._dividend_event = DividendEventRepo(self._db)
        self._user_watchlist = UserWatchlistRepo(self._db)
        self._mihoyo = MihoyoRepo(self._db)
        self._session = SessionRepo(self._db)
        self._schedule = ScheduleRepo(self._db)
        self._subscription = SubscriptionRepo(self._db)
        self._feed_event = FeedEventRepo(self._db)
        self._push_archive = PushArchiveRepo(self._db)
        self._selfcheck = SelfcheckRepo(self._db, self._selfcheck_root)
        self._llm_profile = LLMProfileRepo(self._db)
        self._llm_route = LLMRouteRepo(self._db)

        logger.info("[世界树] 初始化完成  db={}", self._db_path)

        # 会话迁移（幂等）
        legacy_sessions = self._home / "sessions"
        if legacy_sessions.exists():
            imported = await self._session.migrate_from_json(legacy_sessions)
            if imported > 0:
                logger.info("[世界树] 会话迁移  共导入 {} 条", imported)

    async def close(self) -> None:
        """关 DB 连接（重启 / 测试用）。"""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("[世界树] 已关闭")
