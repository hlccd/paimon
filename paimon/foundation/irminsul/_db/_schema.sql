-- ============ 域 1: 授权记录 ============
CREATE TABLE IF NOT EXISTS authz_records (
    id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'default',
    session_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(subject_type, subject_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_authz_user ON authz_records(user_id);

-- ============ 域 2: Skill 生态声明 ============
CREATE TABLE IF NOT EXISTS skill_declarations (
    name TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT '',
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    description TEXT NOT NULL DEFAULT '',
    triggers TEXT NOT NULL DEFAULT '',
    allowed_tools TEXT NOT NULL DEFAULT '[]',
    sensitive_tools TEXT NOT NULL DEFAULT '[]',
    manifest_json TEXT NOT NULL DEFAULT '{}',
    orphaned INTEGER NOT NULL DEFAULT 0,
    installed_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_source ON skill_declarations(source);
CREATE INDEX IF NOT EXISTS idx_skill_orphaned ON skill_declarations(orphaned);

-- ============ 域 4: 记忆索引 ============
CREATE TABLE IF NOT EXISTS memory_index (
    id TEXT PRIMARY KEY,
    mem_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    ttl REAL
);
CREATE INDEX IF NOT EXISTS idx_memory_type_subject ON memory_index(mem_type, subject);
CREATE INDEX IF NOT EXISTS idx_memory_ttl ON memory_index(ttl);

-- ============ 域 5: 活跃任务（4 张表）============
CREATE TABLE IF NOT EXISTS task_edicts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    creator TEXT NOT NULL,
    status TEXT NOT NULL,
    lifecycle_stage TEXT NOT NULL DEFAULT 'hot',
    session_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL
);
CREATE INDEX IF NOT EXISTS idx_task_status ON task_edicts(status);
CREATE INDEX IF NOT EXISTS idx_task_lifecycle ON task_edicts(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_task_session ON task_edicts(session_id);

CREATE TABLE IF NOT EXISTS task_subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    parent_id TEXT,
    assignee TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES task_edicts(id)
);
CREATE INDEX IF NOT EXISTS idx_subtask_task ON task_subtasks(task_id);
CREATE INDEX IF NOT EXISTS idx_subtask_status ON task_subtasks(status);

CREATE TABLE IF NOT EXISTS task_flow_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    action TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES task_edicts(id)
);
CREATE INDEX IF NOT EXISTS idx_flow_task ON task_flow_history(task_id);

CREATE TABLE IF NOT EXISTS task_progress_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    subtask_id TEXT,
    agent TEXT NOT NULL,
    progress_pct INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (task_id) REFERENCES task_edicts(id)
);
CREATE INDEX IF NOT EXISTS idx_progress_task ON task_progress_log(task_id);

-- ============ 域 6: Token 记录 ============
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    component TEXT NOT NULL,
    model_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL,
    purpose TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_token_session ON token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_token_ts ON token_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_token_component ON token_usage(component);
CREATE INDEX IF NOT EXISTS idx_token_purpose ON token_usage(purpose);

