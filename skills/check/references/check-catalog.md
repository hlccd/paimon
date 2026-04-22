# 检查项目录（Check Catalog）

所有可审查的检查项，每项有稳定 ID。审查输出 finding 时必须引用 ID。

---

## 通用原则（所有 module 适用）

### 简洁凝练

- 每句话应有明确信息增量，删掉后不影响理解的内容不该存在
- 同一信息不重复表述，能一句话说清的不用一段
- 单个文件/文档过大（>500 行）时应考虑拆分
- 三处相似逻辑可以提取，但不要为假设性需求过早抽象

### 优先用结构化表达

- 能用表格就不用大段文字
- 能用流程图/ASCII 图就不用纯文字描述
- 代码示例 > 文字描述

---

## Module: accuracy（准确性）

### ACC — Accuracy（14 项）+ LNK — Links（3 项）

适用输入：docs, code-vs-docs；code 仅 ACC-012~014

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| ACC-001 | 方法名/函数名与源码一致 | Grep 精确匹配定义 | P0 |
| ACC-002 | 参数签名与源码一致 | Read 函数定义逐参数比对 | P0 |
| ACC-003 | 文件路径真实存在 | Glob 验证 | P0 |
| ACC-004 | 行为描述与代码逻辑一致 | Read 实现比对描述 | P0 |
| ACC-005 | 配置值与源码一致 | Grep 常量定义 | P1 |
| ACC-006 | API 端点路由与注册一致 | Grep @router | P0 |
| ACC-007 | SQL Schema 与建表语句一致 | Read DB 初始化 | P0 |
| ACC-008 | 继承关系与实际 import 一致 | Grep import | P1 |
| ACC-009 | 数值声明与实际一致 | wc -l / Grep count 比对 | P1 |
| ACC-010 | 错误码与源码定义一致 | Grep 错误码常量 | P0 |
| ACC-011 | 核心接口有文档覆盖 | 列出公开方法比对 | P0 |
| ACC-012 | 代码注释/docstring 与实际行为不符 | Read 函数对照注释 | P1 |
| ACC-013 | CHANGELOG 与实际变更不符 | 比对 git log | P1 |
| ACC-014 | 示例代码输出与实际不符 | 阅读示例推演结果 | P0 |

### LNK — Links（3 项）

适用输入：docs, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| LNK-001 | 内部文件链接目标存在 | link-checker.py / Glob | P0 |
| LNK-002 | 锚点链接目标标题存在 | link-checker.py | P1 |
| LNK-003 | 无虚构的外部 URL | 域名合理性判断 | P0 |

---

## Module: clarity（清晰度）

### CLR — Clarity（4 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| CLR-001 | 嵌套层级过深（>4 层） | 计算嵌套深度 | P2 |
| CLR-002 | 不直观的布尔参数 | 多个 positional bool | P2 |
| CLR-003 | 超大函数（>100 行） | wc -l | P2 |
| CLR-004 | 命名误导 | 变量/函数名与实际行为不符 | P1 |

### BRV — Brevity（5 项）

适用输入：docs, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| BRV-001 | 无冗余重复 | 全文比对相似段落 | P1-P3 |
| BRV-002 | 无空洞描述 | 删除后是否丢信息 | P1 |
| BRV-003 | 无过度铺垫 | 搜索铺垫模式 | P3 |
| BRV-004 | 表述精准 | 审查信息密度比 | P2 |
| BRV-005 | 意义清晰 | 首次阅读者视角 | P1 |

### LNG — Language（3 项）

适用输入：docs, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| LNG-001 | 无推测性用语 | Grep "可能/应该/大概/也许/似乎" | P1 |
| LNG-002 | 无虚构内容 | 交叉验证源码 | P0 |
| LNG-003 | 技术术语统一 | 全文检索同义词 | P2 |

---

## Module: consistency（一致性）

### CON — Consistency（4 项）

适用输入：docs, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| CON-001 | 同一概念跨文档描述一致 | 交叉搜索比对 | P1 |
| CON-002 | 数值引用跨文档一致 | Grep 数值 + 上下文 | P1 |
| CON-003 | 架构图与文字描述一致 | 对照图与正文 | P1 |
| CON-004 | 目录索引与实际文件结构一致 | 比对索引与文件列表 | P1 |

