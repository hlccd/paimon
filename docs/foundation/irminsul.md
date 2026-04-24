# 世界树

> 隶属：[神圣规划](../aimon.md) / 基础层
> 相关：[权限与契约](../permissions.md) · [自进化](../evolution.md) · [迁移方案](../migration.md)

**定位**：提瓦特世界树为原型，承担**全系统唯一的存储层**职责。

> **存储层 / 服务层分离原则**：整个 AIMON 里，**世界树是唯一的存储层**。其他所有模块（派蒙 / 四影 / 七神 / 天使 / 三月 / 地脉 / 神之心 / 原石 / 时执 / 岩神 / …）都是**服务层**——它们持有各自的业务逻辑（推理、策略、计算、聚合、调度），**数据落盘统一经世界树**，不自建 SQLite 或独立文件库。
>
> 一句话：**世界树管"字节"，服务层管"语义"。**

## 核心能力

- **统一落盘枢纽**：全系统所有需要持久化的数据由世界树承载（SQLite 主库 + 文件系统）
- **领域 API 收口**：按 9 个数据域（见下表）提供语义化读写接口，不暴露底层存储细节
- **路径安全闸门**：文件类域（知识库、记忆 body）内部强制 `resolve()` 校验，调用方只传语义化参数（category / topic / memory_id），不传路径字符串
- **写入日志**：所有写 / 删记 INFO 级日志，凸显"世界树记录 XX 做了 XX"的主语关系（见下方日志约定）
- **只存不推**：不做事件广播、不订阅地脉，不对外提供 subscribe / watch 接口
- **schema 集中迁移**：所有数据域的表结构 / 目录结构变更，在世界树内部完成幂等迁移

## 明确不做

- **不做业务推理**：推理归草神
- **不做安全审查**：审查归死执（新 skill）、冰神（生态把关）
- **不做访问决策**：决策归派蒙 / 死执（查缓存后自行判断）
- **不做主动广播**：消费者感知变更走"**启动读 + 服务层回调通知**"两条路径（见 [permissions.md §画像更新链路](../permissions.md)）
- **不缓存别人的数据**：每个服务层模块自己维护本地缓存
- **不对接 channel / LLM / 地脉 / 原石业务接口**：基础层横向独立

## 9 个数据域

| # | 数据域 | 唯一写入者（服务层） | 读取者 | 业务逻辑留在哪 |
|---|---|---|---|---|
| 1 | 用户授权记录 | 派蒙（对话写）、草神面板（撤销写） | 派蒙 / 死执 / 草神面板 | 关键词识别、缓存维护、UI 展示 |
| 2 | Skill 生态声明 | 冰神（唯一） | 派蒙 / 死执 | 扫目录、运行时装载、与死执审查协作 |
| 3 | 知识库 | 草神（唯一） | 草神 | 推理、整合、语义召回、Prompt 调优 |
| 4 | 记忆 memory/（含个人偏好、习惯） | 草神（唯一） | 派蒙（prefetch）/ 草神 / 三月（反思） | 抽取、归一、反思合并 |
| 5 | 活跃任务记录 | 生执 / 空执 / 七神 | 派蒙 / 三月面板 / 时执（归档时读出） | DAG 拆分、状态转移、轮次控制 |
| 6 | Token 记录 | 原石（唯一） | 原石 | 费率查表、缓存折扣、多维聚合 |
| 7 | 审计 / 归档 | 时执（唯一） | 时执 | 分层策略（热/冷/过期）、审计复盘 |
| 8 | 理财数据 | 岩神（唯一） | 岩神 | 股价爬取、分红计算、资产管理 |
| 9 | 聊天会话 | 派蒙（唯一） | 派蒙 / 时执（归档时） | 会话切换、标题生成、压缩触发、response_status 管理 |

> **"读取者"的范围**：上表只列**直接调用世界树 API 的模块**。间接消费者（如派蒙 `/stat` 展示 token、派蒙推送需要理财内容、三月面板展示任务）**通过对应服务层模块**读取，不直接调世界树——这是"世界树管字节、服务层管语义"的直接体现。

> **迁移注意**：会话域有存量数据（当前 [paimon/session.py](../../paimon/session.py) 在 `paimon_home/sessions/*.json`），首版落地需带**迁移脚本**，把旧 JSON 文件逐个导入 sessions 表后废弃 JSON 目录。

## 与草神的边界

