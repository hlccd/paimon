---
name: topic
description: 中文多源舆情聚合调研。给定话题，跨 B 站 / 小红书等中文平台并发拉近 30 天热门内容，按 engagement + recency + relevance 计分排序，输出综合简报。
triggers: 调研, 全网调研, 近 30 天, 30天内, 多源聚合, 舆情调研
license: MIT
allowed-tools: Bash
---

# topic：中文多源舆情聚合

按"事件 / 话题"做近 30 天的横向调研。每个平台独立 collector 拿 engagement 数据，跨源去重 + 计分 + 排序，输出 markdown 简报。

主入口在本 skill 目录的 `scripts/research.py`，子进程方式调用。

## ⛔ 唯一执行路径（违规即重写整个 reply）

**收到 `/topic <query>` 后，第一个动作必须是**：调 `exec` 跑 `python3 skills/topic/scripts/research.py "<query>" --emit md`（Linux/服务器；Windows 本地若 `python3` 不存在再用 `python`）。

**不存在以下决策路径**——下面任何一种推理出现都违规，必须重写：

- ❌ 「这不属于 topic 范畴」「这是 X 咨询不是舆情调研」「应该常规对话回答」
- ❌ 「这是单一话题 / 单 URL / 角色攻略 / 宠物咨询，不需要多源调研」
- ❌ 「我不认识 query 里的实体，先 web_fetch 查证 / 直接告诉用户没听过」
- ❌ 「user 应该用 web-search / bili / xhs / chat 而不是 /topic」

**只要 user 输入 `/topic <query>`**，无论 query 是：
- 不认识的新角色名（"绯英"、"尼可"、"浔"）→ **跑脚本**（脚本会真采集，数据说话）
- 看起来完全不像调研（"我家狗拉肚子怎么办"、"今天天气真好"）→ **跑脚本**（user 用 /topic 就是要 topic 输出，脚本采集结果决定）
- 看起来该用别的 skill 的（单 URL / 普通搜索类问题）→ **跑脚本**（user 主动选了 topic，不要替 user 改路径）
- 海外语种 / 非中文话题 → **跑脚本**（采集为空就走「数据缺失说明」段照实说）

**严禁的逃逸动作**：跳过 exec 直接基于训练知识答 / 用 `web_fetch` 自己搜 / 调 `use_skill` 切其他 skill。

跑完 `exec` 拿到 stdout 之后，才有资格按下面「输出契约」格式写 reply。

## ⚠️ 输出契约（必须严格遵守，违规即重写）

### 独立调研原则（跨轮隔离）

**每次 `/topic` 调用是独立的**——只看本次 user 消息里的 topic 词，**完全忽略 chat history 里之前的调研**：

- ❌ 不允许跨轮对比（连续两次 `/topic <X>` `/topic <Y>` 时，第二次不要做 `X vs Y` 对比）
- ❌ 不允许引用上一次调研的结论 / 数据
- ❌ 不允许"延续上次话题"
- ✅ 每次都从零开始：跑 `research.py "<topic>"` → 按下面格式输出本次结果

### 标准输出结构（结构固定，内容动态）

