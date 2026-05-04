# Paimon · 神圣规划

> 个人 AI 助手系统 — 代号 **AIMON**（*Algorithm of Intransient Matrix of Overseer Network*，永恒统辖矩阵）
> 入口为 **PAIMON**（*Primordial* + AIMON，原初永恒统辖矩阵 / 向导·派蒙）

派蒙是系统与用户之间唯一的出入口，负责轻鉴权、意图分类、任务路由和人格化送达。背后由「天使体系」处理简单任务，「四影-七神」处理复杂任务，一整套基础设施（神之心 / 原石 / 地脉 / 世界树 / 三月）提供支撑。

---

## 架构总览

- **【神圣规划】**
  - [**向导·派蒙**](docs/paimon/paimon.md)（统一入口）
    - 入口接入：统一对接 WebUI / Telegram / QQ 等渠道
    - 轻鉴权：各 channel 沿用原有机制（WEBUI_ACCESS_CODE / BOT_TOKEN+OWNER_ID / APPID+SECRET）
    - 轻量安全：关键词过滤、恶意参数拦截
    - 意图粗分类：判断任务类型 + 复杂度
    - 任务路由：简单 → 天使；复杂 → 四影-七神
    - 天使调度：按 skill 派发、30s 超时、失败走魔女会流转
    - 闲聊响应：走浅层 LLM，不经任何天使
    - 权限询问：启动读世界树画像；运行时只接四影通知；敏感操作询问用户；识别"永久"写世界树
    - 指令规则：「/task」开头强制路由四影-七神
  - **【第一轨】**[**天使体系**](docs/angels/angels.md)（简单任务）
    - 天使 = skill 代名词，一一对应
    - 1~2 个天使能完成 → 派蒙直调
    - 无法处理 / 实际复杂 → 魔女会 → 生执重新编排
    - 内置 30s 超时
  - **【第二轨】四影-七神**（复杂任务）
    - **四影**（流程骨架，不做业务）
      - [**生执·纳贝里士**](docs/shades/naberius.md)：任务编排、DAG 拆分、依赖环检测、多轮迭代轮次控制、失败回滚
      - [**死执·若纳瓦**](docs/shades/jonova.md)：安全审查（违规 / 越权）+ 规则合规校验 + 运行时新 skill 审查
      - [**空执·阿斯莫代**](docs/shades/asmoday.md)：动态路由、服务发现、故障切换
      - [**时执·伊斯塔露**](docs/shades/istaroth.md)：活跃压缩 + 生命周期 + 最终归档 + 最终审计
    - **七神**（能力模块）
      - [**风神·巴巴托斯**](docs/archons/venti.md)：自由·歌咏 → 时事新闻采集 + 新闻推送整理（✅ 信息流面板）
      - [**岩神·摩拉克斯**](docs/archons/zhongli.md)：契约·财富 → 理财（红利股 / 资产 / 退休规划）+ 股价 / 分红提醒整理(✅ 理财面板)
      - [**雷神·巴尔泽布**](docs/archons/raiden.md)：永恒·造物 → 写代码（含自检）
      - [**草神·纳西妲**](docs/archons/nahida.md)：智慧·文书 → 推理、意图、知识整合、文书起草、Prompt 调优、个人偏好管理（✅ 知识 / 偏好面板）
      - [**水神·芙宁娜**](docs/archons/furina.md)：戏剧·评审 → 游戏 + 成品评审（✅ 游戏面板）
      - [**火神·玛薇卡**](docs/archons/mavuika.md)：战争·冲锋 → shell/code 执行、重型工具、技术性重试
      - [**冰神·冰之女皇**](docs/archons/tsaritsa.md)：反抗·联合 → skill 生态全管（发现 + 写世界树 + AI 自举）（✅ 插件面板）
  - **全局支撑层**
    - [**三月女神**](docs/foundation/march.md)：守护进程、任务观测（✅ 观测面板）、定时调度、推送响铃（定时 + 事件）
    - [**地脉**](docs/foundation/leyline.md)：全局事件总线（所有模块间事件流转）
    - [**世界树**](docs/foundation/irminsul.md)：知识持久化 + 缓存 + skill 生态声明 + 用户授权记录（权威源）
    - [**神之心**](docs/foundation/gnosis.md)：独立 LLM 资源池（浅层 / 深层分层）
    - [**原石**](docs/foundation/primogem.md)：Token + 花费统计（按模块 / 用途 / 会话 多维度聚合）

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

```bash
python -m paimon
# 或安装后使用命令
paimon
```

WebUI 启动后访问 `http://localhost:2975`，用 `WEBUI_ACCESS_CODE` 登录即可开始对话。

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
| `/stat` | 查看 token / 花费统计 |
| `/help` | 帮助 |

---

## License

见 [LICENSE](LICENSE)。
