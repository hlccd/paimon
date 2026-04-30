---
name: mihoyo
description: 米游社 I/O 客户端 — 由水神后台调用，扫码登录 / 签到 / 便笺 / 深渊 / 剧诗 / 抽卡，不含业务规则
license: MIT
metadata:
  author: paimon
  version: "0.1.0"
  data-source: 米游社
  layer: io-only
  upstream: gsuid_core (salt / API URL 需定期跟上游同步)
allowed-tools: Bash
---

# mihoyo · 米游社 I/O

## 职责边界

本 skill **只做米游社 API I/O**，**不含业务规则**：

- ✅ 签名 DS token / 设备指纹 / Cookie 续命
- ✅ 扫码登录全流程（QR → GameToken → Stoken → Cookie）
- ✅ 签到 / 便笺 / 深渊 / 剧诗 / 抽卡的 HTTP 调用
- ❌ UID 绑定策略 / 多账号管理（归水神 + 世界树）
- ❌ 树脂阈值判断 / 推送时机（归水神 + 三月）
- ❌ 抽卡统计分析（归水神）

## 使用方式

**用户不直接跑**—— 由水神 subprocess 调用。开发调试时可直接：

```bash
cd skills/mihoyo
python3 main.py gen-fp                           # 生成设备指纹
python3 main.py qr-create                        # 创建扫码 URL
echo '{"app_id":"2","ticket":"xxx","device":"xxx"}' | python3 main.py qr-poll
echo '{"uid":"100xxxxxx","cookie":"...","fp":"...","device_id":"..."}' | python3 main.py daily-note
```

### 输出契约

- stdout：紧凑 JSON（UTF-8, `ensure_ascii=False`）
- stderr：日志 + 错误
- 退出码：`0` 成功 / `2` 参数错 / `3` 米游社错误

### 子命令

| 命令 | stdin | 说明 |
|---|---|---|
| `gen-fp` | — | 生成 `{device_id, fp, device_info, seed_id, seed_time}` |
| `qr-create` | — | 创建登录 QR，返 `{ticket, device, url}` |
| `qr-poll` | `{app_id, ticket, device}` | 轮询，返 `{stat, uid?, game_token?}` |
| `stoken-exchange` | `{account_id, game_token}` | GameToken → Stoken |
| `cookie-exchange` | `{game_token, account_id}` | GameToken → Cookie |
| `refresh-cookie` | `{stoken, mys_id}` | Stoken → 新 Cookie（续命） |
| `sign` | `{game, uid, cookie, fp, device_id}` | 签到（game ∈ gs/sr/zzz） |
| `sign-info` | `{game, uid, cookie, fp, device_id}` | 查询签到状态 |
| `daily-note` | `{uid, cookie, fp, device_id}` | 原神便笺（树脂/派遣/委托） |
| `spiral-abyss` | `{uid, cookie, fp, device_id, schedule?}` | 深渊（1 本期 / 2 上期） |
| `poetry-abyss` | `{uid, cookie, fp, device_id}` | 幻想真境剧诗 |
| `gacha-log` | `{authkey, gacha_type, is_os?, since_id?, max_pages?}` | 全量抓抽卡（翻页到 since_id） |
| `parse-authkey` | `{url}` | 从祈愿历史 URL 提 authkey |

## 注意

- `mys_version` 和 `_SALTS` 常量需要跟 `/home/mi/code/gsuid_core/gsuid_core/utils/api/mys/tools.py` 上游同步；米游社改版会失效
- 签到被风控时（`risk_code 375/5001`）返回 `is_risk=true`，水神需识别后上报或重试 —— 本 skill 不内置打码
- 抽卡 authkey 有效期约 24 小时，用户要自己从游戏"祈愿历史"页面复制 URL
- 国际服 UID（首位 ≥6）会走对应 OS 域名，无需 proxy（若需可由水神在调用前加）
