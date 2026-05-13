# 当前任务：WebUI 全面优化（温馨柔和风改造收尾 + 10 轮深度迭代）

> 隶属：[神圣规划](aimon.md) · WebUI 改造延续
>
> **强约束**：本文档定义的所有任务、轮次、范围**必须严格按此执行，不允许缩短任何一环、不允许省略任何一个 page、不允许把"10 轮 PDCA"压缩成更少轮次**。
>
> 工期不限，按此清单一直推进直到全部完成才能停。

---

## 0. 背景

WebUI 已完成温馨柔和风改造的「面板拆分」阶段（P0 + P2-1 ~ P2-8 共 9 个 commit），把 6 个子包形式 + 1 个对话主入口 + 1 个 feed 单文件面板从 inline Python 字符串拆到独立 templates / static 文件，配套抽出公共 layout（`_warm_layout.html` + `_warm_sidebar.html` + `warm.css`）和通用控件库（components.css / components.js / icons.js / tokens.css）。

但当前产出存在以下问题，需要继续做完：

1. **plugins_html.py 还没拆**（最后一个 815 行单文件面板，是的 sidebar 上能点进去的旧风格界面之一）
2. **命名混乱**：副标题/路由 tab/用量统计/路由分组里大量出现"神/影/三月/天使/晨星/神之心/管辖"等暴露内部架构的词，对用户没意义
3. **md 不渲染**：聊天消息、推送内容、资讯卡片应该用 marked 渲染成 HTML，现在大量地方仍是 txt 直出，难看
4. **页面深度不够**：每个 page 只是把字符串搬到独立文件 + token 替换 + 图标替换 emoji，**没有针对每个 page 做"配色 / 字号 / 留白 / 对齐 / 信息密度 / 交互"的真正打磨**，特别是 game / wealth 这种组件多的页面看起来很丑

---

## 1. 任务清单（5 个 Phase，严格按顺序）

### Phase 1 — 拆完最后一个面板（P2-9）✅

- [x] 拆 `paimon/channels/webui/plugins_html.py`（815 行单文件）→ 独立三件套
  - `paimon/channels/webui/templates/plugins.html`
  - `paimon/channels/webui/static/css/plugins.css`
  - `paimon/channels/webui/static/js/plugins.js`
- [x] 改 handler 用 `render_warm_page`
- [x] 删除旧 `plugins_html.py`
- [x] 实机校验 200 + 0 console error
- [x] **独立 commit**：`refactor: P2-9 拆 plugins 面板到温馨柔和风`（19965d6）

> 完成 Phase 1 后，所有 sidebar 入口 page 都已拆到温馨柔和风，没有"还能点回老界面"的入口。

### Phase 2 — 命名问题全局审计（**不独立 commit**，结果作为 Phase 4 各 page 必修项）

#### 严禁词汇清单

全 web 界面**除了顶部 Paimon 品牌字外**，禁止出现以下任意词：

- `神之心`、`七神`、`四影`、`三月`、`天使`
- 具体神名：`风神`、`水神`、`草神`、`岩神`、`火神`、`雷神`、`晨星`
- 具体英文 codename：`archon`、`shade`、`morningstar`、`raiden`、`mavuika` 等
- 「XX 管辖」、「XX 代管」、「XX 主管」之类身份描述
- 任何暴露 paimon 内部"神 / 影 / 天使"组织架构的词

#### 整改原则

**用做什么事直接描述，不写谁做的**。例：

| 旧（含命名） | 新（功能描述） |
|------|--------|
| 「Paimon 各组件 LLM 调用统计 + 花费分析（神之心代管）」 | 「LLM 调用统计 + 花费分析」 |
| 「跨会话记忆 + 结构化知识库（草神管辖）」 | 「跨会话记忆 + 结构化知识库」 |
| 「LLM Profile 管理 + 调用点路由配置（神之心管辖）」 | 「LLM Profile 管理 + 调用点路由配置」 |
| 「三月组件探针 + Quick / Deep 历史 + 自动升级（三月管辖）」 | 「组件探针 + Quick / Deep 历史 + 自动升级」 |
| 「A 股红利股追踪 — 评分 + 行业均衡 + 变化检测（岩神管辖）」 | 「A 股红利股追踪 — 评分 + 行业均衡 + 变化检测」 |
| 「米哈游 三游戏便笺 + 抽卡 + 战报（水神管辖）」 | 「米哈游 三游戏便笺 + 抽卡 + 战报」 |
| 「topic UGC 多源调研 + 每日热点 + 近期回顾（风神管辖）」 | 「topic UGC 多源调研 + 每日热点 + 近期回顾」 |
| 「岩神·理财日报」 | 「理财日报」 |
| 「晨星·调研」（用量明细 purpose 字段） | 「多视角讨论」或「跨视角调研」 |
| 路由分组：「派蒙·守门 / 出口·skill / 出口·agents / 出口·evolve / 七神·archon 业务接口 / 三月女神·调度 / 草神-memory / 音视频处理」 | 改为按"做什么的事"分组：「对话入口 / 工具调用 / 多视角讨论 / 自进化提案 / 业务面板后台 / 任务调度 / 记忆/知识库 / 音视频处理」 |

#### 扫描位置（不许漏）

- [ ] 所有 `paimon/channels/webui/templates/*.html` 副标题 / 标题 / 占位文字 / tooltip
- [ ] 所有 `paimon/channels/webui/static/js/*.js` 渲染文本 / alert / toast 内容 / 按钮文案 / table th
- [ ] `paimon/foundation/model_router.py` 路由 metadata 的 category 名 / component 描述
- [ ] `paimon/channels/webui/api/*.py` handler 里 `render_warm_page(title=...)` 参数
- [ ] `paimon/channels/webui/templates/_warm_sidebar.html` 中 nav 文字
- [ ] 数据库 `token_calls.purpose` 字段已存值审计：`SELECT DISTINCT purpose FROM token_calls`，含命名的修正（要么改源代码不再写入新值，要么 UPDATE 旧记录改名）

> **注意**：Phase 2 **不独立 commit**。命名净化跟 page 强绑定（每个 page 自己的副标题 / 文案 / 路由分组都属于该 page），所以扫描出的所有命名问题**分摊到 Phase 4 对应 page 的 10 轮迭代里修复**，最终归属各 page 的 commit。
>
> 但跨多个 page 的全局元数据（如 `paimon/foundation/model_router.py` 的 category 名）影响多个 page 显示，这种改动归到**「最受益的 page」对应的 commit**（model_router 主要影响 `/llm` 路由 tab，归 llm commit）；如果实在跨度太大无法归属单个 page，可以 1 个独立 commit 但要尽量避免。