### CST — Code Style Consistency（5 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| CST-001 | 错误处理模式不一致 | 比对不同模块的 error handling | P2 |
| CST-002 | API 命名约定不一致 | camelCase/snake_case 混用 | P2 |
| CST-003 | 配置格式不一致 | YAML/JSON/TOML/env 混用 | P3 |
| CST-004 | 日志格式不一致 | 不同模块日志结构不同 | P2 |
| CST-005 | 注释/docstring 风格不一致 | 部分详细部分无 | P3 |

---

## Module: security（安全性）

### SEC — Security（17 项）

适用输入：code, code-vs-docs；docs/spec 仅 SEC-005/006

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| SEC-001 | SQL 注入 | f-string 拼接 SQL | P0 |
| SEC-002 | 命令注入 | shell=True 或拼接 exec | P0 |
| SEC-003 | 路径穿越 | 用户输入直接拼路径 | P0 |
| SEC-004 | SSRF | URL 来自用户输入 | P0 |
| SEC-005 | 硬编码密钥 | 源码/文档中 API_KEY/token | P0 |
| SEC-006 | 密钥打印到日志 | 密钥出现在 log/print | P1 |
| SEC-007 | 未校验的反序列化 | pickle/yaml.load 用户输入 | P0 |
| SEC-008 | 弱加密/哈希 | MD5/SHA1 用于密码 | P1 |
| SEC-009 | 随机数熵不足 | random 用于安全场景 | P1 |
| SEC-010 | CSRF 保护缺失 | 修改类 API 无 CSRF token | P1 |
| SEC-011 | XSS | 用户输入未转义插入 HTML | P1 |
| SEC-012 | 越权（IDOR） | 对象访问不校验所有者 | P0 |
| SEC-013 | 越权（ABAC 缺失） | 管理接口无角色校验 | P0 |
| SEC-014 | 敏感信息响应 | 接口返回内部错误栈 | P1 |
| SEC-015 | 日志/异常消息泄漏 | 错误消息泄漏系统信息 | P2 |
| SEC-016 | 依赖锁文件缺失 | 无 lockfile 或未提交到版本控制 | P1 |
| SEC-017 | 依赖版本范围过宽 | 使用 >= / * 等不限定范围，存在供应链攻击风险 | P1 |

---

## Module: hygiene（卫生度）

### DEAD — Dead Code（8 项；hygiene 主管 6 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 | 主归属 |
|----|--------|---------|---------|--------|
| DEAD-001 | 未使用 import | 全文无引用 | P3 | hygiene |
| DEAD-002 | 未使用变量 | 仅赋值无读取 | P3 | hygiene |
| DEAD-003 | 未使用函数 | 全项目 grep 无调用 | P2 | hygiene |
| DEAD-004 | 未使用参数 | 签名有但内部不用 | P3 | hygiene |
| DEAD-005 | 不可达分支 | 永真/永假条件 | P2 | hygiene |
| DEAD-006 | 重复实现 | 两处逻辑 90%+ 相似 | P2 | architecture |
| DEAD-007 | 过时 TODO/FIXME | 超过 6 个月未处理 | P3 | hygiene |
| DEAD-008 | 未使用模块 | 无 import 指向该文件 | P2 | architecture |

### HYG — Hygiene（4 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| HYG-001 | 注释掉的代码块 | >5 行被注释代码 | P3 |
| HYG-002 | 空文件/空测试 | 文件存在无实质内容 | P2 |
| HYG-003 | 过时配置项 | config 中代码不再读取的键 | P2 |
| HYG-004 | 重复依赖声明 | requirements 中同包多次 | P3 |

---

## Module: completeness（完整性）

### CMP — Completeness（7 项）

适用输入：docs CMP-001~005；code CMP-006~007；code-vs-docs 全部

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| CMP-001 | 核心公开接口未文档化 | 列出公开 API 比对文档 | P0 |
| CMP-002 | 错误处理场景未文档化 | 报错无文档指导 | P1 |
| CMP-003 | 配置项未文档化 | getenv 在文档中无说明 | P1 |
| CMP-004 | 关键用例未覆盖 | 只有 happy path | P2 |
| CMP-005 | 缺少环境变量说明 | getenv 无对应文档 | P1 |
| CMP-006 | switch/match 缺 default | 枚举分支不完整 | P1 |
| CMP-007 | 函数缺空/null/异常输入处理 | 公开函数无输入验证 | P1 |

---

## Module: usability（易用性）

### USB — Usability（8 项）

