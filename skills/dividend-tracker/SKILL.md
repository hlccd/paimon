---
name: dividend-tracker
description: 红利股数据抓取（BaoStock I/O）— 由岩神后台调用，抓全 A 股行情/股息/财务，不含业务规则
user-invocable: false
license: MIT
metadata:
  author: paimon
  version: "2.0.0"
  data-source: BaoStock
  layer: io-only
allowed-tools: Bash
---

# dividend-tracker · 纯 I/O 数据源

## 职责边界（重要）

本 skill **只做数据抓取**，**不含任何业务规则**：

- ✅ 调 BaoStock 拉全市场股票 / 股息历史 / 财务指标
- ✅ 本地缓存（`data/cache/`）+ 重试 + 格式转换
- ❌ 不做市值 / 股息率门槛过滤
- ❌ 不做行业分类权重 / 评分算法
- ❌ 不做 watchlist / changes 检测

所有业务规则归属 **岩神**（`paimon/archons/zhongli/`），由岩神 subprocess 调本 skill 取原始数据，自己评分 + 写世界树 + 推送。

## 使用方式

**用户不直接跑**本 skill——由岩神后台按 cron 或用户触发调用。开发/调试时可直接跑：

```bash
cd skills/dividend-tracker
python3 main.py fetch-board
python3 main.py fetch-dividend --codes=600519,600900
python3 main.py fetch-financial --codes=600519,600900
python3 main.py cleanup-cache
```

### 输出契约

- stdout：紧凑 JSON（UTF-8，`ensure_ascii=False`），岩神 `json.loads` 解析
- stderr：日志 + 错误信息
- 退出码：`0` 成功 / `2` 参数错 / `3` BaoStock 连接/查询失败

### 子命令

| 命令 | 参数 | 输出 |
|---|---|---|
| `fetch-board` | `--cache-dir=<path>` | `{industry_map, market_data, count}` 全 A 股 |
| `fetch-dividend` | `--codes=a,b,c` `[--cached-only]` `[--cache-dir]` | `{dividends, count, total}` |
| `fetch-financial` | `--codes=a,b,c` `[--cached-only]` `[--cache-dir]` | `{financials, count, total}` |
| `cleanup-cache` | `[--cache-dir]` | `{ok: true}` |

`--cached-only` 只读本地缓存（rescore 用，秒级返回）。

## 依赖

```bash
pip install baostock pandas
```

## 数据源说明

- **BaoStock**（`public-api.baostock.com`）：免费无限额；登录需 1-2 秒
- **缓存**：股息/财务 30 天 TTL，行情 7 天（见 `tracker/provider.py` `CACHE_TTL`）
- 全市场扫描单进程约 **15-20 分钟**（5800+ 股 + 串行 I/O）

## 目录结构

```
skills/dividend-tracker/
├── SKILL.md          本文件
├── main.py           CLI 入口（纯 I/O 三子命令）
├── requirements.txt  baostock + pandas
├── tracker/
│   ├── provider.py            缓存 + 重试工具
│   ├── provider_baostock.py   BaoStock 登录 + 抓取（核心）
│   └── __init__.py            空（不对外 import）
├── data/cache/       JSON 缓存（gitignore）
└── README.md         历史说明（可选）
```

## 变更记录

- **v2.0.0（2026-04-24，paimon 架构重构）**：按"skill 纯 I/O / 岩神管业务 / 世界树存储"三层分离
  - 删除：`tracker/tracker.py` `tracker/store.py` `tracker/scorer.py` `tools/analyzer.py` `reset_data.py` `data/config.json`
  - 业务迁移：scorer / 扫描编排 / 变化检测 → 岩神；三张表 → 世界树 dividend 域
  - 新增：`main.py` CLI 三子命令
- v1.x（fairy 时代）：完整业务模块形态（户部 import tracker），已退役

## 风险提示

本 skill 输出的数据仅供算法分析参考，不构成投资建议。