### Phase 3 — Markdown 渲染问题全局审计（**不独立 commit**，结果作为 Phase 4 各 page 必修项）

#### 问题症状

聊天消息、推送内容、资讯卡片显示成纯 txt，没有用 marked 渲染成 HTML。粗体不粗、链接不蓝、列表不缩进、代码块不高亮。

#### 排查 + 修复位置

- [ ] **chat (`/`) 主聊天消息渲染**：检查 `static/js/chat.js` 里 `appendMessage` / `streamMessage` 等函数，把 `textContent = msg` 改为 `innerHTML = marked.parse(msg)` 但要先 sanitize（防 XSS）
- [ ] **feed 今日热点 / 近期回顾**：`static/js/feed.js` 里渲染 hotspot.body / weekly.body 的地方
- [ ] **wealth 关注股资讯卡片**：`static/js/wealth.js` 里渲染 user_watch.feed_text / news_text 的地方
- [ ] **game 推送内容 / 战报渲染**：`static/js/game.js`
- [ ] **knowledge 详情 modal**：`static/js/knowledge.js` 里 `modalBody.textContent = it.body` 改为 marked
- [ ] **每个引入 marked 的 page 验证**：`<script src="marked.min.js">` 是否真在 `_warm_layout.html` 的 head 里加载

#### XSS 防护要点

marked.parse 出 HTML 后必须做白名单 sanitize（Paimon 自己的内容相对可信，但用户/外部源内容必须过 DOMPurify 或自写白名单）。

> **注意**：Phase 3 **不独立 commit**。md 渲染问题跟 page 强绑定（chat 渲染 chat 消息、feed 渲染 hotspot 卡片、wealth 渲染资讯卡片...），所以**分摊到 Phase 4 对应 page 的 10 轮迭代里修复**，最终归属各 page 的 commit。
>
> 全局共享的工具（如 `static/js/components.js` 里如果加了通用 markdown render helper），归到第一个用它的 page commit；后续 page 共用即可。

### Phase 4 — 每个 page 做 10 轮完整 PDCA 深度迭代（**唯一产生 commit 的 phase**）

#### 范围 — 10 个 page，一个不许漏

1. `/` (chat 主入口)
2. `/dashboard` (用量)
3. `/tasks` (任务)
4. `/knowledge` (世界树记忆 + 知识库)
5. `/llm` (模型 + 路由)
6. `/selfcheck` (自检)
7. `/wealth` (理财)
8. `/game` (游戏)
9. `/feed` (订阅 + 热点)
10. `/plugins` (插件)

#### 每一轮的完整结构（每轮都做完整一套 PDCA，**不许拆分**到不同轮）

```
某 page · 第 N 轮（N = 1..10）

  1. 代码分析（必做）
     · 读这个 page 的 .html / .css / .js
     · 找出本轮要聚焦的具体问题（命名/字号/留白/对齐/颜色/交互/可访问性/重复...任选 1-3 个角度）
     · 必要时 curl 取 HTML 看结构 / 看 computed CSS

  2. 界面思考（必做）
     · 基于代码分析的问题，思考改成什么样
     · 参考 components.css / warm.css 已建立的设计语言
     · 不引入跟温馨柔和风冲突的元素（暖米白底 + violet 紫 + stone 暖灰）

  3. 界面优化（必做）
     · 实际改 .html / .css / .js
     · 改完起 paimon 跑 curl 验证 200 + 0 console error
     · 如有必要小截图（viewport ≤ 1200×800）但不 Read 像素

  4. 自问 4 题把关（必做，4 题都要过关才算这一轮 done）
     · 好看吗？     ← 视觉上比上一轮明显进步？
     · 配色合理吗？ ← 符合温馨柔和风（暖白 + 紫 + 暖灰），无突兀
     · 符合要求吗？ ← 没违反 Phase 2 命名净化、Phase 3 md 渲染等强约束
     · 交互方便吗？ ← 按钮可达、状态明确、错误友好、键盘可用
     · 任一题不过关 → 这一轮不能停，继续优化直到 4 题过关

  完成 → 进入第 N+1 轮（聚焦不同的角度）
```

#### 每个 page 10 轮的常见聚焦角度（参考，不强制按此顺序）

可根据该 page 实际问题挑 10 个角度做：

- 命名净化（应该 Phase 2 已做，但 page 内细节再过一遍）
- 字号层级（h1 / h2 / 正文 / 副文 / 数字 / 标签 间距是否清晰）
- 行高 / 字重 / letter-spacing
- 留白（padding / margin / gap）
- 对齐（左对齐 / 居中 / 数字 tabular-nums 等宽对齐）
- 颜色对比度（满足 WCAG AA 4.5:1）
- 信息密度（卡片是否太空 / 太挤）
- 状态明确（加载 / 空 / 成功 / 失败 / 禁用 都有清晰视觉）
- 交互反馈（hover / focus / active / loading）
- 错误处理（fetch 失败 / 空数据 / 输入校验）
- 键盘可用 + a11y（focus ring / tab 顺序 / aria）
- 动效 / 过渡（不张扬，符合清冷感）
- 响应式（窄屏会不会塌）
- 数据卡片排版（数字字号 / 单位位置 / 副数据 hint）
- 表格密度（行高 / 行 hover / th 字重）
- modal 体验（focus trap / ESC 关 / 背景遮罩）
- toast / flash 提醒位置和持续时间
- 空状态引导（不只一句"暂无数据"，要有 icon + 引导 CTA）
- 动态内容渲染（md / 代码 / 链接是否可点）
- 整体一致性（同一个 page 内各组件风格是否一致）

#### Phase 4 必含的内容（每个 page 都要在 10 轮内完成，作为该 page commit 的一部分）

每个 page 的 10 轮迭代**必须包含**以下三类工作（不允许漏，不允许遗留到后续 phase）：

1. **该 page 的命名净化**（Phase 2 审计出的命名问题中，该 page 涉及的部分必须修完）
2. **该 page 的 md 渲染修复**（Phase 3 审计出的 md 渲染问题中，该 page 涉及的部分必须修完）
3. **该 page 的视觉/交互/信息密度迭代**（10 轮的主体工作）

#### 完成判据

每个 page 做完 10 轮后：
- 视觉上比第 0 轮（Phase 1 拆完后）有 **质的飞跃**
- 4 道自问题在第 10 轮全部「过关」
- 0 console error / 0 page error
- 该 page 内 **0 命名违例**（无神/影/天使等内部词）
- 该 page 内 **md 内容真正渲染成 HTML**（不是 txt 直出）
- 该 page 视觉/控件/字号/留白符合 §4-§6 的所有验收标准