适用输入：code USB-001/002/005/007/008；docs USB-003/004/006；code-vs-docs 全部

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| USB-001 | API 错误信息不具可操作性 | 报错只说 failed 不说原因 | P1 |
| USB-002 | 配置过于复杂 | 必填项过多/默认值不合理 | P2 |
| USB-003 | 缺少快速开始示例 | 无法 5 分钟内跑通 | P1 |
| USB-004 | 错误码/异常无对应文档 | 报错无处可查 | P1 |
| USB-005 | CLI 帮助信息不完整 | --help vs 实际行为 | P1 |
| USB-006 | 文档结构不便查找 | 深层嵌套/无索引 | P2 |
| USB-007 | 破坏性操作无确认/撤销 | 删除/覆盖无二次确认 | P0 |
| USB-008 | 无障碍访问缺失 | 交互元素缺少 a11y 属性/标签/键盘导航支持 | P2 |

---

## Module: freshness（新鲜度）

### FRS — Freshness（6 项）

适用输入：code FRS-002/003/006；docs FRS-001/004/005；code-vs-docs 全部

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| FRS-001 | 文档描述已删除/重命名的功能 | Grep 源码确认 | P0 |
| FRS-002 | 依赖库已停维或存在已知 CVE | 检查版本和维护状态 | P1 |
| FRS-003 | 代码使用已废弃 API/方法 | Grep deprecated | P1 |
| FRS-004 | 文档引用的外部资源已下线 | URL 合理性判断 | P1 |
| FRS-005 | 文档与代码最后修改差距 >6 月 | git log 比对 | P2 |
| FRS-006 | 使用过时语言特性/模式 | Python 2 兼容代码等 | P2 |

---

## Module: compliance（合规性）

### SKL — Skill 合规（18 项，仅当源码含 SKILL.md 时启用）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| SKL-001 | frontmatter 必填字段齐全 | 检查 name + description | P0 |
| SKL-002 | name 与目录名一致 | 比对 | P0 |
| SKL-003 | name 格式合规 | 小写+连字符 1-64 字符 | P0 |
| SKL-004 | description ≤1024 字符且非空 | 字符数 | P1 |
| SKL-005 | allowed-tools 格式正确 | 空格分隔字符串 | P1 |
| SKL-006 | allowed-tools 与实际使用一致 | 双向比对 | P1 |
| SKL-007 | references/ 引用文件存在 | Glob | P0 |
| SKL-008 | scripts/ 引用文件存在且可执行 | Glob + 权限 | P1 |
| SKL-009 | module 引用的 check-id 在 catalog 存在 | Grep | P1 |
| SKL-010 | catalog 中无死 ID | 逐 ID grep 所有 module | P2 |
| SKL-011 | template 占位符有填充来源 | 逐 {xxx} 匹配 | P2 |
| SKL-012 | 填充逻辑占位符在 template 存在 | 反向匹配 | P2 |
| SKL-013 | module 结构完备 | 检查核心段落 | P2 |
| SKL-014 | 流程分支闭合 | 每条件有出口 | P1 |
| SKL-015 | 输出格式明确 | 有 pipe-delimited 示例 | P1 |
| SKL-016 | 参数组合冲突有报错 | 检查非法组合处理 | P1 |
| SKL-017 | state.json 字段与逻辑自洽 | 比对模板 vs 读写 | P2 |
| SKL-018 | SKILL.md ≤500 行 | wc -l | P2 |

### CPL — Compliance（7 项）

适用输入：code CPL-002~004/006/007；docs CPL-001/005；code-vs-docs 全部

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| CPL-001 | 许可证兼容性 | 依赖 license vs 项目 license | P1 |
| CPL-002 | 项目代码规范未遵守 | .editorconfig/.eslintrc vs 实际 | P2 |
| CPL-003 | commit message 不符约定格式 | git log 比对 | P3 |
| CPL-004 | API 版本控制规范不符 | 语义化版本检查 | P2 |
| CPL-005 | 数据隐私合规 | GDPR/个人信息处理 | P0 |
| CPL-006 | API 破坏性变更无废弃通知 | 公开接口签名变更未标 @deprecated/迁移说明 | P1 |
| CPL-007 | 破坏性变更缺迁移指南 | 大版本升级无 MIGRATION.md 或 CHANGELOG 迁移段 | P1 |

---

## Module: reliability（可靠性）