-- ============ 域 7: 审计记录 ============
CREATE TABLE IF NOT EXISTS audit_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    session_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_revisions(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_revisions(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_revisions(task_id);

-- ============ 域 8: 理财数据（岩神·红利股追踪）============
-- 三张表：watchlist（推荐股池）+ snapshot（每日评分）+ changes（变化事件）
-- 唯一写入者：岩神
CREATE TABLE IF NOT EXISTS dividend_watchlist (
    stock_code   TEXT PRIMARY KEY,
    stock_name   TEXT NOT NULL DEFAULT '',
    industry     TEXT NOT NULL DEFAULT '',
    added_date   TEXT NOT NULL,
    last_refresh TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_watchlist_industry ON dividend_watchlist(industry);

CREATE TABLE IF NOT EXISTS dividend_snapshot (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date             TEXT NOT NULL,
    stock_code            TEXT NOT NULL,
    stock_name            TEXT NOT NULL DEFAULT '',
    industry              TEXT NOT NULL DEFAULT '',
    total_score           REAL NOT NULL DEFAULT 0,
    sustainability_score  REAL NOT NULL DEFAULT 0,
    fortress_score        REAL NOT NULL DEFAULT 0,
    valuation_score       REAL NOT NULL DEFAULT 0,
    track_record_score    REAL NOT NULL DEFAULT 0,
    momentum_score        REAL NOT NULL DEFAULT 0,
    penalty               REAL NOT NULL DEFAULT 0,
    dividend_yield        REAL NOT NULL DEFAULT 0,
    pe                    REAL NOT NULL DEFAULT 0,
    pb                    REAL NOT NULL DEFAULT 0,
    roe                   REAL NOT NULL DEFAULT 0,
    market_cap            REAL NOT NULL DEFAULT 0,
    reasons               TEXT NOT NULL DEFAULT '',
    advice                TEXT NOT NULL DEFAULT '',
    detail_json           TEXT NOT NULL DEFAULT '{}',
    created_at            REAL NOT NULL,
    UNIQUE(scan_date, stock_code)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_code_date ON dividend_snapshot(stock_code, scan_date DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_date_score ON dividend_snapshot(scan_date, total_score DESC);

CREATE TABLE IF NOT EXISTS dividend_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date  TEXT NOT NULL,
    stock_code  TEXT NOT NULL,
    stock_name  TEXT NOT NULL DEFAULT '',
    event_type  TEXT NOT NULL,   -- 'entered' | 'exited' | 'score_change'
    old_value   REAL,
    new_value   REAL,
    description TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_date ON dividend_changes(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_changes_code ON dividend_changes(stock_code, event_date DESC);

-- ============ 域 8.5: 理财事件聚类（岩神 P0/P1/P2 事件化）============
-- 跨扫描 merge 语义：同 stock_code+event_type 在 7 天内合并进 timeline，
-- 超 7 天起新事件；本轮该股没命中此 type 但表里有 active → mark resolved。
-- event_type 集合：st_risen / dividend_halt / score_crash / history_broken
--                  / dividend_drop / score_decline / score_change
CREATE TABLE IF NOT EXISTS dividend_events (
    id              TEXT PRIMARY KEY,                  -- 12 位 hex
    stock_code      TEXT NOT NULL,
    stock_name      TEXT NOT NULL DEFAULT '',
    industry        TEXT NOT NULL DEFAULT '',
    severity        TEXT NOT NULL DEFAULT 'p2',        -- 'p0'|'p1'|'p2'
    event_type      TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    timeline_json   TEXT NOT NULL DEFAULT '[]',        -- [{scan_date, severity, total_score, ...}]
    first_seen_at   REAL NOT NULL,
    last_seen_at    REAL NOT NULL,
    last_pushed_at  REAL,
    last_severity   TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',    -- 'active'|'resolved'|'aged_out'
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    detail_json     TEXT NOT NULL DEFAULT '{}',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dividend_events_code
    ON dividend_events(stock_code, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_dividend_events_severity
    ON dividend_events(severity, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_dividend_events_status
    ON dividend_events(status, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_dividend_events_merge
    ON dividend_events(stock_code, event_type, status, last_seen_at DESC);

-- ============ 域 8.6: 用户关注股（岩神 · user watchlist）============
-- 区别于 dividend_watchlist（岩神自动按行业均衡 25 只红利股池）：
-- user_watchlist 是用户手动添加的自选股，无数量/行业限制，每日 scan 顺手拉价量。
-- 主表关注清单 + 价格历史表（首次 add 拉 3 年历史，后续 daily 追加 1 条）。
CREATE TABLE IF NOT EXISTS user_watchlist (
    stock_code   TEXT PRIMARY KEY,       -- baostock 格式 'sh.600519' / 'sz.000001'
    stock_name   TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    added_date   TEXT NOT NULL,
    alert_pct    REAL NOT NULL DEFAULT 3.0   -- |日涨跌%| ≥ 此值触发 P1 推送
);

CREATE TABLE IF NOT EXISTS user_watchlist_price (
    stock_code  TEXT NOT NULL,
    date        TEXT NOT NULL,     -- 交易日 'YYYY-MM-DD'
    close       REAL NOT NULL DEFAULT 0,
    change_pct  REAL NOT NULL DEFAULT 0,   -- 当日涨跌 %
    pe          REAL NOT NULL DEFAULT 0,   -- peTTM
    pb          REAL NOT NULL DEFAULT 0,   -- pbMRQ
    volume      REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (stock_code, date)
);
CREATE INDEX IF NOT EXISTS idx_user_price_code_date
    ON user_watchlist_price(stock_code, date DESC);

-- ============ 域 8.7: 米哈游账号（水神 · mihoyo）============
-- 唯一写入者：水神（经 mihoyo skill 调米游社 API 后）
-- 读取者：水神（签到/便笺/深渊/抽卡流程）、WebUI /game 面板
-- 账号按 (game, uid) 分行：同一 mys_id 下三游戏可各绑一条
CREATE TABLE IF NOT EXISTS mihoyo_account (
    game         TEXT NOT NULL,            -- gs | sr | zzz
    uid          TEXT NOT NULL,
    mys_id       TEXT NOT NULL DEFAULT '', -- 米游社账号 ID（ltuid / stuid）
    cookie       TEXT NOT NULL DEFAULT '', -- web Cookie
    stoken       TEXT NOT NULL DEFAULT '', -- Stoken（续命 key）
    fp           TEXT NOT NULL DEFAULT '', -- 设备指纹
    device_id    TEXT NOT NULL DEFAULT '',
    device_info  TEXT NOT NULL DEFAULT '',
    authkey      TEXT NOT NULL DEFAULT '', -- 抽卡 authkey（24h 过期）
    authkey_ts   REAL NOT NULL DEFAULT 0,  -- authkey 获取时间戳
    note         TEXT NOT NULL DEFAULT '',
    added_date   TEXT NOT NULL,
    last_sign_at REAL NOT NULL DEFAULT 0,  -- 最后签到时间（防重签）
    enabled      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (game, uid)
);

CREATE TABLE IF NOT EXISTS mihoyo_note (
    game              TEXT NOT NULL,
    uid               TEXT NOT NULL,
    scan_ts           REAL NOT NULL,
    current_resin     INTEGER NOT NULL DEFAULT 0,
    max_resin         INTEGER NOT NULL DEFAULT 160,
    resin_full_ts     REAL NOT NULL DEFAULT 0,   -- 树脂满时间戳
    finished_tasks    INTEGER NOT NULL DEFAULT 0,
    total_tasks       INTEGER NOT NULL DEFAULT 4,
    daily_reward      INTEGER NOT NULL DEFAULT 0,-- 每日已领 0/1
    remain_discount   INTEGER NOT NULL DEFAULT 3,-- 周本减半剩余
    current_expedition INTEGER NOT NULL DEFAULT 0,
    max_expedition    INTEGER NOT NULL DEFAULT 5,
    expeditions_json  TEXT NOT NULL DEFAULT '[]',
    transformer_ready INTEGER NOT NULL DEFAULT 0,-- 参量质变仪就绪 0/1
    raw_json          TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (game, uid)
);

CREATE TABLE IF NOT EXISTS mihoyo_abyss (
    game         TEXT NOT NULL,
    uid          TEXT NOT NULL,
    abyss_type   TEXT NOT NULL,          -- spiral | poetry
    schedule_id  TEXT NOT NULL,          -- 期号（米游社返回的 schedule_id）
    scan_ts      REAL NOT NULL,
    max_floor    TEXT NOT NULL DEFAULT '',
    total_star   INTEGER NOT NULL DEFAULT 0,
    total_battle INTEGER NOT NULL DEFAULT 0,
    total_win    INTEGER NOT NULL DEFAULT 0,
    start_time   TEXT NOT NULL DEFAULT '',
    end_time     TEXT NOT NULL DEFAULT '',
    raw_json     TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (game, uid, abyss_type, schedule_id)
);

CREATE TABLE IF NOT EXISTS mihoyo_character (
    game         TEXT NOT NULL,              -- gs | sr | zzz
    uid          TEXT NOT NULL,
    avatar_id    TEXT NOT NULL,              -- 米游社角色 ID
    name         TEXT NOT NULL DEFAULT '',
    element      TEXT NOT NULL DEFAULT '',   -- 原神元素 / 崩铁命途 / 绝区零属性
    rarity       INTEGER NOT NULL DEFAULT 4, -- 4/5 星
    level        INTEGER NOT NULL DEFAULT 1,
    constellation INTEGER NOT NULL DEFAULT 0,-- 命座/星魂/影画
    fetter       INTEGER NOT NULL DEFAULT 0, -- 原神好感度
    weapon_json  TEXT NOT NULL DEFAULT '{}', -- {name, level, affix, rarity}
    relics_json  TEXT NOT NULL DEFAULT '[]', -- 圣遗物/遗器/驱动盘摘要
    icon_url     TEXT NOT NULL DEFAULT '',   -- 米游社头像 CDN
    scan_ts      REAL NOT NULL,
    raw_json     TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (game, uid, avatar_id)
);
CREATE INDEX IF NOT EXISTS idx_character_by_uid ON mihoyo_character(game, uid, rarity DESC, level DESC);

CREATE TABLE IF NOT EXISTS mihoyo_gacha (
    id           TEXT PRIMARY KEY,       -- 米游社返回的全局唯一 gacha id
    game         TEXT NOT NULL DEFAULT 'gs',  -- gs/sr/zzz
    uid          TEXT NOT NULL,
    gacha_type   TEXT NOT NULL,          -- gs:301/302/200/100/500 sr:1/2/11/12 zzz:1/2/3/5
    item_id      TEXT NOT NULL DEFAULT '',
    item_type    TEXT NOT NULL DEFAULT '',-- 角色 | 武器
    name         TEXT NOT NULL DEFAULT '',
    rank_type    INTEGER NOT NULL DEFAULT 3, -- 3/4/5
    time         TEXT NOT NULL DEFAULT '',   -- 抽取时间 YYYY-MM-DD HH:MM:SS
    time_ts      REAL NOT NULL DEFAULT 0,
    raw_json     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_gacha_uid_type ON mihoyo_gacha(game, uid, gacha_type, time_ts DESC);
CREATE INDEX IF NOT EXISTS idx_gacha_rank ON mihoyo_gacha(game, uid, gacha_type, rank_type, time_ts DESC);

-- ============ 域 10: 定时任务（三月）============
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    channel_name TEXT NOT NULL DEFAULT '',
    task_prompt TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_value TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at REAL NOT NULL DEFAULT 0,
    last_run_at REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sched_enabled ON scheduled_tasks(enabled);
CREATE INDEX IF NOT EXISTS idx_sched_next ON scheduled_tasks(next_run_at);

-- ============ 域 11: 订阅（风神）============
CREATE TABLE IF NOT EXISTS subscriptions (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL DEFAULT 'default',
    query          TEXT NOT NULL,
    channel_name   TEXT NOT NULL,
    chat_id        TEXT NOT NULL,
    schedule_cron  TEXT NOT NULL,
    max_items      INTEGER NOT NULL DEFAULT 10,
    engine         TEXT NOT NULL DEFAULT '',
    enabled        INTEGER NOT NULL DEFAULT 1,
    linked_task_id TEXT NOT NULL DEFAULT '',
    last_run_at    REAL NOT NULL DEFAULT 0,
    last_error     TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sub_enabled ON subscriptions(enabled);
CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id);

CREATE TABLE IF NOT EXISTS feed_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    engine          TEXT NOT NULL DEFAULT '',
    captured_at     REAL NOT NULL,
    pushed_at       REAL,
    digest_id       TEXT NOT NULL DEFAULT '',
    UNIQUE(subscription_id, url),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
CREATE INDEX IF NOT EXISTS idx_feed_sub ON feed_items(subscription_id);
CREATE INDEX IF NOT EXISTS idx_feed_captured ON feed_items(captured_at);
CREATE INDEX IF NOT EXISTS idx_feed_pushed ON feed_items(pushed_at);

-- ============ 域 11.5: 事件聚类（风神 L1 舆情）============
-- 跨批次事件聚类：feed_events 为事件主体，feed_items.event_id 关联
-- docs/archons/venti.md §L1 事件级舆情监测
CREATE TABLE IF NOT EXISTS feed_events (
    id              TEXT PRIMARY KEY,                -- 12 位 hex
    subscription_id TEXT NOT NULL,                   -- 同订阅下聚类
    title           TEXT NOT NULL DEFAULT '',        -- LLM 给的事件标题（≤80 字）
    summary         TEXT NOT NULL DEFAULT '',        -- 一句话摘要（≤200 字）
    entities_json   TEXT NOT NULL DEFAULT '[]',      -- ["人物", "公司", ...]
    timeline_json   TEXT NOT NULL DEFAULT '[]',      -- [{ts, point}, ...]
    severity        TEXT NOT NULL DEFAULT 'p3',      -- 'p0'|'p1'|'p2'|'p3'
    sentiment_score REAL NOT NULL DEFAULT 0.0,       -- [-1.0, 1.0]
    sentiment_label TEXT NOT NULL DEFAULT 'neutral', -- positive/neutral/negative/mixed
    item_count      INTEGER NOT NULL DEFAULT 0,      -- 关联 feed_items 数
    first_seen_at   REAL NOT NULL,                   -- 首次聚出时间
    last_seen_at    REAL NOT NULL,                   -- 最近一次更新时间
    last_pushed_at  REAL,                            -- 上次推送时间（限流用）
    last_severity   TEXT NOT NULL DEFAULT '',        -- 上次推送时的 severity（升级判定）
    pushed_count    INTEGER NOT NULL DEFAULT 0,
    sources_json    TEXT NOT NULL DEFAULT '[]',      -- ["xxx.com", ...]
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
CREATE INDEX IF NOT EXISTS idx_feed_events_sub ON feed_events(subscription_id);
CREATE INDEX IF NOT EXISTS idx_feed_events_last_seen ON feed_events(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_feed_events_severity ON feed_events(severity);

-- ============ 域 9: 聊天会话 ============
CREATE TABLE IF NOT EXISTS session_records (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    channel_key TEXT NOT NULL DEFAULT '',
    messages_json TEXT NOT NULL DEFAULT '[]',
    session_memory_json TEXT NOT NULL DEFAULT '[]',
    last_context_tokens INTEGER NOT NULL DEFAULT 0,
    last_context_ratio REAL NOT NULL DEFAULT 0.0,
    last_compressed_at REAL NOT NULL DEFAULT 0.0,
    compressed_rounds INTEGER NOT NULL DEFAULT 0,
    response_status TEXT NOT NULL DEFAULT 'idle',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL,
    compression_failures INTEGER NOT NULL DEFAULT 0,
    auto_compact_disabled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_session_channel ON session_records(channel_key);
CREATE INDEX IF NOT EXISTS idx_session_updated ON session_records(updated_at);

-- ============ 域 12: 自检归档（三月）============
-- 每次 Quick / Deep 自检的元数据 + 聚合计数；完整产物（report.md / candidates.jsonl / state.json）
-- 落文件系统 `.paimon/irminsul/selfcheck/{run_id}/`。
-- docs/foundation/march.md §自检体系
CREATE TABLE IF NOT EXISTS selfcheck_runs (
    id                 TEXT PRIMARY KEY,                 -- 12 位 hex
    kind               TEXT NOT NULL,                    -- 'quick' | 'deep'
    triggered_at       REAL NOT NULL,
    triggered_by       TEXT NOT NULL DEFAULT 'user',     -- 'user' / 'cron' / '三月' 等
    status             TEXT NOT NULL DEFAULT 'running',  -- 'running' | 'completed' | 'failed'
    duration_seconds   REAL NOT NULL DEFAULT 0,
    check_args         TEXT NOT NULL DEFAULT '',         -- deep 专用：check 命令的参数
    error              TEXT NOT NULL DEFAULT '',
    p0_count           INTEGER NOT NULL DEFAULT 0,
    p1_count           INTEGER NOT NULL DEFAULT 0,
    p2_count           INTEGER NOT NULL DEFAULT 0,
    p3_count           INTEGER NOT NULL DEFAULT 0,
    findings_total     INTEGER NOT NULL DEFAULT 0,
    quick_summary_json TEXT NOT NULL DEFAULT '{}'        -- quick 专用：overall + component 快照
);
CREATE INDEX IF NOT EXISTS idx_selfcheck_kind ON selfcheck_runs(kind);
CREATE INDEX IF NOT EXISTS idx_selfcheck_time ON selfcheck_runs(triggered_at DESC);

-- ============ 域 13: 推送归档（替代主动推送到聊天会话）============
-- 各神（风神/岩神/三月）原本经 march.ring_event 推到「📨 推送」聊天的内容，
-- 改为静默归档到本表 + 全局红点抽屉消费。聊天会话彻底纯净（用户对话）。
-- docs/foundation/march.md §推送归档（2026-04-25 新增）
CREATE TABLE IF NOT EXISTS push_archive (
    id            TEXT PRIMARY KEY,                  -- 12 位 hex
    source        TEXT NOT NULL,                     -- "风神·舆情日报" / "风神·舆情预警" / "岩神·..."
    actor         TEXT NOT NULL,                     -- "风神" / "岩神" / "三月"，用于按神分组
    channel_name  TEXT NOT NULL DEFAULT 'webui',     -- 原本要投递的频道（保留供 audit / 未来恢复）
    chat_id       TEXT NOT NULL DEFAULT '',
    message_md    TEXT NOT NULL,                     -- markdown 内容（原 ring_event message 字段）
    level         TEXT NOT NULL DEFAULT 'silent',    -- 'silent' | 'loud'，预留给未来恢复打断推送
    extra_json    TEXT NOT NULL DEFAULT '{}',        -- 关联 task_id / event_id / sub_id / change_id 等
    created_at    REAL NOT NULL,
    read_at       REAL                                -- NULL = 未读；标记后填入时间戳
);
CREATE INDEX IF NOT EXISTS idx_push_archive_created ON push_archive(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_push_archive_actor   ON push_archive(actor);
CREATE INDEX IF NOT EXISTS idx_push_archive_unread  ON push_archive(read_at);

-- ============ 域 14: LLM Profile（2026-04-27 新增）============
-- 用户可管理的"模型条目"第一类实体。同一 API 端点下的不同 model、不同
-- thinking 配置都能独立成条；扩展新 provider 无需改代码。
-- docs/todo.md §"日报面板采集中反馈复用" 上面一项（LLM 分层）
CREATE TABLE IF NOT EXISTS llm_profiles (
    id               TEXT PRIMARY KEY,            -- 12 位 hex
    name             TEXT NOT NULL UNIQUE,        -- 展示名
    provider_kind    TEXT NOT NULL,               -- 'anthropic' | 'openai'
    api_key          TEXT NOT NULL DEFAULT '',
    base_url         TEXT NOT NULL DEFAULT '',
    model            TEXT NOT NULL DEFAULT '',
    max_tokens       INTEGER NOT NULL DEFAULT 64000,    -- 仅 anthropic 生效
    reasoning_effort TEXT NOT NULL DEFAULT '',          -- '' | 'high' | 'max'
    extra_body_json  TEXT NOT NULL DEFAULT '{}',        -- 如 thinking 开关
    is_default       INTEGER NOT NULL DEFAULT 0,        -- 全表仅一行为 1
    notes            TEXT NOT NULL DEFAULT '',
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_profiles_default ON llm_profiles(is_default DESC);

-- ============ 域 15: LLM 路由（2026-04-27 M2 新增）============
-- (component[:purpose]) → profile_id 映射。由 ModelRouter 在 Model.chat
-- 入口按 (component, purpose) resolve。FK CASCADE：profile 被删时该 profile
-- 涉及的路由自动清理，避免悬挂引用。
CREATE TABLE IF NOT EXISTS llm_routes (
    route_key   TEXT PRIMARY KEY,        -- "风神" 或 "风神:事件聚类"
    profile_id  TEXT NOT NULL,
    updated_at  REAL NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES llm_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_llm_routes_profile ON llm_routes(profile_id);
