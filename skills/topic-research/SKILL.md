---
name: topic-research
description: 中文多源舆情聚合调研。给定话题，跨 B 站 / 小红书等中文平台并发拉近 30 天热门内容，按 engagement + recency + relevance 计分排序，输出综合简报。
triggers: 调研, 全网调研, 近 30 天, 30天内, 多源聚合, 舆情调研
license: MIT
allowed-tools: Bash
---

# topic-research：中文多源舆情聚合

按"事件 / 话题"做近 30 天的横向调研。每个平台独立 collector 拿 engagement 数据，跨源去重 + 计分 + 排序，输出 markdown 简报。

主入口在本 skill 目录的 `scripts/research.py`，子进程方式调用。

## 使用方式

### 默认（B 站 + 小红书）

```bash
python3 skills/topic-research/scripts/research.py "Claude 4.7" --emit md
```

### 指定 sources

```bash
python3 skills/topic-research/scripts/research.py "小米 SU7 Ultra" --sources bili --emit md
```

### 调时间窗

```bash
python3 skills/topic-research/scripts/research.py "OpenAI" --days 14 --emit json
```

### 落盘位置

默认产物落到 `~/.paimon/skills/topic-research/cache/<slug>/`，包含：
- `report.md` —— 人类可读简报
- `report.json` —— 结构化数据（其他 skill 可复用）

### CLI 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `topic` | （必需） | 调研主题 |
| `--sources` | `bili,xhs` | 逗号分隔的源列表（当前支持 `bili` / `xhs`）|
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
- **小红书**：⏸ **未实装且无简单路径**（笔记数据走 SPA + edith 加密 API + x-s 签名 + cookies；paimon 现有 xhs skill 只解析单笔记没有搜索）；记 TODO，等 paimon 整体引入 playwright 等浏览器自动化能力时再做
- 计分：`recency × 0.3 + engagement × 0.5 + relevance × 0.2`（engagement 同源内 log 缩放归一化）

## 目录结构

```
skills/topic-research/
├── SKILL.md                # 本文件
└── scripts/
    ├── research.py         # CLI 入口
    └── lib/
        ├── core/           # 公共组件（schema / http / log / dates / score / render / discover）
        └── sources/        # 各 source collector
            ├── bili.py     # 简单 source = 单文件
            ├── xhs.py      # ⏸ TODO stub
            └── ...         # 复杂 source（要 cookies + 多步 enrich）将拆成子目录
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

| Source | 状态 | 难度 | 路径 |
|---|---|---|---|
| **GitHub** | TODO | ★ 易 | issues / discussions / 仓库活跃度，公开 API 免登录；可参考 last30days `github.py` |
| **知乎** | TODO | ★ 易 | `/search_v3?keyword=` 或 `zhihu.com/api/v4/search_v3`；公开搜索 API，匿名可拿标题 / 摘要 / 部分赞数 |
| **贴吧** | TODO | ★ 易 | `tieba.baidu.com/f/search/res` 搜索接口宽松；老 IA 反爬弱 |
| **虎扑** | TODO | ★★ 中 | `bbs.hupu.com/search` 网页搜索 + 二次抓帖子 meta（楼层 / 浏览 / 回复）|
| **TapTap** | TODO | ★★ 中 | `taptap.cn/search` 或 webapi，主要拿"评论"engagement（适合游戏话题，与 bili 互补）|
| **微博** | TODO | ★★★ 难 | `s.weibo.com/weibo?q=` 需 cookies + 防风控；反爬严但可做 |
| **小红书** | ⏸ 暂搁置 | ★★★★ 极难 | 笔记走 SPA + edith 加密 API + x-s 签名 + cookies；paimon 现有 xhs skill 只解析单笔记没搜索；等 paimon 整体引入 playwright 等浏览器自动化能力时再做 |

### 流水线增强

- **B 站二次 enrich**：search API 不返回 like / coin / comment；可补 view stat API 二次拉（按需）
- **跨源去重 dedupe**：同事件在多个平台被讨论时合并
- **同事件聚类 cluster**：把相关讨论聚类成"事件"
- **LLM rerank**：把 ranked top-30 喂给 paimon `model_router`（deepseek-pro）重排相关度
- **实体抽取 entity_extract**：从结果里抽人物 / 公司 / 事件
- **HTML 简报**：可分享、含图片
- **缓存层**：24h TTL，同 topic 不重复跑

### 接入风神

- 风神 `BusinessArchon.call_skill('topic-research', topic=...)` 调用代理（与世界式 v0.3 设计对齐）
- 风神订阅类型扩展：新增 `binding_kind='deep_research'`，每周自动跑（与现有 manual 日报订阅并存）
- WebUI 调研面板：仿 wealth/feed 面板做调研历史 + 一键重跑