### REL — Reliability（20 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| REL-001 | 异常吞没（无日志） | except: pass / 空 catch | P0 |
| REL-002 | 异常吞没（有日志继续跑关键路径） | except 后用可能为 None 的结果 | P1 |
| REL-003 | 持久化非原子写入 | 检查 tmp+rename | P0 |
| REL-004 | 并发竞态（无锁） | 多线程访问共享状态 | P0-P1 |
| REL-005 | 资源泄漏（未关闭） | open/connect 未配 with | P1 |
| REL-006 | 资源泄漏（悬空 task） | create_task 后不 await | P1 |
| REL-007 | 未 await 的协程 | async 被当同步调用 | P0 |
| REL-008 | 主键/ID 碰撞风险 | random.randint 小范围 | P0 |
| REL-009 | INSERT OR REPLACE 触发 CASCADE DELETE | FK CASCADE 表 | P0 |
| REL-010 | 序列化/反序列化类型不一致 | schema 假设不同 | P0-P1 |
| REL-011 | 无限循环/递归无出口 | while True 无 break | P0 |
| REL-012 | 超时未设置 | HTTP/DB/socket 无 timeout | P1 |
| REL-013 | 重试逻辑缺陷 | 无 backoff/上限 | P1-P2 |
| REL-014 | 启动未恢复中断状态 | 崩溃后状态未重置 | P1 |
| REL-015 | 非幂等关键操作 | 重复调用不同结果 | P1 |
| REL-016 | 未处理反序列化错误 | json.loads 裸调用 | P1 |
| REL-017 | 日志脱敏缺失 | 日志中打印密钥/PII | P1 |
| REL-018 | 依赖服务不可用无降级 | 外部挂了直接传播 | P1 |
| REL-019 | 版本迁移破坏旧数据 | Schema 升级未考虑旧格式 | P0 |
| REL-020 | 调度任务重复/丢失 | cron 在多实例下行为 | P1 |

---

## Module: performance（性能）

### PERF — Performance（10 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| PERF-001 | N+1 查询 | 循环中 DB query | P1 |
| PERF-002 | 同步阻塞异步 | async 中 requests.get | P1 |
| PERF-003 | O(n²) 热路径 | 嵌套循环 + 大 n | P1-P2 |
| PERF-004 | 大对象序列化热路径 | json.dumps 大结构 | P2 |
| PERF-005 | 不必要深拷贝 | 只读场景 deepcopy | P2 |
| PERF-006 | 缓存缺失 | 重复计算 pure function | P2 |
| PERF-007 | 缓存无上限 | 全局 cache 无 TTL/LRU | P1 |
| PERF-008 | 大 list 常驻内存 | 只用局部但存整个 | P2 |
| PERF-009 | 正则预编译缺失 | 热路径 re.search(pattern) | P3 |
| PERF-010 | 日志级别过低 | debug 热路径打印大对象 | P2 |

---

## Module: architecture（架构）

### ARCH — Architecture（12 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| ARCH-001 | 循环依赖 | A import B、B import A | P1 |
| ARCH-002 | 上帝对象 | 单类 >500 行 + >20 公开方法 | P2 |
| ARCH-003 | 分层破坏 | 低层依赖高层 | P1 |
| ARCH-004 | 全局可变状态 | 模块级 dict 到处改 | P1 |
| ARCH-005 | 紧耦合 | new 具体类而非接口 | P2 |
| ARCH-006 | 职责泄漏 | 业务逻辑散落非业务层 | P2 |
| ARCH-007 | 接口契约不清晰 | 无 type hints + 无 docstring | P2 |
| ARCH-008 | 数据结构跨层暴露 | ORM 对象直接返回前端 | P2 |
| ARCH-009 | 同步/异步混用 | async 中 time.sleep | P1 |
| ARCH-010 | 配置与代码混合 | 环境值写死在代码 | P2 |
| ARCH-011 | 错误处理层级混乱 | 多层重复 catch | P2 |
| ARCH-012 | 事件驱动失控 | signal 满天飞无追踪 | P2 |

---

## Module: project-health（项目健康）