### Phase 5 — rebase 合并 commit（最后一步）

#### 步骤

1. **必做备份**：
   ```bash
   git branch backup-pre-rebase
   ```
2. 查 rebase 起点（P0 之前的 commit）：
   ```bash
   git log --oneline | grep "CLAUDE.md 加协作规范"  # ca1c6d5
   ```
3. 交互式 rebase：
   ```bash
   git rebase -i ca1c6d5
   ```
4. 把每个 page 的 Phase 4 迭代 commit 用 `fixup` / `squash` 合到对应原 commit（P0 / P2-1 ~ P2-9）。
5. **不会有独立的"命名净化 commit"或"md 渲染 commit"**（Phase 2/3 的修复已经分摊到各 page commit 里了）；唯一可能新增独立 commit 是"跨多个 page 共享的全局元数据改动"（如 model_router 路由分组重命名涉及多 page），但这种也要尽量塞进最相关的 page commit。

#### 最终交付

约 **10 个独立 commit（按 page）**，每个 commit 内含该 page **完整 10 轮迭代后的最终态**（含该 page 的命名净化 + md 渲染 + 视觉/交互优化）：

```
（chronological 顺序）
1. WebUI 改造基础设施 + dashboard 完整版（含 P0 通用控件库 + 10 轮迭代后的 dashboard）
2. tasks 完整版
3. knowledge 完整版
4. selfcheck 完整版
5. llm 完整版（含 model_router 路由分组重命名）
6. wealth 完整版
7. game 完整版
8. chat 完整版
9. feed 完整版
10. plugins 完整版
```

完成后 **不主动 push**（按 paimon feedback memory）。等用户验收后用户自己 push。

### Phase 6 — 全功能回归测试 3 轮（rebase 完成后做）

#### 入场条件

Phase 5 rebase 已完成，`git log --oneline` 看到约 10 个干净 commit，main 分支整洁。

#### 测试规范

启动 paimon（`python3 -m paimon`），对**所有 10 个 page 的所有功能 / 所有模块**至少做 **3 轮完整测试**。每轮的覆盖角度不同：

##### 第 1 轮 — UI 加载 + 路径覆盖

- [ ] 每个 page 都 GET 一次（curl + playwright 加载），HTTP 200 + 0 console error
- [ ] 每个 tab 都点切一次
- [ ] 每个二级 panel / pill / 折叠区都点开一次
- [ ] 每个 modal（含 form modal / 详情 modal / 确认 modal）都开关一次
- [ ] 每个 sidebar 菜单都点跳转一次
- [ ] 截大图核对（≤1200×800 viewport）

##### 第 2 轮 — 实际功能交互

- [ ] **chat**: 发一条简短测试消息（"测试"），看 SSE 流式 + 模型响应 + md 渲染
- [ ] **dashboard**: 刷新按钮 click + chart 各 period (day/week/month/hour/weekday) × 各 metric (tokens/cost) 切完
- [ ] **tasks**: 刷新 + scheduled/system tab 切 + archon section 折叠展开
- [ ] **knowledge**: 4 类 mem pill 切 + 知识库 tab + 「+ 新建」记忆走完整路径（输入 → 保存 → 看 toast → 看列表更新）
- [ ] **llm**:
  - 「+ 新增 Profile」打开 form 但不实际新建（不消耗）
  - **路由切默认 profile xiaomi → mimo → xiaomi**（API 走 set-default）
  - 「测连接」对一个已有 profile 点一次（消耗约 1 次最小请求，可接受）
- [ ] **selfcheck**:
  - 「检查更新」click（fetch /api/selfcheck/upgrade/check）
  - 「Quick / Deep 历史」tab 切
  - **不实际跑 Quick / Deep**（避免副作用）
- [ ] **wealth**:
  - 4 个 tab 切完
  - 「添加股票」form 输入校验（不实际添加 — 走 form 校验路径但点取消）
  - 「立即抓取」/「重评分」/「日更」/「全扫描」按钮 click 后看是否触发 toast 反馈（**实际可能启动后台扫描，看用户接受度**）
- [ ] **game**:
  - 总览 / 原神 / 崩铁 / 绝区零 4 tab 切
  - 点一个游戏的「看详细」展开看
  - 「签到」按钮 click（**会调真实米游社 API**，看用户接受度）
- [ ] **feed**:
  - 4 tab 切完（今日热点 / 近期回顾 / 订阅管理 / 站点登录）
  - 点一个订阅的展开 / 跑按钮（看是否会启动后台采集，看用户接受度）
- [ ] **plugins**:
  - skill 列表 + 跨视角讨论 / 自进化提案 tab 切
  - 看 skill 卡片
  - 一个 skill 的「查看」/「修改」点开看 modal
- [ ] 所有路由相关功能 **xiaomi + mimo 都测一轮**（这是用户特别强调的）

##### 第 3 轮 — 极端场景 + 错误处理

- [ ] 空数据 page：每个 page 找一个空状态展示路径（如 selfcheck 没 quick 历史 / wealth 没关注股 / tasks 没用户任务）— 看空状态文案 + 引导是否符合 §6 要求
- [ ] 网络失败：在 playwright 里禁用网络模拟，看 fetch 失败时是否有友好错误提示
- [ ] 输入校验：表单留空 / 超长 / 特殊字符 — 看 client + server 是否拒绝且提示明确
- [ ] 大数据：dashboard 用量明细如果有大量记录，表格滚动是否顺畅
- [ ] 边界条件：日期切到未来 / 跨年 / 周末等

#### 处理流程

**每发现一个问题**：
1. 记录到本文档 §8 问题登记表（追加）
2. 立即修（不积压）
3. 修完起 paimon 复测一轮验证修复有效

**如果修复涉及多个 page** → 改动归到主受益 page 的 commit；用 `git rebase -i` 把修复 fixup 进对应 page commit。

**3 轮全跑完没新问题** = 完成。

#### 完成判据

- [ ] 3 轮测试全跑完，每轮覆盖完整
- [ ] 所有发现的问题都修完且复测通过
- [ ] paimon 启动到关闭 0 报错（看启动日志）
- [ ] git log --oneline 仍是约 10 个 page commit（修复都 fixup 进去了）
- [ ] **不主动 commit / push**（按 feedback memory），等用户验收

---

## 2. 强约束（不许违背）

### A. 严禁缩短或省略