- 世界树 = 底层存储（原始知识、个人偏好、用户授权、skill 声明、记忆、任务、token、审计、理财全部数据落盘）
- 草神 = 在世界树之上做推理、整合与**业务接口**（面板层的所有读写由草神承接，最终存取走世界树）

**类推**：原石之于 token 数据、时执之于审计归档、岩神之于理财数据，都是同样的"服务层 → 世界树"关系。

## 访问接口与权限

世界树只做存储，按数据域提供 **读 / 写 / 列表 / 快照** 四类原语，并对"写"在架构约束上**单一写入者**（世界树自身不做写入者身份校验，信任服务层契约）：

| 数据域 | 可读 | 可写（架构约束：单一来源） |
|---|---|---|
| 用户授权 | 派蒙 / 死执（启动时）、草神面板（UI） | 派蒙（对话写）、草神面板（撤销写） |
| Skill 生态声明 | 派蒙 / 死执（启动时） | 冰神（唯一） |
| 知识库 | 草神 | 草神 |
| 记忆 | 派蒙（prefetch）/ 草神 / 三月 | 草神 |
| 活跃任务 | 派蒙 / 三月 / 时执 | 生执 / 空执 / 七神 |
| Token 记录 | 原石 | 原石 |
| 审计 / 归档 | 时执 | 时执 |
| 理财数据 | 岩神 | 岩神 |
| 聊天会话 | 派蒙 / 时执（归档时） | 派蒙 |

> 具体"谁什么时候来读 / 写、为什么"详见各服务层模块的职能文档和 [权限与契约](../permissions.md)。

## 日志约定

**世界树的所有写 / 删操作必须打 INFO 日志**，格式凸显"世界树记录 XX 做了 XX"的主语关系。

### 格式

```
[世界树] <服务方>·<动作> <对象+关键参数>
```

### 示例

```text
[世界树] 原石·写入 Token 记录  session=abc123, 消耗=$0.0123
[世界树] 派蒙·授权写入  bili skill → 永久放行
[世界树] 派蒙·授权撤销  bili skill
[世界树] 派蒙·会话创建  s-20260422-001
[世界树] 派蒙·会话保存  s-20260422-001 (12 msgs)
[世界树] 派蒙·会话删除  s-20260322-007
[世界树] 冰神·Skill 声明  bili (builtin, sensitivity=normal)
[世界树] 冰神·Skill 移除  old-plugin
[世界树] 草神·记忆写入  user/default: python 偏好
[世界树] 草神·知识写入  python/asyncio-basics
[世界树] 生执·活跃任务创建  task-abc123
[世界树] 空执·任务状态更新  task-abc123: pending → running
[世界树] 时执·任务归档  task-abc123 → 归档库
[世界树] 岩神·分红记录写入  600519 (2026-04-20)
```

### 规则

- **级别**：写 / 删 = INFO；读 = 不打（避免噪音）；schema 迁移 / 初始化 = INFO
- **主语**：`[世界树]` 前缀，与 `[原石]` `[派蒙·对话]` 等现有日志风格一致
- **服务方**：紧随其后，明确谁触发写入
- **关键参数**：带 session_id / skill name / task_id 等溯源字段；**不带** body / 大字段内容（隐私 + 可读性）
- **调用方不自己打"写入世界树"的日志**——世界树统一打，避免重复

### API 约定

调用方在写 / 删操作中传入 `actor` 参数（服务方中文名），由世界树内部拼日志：

```python
await irminsul.authz_set(
    subject_type="skill",
    subject_id="bili",
    decision="permanent_allow",
    actor="派蒙",
)
# → [世界树] 派蒙·授权写入  skill/bili → permanent_allow
```

## 技术基线

- **SQLite 主库**（[`paimon_home`](../../paimon/config.py)/`irminsul.db`）承载结构化域：authorizations / skills / memory_index / tasks / subtasks / flow_history / progress_log / token_usage / revision_records / archived_* / dividend_* / sessions
- **文件系统**承载文档类域：`irminsul/knowledge/{category}/{topic}.md`、`irminsul/memory/{type}/{subject}/{id}.md`
- **路径安全**：所有文件 API 内部 `resolve()` 后校验不超出根目录（消除 [migration.md 审计 SEC-003](../migration.md) 路径遍历 + 模板 RCE 链）
- **横向独立**：不 import `gnosis` / `model` / `primogem 业务接口` / `leyline`

## 启动时序

