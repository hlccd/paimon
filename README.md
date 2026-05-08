# Paimon · 神圣规划

> 个人 AI 助手系统 — 代号 **AIMON**（*Algorithm of Intransient Matrix of Overseer Network*，永恒统辖矩阵）
> 入口为 **PAIMON**（*Primordial* + AIMON，原初永恒统辖矩阵 / 向导·派蒙）

派蒙是系统与用户之间唯一的出入口：轻鉴权、意图分类、按任务类型分流到 4 个出口（chat / skill / /task / /agents），最后人格化送达。后台由四影管线 + 七神业务模块 + 天使多视角讨论 + 一套基础设施（神之心 / 原石 / 地脉 / 世界树 / 三月）支撑。

---

## 架构总览

- [**向导·派蒙**](docs/paimon/paimon.md) — 统一入口（WebUI / Telegram / QQ），意图分类 + 4 出口路由 + 出口人格化
  - `chat` 闲聊（派蒙浅层 LLM 直答）
  - `skill` 单一任务（直调 [skills/](skills/) 目录下的 skill：topic / web-search / bili / xhs / check ...）
  - `/task` **复杂任务落地**（四影管线 — 写 skill / 写代码 / 改代码 / 修 bug 等工程产物）
  - `/agents` **分析 / 调研 / 决策辅助**（天使多视角讨论，输出纪要不落地）
- **【守门 + 路由 + 出口 + 全程安全闸】派蒙**
  - 安全闸（v7 起从死执上提，[paimon/core/safety/](paimon/core/safety/)）：`task_review` / `scan_plan` / `review_skill_declaration` / `detect_sensitive`
- **【落地引擎】四影**（生 / 审 / 派 / 收 — 复杂任务落地引擎）
  - [**生执·纳贝里士**](docs/shades/naberius.md)：**生** — DAG 编排 + 产出工程产物（spec/design/code/simple_code/exec/chat 6 个动作）
  - [**死执·若纳瓦**](docs/shades/jonova.md)：**审** — 评审循环（review_spec/design/code）+ 静态自检（py_compile/ruff/pytest）
  - [**空执·阿斯莫代**](docs/shades/asmoday.md)：**派** — 拓扑分层 dispatch + stage 路由表 + 失败重试
  - [**时执·伊斯塔露**](docs/shades/istaroth.md)：**收** — 归档 + summary.md + saga 补偿（调生执 exec）+ 生命周期
  - 9 个 stage（assignee 字段值）：spec / design / code / review_spec / review_design / review_code / simple_code / exec / chat
- **【议事辅助】天使**（晨星 leader + 11 协同天使，**不落地，只出纪要**）
  - 职能：分析 / 调研 / 决策辅助（"该不该做 X" / "选 A 还是 B" / "评估这个方案"）
  - 晨星调度（assemble → dispatch+speak loop → synthesize），按议题挑 3-5 个协同天使参与
  - 11 角色池：结构性 5 / 评估性 4 / 对抗性 2
- **【值班模块】七神**（cron + 面板 + 概念归属，**跟 /task 主链路无关**）
  - **A 类（保留 cron / 面板 / 概念归属 5 个）**：
    - [风神·巴巴托斯](docs/archons/venti.md)：信息采集 + LLM digest + `/feed` cron + 站点登录 ✅
    - [岩神·摩拉克斯](docs/archons/zhongli.md)：红利股扫描 + scorer + `/wealth` cron ✅
    - [草神·纳西妲](docs/archons/nahida.md)：`/knowledge` 面板概念归属 ✅
    - [水神·芙宁娜](docs/archons/furina.md)：游戏 `/game` + 2 cron + 1 sub type ✅
    - [冰神·冰之女皇](docs/archons/tsaritsa.md)：`/plugins` 面板代理 + skill 生态 namespace ✅
  - **B 类（archon 本体暂无具体职能 / namespace 壳 2 个）**：
    - [雷神·巴尔泽布](docs/archons/raiden.md) / [火神·玛薇卡](docs/archons/mavuika.md)（execute 兜底返"已解耦"，待用户后续安排）
- **全局支撑层**
  - [**世界树**](docs/foundation/irminsul.md)：全系统**唯一存储层**，9 个数据域（授权 / skill / 知识 / 记忆 / 任务 / token / 审计 / 理财 / 会话）
  - [**地脉**](docs/foundation/leyline.md)：事件总线
  - [**神之心**](docs/foundation/gnosis.md)：LLM 资源池（浅层 / 深层分层）
  - [**三月女神**](docs/foundation/march.md)：守护 + 调度 + 推送响铃 ✅
  - [**原石**](docs/foundation/primogem.md)：token / 花费统计

### 跨模块参考

- [权限与契约体系](docs/permissions.md)：跨模块权限机制
- [关键边界对照表](docs/boundaries.md)：模块职责归属速查
- [自进化体系](docs/evolution.md)：跨会话经验积累与行为自调整方案
- [待办项 / 下一步](docs/todo.md)：进度跟踪
- [架构总图与交互流程详版](docs/aimon.md)

---

## 快速启动

### 1. 安装

要求 Python >= 3.10。

```bash
git clone git@github.com:hlccd/paimon.git
cd paimon
pip install -e .

# 装 chromium 二进制（playwright 用，topic 等登录态 skill 需要，~150MB）
# 国内强烈推荐先设阿里镜像，否则默认 cdn.playwright.dev → google CDN，国内基本 timeout
export PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
playwright install chromium
```

> Windows 用户若 `pip` 提示"无法识别"，改用 `python -m pip install -e .`（或 `py -3 -m pip install -e .`）。

### 2. 配置 `.env`

在项目根目录新建 `.env`，按实际需要填写。最小可跑示例（OpenAI + WebUI）：