### PRJ — Project Health（16 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| PRJ-001 | README 功能描述与代码一致 | Read README + Grep | P1 |
| PRJ-002 | README 安装/运行命令可执行 | 检查依赖+入口 | P0 |
| PRJ-003 | 配置示例键名与代码一致 | Grep config 键名 | P0 |
| PRJ-004 | 配置示例默认值与代码一致 | 比对示例 vs 代码默认 | P1 |
| PRJ-005 | 依赖声明与实际 import 一致 | 比对 requirements vs import | P1 |
| PRJ-006 | 入口文件存在且可定位 | Glob main.py 等 | P0 |
| PRJ-007 | 版本号多处声明一致 | Grep version | P1 |
| PRJ-008 | .env.example 与 getenv 一致 | 比对 | P1 |
| PRJ-009 | CI 配置引用脚本/路径存在 | Glob | P1 |
| PRJ-010 | LICENSE 与项目声明一致 | 比对 | P2 |
| PRJ-011 | 测试文件非空壳 | Read 检查内容 | P2 |
| PRJ-012 | DB migration 编号连续 | 排序检查 | P1 |
| PRJ-013 | Dockerfile 引用路径/端口一致 | 比对 EXPOSE/COPY | P1 |
| PRJ-014 | 项目内部 import 无循环依赖 | 构建导入图 | P2 |
| PRJ-015 | git 中无敏感文件 | Glob .env/credentials | P0 |
| PRJ-016 | 构建锁文件与依赖声明同步 | lockfile 存在且与 requirements/package.json 一致 | P1 |

---

## Module: extensibility（可扩展性）

### EXT — Extensibility（15 项）

适用输入：code, code-vs-docs。使用机会发现引擎。

| ID | 机会类型 | 识别方法 | 价值指标 |
|----|---------|---------|---------|
| EXT-001 | 接口已抽象仅一种实现 | ABC/Protocol + 单实现 | 加新实现成本低 |
| EXT-002 | Hook/事件机制已存在 | EventEmitter/signals | 无需改核心 |
| EXT-003 | 配置驱动行为 | 从 config 读取分支 | 加配置即加功能 |
| EXT-004 | 插件/注册表模式 | register/plugin | 新插件即新能力 |
| EXT-005 | 策略模式已就位 | Strategy/Policy | 新策略零改主流程 |
| EXT-006 | 命令/工具注册中心 | 统一命令分发 | 加命令零侵入 |
| EXT-007 | Channel/Adapter 模式 | 多通道共用核心 | 加 channel 低成本 |
| EXT-008 | 数据源抽象 | Repository/DAO | 切换存储低成本 |
| EXT-009 | 中间件管道 | WSGI/Express middleware | 可插拔 |
| EXT-010 | 模板/主题系统 | template 渲染层 | 可定制 |
| EXT-011 | 核心功能边界 | 梳理边界 | 功能天花板 |
| EXT-012 | 同类工具对比缺口 | 与同领域对比 | 功能差距 |
| EXT-013 | 用户工作流断点 | 手动补全环节 | 自动化机会 |
| EXT-014 | 数据/输出复用机会 | 被其他工具消费 | 生态集成 |
| EXT-015 | 配置/定制化不足 | 硬编码应可配置 | 灵活性 |

---

## Module: feasibility（可实施性）

### FEA — Feasibility（16 项）

适用输入：spec

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| FEA-001 | 技术假设可行性 | 方案依赖的技术/API/能力是否真实可用 | P0 |
| FEA-002 | 依赖可用性 | 声明的外部依赖/三方服务是否存在、维护中 | P1 |
| FEA-003 | 性能目标合理性 | 性能指标与架构设计是否匹配 | P1 |
| FEA-004 | 资源需求合理性 | 人力/时间/基础设施假设是否现实 | P1 |
| FEA-005 | 接口契约完整性 | 所有对外接口是否定义了入参/出参/错误码 | P0 |
| FEA-006 | 数据模型完整性 | 数据结构/Schema 完整定义字段、类型、约束 | P0 |
| FEA-007 | 异常流程覆盖 | 错误/降级/超时/重试场景是否有设计 | P1 |
| FEA-008 | 安全设计充分性 | 数据隔离/传输安全/权限校验/敏感数据处理/认证授权是否有设计 | P1 |
| FEA-009 | 可测试性设计 | 是否定义测试场景和验收标准 | P1 |
| FEA-010 | 部署方案完整性 | 上线步骤/环境配置/灰度策略是否定义 | P2 |
| FEA-011 | 回滚方案 | 是否有失败回滚路径 | P1 |
| FEA-012 | 模糊词检测 | 是否存在无法直接转化为代码的模糊描述 | P1 |
| FEA-013 | 文档结构合规 | 方案是否遵循组织约定的模板/章节结构 | P1 |
| FEA-014 | 强制要素齐全 | 架构设计/接口定义/数据模型/异常处理/测试策略/部署方案是否齐全 | P0 |
| FEA-015 | 逻辑闭环性 | 每个功能的正常+异常流程是否有明确出口 | P1 |
| FEA-016 | 测试策略覆盖 | 正常/边界/异常/并发场景是否有对应测试策略 | P1 |

