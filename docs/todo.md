# 待办项 / 下一步

> 隶属：[神圣规划](aimon.md)
>
> 只记录**尚未实现 / 待完善**的事项。已完成项请查 git log / 归档文档。更新时间：2026-04-29

每一条都已对照源码核过一遍；"部分实装"一栏列出哪些已做、哪些没做、哪些是主动舍弃的设计决策。

## 1. 职能层面

- [ ] **推送策略深化**
  - **已做**：`march.ring_event` 60s/10 次滑窗限流（非 dedup 路径） + `dedup_per_day=True` 日级 upsert + `push_archive` 持久化 + 审计事件 `march_ring_event` + leyline `push.archived` publish + PushHub 进程内 SSE 扇出（满队丢最早） + level 字段预留 `'silent'|'loud'`
  - **未做**：
    - `level='loud'` 的实际打断 UX —— 全仓消费者把 level 当字段存取，但没有任何路径对 `loud` 做差异化（读出来丢前端后前端也没用）
    - 多事件响铃并发时的优先级仲裁（目前 FIFO）
    - 派蒙 crash 后的积压重播（push_hub 内存队列丢失，push_archive 持久化但未读状态不保证按时序重放）
    - 按 source 分级的频率策略（所有 source 共享同一个 60s/10 次窗口）