- **每个 page 必须 10 轮**，不许 5 轮、不许 8 轮、不许"差不多就行"
- **每轮必须完整 PDCA**（代码分析 + 界面思考 + 界面优化 + 自问 4 题），不许只做其中 2-3 步
- **10 个 page 一个不许漏**，feed / plugins / chat 都要做
- **4 道自问题缺一不可**，4 题都过关才算一轮 done
- **不许借口"边际收益递减"提前停**，第 10 轮也要拿出明显改进

### B. 不截图 Read 像素分析

- 截图会导致 context 卡死。所以本任务**禁止用 Read 工具去看 PNG 像素分析**
- 主要靠：
  - 读 `.html` / `.css` / `.js` 源代码
  - `curl http://localhost:2975/<path>` 取实际 HTML
  - playwright 取 computed CSS / DOM 结构
  - 自动化点击 + console.error / pageerror 监听
- 必要时小截图（viewport ≤ 1200 × 800），但只用 `playwright.screenshot` 存盘，**不 Read 出来到对话**

### C. 不动用户手动改的 dashboard.js / dashboard.css

- 工作目录目前有用户手动改的 `dashboard.js`（去组件列）和 `dashboard.css`（bar 加宽 90% / max 96px）
- 这俩 modified 不要单独 commit，留作 dashboard 那一轮 Phase 4 迭代时一并 fixup 进 dashboard 的 commit

### D. rebase 前必备份

- `git branch backup-pre-rebase`
- 不 push 直到用户验收

### E. 命名净化要彻底

- toolbar / button / table th / tooltip / placeholder / error message / route metadata / db purpose 字段全要扫
- 不放过任何角落

### F. md 渲染全 page 验证

- 不只 chat，包括 feed / wealth / game / knowledge 的所有"显示用户/系统内容"区域
- XSS 防护必须到位

### G. 每个 page 完成后才能进入下一个

- 不许"先把 10 个 page 都做第 1 轮，再做第 2 轮"这种横向并行
- 必须**纵向深耕**：当前 page 10 轮全做完才能动下一个 page

---

## 3. 工作量预估

| Phase | 估时 | 备注 |
|------|------|------|
| Phase 1 拆 plugins | 30-60 min | 套路成熟 |
| Phase 2 命名净化 | 1-2 小时 | 含 model_router metadata 改 |
| Phase 3 md 渲染 | 30-60 min | 5 个 page 渲染点 |
| **Phase 4 10 page × 10 轮迭代** | **17-33 小时** | 每轮 10-20 min |
| Phase 5 rebase 合并 commit | 30 min | |
| **合计** | **20-38 小时** | 跨多个晚上完成 |

---

## 4. UI 整改后的核心要求（验收标准）

### A. 视觉风格统一

- [ ] 全 web 走「**温馨柔和风**」（不再有清冷感、不再有 2018-2020 暗色管理后台风、不再有彩色喧宾夺主）
- [ ] 整体调性：**专业 / 职能 / 整洁 / 美观 / 易用 / 优雅 / 温馨柔和**
- [ ] 第一眼印象不是「数据后台」而是「克制专业的助手工作台」
- [ ] 所有 page 共享一致的 layout 骨架（左 sidebar + 主内容区），不允许某个 page 独立另起一套布局（除 chat 全屏模式）

### B. 布局一致性

- [ ] 左 sidebar 宽 240px，10 个菜单项按"功能名"列出，active 项 violet 紫底 + 紫字
- [ ] sidebar 顶部 brand「Paimon」（圆形 violet 块 + 文字），底部「通知」按钮
- [ ] 主内容区 max-width 1200px，padding 32px，居中
- [ ] 每个 page 顶部都有 `.dash-page-header`（标题 + 副标题 + 右侧操作按钮组），格式统一

### C. 通用控件一律走 components.css

- [ ] 按钮统一走 `.pm-btn`（变体：primary / default / ghost / danger / success；尺寸：sm / md / lg；icon-only）
- [ ] 输入 / textarea / select 走 `.pm-input` / `.pm-textarea` / `.pm-select`
- [ ] 卡片统一走 `.pm-card` / `.pm-stat-card`
- [ ] tab 用 `.pm-tabs` + `.pm-tab`（业务 page 内自定义 .tab-btn 的也要在 css 里走相同视觉）
- [ ] modal 用原生 `<dialog>` + `.pm-modal`（自带 focus trap + ESC 关）
- [ ] toast 用 `pmToast.success/.error/.info/.warning`
- [ ] 异步按钮用 `pmBtn.runAsync(btn, fn, opts)`，统一处理 disable / loading / 恢复 / 错误 toast

### D. 信息密度合理

- [ ] 数据卡片不太空（如 wealth 4 个数据卡 0/-/0/已启用 这种"全空状态"要有引导文案）
- [ ] 列表/表格不太挤（行高 ≥ 36px，padding 12-16px）
- [ ] 空状态不能只是一句"暂无数据" — 要有 icon + 引导 CTA

### E. 状态明确

- [ ] 加载：spinner + "加载中…" 文字（不许只是空白）
- [ ] 成功：toast / inline 反馈，不刷整个 page
- [ ] 失败：明确错误信息（不只是"失败"），最好带补救建议
- [ ] 禁用：按钮 disabled + 视觉灰化 + 鼠标 not-allowed

### F. 交互友好

- [ ] 主操作按钮永远在右上角或表单底部（不许"操作按钮散落各处"）
- [ ] 危险操作（删除）用 `pmModal.confirm` 二次确认，不许 confirm() 弹窗或直接执行
- [ ] focus-visible 蓝色 ring（鼠标用户隐藏，键盘 tab 显示）
- [ ] 表单输入支持回车提交（不强制必须 click 按钮）

### G. 可访问性

- [ ] tab 顺序合理（focus 顺序符合视觉流）
- [ ] 表单 input 有 label 或 aria-label
- [ ] 主要 region 有 ARIA role（nav / main / dialog / tablist 等）
- [ ] 文本对比度过 WCAG AA（4.5:1）
- [ ] 图标按钮有 title 或 aria-label

### H. 响应式底线

- [ ] 1280-1600px 视口看起来都好（这是用户实际用的主流分辨率）
- [ ] 960-1280 也不能塌（窄屏可适度堆叠）
- [ ] sidebar 在窄屏可以考虑折叠（可选，不强求）

---

## 5. 整体配色样式要求（验收标准）

### A. 配色（必须严格按此，所有 token 都在 `static/css/warm.css` 里定义）

#### 背景