---

## Module: alignment（方案对齐）

### ALN — Alignment（14 项）

适用输入：code-vs-spec, change-vs-spec

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| ALN-001 | 接口定义对齐 | 方案定义的接口在代码中是否完整实现 | P0 |
| ALN-002 | 数据模型对齐 | 字段名/类型/约束是否与方案一致 | P0 |
| ALN-003 | 架构落位对齐 | 代码分层/模块归属是否符合方案设计 | P1 |
| ALN-004 | 外部依赖对齐 | 方案要求的外部调用是否都已实现 | P1 |
| ALN-005 | 配置项对齐 | 方案定义的配置是否在代码中体现 | P1 |
| ALN-006 | 流程一致性 | 代码执行流程是否与方案流程图一致 | P0 |
| ALN-007 | 测试覆盖对齐 | 方案要求的测试场景是否有对应用例 | P1 |
| ALN-008 | 错误处理对齐 | 异常/降级/兜底是否与方案设计一致 | P1 |
| ALN-009 | 缺失实现检测 | 方案明确要求但代码中完全缺失 | P0 |
| ALN-010 | 超出方案检测 | 代码中存在但方案未提及的实现 | P2 |
| ALN-011 | 偏差分析 | 实现与方案有差异且无说明原因 | P1 |
| ALN-012 | 方案模糊区域 | 方案描述不清导致实现无据可依 | P2 |
| ALN-013 | 方案缺陷反馈 | 代码实现优于方案设计，建议反向更新方案 | P2 |
| ALN-014 | 规范冲突检测 | 方案设计与项目现有规范/最佳实践冲突 | P1 |

---

## Module: coherence（连贯性）

### COH — Coherence（10 项）

适用输入：全部模式（按检查项区分代码侧/文档侧适用性，详见 modules/coherence.md）

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| COH-001 | 跨文件矛盾 | 同一实体/数值/规则在不同文件中描述不一致 | P1 |
| COH-002 | 引用链完整性 | 配置/文档/代码中引用的文件/模块/资源是否全部存在 | P0 |
| COH-003 | 注册一致性 | 注册表/清单/配置文件中的条目与实际文件是否对应 | P1 |
| COH-004 | 孤儿检测 | 存在但无任何其他文件链接/引用/import 指向的文件 | P2 |
| COH-005 | 陈旧内容 | 含日期结论超 90 天未更新；TBD/待定未跟进；引用已删文件 | P1 |
| COH-006 | 索引/目录缺失 | 文件存在但未在索引或目录结构文件中注册 | P2 |
| COH-007 | 跨入口一致性 | README/配置/注册表等多入口文件对同一事实的声明是否一致 | P1 |
| COH-008 | 结构错位 | 文件是否按项目约定的目录模式/命名规范放置 | P2 |
| COH-009 | 缺失交叉引用 | 文档提及实体/概念名称但未链接到对应文件 | P2 |
| COH-010 | 建议合并/拆分 | 同一概念在 3+ 文件中重复描述无专属文件；或单文件 >500 行 | P3 |

---

## Module: testability（可测试性）

### TST — Testability（7 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| TST-001 | 关键路径缺测试覆盖 | Grep 测试文件中对核心函数的调用 | P1 |
| TST-002 | 函数内硬编码外部依赖无注入点 | HTTP/DB/文件系统无法 mock | P2 |
| TST-003 | 测试间共享可变状态 | fixture/全局变量污染 | P1 |
| TST-004 | 业务逻辑与 I/O 混杂 | 无法纯单元测试 | P2 |
| TST-005 | 缺少测试工具/fixture | 无 conftest/factory/mock helper | P2 |
| TST-006 | 异步代码测试困难 | 缺少异步测试基础设施 | P2 |
| TST-007 | 关键分支仅靠集成测试 | 应有单元测试的逻辑依赖 E2E | P2 |

---

## Module: observability（可观测性）