```text
1. 世界树 initialize（建表 / 建目录 / 路径校验就绪 / schema 迁移）
2. 冰神启动：扫 skills/ → skill_declare（幂等写入）→ 从世界树 load plugin 历史声明
3. 派蒙 / 死执启动：
   a. 世界树.skill_snapshot() → 本地缓存
   b. 世界树.authz_snapshot() → 本地缓存
   c. 等待运行时服务层通知（派蒙内部闭环 / 四影通知）
4. 原石、时执、岩神按需初始化，直接调世界树 API 读写
```

---

## 详细实现规范

> 以下为代码实现层面的规范，用于落地和后续维护排查。架构层在本文上半部分。

### 1. 包结构

```
paimon/foundation/irminsul/
├── __init__.py          # 导出 Irminsul + 9 个数据类
├── irminsul.py          # 主门面：initialize/close + 所有 *_xxx 方法委托
├── _paths.py            # resolve_safe 路径安全工具（内部）
├── _db.py               # SQLite 连接管理 + schema 汇总 + 迁移（内部）
├── authz.py             # AuthzRepo + Authz 数据类
├── skills.py            # SkillRepo + SkillDecl 数据类
├── knowledge.py         # KnowledgeRepo（纯文件层，无 SQL）
├── memory.py            # MemoryRepo + Memory/MemoryMeta（SQL 索引 + 文件 body）
├── task.py              # TaskRepo + TaskEdict/Subtask/FlowEntry/ProgressEntry
├── token.py             # TokenRepo + TokenRow
├── audit.py             # AuditRepo + AuditEntry
├── dividend.py          # DividendRepo（聚合 WatchlistRepo + ScoreSnapshotRepo + ChangeEventRepo）+ WatchlistEntry / ScoreSnapshot / ChangeEvent dataclass
└── session.py           # SessionRepo + SessionRecord/SessionMeta（含 JSON 迁移脚本）
```

### 2. 文件系统布局

```
.paimon/
├── irminsul.db                               # 唯一 SQLite 主库
└── irminsul/
    ├── knowledge/{category}/{topic}.md       # 知识库正文（文件层存取）
    └── memory/{type}/{subject}/{id}.md       # 记忆正文（SQL 索引 + 文件 body）
```

### 3. SQLite Schema（10 张表）