| 角色 | hex | 用法 |
|------|-----|------|
| 页面主底 | `#FAF7F2` | `--pm-bg-page`，暖米白 |
| 卡片层 | `#FFFFFF` | `--pm-bg-card`，纯白 |
| hover/输入 | `#F2EEE6` | `--pm-bg-hover`，主底深一档 |
| active | `#EAE5DB` | `--pm-bg-active` |
| 次级面板 | `#F6F2EB` | `--pm-bg-subtle` |
| modal 遮罩 | `rgba(28, 25, 23, 0.4)` | `--pm-bg-overlay` |

#### 边框 / 文字（stone 暖灰系）

| 角色 | hex | 用法 |
|------|-----|------|
| 边框 | `#E7E2DA` | `--pm-border`，stone-200 |
| 强边框 | `#C7C0B5` | `--pm-border-strong` |
| 主文 | `#1C1917` | `--pm-text-primary`，stone-900（暖黑）|
| 次文 | `#57534E` | `--pm-text-secondary`，stone-600 |
| 弱文 / 占位 | `#A8A29E` | `--pm-text-muted`，stone-400 |
| 链接 | `#7C3AED` | `--pm-text-link`，同主紫 |

#### 主色（紫，温暖系）

| 角色 | hex | 用法 |
|------|-----|------|
| 主色 | `#7C3AED` | `--pm-primary`，violet-600 |
| hover | `#6D28D9` | `--pm-primary-hover` |
| active | `#5B21B6` | `--pm-primary-active` |
| 主色淡底 | `#F5F3FF` | `--pm-primary-subtle`，选中态/badge 底 |
| 主色边框 | `#DDD6FE` | `--pm-primary-border` |

#### 语义色

| 角色 | hex | 淡底 |
|------|-----|------|
| 成功 | `#16A34A` | `#F0FDF4` |
| 警告 | `#D97706` | `#FFFBEB` |
| 错误 | `#DC2626` | `#FEF2F2` |
| 信息 | `#0891B2` | `#ECFEFF` |

### B. 阴影（必须用暖色调，不能用冷色）

| 层级 | 值 |
|------|---|
| `--pm-shadow-sm` | `0 1px 2px 0 rgba(120, 80, 50, 0.05)` |
| `--pm-shadow-md` | `0 2px 4px 0 rgba(120, 80, 50, 0.06), 0 1px 2px 0 rgba(120, 80, 50, 0.04)` |
| `--pm-shadow-lg` | `0 4px 12px 0 rgba(120, 80, 50, 0.08), 0 2px 4px 0 rgba(120, 80, 50, 0.04)` |
| `--pm-shadow-xl` | `0 12px 32px 0 rgba(120, 80, 50, 0.12), 0 4px 8px 0 rgba(120, 80, 50, 0.06)` |

### C. 圆角（柔和但不可爱）

| 用途 | 值 | token |
|------|---|-------|
| 极小（badge / chip） | 4px | `--pm-radius-xs` |
| 输入框 / 小按钮 | 6px | `--pm-radius-sm` |
| 按钮 / 一般容器 | 8px | `--pm-radius-md` |
| 卡片 | 12px | `--pm-radius-lg` |
| modal | 16px | `--pm-radius-xl` |
| 圆形 / pill | 9999px | `--pm-radius-full` |

### D. 间距（4-grid，必须严格按 token，不许 inline 写 padding/margin 杂数字）

```
4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64
对应：--pm-space-1 ~ --pm-space-16
```

### E. 字体

```css
--pm-font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI",
                "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
--pm-font-mono: "JetBrains Mono", "SF Mono", "Cascadia Code",
                Menlo, Consolas, monospace;
```

字号层级：

| 用途 | size | weight |
|------|------|--------|
| 弱标签 / 副数据 | 12px | 400 |
| 副文 / 提示 | 13px | 400 |
| 正文（默认） | 14px | 400 |
| 偏大正文 / 副标题 | 15px | 500 |
| 卡片标题 / 按钮 | 16px | 600 |
| 区块标题 | 18px | 600 |
| Page 大标题 | 24px | 600 |
| 数据卡数字 | 28px | 700 |
| 极大数据展示 | 36px | 700 |

行高：`--pm-line-tight: 1.25` / `--pm-line-normal: 1.5` / `--pm-line-relaxed: 1.75`

### F. 浅色变体使用规则（保持统一感优先）

**整体原则**：所有浅色变体都应该围绕 **暖米白主底 + violet 主色 + stone 暖灰** 三个核心展开，**整体观感统一**。差异是用来"分层级"，不是用来"分类型"。

#### ✅ 允许 — 用浅色变体做层级 / 微差异

- 同色相不同明度的层级（如 stone 系 100/200/300 用作 边框 / hover / active）
- 主色 violet 的不同明度 / 饱和度子色阶（如 violet-50 用作选中淡底、violet-100 用作 badge 边框）
- 卡片层 `#FFFFFF` vs 主底 `#FAF7F2` 这种极小明度差，做"卡片浮起"的层次
- subtle 系列（`--pm-bg-subtle` `#F6F2EB`、`--pm-bg-hover` `#F2EEE6`）做次级面板 / hover 态
- 极淡的语义底色（`success-subtle` / `warning-subtle` / `danger-subtle` / `info-subtle`）做 badge / 状态卡 底色
- 同一组数据卡用同色（白底紫数字）整齐排列，靠数字大小 / 内容 / icon 区分

#### ⚠️ 谨慎使用 — 仅在「需要明显语义区分」时才用饱和色

只有这些场景才允许用饱和色：

- **状态语义**：成功（绿）/ 警告（橙）/ 错误（红）/ 信息（青）
- **优先级语义**：P0 红 / P1 橙 / P2 蓝 / P3 灰（自检 / check skill）
- **数据类型语义**：陈述 vs 推断（在带置信度标注的地方）
- 必须是「不同色 = 不同含义」，而不是「不同色 = 装饰好看」

#### ❌ 不允许

- 同一个 page 内出现 3 种以上不同色相的饱和色作主色（除上述明确语义场景）
- 用一组彩色（黄/橙/绿/红/蓝/紫）代表"不同 archon" 或"不同模块" — 既违反命名净化（暴露内部架构）也是视觉污染
- 用渐变 gradient 做主背景或主按钮（违反清冷简洁原则）
- 不同 page 用不同主色调（如 dashboard 用 violet / wealth 用 amber / game 用 cyan 这种）— 全 web 必须**同一套色板**
- 在统一温馨柔和风内插入冷色（如 cool blue / cyan）作主元素 — 信息色 `--pm-info` `#0891B2` 已经是冷感最强的允许色，不能再冷

### G. 不允许的元素（视觉污染清单）