### OBS — Observability（7 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| OBS-001 | 关键业务操作缺日志 | 成功/失败均无记录 | P1 |
| OBS-002 | 错误日志缺上下文 | 只有消息没有请求 ID/参数 | P1 |
| OBS-003 | 缺少健康检查端点 | 无 /health | P2 |
| OBS-004 | 缺少请求追踪 | 无 trace-id 传播 | P2 |
| OBS-005 | 日志结构不统一 | JSON/纯文本混杂 | P2 |
| OBS-006 | 缺少关键指标暴露 | QPS/延迟/错误率无采集 | P2 |
| OBS-007 | 异步任务无状态可查 | fire-and-forget 后无结果 | P1 |

---

## Module: robustness（健壮性）

### ROB — Robustness（7 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| ROB-001 | 缺少输入验证/sanitization | 用户输入直接进业务逻辑 | P1 |
| ROB-002 | 缺少熔断/断路器 | 外部持续失败无保护 | P2 |
| ROB-003 | 缺少速率限制 | 无限请求可打垮系统 | P1 |
| ROB-004 | 异常恢复后状态不一致 | 降级恢复时状态未重置 | P1 |
| ROB-005 | 大批量输入无分页/限制 | 大量数据直接 OOM | P1 |
| ROB-006 | 级联失败无隔离 | 一个下游故障拖垮全部 | P1 |
| ROB-007 | 缺少优雅关闭 | SIGTERM 后请求直接丢弃 | P1 |

---

## Module: portability（可移植性）

### PRT — Portability（8 项）

适用输入：code, code-vs-docs

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| PRT-001 | 硬编码绝对路径 | Grep /home/ C:\ 等 | P1 |
| PRT-002 | 硬编码主机名/端口/URL | localhost:8080 写死 | P1 |
| PRT-003 | 平台特定系统调用 | os.fork 等 Windows 不可用 | P2 |
| PRT-004 | 数据库方言绑定 | 特定 DB 语法无抽象层 | P2 |
| PRT-005 | 字符编码假设 | 假设 UTF-8 未显式声明 | P3 |
| PRT-006 | 文件系统大小写假设 | macOS vs Linux | P2 |
| PRT-007 | 缺少容器化配置 | 无 Dockerfile 且有多依赖 | P3 |
| PRT-008 | 用户可见字符串硬编码 | 无 i18n 机制，用户界面文本写死在代码中 | P2 |

---

## Module: maintainability（可维护性）

### MNT — Maintainability（6 项）

适用输入：code, code-vs-docs；docs 仅 MNT-005

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| MNT-001 | 变更放大 | 改一业务规则需改 >3 文件 | P2 |
| MNT-002 | 缺少变更隔离 | 无 feature flag/策略 | P2 |
| MNT-003 | 魔法值散落 | 常量散布各处未集中 | P2 |
| MNT-004 | 缺少迁移工具/脚本 | schema 变更需手动操作 | P2 |
| MNT-005 | 文档与代码同步成本高 | 文档硬编码代码细节 | P2 |
| MNT-006 | 测试脆弱性 | 测试依赖实现细节非接口 | P2 |

---

## 跨 module 检查项归属

部分检查项被多个 module 引用。每项有一个主归属，去重时主归属严重度优先。

| 检查项 | 主归属 | 引用方 |
|--------|--------|--------|
| COR-001 | reliability | — |
| COR-002 | completeness | robustness |
| COR-004 | robustness | security |
| COR-005 | accuracy | — |
| COR-007 | reliability | — |
| COR-008 | clarity | architecture |
| COR-014 | reliability | — |
| COR-015 | hygiene | — |
| REL-001 | reliability | observability |
| REL-005 | reliability | performance |
| REL-012 | reliability | performance, robustness |
| REL-013 | reliability | robustness |
| REL-016 | reliability | security, robustness |
| REL-017 | reliability | security, observability |
| REL-018 | reliability | robustness |
| SEC-001 | security | reliability |
| ACC-011 | accuracy | completeness |
| ARCH-001 | architecture | maintainability |
| ARCH-002 | architecture | clarity, hygiene, maintainability |
| ARCH-004 | architecture | reliability, testability |
| ARCH-005 | architecture | testability, maintainability |
| ARCH-006 | architecture | clarity |
| ARCH-007 | architecture | clarity |
| ARCH-009 | architecture | reliability, performance |
| ARCH-010 | architecture | clarity, portability, testability |
| ARCH-011 | architecture | maintainability |
| ARCH-012 | architecture | maintainability |
| DEAD-006 | architecture | maintainability |
| DEAD-007 | hygiene | freshness |
| DEAD-008 | architecture | — |
| PRJ-005 | project-health | freshness |
| PRJ-007 | project-health | consistency |
| PRJ-008 | project-health | portability |
| PRJ-010 | project-health | compliance |
| PRJ-011 | project-health | testability |
| PRJ-013 | project-health | portability |
| PRJ-015 | project-health | security |
| PERF-010 | performance | observability |
| PRJ-009 | project-health | coherence |
| PRJ-014 | project-health | architecture |
| CST-004 | consistency | observability |
| USB-004 | usability | completeness |
| CON-001 | consistency | coherence |
| LNG-003 | clarity | consistency |