- [ ] **三月·自检 Deep 暂缓**
  - 底层 `SelfCheckService.run_deep / _invoke_check_skill / _progress_watcher` 全部实装；[`config.py:124`](../paimon/config.py#L124) `selfcheck_deep_hidden=True` 默认隐藏 + [`selfcheck_html.py:639`](../paimon/channels/webui/selfcheck_html.py#L639) 按 deep_hidden 关按钮 + Deep Tab + `[SELFCHECK_DEEP]` cron 分派已撤销（[`bootstrap.py:362`](../paimon/bootstrap.py#L362)）
  - **卡点**：当前 mimo-v2-omni 对 check skill 的 N+M+K 多轮迭代执行不充分（单轮 ~30s 就返回简短 finding 停止），跑不出可靠体检
  - **预期解**：换 Claude Opus 级模型给 deep pool（1M context + 原生 agentic 长链指令遵循更强）
  - **恢复步骤**：(1) `.env` 配 `CLAUDE_OFFICIAL_API_KEY` + `LLM_DEEP_PROVIDER=claude-official` (2) `SELFCHECK_DEEP_HIDDEN=false` (3) 重启 (4) 视观测再启 `[SELFCHECK_DEEP]` cron 分派

- [ ] **三月·测试基础设施** —— 仓库零测试：无 `tests/`、无 `conftest.py`、`pyproject.toml` 无 test 配置、全仓 zero import of pytest / unittest、无 CI workflow。需要设计静态契约测试 / 离线冒烟 / 真实 API 测试分层

- [ ] **权限体系 v2 重新设计**
  - **临时缓解已做**：[`bootstrap.py:256-284`](../paimon/bootstrap.py#L256) 启动时把已加载的 builtin skill + 7 个 archon 自动写 `permanent_allow`（`permanent_deny` 不覆盖）
  - **根本设计待重做**：
    - 工具粒度细化：当前 `AuthzDecision.check_skill` 只支持 skill 级授权；需支持 tool 级 + 参数模式（`Bash(rm:*)` / `Bash(curl http*download*)`）
    - 取消 archon 神名作 subject（当前 bootstrap 把 shades_node 当 subject_type 写，但实际从未在决策路径使用——粒度过粗，徒增存储）
    - 单用户场景分级：「自用模式」全自动放行 + 真破坏命令依赖 pre_filter ／「严格模式」按现状询问
  - 正式重构等需求更明确后再启动

- [ ] **草神增强** —— 2026-04-29 完成 Phase 1 + 2（面板重做 + archon prompt 调优），剩余为 Phase 3 可选扩展
  - ~~(2) **独立知识面板**~~ ✅ 2026-04-29：`/preferences` 升级为 [`/knowledge`](../paimon/channels/webui/knowledge_html.py)（草神·智识），3 tab（记忆 / 知识库 / 文书归档）；记忆 tab 含 user/feedback/project/reference 四类 pill 切换；知识库 tab 按 category 分组浏览 + 查看全文；文书归档 tab 扫 `.paimon/tasks/<id>/` 下四影任务产物（spec.md / design.md / code/ / summary.md 等）+ markdown 预览
  - ~~(3) **Archon 的 prompt 调优能力**~~ ✅ 2026-04-29：[`archons/base.py`](../paimon/archons/base.py) 加 `_load_feedback_memories_block()` helper；7 个 archon（venti/nahida/furina/mavuika/raiden/tsaritsa/zhongli）`execute()` 路径在 system prompt 末尾注入 feedback 记忆——`/remember` 的反馈现在对复杂任务路径也生效。cron 后台路径（collect_subscription / collect_dividend）有意**不注入**避免污染采集逻辑
  - (1) `preference_get / preference_set` 专属工具 —— 偏好读写已由 `memory` 工具 `mem_type="user"` 路径覆盖，**能力等价但缺语义化**。是否值得造独立工具，看未来偏好场景是否明显异于 memory（低优先）
  - **Phase 3（可选）** 主动知识管家 + `/write` 指令：
    - 草神 `scan_memory_health()`：扫重复（title 相似）/ 冲突（feedback 相悖）/ 过时（ttl 将至或长期未引用）；结果走方案 D（新 task_type `memory_hygiene`，周一 3:00 cron 触发）写 push_archive(actor="草神")，面板加"健康报告"tab 渲染
    - `/write <需求>` 指令：草神单跑 requirement-spec skill 不走完整四影，产物直接进文书归档
    - 估算 ~4h；需要调试 LLM 相似度判定 prompt
  - **注**：原计划的"project/reference tabs + 编辑 + 手动新增" `preferences_html.py:7-8` 明确"MVP 不做"——Phase 1 把 project/reference tabs 做了（只读+删除），编辑/新增仍不做（走 /remember 指令）

- [ ] **火神增强** —— [`mavuika.py`](../paimon/archons/mavuika.py) 仅 67 行，`allowed_tools={"exec"}`
  - (1) 沙箱执行环境 —— [`exec.py`](../paimon/tools/builtin/exec.py) 是 `asyncio.create_subprocess_shell(command, ...)` 直出，60s 超时 + 8K 输出截断，**无任何沙箱/Namespace/容器化隔离**
  - (2) 技术重试机制 —— 当前仅 system prompt 里写"最多 2 次"，`mavuika.execute` 里**无任何重试 / 错误诊断代码**
  - (3) 部署工具（Docker/SSH）—— 全仓无 Docker/SSH 工具

- [ ] **冰神·AI 自举生成 skill** —— [`tsaritsa.py`](../paimon/archons/tsaritsa.py) 69 行，`allowed_tools={"skill_manage","exec"}`
  - 现状：
    - `tsaritsa.py:34` description 写"AI 自举"；prompt:22 写"规划新 skill 的设计方案"
    - `skills` 表 `source` 字段预留 `ai_gen` 枚举值 [`skills.py:19`](../paimon/foundation/irminsul/skills.py#L19)
    - `AuthzCache` 注释 [`cache.py:4`](../paimon/core/authz/cache.py#L4) 提到未来失效点
  - 关键缺口：[`skill_manage.py:22-106`](../paimon/tools/builtin/skill_manage.py) 只有 `scan / list / get`，**无 create / write 分支**。[`registry.reload_one`](../paimon/angels/registry.py#L83) 是对已有磁盘 SKILL.md 做热重载，不是 AI 生成
  - 待做：设计生成流程（模板 or LLM 自由生成 SKILL.md）+ 落地 `skill_manage.create` + 生成 skill 强制经死执 review（区别于启动自动放行）+ 可行性验证

## 2. 技术选型层面

- [ ] **异常日志落盘方案** —— [`log.py`](../paimon/log.py) 全文 25 行，只 `logger.add(sys.stderr, ...)` + 可选 `logger.add(paimon.log, 10MB rotation / 7 天 retention, level=DEBUG)`，全 level 混合、无独立 error-only handler / 无结构化异常归档 / 无 error 专属路径。待定：加 error 专属 file handler，或接外部聚合（Sentry 之类）

- [ ] **通用日报合成器**（[`paimon/foundation/digest/`](../paimon/foundation/digest/)）—— 只 prompt 层抽好，实装条件**尚未**达成
  - 当前抽象：`DigestSpec` + `render_cluster_prompt` / `render_analyze_prompt` / `render_digest_prompt` 三个函数，均只对 **LLM 驱动**的日报有效
  - 消费者：**只有风神**（`venti_event.py:102-128` + `venti.py:85`）真的调用 render_*
  - **岩神不算同构**：`zhongli._compose_daily_digest` 是**规则驱动**的 markdown 拼接（不调 LLM），无法通过 DigestSpec 参数化
  - 真正"起抽 `DigestPipeline` 条件"：**≥2 个 LLM 驱动**日报实现（比如未来水神 / 草神日报走 LLM）。届时再读两个找共同抽象
  - 当前动作：保持 prompt 层现状，等第二个 LLM 驱动消费者出现

## 3. 迁移层面

_迁移工作已全部完成（三频道、全部 skills、旧 workflow 引擎 → 生执）。_

## 附：代码体量观察（非紧急）

几个核心模块已偏大，短期尚可维护，持续扩展需要考虑拆分：

- [`archons/zhongli/zhongli.py`](../paimon/archons/zhongli/zhongli.py) 1414 行 + [`scorer.py`](../paimon/archons/zhongli/scorer.py) 764 行
- [`archons/venti.py`](../paimon/archons/venti.py) 939 行 + [`venti_event.py`](../paimon/archons/venti_event.py) 559 行
- [`shades/naberius.py`](../paimon/shades/naberius.py) 872 行
- [`foundation/selfcheck.py`](../paimon/foundation/selfcheck.py) 960 行
- [`foundation/irminsul/irminsul.py`](../paimon/foundation/irminsul/irminsul.py) 852 行

[`archons/base.py:_invoke_skill_workflow`](../paimon/archons/base.py#L175) 仍叫 `workflow`（旧引擎名），实为"skill 驱动的 tool loop"；命名残留，可择期改名。
