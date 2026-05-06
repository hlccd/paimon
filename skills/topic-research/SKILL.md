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

复用 `web-search` skill 做发现层，各 collector 做 enrichment：

```
topic → web-search（site:bilibili.com） → bili.collect()  ─┐
       └ web-search（site:xiaohongshu.com） → xhs.collect() ─┤→ score → rank → render
                                                              ↓
                                                         report.md / report.json
```

- B 站：直接走官方 search API（免签名免登录），返回 bvid/title/view/danmaku/favorites/pubdate
- 小红书：**MVP 阶段未实装**（反爬严格，搜索引擎索引覆盖近零，需 cookies + xhs 笔记 API；P2 阶段做）
- 计分：`recency × 0.3 + engagement × 0.5 + relevance × 0.2`（engagement 同源内 log 缩放归一化）

## 何时用

- 用户要"调研近期某话题" / "搜集多平台讨论" / "看一下 30 天内 X 的情况"
- 风神订阅采集：将来可作为 `binding_kind='deep_research'` 的执行体（每周 1 次而非每日）

## 何时不用

- 单一 URL 解析 → 用 `bili` / `xhs` skill
- 普通搜索拿一堆 URL → 用 `web-search` skill
- 跨语种海外平台调研 → 现阶段不支持（last30days-skill 原版有这能力，但腾讯云上墙问题暂未解决）

## 计划中（P2）

- **xhs 实装**（优先级高）：复用 paimon/skills/xhs 的 cookies + 直连 `/api/sns/web/v1/search/notes` 笔记搜索；拿真实点赞 / 收藏 / 评论 / 分享 + 发布日期
- 加 source：知乎 / 微博 / 贴吧 / GitHub（GitHub 直接复用 last30days 现有实现）
- B 站二次 enrich：search API 不返回 like/coin/comment，可加 view stat API 二次拉（按需）
- 跨源去重（dedupe）+ 同事件聚类（cluster）
- LLM rerank（接 paimon 现有 model_router）
- 实体抽取（找出讨论中的关键人 / 公司 / 事件）
- HTML 简报（可分享）
- 接入风神：风神 BusinessArchon.call_skill('topic-research', topic=...)；将来作为 binding_kind='deep_research' 订阅类型的执行体