```markdown
调研完成。

## 情绪分析
- 正面：<1-2 句基于实际笔记内容>
- 负面：<1-2 句>
- 中性 / 信息向：<1-2 句>
（如某维度本次完全没有，就**省略那条 bullet**；不脑补）

## 各源讨论重点
- **<源中文名>**：<1-2 句基于本源 top 5 实际内容的事实归纳>
- **<源中文名>**：<同上>

### 数据缺失说明
- **<源中文名>**：⚠️ 缺 cookies / 本次未拉到内容 / ⚠️ 采集失败：<错误>

## 综合 Top {N}
1. **[<标题原文>](<url>)** _(<源中文名>)_ — <≤50 字摘要>
2. **[<标题原文>](<url>)** _(<源中文名>)_ — <≤50 字摘要>
...（{N} 是 stdout `## 综合 Top N` 段的实际条数，最多 10）
（摘要从 stdout「各源原始素材」段提取；缺失时降级为 `**[标题](url)** _(源)_`，不强加 "—"）
```

> **归档说明**（reply 模板**外**，仅作背景信息）：脚本会把完整数据（含 engagement 数字 + JSON）落盘到 `.paimon/skills/topic/cache/<slug>/` 供 user 后续查看。**reply 内容不要提及落盘路径，更不要 `file_ops read` 这些文件**——stdout 已含 reply 需要的所有素材。

### ⚠️ 执行流程（必读，违规重写）

**调脚本 → 用 stdout 写 reply，两步结束**：

1. 调 `exec` 跑 `python3 skills/topic/scripts/research.py "<topic>" --emit md`（Linux/Mac/服务器；Windows 本地若 `python3` 不在再换 `python`）
2. stdout 已包含 `## 综合 Top N` / `## 各源讨论重点` / `## 各源采集情况` / 「各源原始素材」全部段落——**这就是 reply 的唯一素材来源**，按上面「标准输出结构」格式重组发出

**严禁**：

- ❌ `file_ops read .paimon/skills/topic/cache/<slug>/report.md` 或 `.json`——那只是落盘存档，stdout 已经够了，再读纯属浪费 token
- ❌ `file_ops list` 找 cache 目录或 slug 名——stdout 末尾「已落盘」提示行就含 slug
- ❌ 跑完脚本再调 `web_fetch` 补充信息——stdout 数据是唯一源，缺数据的源走「数据缺失说明」段，不要再去搜

### 各源讨论重点 — 分两段（有数据 / 缺数据）

stdout 「各源采集情况」段会列**全部 5 个源**。reply 的「各源讨论重点」分上下两段：

**上半段（主体）**：只列**实际采集到 ≥1 条数据的源**，每个源 1-2 句基于本源 top 5 实际内容的事实归纳。正负分化（≥2 正 + ≥2 负）的源用「主流认为 X，反方认为 Y」保留双方。

**下半段「### 数据缺失说明」**：列出**所有没数据的源**及原因，按 stdout 状态原样写：

- `⚠️ 缺 cookies`：原样写 `⚠️ 缺 cookies，去 webui /feed「站点登录」tab 扫码`
- `本次未拉到内容`：原样写 `本次未拉到内容`（**不要**自己揣测原因）
- `⚠️ 采集失败：xxx`：原样写 `⚠️ 采集失败：<错误信息>`

**5 个源必须全部出现**（上半段或下半段，不重复），不要省略。**不要替用户揣测原因**（比如把"未拉到"写成"cookies 失效"或"近期无讨论"）——用户自己能判断。如果 5 源全都没数据，上半段空着不写，只有下半段「数据缺失说明」。

### 违规模式（看到这些立即重写，不要发送）

- 顶部加 emoji / 角色扮演开场白：`🔥 调研结果来啦~` / `旅行者，派蒙这就帮你跑`
- 自创章节名：`## 核心发现` / `## 热点话题` / `## 整体风向` / `## 关键事件` / `## 舆情速览` / `## 关键人物`
- Top 数量错：列 12 / 15 / 20 都不对，**最多 10 条**（stdout `## 综合 Top N` N 是实际条数；ranked 不足 10 时按实际条数照搬，**不要**强凑 10 条）
- 章节名变体错：标准是 `## 综合 Top {数字}`，不要写成 `## 热度 Top X` / `## 综合榜` / `## TOP10` 等
- 输出分源明细块：`## B 站（N 条）` / `## 知乎（N 条）` / `## 小红书（N 条）` —— 这些只在落盘文件里
- 在 reply 里保留 engagement 数字：`播放 1.2M · 赞 50K · 评 3K · score 0.85` —— 全部去掉，只留 标题 + 链接 + 源标记 + 摘要
- 摘要超 50 字 / 摘要里塞观点：`这条很火` / `值得一看` 等评价 —— 必须是事实摘要，限 50 字内
- 主观评价词：`封神` / `评价极高` / `热度可观` / `值得关注` / `值得期待` / `凶猛` / `亮眼` / `炸裂`
- 改写笔记标题（翻译 / 缩短 / 拼接）—— 必须原文
- 跨轮对比：`A vs B 对比` / `延续上次话题`

