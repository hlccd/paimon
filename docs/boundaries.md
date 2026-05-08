# 关键边界对照表

> 隶属：[神圣规划](aimon.md)

模块职责归属速查，按场景分类。v7 后边界（生 / 审 / 派 / 收 + 派蒙安全闸 + 七神值班）。

## 1. 入口 & 意图

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 意图识别（粗）| 派蒙 | 走哪条出口（chat / skill / /task / /agents） |
| 闲聊响应 | 派蒙 | 浅层 LLM 直答，不经四影/天使 |
| 出口人格化 | 派蒙 | 所有对话回复经派蒙包装 |

## 2. 安全与审查

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 入口安全审 | 派蒙 `core/safety/task_review` | 入口任务级合规/越权审查（v7 起从死执上提）|
| 关键词预过滤 | 派蒙 `core/pre_filter.py` | shell 破坏命令直接 block / prompt injection warn |
| DAG 敏感扫描 + 批量授权 | 派蒙 `core/safety/scan_plan` | 生执编排后调（v7 起从死执上提）|
| skill 热加载审 | 派蒙 `core/safety/skill_review` | skill_loader 注册前调（v7 起从死执上提）|
| 敏感串过滤（密钥/身份证）| 派蒙 `core/safety/sensitive_filter` | memory / 知识库写入路径用 |
| 产物质量审 | 死执 review_* stage | spec/design/code 评审循环（生执出活 → 死执打 verdict）|
| 静态自检 | 死执 self_check | py_compile + ruff + pytest |
| 流程审计 | 时执 | archive + summary.md，执行链路复盘 |

## 3. 编排 & 执行（四影 v7：生 / 审 / 派 / 收）

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 任务编排（DAG 拆分）| 生执 plan | LLM 输出 DAG（assignee=stage 名）+ 多轮 revise |
| 产出工程产物 | 生执 produce | spec/design/code（调对应 skill）+ simple_code/exec/chat（LLM tool-loop）|
| 评审循环 | 死执 review | review_spec/design/code 出 verdict |
| 拓扑分发 | 空执 | _STAGE_ROUTER 派各影 + 失败重试 |
| 失败补偿 | 时执 saga | 反序对 completed 节点跑补偿（调生执 exec）|
| 归档 | 时执 archive | 任务结束（成功/失败）→ 落档 + 审计 |

## 4. 时间 & 归档

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 运行时压缩 | 时执 compress | 活跃会话 token 压缩（4 项改进）|
| 最终归档 | 时执 archive | 结束后入冷区 → 过期清扫 |
| 跨会话经验提取 | 时执 extract_experience | 归档时提取记忆条目入世界树 memory 域 |

## 5. 资源计量

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| Token + 花费统计 | 原石 | 按模块 / 用途 / 会话 多维度聚合 |
| 理财业务 | 岩神 | 用户个人财富（红利股 / 资产 / 退休）|

## 6. Skill 生态（冰神业务接口）

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| skill 生态业务接口 | **冰神** | skill 发现 / 注册 / AI 自举的语义负责人 |
| skill 唯一写入者 | 冰神（→ 世界树 skill 域） | 启动扫入 / 运行时审查通过后写世界树 |
| skill 装载审 | 派蒙 `core/safety/skill_review` | 运行时新增的 skill 必过审 |
| AI 自举生成新 skill | 四影 `/task`（仍归冰神生态） | 走生执 produce_spec → design → code → 死执 review_code，落盘走冰神写世界树 |
| 物理实现 | `paimon/skill_loader/`（冰神语义壳）+ webui `/plugins` 面板 | 代码层模块名是 skill_loader，语义归属仍是冰神 |

## 7. 权限画像与授权

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 权限画像（权威存储）| 世界树 authz 域 | 跨模块统一持久化 |
| 本地缓存 | 派蒙 AuthzCache | 启动读世界树；运行时四影通知更新 |
| stage 维度授权 | 派蒙 `core/safety/scan_plan` | subject_type=stage（v7 起统一，不再 shades_node）|
| 永久授权写入 | 派蒙 | 识别"永久"关键词 → 写世界树 + 自更新缓存 |
| 授权查看 / 撤销 | **冰神**（webui `/plugins` 面板）| 冰神语义负责人：UI 入口直读 + 写世界树 |

## 8. 推送链路

| 场景 | 归属 | 关键区分点 |
|---|---|---|
| 推送内容整理 | 数据收集者（风神 / 岩神 等）| 谁的数据谁整理 |
| 静默归档（cron 推送）| 三月 ring_event | 落 push_archive 域 → webui 红点抽屉，**不打断对话流** |
| 用户对话推送 | 派蒙 | 三月响铃 / 四影产物 / 晨星纪要等需要对话回话时经派蒙人格化 |

## 9. Web 面板（独立交互通道，不走对话流）

七神是各面板的**业务接口 + 概念归属者**。代码实现层 webui api 直读 irminsul / skill_loader（v7 解耦后不经 archon 实例），但业务语义归各七神。

| 面板 | 业务接口归属 | 数据域 |
|---|---|---|
| `/feed` `/sentiment` | 风神 | irminsul feed_items / feed_events |
| `/wealth` | 岩神 | irminsul scoring / dividend 域 |
| `/game` | 水神 | irminsul mihoyo 域 |
| `/knowledge` | 草神 | irminsul memory / knowledge / archives |
| `/plugins` | 冰神 | skill_loader + irminsul authz |
| `/tasks` | 时执 | irminsul task 域 |

## 10. 数据域业务接口（七神承接）

世界树是唯一存储层（管字节）；各业务接口归对应七神（管语义）：

| 数据域 | 业务接口归属 | 写入触发 |
|---|---|---|
| memory（记忆）| 草神 | 时执 extract_experience 收尾 / 用户 `/remember` / 草神 hygiene cron |
| knowledge（知识库）| 草神 | 用户面板编辑 / 文档归档 |
| skill 声明 | 冰神 | skill_loader 启动扫入 + 运行时审过 |
| feed_items / feed_events（信息流）| 风神 | feed_collect cron + 事件聚类 |
| scoring / dividend（红利股）| 岩神 | dividend_scan cron + 用户关注股 |
| mihoyo 账号 / 抽卡 / 便笺 | 水神 | mihoyo_collect cron + 用户绑定 |
| task 任务域 | 时执 | 四影管线归档 / 生命周期清扫 |
| authz 授权 | 派蒙 + 冰神 | 派蒙写永久授权；冰神面板撤销 |
| token / cost | 原石 | 各模块 LLM 调用自动计 |
