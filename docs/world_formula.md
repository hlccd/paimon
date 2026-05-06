# 世界式（World-Formula）

> **文档状态**：草案 / 讨论中 / 不影响现有实现
> **关系**：本文档**不替代** [aimon.md](aimon.md)；新架构稳定后再讨论分模块迁移路径。

---

## 一、架构总览

- **【世界式】**
  - [**向导·派蒙**](paimon/paimon.md)（统一入口 + 自动路由）
    - 入口接入：channel（WebUI / TG / QQ）
    - 轻鉴权 / 轻量安全 / 意图分类
    - 自动路由：按三维度任务特征分流到 4 出口（详 §二）
    - 闲聊响应：浅层 LLM 直答
    - 出口人格化：所有产物经派蒙回 channel
  - **【主持·多节点任务】四影**（流程骨架，不做业务）
    - [**死执·若纳瓦**](shades/jonova.md)：入口审（合规 / 越权）+ DAG 敏感扫描 + 批量授权
    - [**生执·纳贝里士**](shades/naberius.md)：DAG 拆分 + revise 重写（cap=3）+ 失败回滚
    - [**空执·阿斯莫代**](shades/asmoday.md)：拓扑分层 dispatch + 节点并发 + saga
    - [**时执·伊斯塔露**](shades/istaroth.md)：归档 + 审计 + 生命周期
  - **【主持·多视角讨论】晨星 + 天使**
    - **晨星**：leader 天使（召集 / 调度发言 / 判收敛 / 综合输出）
    - **天使**：协同角色，预定义 11 个池（结构性 / 评估性 / 对抗性，详 §三 /agents）
  - **【能力】七神**（skill 调用代理 + 业务 cron + 面板，**不进 LLM 对话流**）
    - [**风神·巴巴托斯**](archons/venti.md)：信息采集 → web-search / bili / xhs
    - [**岩神·摩拉克斯**](archons/zhongli.md)：财富 → dividend-tracker
    - [**草神·纳西妲**](archons/nahida.md)：智慧 + 写代码 4 件套（spec / design / code / check）
    - [**雷神·巴尔泽布**](archons/raiden.md)：（写代码 skill 已转草神，业务身份待定）
    - [**火神·玛薇卡**](archons/mavuika.md)：重型工具 → exec / file_ops / web_fetch
    - [**水神·芙宁娜**](archons/furina.md)：游戏 → mihoyo
    - [**冰神·冰之女皇**](archons/tsaritsa.md)：skill 生态管理
  - **【全局支撑层】**（沿用 aimon，不变）
    - [**世界树**](foundation/irminsul.md)：唯一存储层
    - [**三月女神**](foundation/march.md)：调度 + 推送响铃
    - [**神之心**](foundation/gnosis.md)：LLM 资源池
    - [**地脉**](foundation/leyline.md)：事件总线
    - [**原石**](foundation/primogem.md)：token / 花费统计

### 出场铁律

- 四影**只**在 /task；天使**只**在 /agents；两者不交叉
- skill 调用**永远**经主管七神 `archon.call_skill()`
- 七神**不进** LLM 对话流——只做调用代理 + cron + 面板

### 与老架构差异

| 维度 | 老架构 aimon | 世界式 |
|---|---|---|
| 入口 | /task 一种复杂入口 | 4 出口 + 派蒙自动路由 |
| 七神身份 | 业务 + 扮 LLM 节点 | 业务 + skill 调用代理；不扮 LLM |
| 写代码节点 | 七神跑 LLM | asmoday → 草神.call_skill → skill |
| 多视角讨论 | 无 | /agents 新轨道 |

### 跨模块参考

- [aimon.md 老架构](aimon.md) / [permissions.md](permissions.md) / [boundaries.md](boundaries.md) / [todo.md](todo.md)

---

## 二、自动路由

`/task` `/agents` 是过渡期手动 override；最终派蒙根据自然语言**自动**分流。

### 三维度任务特征

| 维度 | 含义 |
|---|---|
| 要执行？ | 写文件 / 调 API / 跑命令 / 产物落盘 |
| 要多步？ | 跨 >1 个工具 / 动作 |
| 要多视角？ | 权衡 / 选型 / 决策 / 复盘 |

### 三维度 → 出口（不重叠）

| 执行 | 多步 | 多视角 | → 出口 |
|---|---|---|---|
| 0 | 0 | 0 | chat |
| 1 | 0 | 0 | skill |
| 1 | 1 | 0 | /task |
| · | · | 1 | /agents |

多视角是最强信号——一旦命中，前两维不论。

### 边界样例

| 用户消息 | 出口 |
|---|---|
| "装饰器是什么" / "30 分钟后提醒我" | chat |
| "搜一下 RBAC 库" / "看看米游社签到了" | skill |
| "写个 todo 服务" / "采集新闻+摘要+推送" | /task |
| "用 sqlite 还是 postgres" / "应不应该上 RBAC" | /agents |

### 运行时升级（兜底）

初始分类不准时，主持人**问 user 确认后**升级（不允许静默切换）：
chat → /task / /agents（发现要执行多步） · skill → /task（七神判超出） · /task → /agents（spec 报歧义） · /agents → /task（共识落地）

---

## 三、交互流程

### 3.1 chat
```
用户 → 派蒙意图分类 → 派蒙 LLM 直答 → channel
```

### 3.2 skill
```
派蒙 → 主管七神 archon.call_skill(X, params) → skill 内部 LLM → 派蒙 → channel
```

### 3.3 /task
```
派蒙 → 四影
   jonova    审需求 + DAG 敏感扫描 + 批量授权
   naberius  拆 DAG（trivial 1 / simple 2 / complex 6 节点）
   asmoday   各节点经主管七神.call_skill(...)；review issue → revise（cap=3）
   istaroth  归档 + 审计
派蒙 → channel
```

### 3.4 /agents

适用 5 类场景：决策 / 选型权衡 / 需求澄清 / 复盘对抗 / 方案评估。

```
派蒙 → 晨星召集 N≤5 个天使 → 循环（晨星定下一个发言者 → 天使看 history 后发言）
       → 收敛（共识 / 死锁 / 30 次 LLM 上限） → 晨星综合输出 → 派蒙 → channel
```

天使预定义池（晨星按任务挑）：
- **结构性 5 个**：需求分析 / 架构 / 实施 / 测试 / 审查
- **评估性 4 个**：财务评估 / 风险评估 / 用户代言 / 历史复盘
- **对抗性 2 个**：挑刺者 / 提议者

召集示例：写代码 = 需求分析+架构+审查；投资决策 = 财务+风险+挑刺者；复盘 = 历史+挑刺者+用户代言。

---

## 四、待补

- 派蒙意图分类的 LLM prompt（三维度判定 + few-shot）
- 路由失误的 ask-clarify 协议
- /task：四影各档位具体场景（trivial / complex / 跨域复合 / council 落地）
- /agents：晨星调度协议 / token 熔断 / 用户插话状态机 / 角色池扩展
- 形态切换：council → /task 的 spec.md 移交协议
- 七神 `call_skill()` 接口形态
- 实施路线图分阶段拆分

---

> 各模块详情见上方索引或老架构 [aimon.md](aimon.md)。世界式稳定后再讨论分模块迁移。