### 输出前 Self-Check（必过，**md 格式必须正确**）

发送 reply 前，逐条核对：

1. [ ] 顶部第一行是 "调研完成。"，没有 emoji / 角色扮演开场？
2. [ ] **没有** `## B 站(N 条)` / `## 知乎(N 条)` / `## 小红书(N 条)` 段？
3. [ ] **没有** `## 核心发现` / `## 热点话题` / `## 整体风向` / `## 关键事件` / `## 舆情速览` 等自创章节？
4. [ ] Top **≤ 10 条**（ranked 满 10 就是 10；不足时按 stdout `## 综合 Top N` 的 N 照搬，不强凑）？
5. [ ] Top 的笔记标题原文输出，**没改写、没翻译、没缩短**？
6. [ ] **每条 Top 格式严格符合** `1. **[标题](url)** _(源)_ — 摘要`：
   - markdown 链接 `[标题](url)` 中括号 / 圆括号配对，url 不带空格
   - 加粗 `**` / 斜体 `_..._` 配对（不要漏一边）
   - 摘要前的 ` — ` 是「空格 + em-dash + 空格」（U+2014），不是 `--` 或 `-`
   - 摘要 ≤ 50 字（中文字符计数；超出截断加 `...`）
7. [ ] 摘要缺失（body 空）的条目降级为 `**[标题](url)** _(源)_` 单行，**没**强加 "— "
8. [ ] **没有** engagement 数字（播放 / 赞 / 评 / 收藏 / score / 日期）混进 reply
9. [ ] 「各源讨论重点」上半段只列**有数据的源**；下半段「### 数据缺失说明」列**所有缺数据的源**及原因（原样照搬 stdout 状态，不揣测）；5 源**全部出现**，不重复？
10. [ ] 「情绪分析」是事实归纳，**没有** `封神 / 评价极高 / 热度可观 / 值得关注 / 值得期待 / 凶猛` 这类评价词？
11. [ ] 全文无 emoji（🔥 / 😊 / 💬 / 📊 / 🎯 / ✨ / ⭐）？
12. [ ] 章节顺序严格 `情绪分析` → `各源讨论重点` → `综合 Top {N}`（不调换、不删减）
13. [ ] 总长度 < 1500 token / 6000 字符（QQ 单条限制）？

任何一条 ❌ → 立刻重写，不要发出去。

### Token 预算

- 单次 reply 硬上限：**1500 token**（约 6000 中文字符）
- 估算：Top 10（≈ 1500 字符）+ 各源讨论重点（≈ 350 字）+ 情绪分析（≈ 200 字）≈ 2000 字符 ≈ 1100 token，安全
- 一旦超 2000 token → **必然违规**（多半是塞了分源明细 / Top 超 10 / 摘要超 50 / 自创总结段）→ 重写

## 使用方式

> 注：`exec` 工具已把 cwd 设为项目根（paimon/），直接用相对路径，**不要 `cd`，不要拼绝对路径**。
>
> **Python 命令：默认 `python3`**（Linux/Mac/部署服务器都是这个）。仅当 `python3` 报 "command not found" 时再换 `python`（Windows 本地常见情况）。**首次直接用 `python3`，不要无脑 fallback**。

### 默认（B 站 + 知乎 + 小红书 + 贴吧 + 微博，5 源全跑）

```bash
python3 skills/topic/scripts/research.py "Claude 4.7" --emit md
```