```bash
# LLM: 五选一 — claude-xiaomi / claude-official / openai / deepseek-pro / deepseek-flash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# WebUI（默认启用，端口 2975）
WEBUI_ENABLED=true
WEBUI_HOST=0.0.0.0
WEBUI_PORT=2975
WEBUI_ACCESS_CODE=your-access-code

# 系统
PAIMON_HOME=~/.paimon
DEBUG=false
```

切换到 Claude（官方 / 小米内网）：

```bash
LLM_PROVIDER=claude-official     # 或 claude-xiaomi
CLAUDE_OFFICIAL_API_KEY=sk-ant-xxx
CLAUDE_OFFICIAL_MODEL=claude-opus-4-6
```

启用 Telegram / QQ 频道（按需追加）：

```bash
# Telegram
BOT_TOKEN=123456:ABC-DEF...
OWNER_ID=123456789

# QQ 机器人
QQ_APPID=your-appid
QQ_SECRET=your-secret
QQ_OWNER_IDS=qq1,qq2
```

所有可配置项见 [paimon/config.py](paimon/config.py)。

### 3. 启动

#### 本地开发

```bash
python -m paimon          # 或 paimon
```

WebUI 默认 `http://localhost:2975`，用 `WEBUI_ACCESS_CODE` 登录。

#### 云端部署（watchdog 守护，推荐）

`scripts/run_with_watchdog.sh` 提供三个能力：

- **webui 一键升级**：`/selfcheck` 面板「🔄 检查更新 / ⬇️ 拉取并重启」，无需 ssh 登录服务器
- **崩溃自动重启**：paimon 异常退出 → watchdog 重新拉起
- **broken commit 自动回退**：连续异常 3 次 → `git reset --hard <last_good_commit>` 回退到最后一次稳定版本

##### 首次部署

```bash
# 在云端服务器
git clone git@github.com:hlccd/paimon.git
cd paimon
pip install -e .                                          # Python ≥ 3.10

# 装 chromium 二进制（~150MB；云端 minimal 镜像加 --with-deps 顺手装系统 .so）
# 腾讯云 / 阿里云国内节点直连 google CDN 几乎必超时，必设阿里镜像：
export PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
playwright install chromium

cp .env.example .env && vim .env                          # 填 LLM_PROVIDER / API key / WEBUI_ACCESS_CODE 等
nohup ./scripts/run_with_watchdog.sh 80 > .paimon/paimon.log 2>&1 &     # 日志落 .paimon/，仓库内 .gitignore 已排

# 验证
tail -f .paimon/paimon.log                                # 看到 [派蒙·启动] 系统就绪 即可
curl -s localhost:80/api/selfcheck/upgrade/check          # 应返回 {"ok":true,"head":"...","behind":0,"commits":[]}
```

##### 已有 nohup paimon 改造（一次性）

```bash
ssh 到云端
cd paimon
pkill -f 'paimon'                                         # 杀掉旧的 nohup paimon
git pull                                                  # 拉新代码（含 scripts/run_with_watchdog.sh）
pip install -e .                                          # 同步新增依赖（如 playwright）

# 一次性补装 chromium 二进制（~150MB；国内必设阿里镜像，否则 google CDN 超时）
export PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
playwright install chromium

nohup ./scripts/run_with_watchdog.sh 80 > .paimon/paimon.log 2>&1 &     # 日志落 .paimon/，仓库内 .gitignore 已排
```

之后**所有更新走 webui** `/selfcheck` 面板的「🔄 检查更新 → ⬇️ 拉取并重启」按钮，**不再需要 ssh**。

##### watchdog 工作原理

paimon 进程退出码约定：

| RC | 含义 | watchdog 动作 |
|---|---|---|
| 0 | 用户主动 stop / 正常退出 | watchdog 一同退出 |
| 100 | webui 升级请求（git pull 后 `sys.exit(100)`） | **立即** 重启加载新代码 |
| 其他 | 异常崩溃 | 累计 `restart_fail_count` +1；达 3 次 → `git reset --hard <last_good_commit>` 回退 |

状态文件（在 `.paimon/`）：

| 文件 | 写入时机 | 用途 |
|---|---|---|
| `last_good_commit` | paimon 启动稳定 **60s** 后自动写当前 git HEAD | broken commit 回退点；启动失败 60s 内 → 此文件不更新，保留旧 commit 作为回退目标 |
| `restart_fail_count` | watchdog 每次异常退出 +1，达 3 触发回退后清零 | 累计失败计数 |

##### 故障处理

升级失败常见情形：

- **`git pull 失败: ...`**：本地有 uncommitted 修改（`git status` 看），ssh 上 `git stash` 或 `git checkout -- .` 清掉
- **依赖变更需要 pip install**：升级 endpoint 检测到 `pyproject.toml` 变化时会在响应里 warning，需要 ssh 一次跑 `pip install -e .` 再触发升级
- **拉到 broken commit 后陷入循环**：watchdog 自动回退应该处理；如未生效手动 `git log .paimon/last_good_commit` + `git reset --hard <hash>` + 重启 watchdog

### 4. 常用指令

在任意频道发送：

| 指令 | 作用 |
|---|---|
| `/new` | 新建会话 |
| `/sessions` | 列出会话 |
| `/switch <id>` | 切换会话 |
| `/rename <name>` | 重命名当前会话 |
| `/delete <id>` | 删除会话 |
| `/clear` | 清空当前会话消息 |
| `/stop` | 中止流式输出 |
| `/task <描述>` | 复杂任务（四影） |
| `/agents <议题>` | 多视角讨论（天使体系） |
| `/skills` | 列所有可调 Skill |
| `/stat` | 查看 token / 花费统计 |
| `/help` | 帮助 |

---

## License

见 [LICENSE](LICENSE)。