---

## COR — 原 Correctness 检查项（15 项，已分散到各 module）

COR 前缀保留用于交叉引用。每项已分配到新主归属 module。

| ID | 检查项 | 验证方法 | 默认级别 | 主归属 |
|----|--------|---------|---------|--------|
| COR-001 | 状态机非法转换 | 对照转换表检查赋值 | P0 | reliability |
| COR-002 | 边界条件未处理 | 空列表/零值/极大值 | P1 | completeness |
| COR-003 | Off-by-one 错误 | range/切片边界 | P1 | accuracy |
| COR-004 | 类型强制转换错误 | int(input) 无 try | P1 | robustness |
| COR-005 | 函数契约违反 | 调用处传参与签名不符 | P0 | accuracy |
| COR-006 | 返回值类型不一致 | 不同分支返回不同类型 | P1 | accuracy |
| COR-007 | 空值处理错误 | None 传递到不接受位置 | P0-P1 | reliability |
| COR-008 | 枚举值用字符串字面量 | 散落 magic string | P2 | clarity |
| COR-009 | 时间/日期处理错误 | 时区/夏令时/跨天 | P1 | accuracy |
| COR-010 | 浮点数相等比较 | == 判断浮点 | P2 | accuracy |
| COR-011 | 引用而非复制 | 浅拷贝导致副作用 | P1 | reliability |
| COR-012 | 并发计数/累加 | ++ 非原子 | P1 | reliability |
| COR-013 | 字符串拼接路径/SQL | 应使用参数化 | P0-P1 | security |
| COR-014 | 日期时间 None 处理 | parse("") 返回 now() | P1 | reliability |
| COR-015 | 条件逻辑冗余/错误 | A and A、蕴涵错误 | P2 | hygiene |

### COR 到 Module 的分配映射

| 原 ID | 检查内容 | 新主归属 |
|-------|---------|---------|
| COR-001 | 状态机非法转换 | reliability（状态导致崩溃） |
| COR-002 | 边界条件未处理 | completeness（分支不完整） |
| COR-003 | Off-by-one | accuracy（逻辑不准确） |
| COR-004 | 类型强制转换错误 | robustness（意外输入） |
| COR-005 | 函数契约违反 | accuracy（声明与实现不符） |
| COR-006 | 返回值类型不一致 | accuracy（行为不一致） |
| COR-007 | 空值处理错误 | reliability（崩溃原因） |
| COR-008 | 枚举用字符串字面量 | clarity（含义不自明） |
| COR-009 | 时间/日期处理错误 | accuracy（计算不准确） |
| COR-010 | 浮点数相等比较 | accuracy（比较不准确） |
| COR-011 | 引用而非复制 | reliability（副作用导致数据损坏） |
| COR-012 | 并发计数/累加 | reliability（并发问题） |
| COR-013 | 字符串拼接路径/SQL | security（注入风险） |
| COR-014 | 日期时间 None 处理 | reliability（异常数据处理） |
| COR-015 | 条件逻辑冗余 | hygiene（代码垃圾） |

> COR 前缀保留用于交叉引用。新发现的逻辑正确性问题使用各自主归属 module 的前缀或 UNKNOWN-{category}-{hash}。

---

## 使用约定

1. **必须引用 ID**：`CANDIDATE | P0 | REL-003 | session.py:45 | ...`
2. **未列出的新问题**：用 `UNKNOWN-{category}-{hash}` 作为临时 ID
3. **module 文件声明该 module 使用哪些 ID**
4. **默认级别可被 module 覆盖**
5. **通用原则在所有检查中持续关注，不另编号**
6. **跨 module 去重**：同一 file:line 被多个 module 标记时，保留主归属 module 的严重度