> 知乎 / 小红书需要 cookies；首次使用前去 webui `/feed` 面板的「站点登录」tab 扫码登录
> （cookies 落到 `<paimon_home>/cookies/<site>.json`，默认 `.paimon/cookies/`，3-12 个月失效后回面板重扫）
> xhs 走 playwright headless，每次 collect 多 3-5s 启动开销

### 指定 sources

```bash
python3 skills/topic/scripts/research.py "小米 SU7 Ultra" --sources bili --emit md
```

### 调时间窗

```bash
python3 skills/topic/scripts/research.py "OpenAI" --days 14 --emit json
```

### 落盘位置

默认产物落到 `~/.paimon/skills/topic/cache/<slug>/`，包含：
- `report.md` —— 人类可读简报
- `report.json` —— 结构化数据（其他 skill 可复用）

### CLI 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `topic` | （必需） | 调研主题 |
| `--sources` | `bili,zhihu,xhs,tieba,weibo` | 逗号分隔的源列表（支持 `bili` / `zhihu` / `xhs` / `tieba` / `weibo`；xhs/tieba/weibo 各启一次 chromium ~3-5s）|
| `--days` | `30` | 时间窗（天）|
| `--emit` | `md` | 标准输出格式：`md` / `json` / `both` |
| `--output-dir` | `<默认缓存>` | 产物落盘目录 |
| `--discover-limit` | `20` | 每源 web-search 候选数 |
| `--enrich-limit` | `15` | 每源真正 enrich 的上限 |
| `--top-n` | `10` | brief 版 stdout 输出的 Top N 条数 |

## 架构

每个 collector 自管 discover + enrich，按统一 schema 输出 Item，再跨源聚合 → 计分 → 渲染：

```
topic → bili.collect()   ─┐
      → github.collect()  ├→ items_by_source → score → rank → render → report.md / .json
      → zhihu.collect()  ─┤
      → ... 其他源       ─┘
```

各源现状：
- **B 站**：官方 search API（免签名免登录），返回 bvid / title / view / danmaku / favorites / pubdate
- **知乎**：search v3 API（`/api/v4/search_v3`），需要 cookies（playwright 登录后 storage_state）；处理 question / answer / article 三种 hit 类型，拿点赞 / 评论 / 收藏 / 感谢
- **小红书**：playwright sync_api 启 headless chromium → 加载 cookies → goto 搜索页 → page.evaluate 解析 DOM 拿 title/url/作者/点赞；每次 collect 冷启动 chromium ~3-5s（单用户低频可接受）；published_at 用 range_to 占位（搜索列表卡片无日期）
- 计分：平台特性化（`scripts/lib/core/score.py`）—— 各源专属 engagement 公式 + 同源 P90 归一化，最终 `0.25·recency + 0.5·engagement + 0.25·relevance`：
  - **B 站**：`0.4·log10(view) + 0.3·log10(favorite) + 0.3·log10(danmaku)`
  - **知乎**：`0.5·log10(voteup) + 0.3·log10(thanks) + 0.1·log10(comment) + 0.1·log10(favorite)`
  - **小红书**：`log10(like)`（搜索列表 only-like，favorite/comment 缺失走兜底）
  - **贴吧**：`log10(reply)` 主信号，view 有则加权 0.7/0.3
  - **微博**：`0.4·log10(repost) + 0.3·log10(comment) + 0.3·log10(like)`
- 排序：diversity rank（每源至少 1 无条件上榜；剩余名额按全局 score 降序填；源数 > top_n 时按各源 top 1 score 截前 top_n 个）

## 目录结构