- [ ] **不许出现 emoji 当图标**（菜单 / 按钮 / 标题 / 副标题 等关键位置都用 Lucide SVG，emoji 只能出现在用户消息内容 / 推送内容 / 标记性提示如 ✅⚠️🚨 这种"语义图标"且偶尔用）
- [ ] **不许出现纯黄色 / 纯橙色作主色**（除非 amber-600 用作 warning 语义）
- [ ] **不许出现 linear-gradient 主按钮**（按钮一律纯色）
- [ ] **不许出现深紫底**（旧 paimon-bg #1a1625 系列绝对禁止）
- [ ] **不许出现 box-shadow 用 rgba(0,0,0,...) 冷阴影**（必须 rgba(120,80,50,...) 暖系）
- [ ] **不许 inline 写硬编码 hex / px**（必须用 token / CSS variable，例外：data-driven 的 chart 高度 / 动态宽度 等）

---

## 6. 文字表述要求（验收标准）

### A. 严禁词汇（已在 Phase 2 列出，此处再贴一遍方便检索）

- 神之心 / 七神 / 四影 / 三月 / 天使
- 风神 / 水神 / 草神 / 岩神 / 火神 / 雷神 / 晨星
- archon / shade / morningstar / raiden / mavuika
- 「XX 管辖」「XX 代管」「XX 主管」

### B. 措辞风格

- [ ] **用做什么的事描述**，不写谁做的（参考 Phase 2 的对照表）
- [ ] **副标题 ≤ 25 字**，长了拆两行（页面副标题简洁优先）
- [ ] **按钮文案动词起头**：刷新 / 添加 / 删除 / 保存 / 取消 / 关闭 / 跑 Quick / 立即跑 / 查看 / 编辑 / 设默认 / 测连接
- [ ] **错误消息明确**：不只是"失败"或"加载失败"，要带原因或补救（"网络中断，请检查连接"、"参数无效：name 必填"）
- [ ] **空状态有引导**：不只是"暂无数据"，要有"暂无数据 + 怎么造数据"（如 tasks 空：「暂无定时任务，在对话中说 '每小时提醒我喝水' 或使用 /schedule 指令创建」）

### C. 列表 / 表格表头用名词

- [ ] th 用名词（"组件"、"用途"、"花费"、"次数"），不用动词或描述短句
- [ ] 数字列右对齐 + tabular-nums
- [ ] 时间列格式统一：`MM-DD HH:mm` 或 `YYYY-MM-DD HH:mm`（page 内一致）

### D. 数字带单位

- [ ] tokens：`1,234,567`（千分位）/ `1.2M` / `685.9K`（图表 Y 轴）
- [ ] cost：`$24.7225`（4 位小数）/ `$5.30`（2 位）
- [ ] 时间：人话（"3 秒前"、"5 分钟前"、"昨天"）+ 完整时间（hover tooltip 显示）
- [ ] 文件大小：`33 KB` / `1.2 MB`
- [ ] 百分比：`100.0%`

### E. 时间表达

- [ ] 相对时间用人话：刚刚 / N 秒前 / N 分钟前 / N 小时前 / N 天前 / N 月前
- [ ] 绝对时间统一格式：`MM-DD HH:mm`（同一年内）/ `YYYY-MM-DD HH:mm`（跨年）
- [ ] 日期范围用 `2026-05-12 ~ 2026-05-19` 或 `近 7 天` / `近 30 天`

### F. 链接 / 跳转

- [ ] 链接用紫色 `--pm-text-link`（不下划线，hover 才显下划线）
- [ ] 外部链接末尾加 `↗` 或 `external-link` 图标
- [ ] 内部跳转用「→」或带 chevron-right 图标

### G. 占位符 / 提示

- [ ] input placeholder 用「示例值」而不是「请输入 X」（如 `placeholder="股票代码（如 60051）"`，不是 `placeholder="请输入股票代码"`）
- [ ] textarea 给举例（如 `例：我主要用 Python / 不要给总结 / 项目 DB 是 PostgreSQL`）
- [ ] hint 用斜体 + 浅灰

### H. 路由/分组命名（特别强调，最容易出问题）

`/llm` 路由配置 tab 的 category 分组名要按"做什么的事"分，不按内部架构分。例：

- ❌ 派蒙 · 守门 / 路由 / 出口 / 全程安全闸
- ✅ 入口意图分类 / 工具调用路由 / 出口模型路由 / 安全闸

- ❌ 出口 · skill · 单步任务直调
- ✅ 工具调用 · skill 单步任务

- ❌ 七神 · archon 业务接口
- ✅ 业务面板后台

- ❌ 三月女神 · 调度 / 自检 / 响铃
- ✅ 任务调度 · 自检 · 响铃

- ❌ 草神-memory/知识库 LLM 调用域
- ✅ 记忆 · 知识库 · 实体提取

完成判据：路由 tab 截图给 **完全不知道 paimon 内部架构** 的人看，他能 100% 看懂"这个分组是干嘛的"。

---

## 7. 进度追踪

> 完成一项后立即在此勾选。**不许偷工**。

### Phase 1 — 拆 plugins ✅
- [x] templates/plugins.html 写完
- [x] static/css/plugins.css 写完
- [x] static/js/plugins.js 写完
- [x] handler 改完
- [x] 旧 plugins_html.py 删
- [x] 实机校验 200 + 0 error
- [x] commit `refactor: P2-9 拆 plugins 面板到温馨柔和风`（19965d6）

