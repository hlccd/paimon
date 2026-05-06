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

## 使用方式

### 默认（B 站 + 知乎 + 小红书）

```bash
python3 skills/topic/scripts/research.py "Claude 4.7" --emit md
```

> 知乎 / 小红书需要 cookies；首次使用前去 webui `/feed` 面板的「站点登录」tab 扫码登录
> （cookies 落到 `~/.paimon/cookies/<site>.json`，3-12 个月失效后回面板重扫）
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
| `--sources` | `bili,zhihu,xhs` | 逗号分隔的源列表（支持 `bili` / `zhihu` / `xhs`；xhs 启 chromium 多 3-5s）|
| `--days` | `30` | 时间窗（天）|
| `--emit` | `md` | 标准输出格式：`md` / `json` / `both` |
| `--output-dir` | `<默认缓存>` | 产物落盘目录 |
| `--discover-limit` | `20` | 每源 web-search 候选数 |
| `--enrich-limit` | `15` | 每源真正 enrich 的上限 |

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
- 计分：`recency × 0.3 + engagement × 0.5 + relevance × 0.2`（engagement 同源内 log 缩放归一化）

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
            ├── xhs.py      # ✅ playwright headless 解析 DOM
            └── ...         # 后续 tieba / hupu / weibo / taptap / github
```

每个 source collector 必须暴露统一签名：
```python
def collect(topic: str, range_from: str, range_to: str, *, limit: int) -> list[Item]
```

## 何时用

- 用户要"调研近期某话题" / "搜集多平台讨论" / "看一下 30 天内 X 的情况"
- 风神订阅采集：将来可作为 `binding_kind='deep_research'` 的执行体（每周 1 次而非每日）

## 何时不用

- 单一 URL 解析 → 用 `bili` / `xhs` skill
- 普通搜索拿一堆 URL → 用 `web-search` skill
- 跨语种海外平台调研 → 现阶段不支持（last30days-skill 原版有这能力，但腾讯云上墙问题暂未解决）

## TODO

### Sources 待加（按计划顺序）

实测下来除 B 站 / GitHub 外，主流中文 UGC 平台**全部需要登录态**（匿名直接 403 / 302 跳登录）。所以统一走 playwright cookies 路径——首次本地扫码登录，cookies 落 `~/.paimon/cookies/{site}.json`，云端 rsync。

| Source | 状态 | 难度 | 路径 |
|---|---|---|---|
| **B 站** | ✅ 已接入 | ★ 易 | 官方 search API，免登录 |
| **知乎** | ✅ 已接入 | ★★ 中 | search v3 API + cookies；首次去 webui /feed「站点登录」tab 扫码 |
| **小红书** | ✅ 已接入 | ★★★ 中难 | playwright headless + cookies + DOM 解析；MVP 不抓发布日期 |
| **贴吧** | TODO | ★★ 中 | 百度统一登录，`BDUSS` cookie；登录后调 `tieba.baidu.com/f/search/res` |
| **虎扑** | TODO | ★★ 中 | `bbs.hupu.com/search` 网页搜索；登录后反爬宽松 |
| **微博** | TODO | ★★★ 难 | `s.weibo.com/weibo?q=` 需 cookies；防风控较严 |
| **TapTap** | TODO | ★★ 中 | webapi 搜索；游戏话题用 |
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