```
skills/topic/
├── SKILL.md                # 本文件
└── scripts/
    ├── research.py         # CLI 入口
    └── lib/
        ├── core/           # 公共组件（schema / http / log / dates / score / render / discover）
        └── sources/        # 各 source collector
            ├── bili.py     # ✅ 走官方 search API，免登录
            ├── zhihu.py    # ✅ search v3 + cookies
            ├── xhs.py      # ✅ playwright headless + cookies + DOM
            ├── tieba.py    # ✅ playwright + 百度 BDUSS cookies + DOM
            ├── weibo.py    # ✅ playwright + cookies + s.weibo.com DOM
            └── ...         # 后续 GitHub（公开 search API，技术话题补充）
```

每个 source collector 必须暴露统一签名：
```python
def collect(topic: str, range_from: str, range_to: str, *, limit: int) -> list[Item]
```

## 何时用

- 用户要"调研近期某话题" / "搜集多平台讨论" / "看一下 30 天内 X 的情况"
- 风神订阅采集：将来可作为 `binding_kind='deep_research'` 的执行体（每周 1 次而非每日）

## 限制

- topic 只跑中文平台（B 站 / 知乎 / 小红书 / 贴吧 / 微博）。海外语种话题脚本会照跑但拉不到内容，落入「数据缺失说明」段。跨语种海外平台调研现阶段不支持（last30days-skill 原版有这能力，但腾讯云上墙问题暂未解决）。
- topic **不预判 query 范畴**：无论 query 看起来是单 URL / 单实体咨询 / 普通问题 / 不熟悉的角色名，都按 user 输入的字面 query 直接跑 `research.py`。脚本采集结果由数据说话，命中没结果时照实输出「数据缺失说明」段。**严禁 LLM 在调脚本前判定「这不属于 topic 范畴」从而绕过脚本去用 web_fetch / 训练知识。**

## TODO

### Sources 待加（按计划顺序）

实测下来除 B 站 / GitHub 外，主流中文 UGC 平台**全部需要登录态**（匿名直接 403 / 302 跳登录）。所以统一走 playwright cookies 路径——首次本地扫码登录，cookies 落 `~/.paimon/cookies/{site}.json`，云端 rsync。

| Source | 状态 | 难度 | 路径 |
|---|---|---|---|
| **B 站** | ✅ 已接入 | ★ 易 | 官方 search API，免登录 |
| **知乎** | ✅ 已接入 | ★★ 中 | search v3 API + cookies；首次去 webui /feed「站点登录」tab 扫码 |
| **小红书** | ✅ 已接入 | ★★★ 中难 | playwright headless + cookies + DOM 解析；MVP 不抓发布日期 |
| **贴吧** | ✅ 已接入 | ★★ 中 | playwright headless + 百度 BDUSS cookies + DOM 解析（匿名 403 跳百度安全验证）|
| **微博** | ✅ 已接入 | ★★★ 难 | playwright headless + cookies + 解析 s.weibo.com 搜索页 DOM；selector 待 user 实测调 |
| **GitHub** | TODO | ★ 易 | 公开 search API，免登录；技术话题补充 |

各站 cookies 失效后，回 webui /feed「站点登录」tab 扫码续期。

### 流水线增强

- **B 站二次 enrich**：search API 不返回 like / coin / comment；可补 view stat API 二次拉（按需）
- **跨源去重 dedupe**：同事件在多个平台被讨论时合并
- **同事件聚类 cluster**：把相关讨论聚类成"事件"
- **LLM rerank**：把 ranked top-30 喂给 paimon `model_router`（deepseek-pro）重排相关度
- **实体抽取 entity_extract**：从结果里抽人物 / 公司 / 事件
- **HTML 简报**：可分享、含图片
- **缓存层**：24h TTL，同 topic 不重复跑

### 接入风神

- 风神 `BusinessArchon.call_skill('topic', topic=...)` 调用代理（与世界式 v0.3 设计对齐）
- 风神订阅类型扩展：新增 `binding_kind='deep_research'`，每周自动跑（与现有 manual 日报订阅并存）
- WebUI 调研面板：仿 wealth/feed 面板做调研历史 + 一键重跑