### Phase 2 — 命名问题全局审计 ✅（不独立 commit，输出清单驱动 Phase 4）
- [x] templates/*.html 扫完
- [x] static/js/*.js 扫完
- [x] model_router.py 路由分组扫完
- [x] api/*.py 扫完（含 title 参数 + log/actor/error/docstring）
- [x] _warm_sidebar.html 检查（已干净，无违例）
- [x] db `primogem.db / token_usage.purpose` 现存值审计 — 全是 `bili/意图分类/标题生成/闲聊`，**已干净，无需 UPDATE DB**
- [x] 输出问题清单 ↓

#### Phase 2 输出 — 按 page 归类的命名违例清单（Phase 4 各 page 修）

##### `/dashboard` （用量）
- `templates/dashboard.html:4` 副标题 `（神之心代管）` → 删

##### `/llm` （模型 + 路由）— 改动量最大
- `templates/llm.html:4` 副标题 `（神之心管辖）` → 删
- `static/js/llm.js:319-410` 整套路由分组 metadata（GROUP_LABELS / GROUP_TITLES / SECTIONS / SECTION_LABELS / SKILLS_NOTE）按"做什么的事"重命名：派蒙→入口意图分类；出口·skill→工具调用·skill；出口·agents→多视角讨论；出口·evolve→自进化提案；七神 archon→业务面板后台；三月女神→任务调度·自检·响铃；草神-memory→记忆·知识库；外加去掉 `（按七神保留铁律全列）` 这种内部叙事
- `paimon/foundation/model_router.py:1,27-78,107` docstring + ROUTE_DEFAULTS 里 component 名（"风神"/"草神"/"岩神"/"水神"/"火神"/"雷神"/"冰神"/"晨星"等）→ 全部改"做什么的事"，加载日志去掉"神之心·路由"
- 注意 ModelRouter 的 component 名是 DB key 也是 web 显示文本，改时要 DB UPDATE 旧记录或先清空 routes 表（实测当前是空表，可直接改源码）

##### `/tasks` （任务）
- `templates/tasks.html:4` 副标题 `用户定时任务 + archon 注册的系统周期任务（三月管辖）` → `用户定时任务 + 系统周期任务`
- `api/tasks.py:35` docstring `列三月所有调度任务...按神分组` → `列所有调度任务...按业务分组`

##### `/knowledge`
- `templates/knowledge.html:4` 副标题 `（草神管辖）` → 删
- `static/js/knowledge.js:179,228` 提示 `详情见「📨 推送」收件箱的「草神」条目` → `详情见「📨 推送」收件箱的「记忆整理」条目`
- `static/js/knowledge.js:431` 空状态 `让草神调 knowledge 工具写入...` → `调 knowledge 工具写入或在对话里说...`
- `api/knowledge.py:121,160,205,207` actor=草神面板/草神 → actor=知识面板（user-visible 字段，必须改）

##### `/selfcheck`
- `templates/selfcheck.html:4` 副标题 `（三月管辖）` → 删

##### `/wealth`
- `templates/wealth.html:4` 副标题 `（岩神管辖）` → 删
- `templates/wealth.html:30` `<h2>📨 岩神 · 理财日报 ...</h2>` → `<h2>理财日报 ...</h2>`
- `static/js/wealth.js` 多处 actor='岩神' 拉 push_archive 列表 → 必须保留作为查询 key（DB 现存数据用这值），但 UI 显示文字 `岩神·` 前缀 / `暂无岩神推送` 等 → 改"理财·"前缀和"暂无理财推送"
- `api/wealth_stock_subs.py:1,16,43,58,71,78,89,99` docstring + error 文字 `非岩神关注股订阅` 等 → 改"非关注股订阅"
- **DB 字段保留**：`push_archive.actor='岩神'`、`subscription.binding_kind='stock_watch'` 这些 DB 值不动（避免 schema 改动），改的是源代码里"写入新值的常量"和"显示给用户的文案"

##### `/game`
- `templates/game.html:4` 副标题 `（水神管辖）` → 删
- `static/js/game.js:1,170,872+` 多处 console.log `[水神·采集]` `[水神·抽卡]` → 改 `[游戏·采集]` `[游戏·抽卡]`（注释 + 日志，用户偶尔看 console 也不会迷惑）
- 跟 wealth 一样，不动 DB 数据 key，只改源代码常量和 UI 文案

##### `/feed`
- `templates/feed.html:4` 副标题 `（风神管辖）` → 删
- `static/js/feed.js:1` 文件注释 `风神订阅 + 今日热点 + 近期回顾...` → `订阅 + 今日热点 + 近期回顾...`

##### `/plugins`
- 已基本干净（副标题 OK）
- `static/js/plugins.js:159` 提示 `四影 propose 阶段产出后会落到这里等你审` → `自进化 propose 阶段产出后会落到这里等你审`

##### `/` (chat)
- `static/js/chat.js:294,320` 注释 `如四影 prepare 失败` `/stop 取消四影` → 改"如生执 prepare 失败" / "/stop 取消推理流"（**注释，用户看不到，但严格按 Phase 2 字面执行**）

##### 政策（2026-05-13 校准）：**只改 web 展示，code / log / comment 全部保留**

用户对此明确：
> 我只是不希望在 web 上展示，不是要让日志/代码/注释里也不展示

所以以下 **不改**（保留原命名以便对着架构找代码）：
- 后端 `.py` 文件的 docstring（如 `"""草神知识面板 - 记忆段..."""`）
- 后端 logger.info/warning 标签（如 `[神之心·路由]`、`[岩神·关注股订阅]`、`[水神·采集]`）
- 代码注释里的"四影/晨星/三月/七神"
- 代码常量 `actor="草神面板"`、`source="草神面板·手动"`、`purpose="晨星·拆议题"`、`purpose=f"天使·{cat_label}"` 等 → DB 写入键值不动
- `model_router.py` `KNOWN_CALLSITES` 元组里的 `("agents", "晨星·拆议题")` 等 — 这是路由 key 源头，必须跟代码 purpose 字符串一致

**只改 web 渲染层**：
- `templates/*.html` 副标题 / 标题等 user-visible 文本
- `static/js/*.js` 渲染到 innerHTML / textContent / toast / placeholder / alert 的字符串
- 必要时给 web 加 display 翻译（如 llm.js 加 `purposeDisplay()` 把 `晨星·拆议题` 显示为 `拆议题`，DB key 仍用原值）

**已 revert 回原命名的代码**（前几个 commit 里改了，这次 llm round 一并 revert）：
- `paimon/foundation/model_router.py` — docstring + KNOWN_CALLSITES purposes + 段注释 + logger label 全部 revert 到 `神之心·` / `晨星·*` / `天使·*` / `七神·archon` / `四影·...` 原始命名
- `paimon/morningstar/_scout.py / council.py / morningstar.py / prompts.py` — purpose 字符串 revert 到 `晨星·拆议题/调研/召集/调度/综合` + `f"天使·{cat_label}"`
- `paimon/channels/webui/api/knowledge.py / knowledge_kb.py / tasks.py` — docstring + actor + source 字面量 revert 到 `草神面板` / `三月调度任务`
- `paimon/channels/webui/static/js/chat.js` — 注释 `如四影 prepare` / `/stop 取消四影` revert 到原文


### Phase 3 — md 渲染问题全局审计 ✅（不独立 commit，输出清单驱动 Phase 4）
- [x] chat 渲染点排查
- [x] feed 渲染点排查
- [x] wealth 渲染点排查（已 OK）
- [x] game 渲染点排查（已 OK）
- [x] knowledge 渲染点排查
- [x] selfcheck / llm / plugins / dashboard / tasks 排查
- [x] 输出问题清单 ↓

#### Phase 3 输出 — 按 page 归类的 md 渲染问题清单（Phase 4 各 page 修）

##### `/` (chat) — **严重 bug，目前消息不渲染**
- `chat.js:249,284,307,355` 调用 `window.safeMd(...)`，但 **safeMd 整个 repo 没定义**
- chat handler `api/main.py:32-44` **没引入 marked.min.js**
- 结果：assistant 消息当前会触发 `TypeError: window.safeMd is not a function`
- 修：
  1. `api/main.py` 给 chat 的 extra_css 加 `<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>`
  2. 在 `static/js/components.js` 加全局 `window.safeMd = function(md){...}` 包装 marked.parse + 链接 target=_blank rel=noopener + try/catch fallback `<pre>`（chat 直接复用，game/wealth 的局部 _renderMdSafe 后续 Phase 4 也可改调 window.safeMd 复用）

##### `/feed`
- feed.js 三处 `marked.parse` 用得对（已带 fallback），但 feed handler `api/feed.py:24-32` **没引入 marked.min.js** → 当前实际跑的是 `<pre>` fallback，热点 / 周报 md 不渲染
- 修：feed handler 的 extra_css 加 `<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>`

##### `/knowledge` — **严重，知识库内容不渲染**
- `knowledge.js:88` `modalBody.textContent = it.body || '(空)'` — 记忆/知识库正文直 txt 渲染
- `api/knowledge.py:14-30` knowledge handler **没引入 marked.min.js**
- 修：
  1. handler 加 marked.min.js
  2. `knowledge.js:88` 改 `modalBody.innerHTML = window.safeMd(it.body || '')`

##### `/wealth` — **已 OK**
- 局部 `_renderMdSafe` + 已引入 marked.min.js（api/wealth.py:28）
- Phase 4 可考虑改成调 `window.safeMd` 复用，但功能已正常

##### `/game` — **已 OK**
- 局部 `_renderMdSafe` + 已引入 marked.min.js（api/game.py:28）

##### `/dashboard` / `/tasks` — 无需 md 渲染
- dashboard：纯统计数字 + 表格 + 柱状图，无 md 内容
- tasks：任务列表 + cron 表达式，无 md 正文

##### `/selfcheck` — modalBody 是 JS 拼装的 HTML，不是 md → 不需要 marked
- 但「Quick / Deep 历史报告正文」如果将来要支持 md 评语，可再加；当前无需

##### `/llm` — profile description 当前是单行文本，不需要 marked

##### `/plugins`
- skill `description` / proposal `rationale` / `review_notes` 都是 esc() 后 txt 直出
- 这些字段语义上偏单段说明，**当前不渲染 md 是 OK 的**（不像 chat 消息那样必然有 md）；但 `system_prompt` 是 code-block 形式（已 `<pre class="code">` 类似处理）
- Phase 4 的 plugins 轮可视情决定是否引入轻量 md（比如 review_notes 偶尔会含项目符号）


### Phase 4 — 10 page × 10 轮 PDCA
- [x] `/` (chat) 第 1-10 轮 ✅ — 修 safeMd undefined / 命名净化 / 紫主色一致 / a11y / pmModal 替换 confirm
- [x] `/dashboard` 第 1-10 轮 ✅ — 命名净化 + bar 加宽 + 控制条段控件化 + cost bar amber + tip 增强 + 表格列宽 + a11y
- [x] `/tasks` 第 1-10 轮 ✅ — 命名净化 + 删除 dead modal + 折叠区 keyboard a11y + line-clamp + tokens.css 加 *-border + clock icon + 自动刷新 hint
- [x] `/knowledge` 第 1-10 轮 ✅ — 命名净化 + handler 加 marked + modalBody 改 safeMd + actor=知识面板 + pill role=tab + 删除走 pmModal/pmToast + tab focus-visible
- [x] `/llm` 第 1-10 轮 ✅ — 副标题去"神之心管辖"+ tab 去 emoji + COMPONENT_DESC / CATEGORY_DESC / DISABLED_COMPONENTS / SKILLS_NOTE 全清内部命名 + 加 purposeDisplay() 翻译 + 之前 commit 里误改的 code/log/comment 全部 revert
- [x] `/selfcheck` 第 1-10 轮 ✅ — 副标题去"三月管辖" + alert/confirm 全改 pmModal/pmToast + #FEE2E2 改 token + tab role=tab/aria-selected/键盘可达 + ESC 关 modal + btn focus-visible
- [x] `/wealth` 第 1-10 轮 ✅ — 副标题去"岩神管辖"+ 大标题去"📨 岩神 · 理财日报"+ 进度条/空状态文 "岩神" → "理财" + alert/confirm 全改 pmModal/pmToast + linear-gradient 主按钮改纯紫 + rgba(0,0,0,.6) 改 token / 暖系 + btn focus-visible
- [x] `/game` 第 1-10 轮 ✅ — 副标题去"水神管辖" + alert/confirm 全改 pmModal/pmToast + btn primary 去 linear-gradient + 所有 rgba(0,0,0,*) 背景改 token / ac-resin-fill 三档语义色 / r5/r4 char-row 去渐变 + btn focus-visible
- [x] `/feed` 第 1-10 轮 ✅ — 副标题去"风神管辖" + handler 加 marked.min.js（修复 hotspot/weekly md 不渲染）+ alert/confirm 全改 pmModal/pmToast + 4 个 tab 去 emoji + role=tab/aria-selected + btn-primary 去 linear-gradient + qr-modal 遮罩用 token
- [ ] `/plugins` 第 1-10 轮

### Phase 5 — rebase
- [ ] `git branch backup-pre-rebase`
- [ ] `git rebase -i ca1c6d5`
- [ ] 每个 page 的 commit 都 fixup 到原 commit
- [ ] 全部 conflict 解决 + 0 error
- [ ] git log --oneline 检查最终 commit 链整洁
- [ ] **不 push**，等用户验收

### Phase 6 — 全功能回归测试 3 轮
- [ ] 第 1 轮 UI 加载 + 路径覆盖（10 个 page 全过）
- [ ] 第 2 轮 实际功能交互（含 xiaomi/mimo 路由切换）
- [ ] 第 3 轮 极端场景 + 错误处理
- [ ] 每发现的问题记录 + 修复 + fixup 到对应 page commit
- [ ] paimon 启动 0 报错 + 3 轮 0 console error
- [ ] git log --oneline 最终仍是约 10 个干净 commit
- [ ] 不 push，等用户最终验收

---

## 8. 问题登记表（Phase 6 测试中发现的问题随时追加，修完打勾）

> 格式：`[ ] [page] [严重度] 问题描述 → 修复方案 → 归属 commit`

（暂无）