```sql
-- ============ 域 1: 授权记录 ============
CREATE TABLE IF NOT EXISTS authz_records (
    id TEXT PRIMARY KEY,                       -- uuid4().hex (32 字符 = 128bit)
    subject_type TEXT NOT NULL,                -- 'skill' | 'tool'
    subject_id TEXT NOT NULL,
    decision TEXT NOT NULL,                    -- 'permanent_allow' | 'permanent_deny'
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
    source TEXT NOT NULL,                      -- 'builtin' | 'plugin' | 'ai_gen'
    origin TEXT NOT NULL DEFAULT '',           -- ai_gen 时填 proposed_by_session
    sensitivity TEXT NOT NULL DEFAULT 'normal',-- 'normal' | 'sensitive'
    description TEXT NOT NULL DEFAULT '',
    triggers TEXT NOT NULL DEFAULT '',
    allowed_tools TEXT NOT NULL DEFAULT '[]',  -- JSON array
    manifest_json TEXT NOT NULL DEFAULT '{}',  -- 完整 manifest 备份
    orphaned INTEGER NOT NULL DEFAULT 0,       -- 0=活, 1=目录缺失
    installed_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_source ON skill_declarations(source);
CREATE INDEX IF NOT EXISTS idx_skill_orphaned ON skill_declarations(orphaned);

-- ============ 域 4: 记忆索引（body 走文件）============
CREATE TABLE IF NOT EXISTS memory_index (
    id TEXT PRIMARY KEY,                       -- uuid；body 文件也用此为名
    mem_type TEXT NOT NULL,                    -- 'user'|'feedback'|'project'|'reference'
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',           -- JSON array
    source TEXT NOT NULL DEFAULT '',           -- session_id 溯源
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    ttl REAL                                   -- NULL = 永久
);
CREATE INDEX IF NOT EXISTS idx_memory_type_subject ON memory_index(mem_type, subject);
CREATE INDEX IF NOT EXISTS idx_memory_ttl ON memory_index(ttl);

-- ============ 域 5: 活跃任务（4 张表）============
CREATE TABLE IF NOT EXISTS task_edicts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    creator TEXT NOT NULL,                     -- '生执'/'派蒙'/...
    status TEXT NOT NULL,                      -- 'pending'|'planning'|'running'|'completed'|'failed'
    lifecycle_stage TEXT NOT NULL DEFAULT 'hot', -- 'hot'|'cold'|'archived'
    session_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL                           -- NULL = 活跃
);
CREATE INDEX IF NOT EXISTS idx_task_status ON task_edicts(status);
CREATE INDEX IF NOT EXISTS idx_task_lifecycle ON task_edicts(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_task_session ON task_edicts(session_id);

CREATE TABLE IF NOT EXISTS task_subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    parent_id TEXT,
    assignee TEXT NOT NULL,                    -- '草神'/'雷神'/...
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
    payload TEXT NOT NULL DEFAULT '',          -- JSON
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

-- ============ 域 6: Token 记录（迁自原 primogem.db）============
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
    event_type TEXT NOT NULL,                  -- 'compression'|'archival'|'review'|...
    actor TEXT NOT NULL,                       -- '时执'/'水神'/...
    payload TEXT NOT NULL DEFAULT '',          -- JSON 详情
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_revisions(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_revisions(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_revisions(task_id);

-- ============ 域 8: 理财数据（岩神占位）============
CREATE TABLE IF NOT EXISTS dividend_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    record_date TEXT NOT NULL,                 -- 'YYYY-MM-DD'
    amount REAL NOT NULL,
    yield_pct REAL NOT NULL DEFAULT 0,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dividend_symbol ON dividend_stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_dividend_date ON dividend_stocks(record_date);

-- ============ 域 9: 聊天会话（消息链 JSON 存字段内）============
CREATE TABLE IF NOT EXISTS session_records (
    id TEXT PRIMARY KEY,                       -- session_id
    name TEXT NOT NULL DEFAULT '',
    channel_key TEXT NOT NULL DEFAULT '',
    messages_json TEXT NOT NULL DEFAULT '[]',
    response_status TEXT NOT NULL DEFAULT 'idle',
    context_tokens INTEGER NOT NULL DEFAULT 0,
    context_ratio REAL NOT NULL DEFAULT 0.0,
    last_memory_block_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL                           -- NULL = 活跃
);
CREATE INDEX IF NOT EXISTS idx_session_channel ON session_records(channel_key);
CREATE INDEX IF NOT EXISTS idx_session_updated ON session_records(updated_at);
```

> 知识库域（#3）**不建 index 表**：首版只按 `(category, topic)` 两级键存取，文件路径即键。未来需要 tags / FTS 时再引入表。

### 4. 连接管理关键点

- **FK 约束必须显式开启**：每个新开连接执行 `PRAGMA foreign_keys = ON`，SQLite 默认关闭
- **单连接贯穿全程**：世界树实例持有一个 `aiosqlite.Connection`，所有 repo 共享；写入被自然串行化
- **schema 幂等迁移**：`CREATE TABLE IF NOT EXISTS` 建表；旧版新增列用 `_MIGRATION_COLUMNS` 列表 + `PRAGMA table_info` 检查后 `ALTER TABLE ADD COLUMN`（沿用 primogem.py:56-60 已验证的模式）

### 5. 主门面 API 签名

`Irminsul` 类对外暴露**扁平 `<域>_<动作>` 方法**，对应 9 个域共约 45 个方法：

| 域 | 主要方法 |
|---|---|
| authz | `authz_get` / `authz_set` / `authz_revoke` / `authz_list` / `authz_snapshot` |
| skill | `skill_declare` / `skill_get` / `skill_list` / `skill_mark_orphaned` / `skill_remove` / `skill_snapshot` |
| knowledge | `knowledge_read` / `knowledge_write` / `knowledge_list` / `knowledge_delete` |
| memory | `memory_write` / `memory_get` / `memory_list` / `memory_update` / `memory_delete` / `memory_expire` |
| task | `task_create` / `task_get` / `task_update_status` / `task_update_lifecycle` / `task_list` / `subtask_*` / `flow_*` / `progress_*`（共 10 个） |
| token | `token_write` / `token_rows` / `token_aggregate` |
| audit | `audit_append` / `audit_list` |
| dividend | `watchlist_save` / `watchlist_get` / `watchlist_last_refresh` / `snapshot_upsert` / `snapshot_clear_date` / `snapshot_latest_date` / `snapshot_latest_top` / `snapshot_latest_for_watchlist` / `snapshot_history` / `snapshot_get` / `change_save` / `change_recent` / `dividend_cleanup` |
| session | `session_create` / `session_save` / `session_load` / `session_list` / `session_delete` / `session_archive` |

