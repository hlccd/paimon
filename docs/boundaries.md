# 关键边界对照表

> 隶属：[神圣规划](aimon.md)

模块职责归属速查（派蒙安全闸 + 四影自进化管线 + 天使 + 七神业务接口）。

## 1. 入口 & 意图

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 意图识别（粗）| 派蒙 | 走哪条出口（chat / skill / /agents / /evolve） |
| 闲聊响应 / 复杂分析 | 派蒙 | 浅层 LLM 直答，不经四影/天使 |
| 出口人格化 | 派蒙 | 所有对话回复经派蒙包装 |

## 2. 安全与审查

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 入口安全审 | 派蒙 `core/safety/task_review` | 入口任务级合规/越权审查（/evolve 命令调） |
| 关键词预过滤 | 派蒙 `core/pre_filter.py` | shell 破坏命令直接 block / prompt injection warn |
| skill 装载审 | 派蒙 `core/safety/skill_review` | 空执装载 plugin / AI 自进化生成 skill 时调 |
| 敏感串过滤（密钥/身份证）| 派蒙 `core/safety/sensitive_filter` | memory / 知识库写入路径用 |
| 自进化提案质量审 | 死执 `review_proposal` stage | 写 review_verdict ∈ {pass, needs_revise, reject} 同步 skill_proposals 域 |
| 流程审计 | 时执 | archive + summary.md，执行链路复盘 |

## 3. 自进化提案管线（四影：生执 / 死执 / 空执 / 时执）

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 凝练 skill 草案 | 生执 | 看上下文产出草案落待审队列；不值得做时短路；单次最多 5 条 |
| 按用户反馈重写 | 生执 | 用户在面板提建议后 in-place 覆盖草案 |
| 提案质量审 | 死执 | 审完整度 / 跟现有 skill 重叠 / 工具越权 / 边界清晰；多条循环审 |
| 触发：用户主动 | 派蒙 `/evolve` 命令 | 直调生执 + 死执函数链 |
| 触发：对话累积 | 时执 | 每 5 条用户消息浅判一次 |
| 触发：定时 | 三月（每月 1 日 04:00） | 先清 30 天前未审 pending → 再扫近 30 天任务 |
| 任务/会话归档 | 时执 | 状态固化 + 审计 + summary + 触发 hook |
| 落盘 | 空执 | 用户审过后写 `skills/` 子目录 + 注册 skill 声明 |

## 4. 时间 & 归档

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 运行时压缩 | 时执 compress | 活跃会话 token 压缩（4 项改进）|
| 跨会话经验提取 | 草神 extract_experience（由时执会话压缩末尾触发） | 提取 user/feedback/project/reference 4 类条目入世界树 memory 域 |

## 5. 资源计量

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| Token + 花费统计 | 原石 | 按模块 / 用途 / 会话 多维度聚合 |
| 理财业务 | 岩神 | 用户个人财富（红利股 / 资产 / 退休）|

## 6. Skill 生态（空执业务接口）

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| skill 生态业务接口 | **空执** | skill 发现 / 注册 / 自进化提案落盘 |
| skill 唯一写入者 | 空执（→ 世界树 skill 域） | 启动扫入 / 运行时审查通过后写世界树 |
| skill 装载审 | 派蒙 `core/safety/skill_review` | 运行时新增的 skill 必过审 |
| **AI 自进化提案产生** | 四影·生执 `propose_skill` stage | 凝练 skill 草案落世界树 skill_proposals 域（status=pending）|
| **AI 自进化提案质量审** | 四影·死执 `review_proposal` stage | 写 review_verdict ∈ {pass, needs_revise, reject}|
| **AI 自进化提案用户审** | 用户 `/plugins` 面板"自进化提案"tab | 死执说 needs_revise 时 approve 按钮 disabled 强制重产再审 |
| **AI 自进化提案落盘** | 空执（apply：读 approved → 派蒙安全审 → 写 `skills/`）| 标 applied 后正式生效；空执是 skill 域唯一写入者 |
| 物理实现 | `paimon/shades/asmoday/`（空执 · 启动装载 + 提案落盘）+ `paimon/shades/istaroth/skill_watcher.py`（时执 · 文件热重载）+ webui `/plugins` 面板（含"自进化提案"tab）| skill 域归空执，热重载归时执 |

> 自进化提案产出的是**skill 草案**（name + description + system_prompt + allowed_tools 等），由空执 apply 时落 `skills/<name>/SKILL.md`。详见 [自进化](evolution.md)。

## 7. 权限画像与授权

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 权限画像（权威存储）| 世界树 authz 域 | 跨模块统一持久化 |
| 本地缓存 | 派蒙 AuthzCache | 启动读世界树；运行时通知更新 |
| stage 维度授权 | bootstrap 启动期自动放行 | propose_skill / review_proposal 默认 permanent_allow |
| 永久授权写入 | 派蒙 | 识别"永久"关键词 → 写世界树 + 自更新缓存 |
| 授权查看 / 撤销 | **空执**（webui `/plugins` 面板）| UI 入口直读世界树 + 写撤销 |

## 8. 推送链路

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 推送内容整理 | 数据收集者（风神 / 岩神 等）| 谁的数据谁整理 |
| 静默归档（cron 推送）| 三月 ring_event | 落 push_archive 域 → webui 红点抽屉，**不打断对话流** |
| 用户对话推送 | 派蒙 | 三月响铃 / 自进化提案产出 / 晨星纪要等需要对话回话时经派蒙人格化 |

## 9. Web 面板（独立交互通道，不走对话流）

七神是各面板的**业务接口 + 概念归属者**。代码实现层 webui api 直读 irminsul + 空执 SkillRegistry（不经 archon 实例），但业务语义归各七神。

| 面板 | 业务接口归属 | 数据域 |
|---|---|---|
| `/feed` `/sentiment` | 风神 | irminsul feed_items / feed_events |
| `/wealth` | 岩神 | irminsul scoring / dividend 域 |
| `/game` | 水神 | irminsul mihoyo 域 |
| `/knowledge` | 草神 | irminsul memory / knowledge |
| `/plugins` | 空执 | irminsul skill_declarations + skill_proposals + authz |
| `/tasks` | 时执 | irminsul scheduled_tasks 域 |

## 10. 数据域业务接口（七神承接）

世界树是唯一存储层（管字节）；各业务接口归对应七神（管语义）：

| 数据域 | 业务接口归属 | 写入触发 |
|---|---|---|
| memory（记忆）| 草神 | 用户 `/remember` / 会话压缩末尾经验提取 / 草神 hygiene cron |
| knowledge（知识库）| 草神 | 用户面板编辑 / 文档归档 |
| skill 声明 | 空执 | 启动扫入 + 运行时审过 + 自进化提案 apply |
| skill_proposals（自进化提案）| 四影 | 生执提案 / 死执审 verdict / 空执标 applied |
| feed_items / feed_events（信息流）| 风神 | feed_collect cron + 事件聚类 |
| scoring / dividend（红利股）| 岩神 | dividend_scan cron + 用户关注股 |
| mihoyo 账号 / 抽卡 / 便笺 | 水神 | mihoyo_collect cron + 用户绑定 |
| authz 授权 | 派蒙 + 空执 | 派蒙写永久授权；空执面板撤销 |
| token / cost | 原石 | 各模块 LLM 调用自动计 |