**所有写 / 删方法必传 `actor: str` 参数**（服务方中文名），世界树统一按 §日志约定 打 INFO 日志。

### 6. Token 域聚合接口（给原石用）

因为原石的 dashboard 需要多维聚合，世界树 token 域专门暴露：

```python
# 写
async def token_write(
    session_id: str, component: str, model_name: str,
    input_tokens: int, output_tokens: int, cost_usd: float, *,
    cache_creation_tokens: int = 0, cache_read_tokens: int = 0,
    purpose: str = "", actor: str,
) -> None

# 读原始行（条件过滤）
async def token_rows(
    *, session_id: str | None = None, component: str | None = None,
    purpose: str | None = None, since: float | None = None,
    until: float | None = None, limit: int = 10000,
) -> list[TokenRow]

# GROUP BY 聚合（原石用来画 dashboard）
async def token_aggregate(
    *, group_by: list[str],                    # ['component'] / ['purpose'] / ['component', 'purpose'] / ['hour'] / ['weekday'] / ['day'] / ['week'] / ['month']
    session_id: str | None = None,             # 可选过滤
    since: float | None = None,
) -> list[dict]                                # 每行 {group_key..., sum_cost, sum_tokens, count}
```

原石保留：`ModelRate` 费率表、`compute_cost()`、dashboard HTML 组装；原先的 `get_session_stats` / `get_global_stats` / `get_timeline_stats` 等方法**改为调世界树 `token_aggregate` 的薄包装**。

### 7. 会话迁移脚本

`SessionRepo.migrate_from_json(legacy_dir: Path)` 在 `Irminsul.initialize()` 末尾自动调用：

1. 检测 `paimon_home/sessions/` 存在且非空 → 进入迁移流程
2. 逐个 JSON 文件：解析 → 兼容缺失字段（`channel_key` 缺省 `""`）→ 写入 `session_records`
3. 单个文件解析失败 try/except，不阻塞其他（审计 REL-008）
4. 全部完成后把 `sessions/` 改名为 `sessions.migrated/`，保留备份
5. 下次启动看到 `sessions.migrated/` 就跳过

### 8. 日志约定落地

每个带 `actor` 的方法在 **成功写/删** 后打一行 INFO 日志，格式：

```
[世界树] {actor}·{动作} {对象+关键参数}
```

例：
- `[世界树] 派蒙·授权写入  skill/bili → permanent_allow`
- `[世界树] 原石·写入 Token 记录  session=abc123, 消耗=$0.0123`
- `[世界树] 冰神·Skill 标记孤儿  bili`

读操作不打日志（避免噪音）。schema 初始化 / 迁移打 INFO。

### 9. 启动集成

`paimon/bootstrap.py` 的 `create_app` 改为 **async `initialize_app`**，流程：

```python
state.cfg = cfg
cfg.paimon_home.mkdir(parents=True, exist_ok=True)

# 世界树最早
state.irminsul = Irminsul(cfg.paimon_home)
await state.irminsul.initialize()   # 含 schema 迁移 + 会话 JSON 迁移

# session_mgr 改为从世界树加载
state.session_mgr = await SessionManager.load(irminsul=state.irminsul)

# 原石持有 irminsul 引用
state.primogem = Primogem(state.irminsul)

# ... gnosis / channels 等保持不变
```

对应 `main.py` 入口改为 `asyncio.run(initialize_app(cfg))` 后再 run channels。

### 10. 模块间调用模式示例

```python
# 派蒙识别到"永久放行"关键词后
await state.irminsul.authz_set(
    subject_type="skill", subject_id="bili",
    decision="permanent_allow",
    session_id=session.id,
    reason="用户对话中声明永久放行",
    actor="派蒙",
)
# 自动记日志: [世界树] 派蒙·授权写入  skill/bili → permanent_allow

# 原石记 token（被 Model 调用）
await state.irminsul.token_write(
    session_id=sess_id, component="paimon", model_name="claude-opus-4-6",
    input_tokens=1234, output_tokens=567, cost_usd=0.0123,
    actor="原石",
)
# 自动记日志: [世界树] 原石·写入 Token 记录  session=abc123, 消耗=$0.0123
```
