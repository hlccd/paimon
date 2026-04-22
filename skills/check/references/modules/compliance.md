# Module: compliance（合规性）

## 核心问题

合不合规？——是否符合规范和标准。

## 适用输入模式

| 输入模式 | 激活检查项 |
|---------|-----------|
| code | SKL-001 ~ SKL-018（条件）, CPL-002 ~ CPL-004 |
| docs | CPL-001, CPL-005 |
| code-vs-docs | 全部 |

---

## 检查项

### Skill 合规（SKL，18 项）——仅当源码含 SKILL.md 时自动启用

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| SKL-001 | frontmatter 必填字段齐全 | 检查 name + description | P0 |
| SKL-002 | name 与目录名一致 | 比对 name vs 父目录名 | P0 |
| SKL-003 | name 格式合规 | 小写+连字符，无 `--`，1-64 字符 | P0 |
| SKL-004 | description ≤1024 字符且非空 | 字符数统计 | P1 |
| SKL-005 | allowed-tools 格式正确 | 空格分隔字符串 | P1 |
| SKL-006 | allowed-tools 声明与实际使用一致 | 双向比对 | P1 |
| SKL-007 | 引用的 references/ 文件存在 | Glob 逐个确认 | P0 |
| SKL-008 | 引用的 scripts/ 文件存在且可执行 | Glob + 权限 | P1 |
| SKL-009 | module 引用的 check-id 在 catalog 中存在 | Grep catalog | P1 |
| SKL-010 | catalog 中无死 ID | 逐 ID grep 所有 module | P2 |
| SKL-011 | template 占位符有填充来源 | 逐 `{xxx}` 匹配逻辑 | P2 |
| SKL-012 | 填充逻辑的占位符在 template 中存在 | 反向匹配 | P2 |
| SKL-013 | module 结构完备 | 检查核心问题/检查项/严重度/发现指令/验证指令 | P2 |
| SKL-014 | 流程分支闭合 | 每个条件有出口/终止 | P1 |
| SKL-015 | 输出格式明确 | 有 pipe-delimited 示例 | P1 |
| SKL-016 | 参数组合冲突有报错 | 检查非法组合处理 | P1 |
| SKL-017 | state.json 字段与逻辑自洽 | 比对模板 vs 读写代码 | P2 |
| SKL-018 | SKILL.md ≤500 行 | wc -l | P2 |

### 通用合规（CPL，7 项）

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| CPL-001 | 许可证兼容性 | 依赖的 license 与项目 license 冲突 | P1 |
| CPL-002 | 项目约定的代码规范未遵守 | .editorconfig/.eslintrc 等规则 vs 实际代码 | P2 |
| CPL-003 | commit message 不符项目约定格式 | git log 比对 | P3 |
| CPL-004 | API 版本控制规范不符 | 语义化版本不一致 | P2 |
| CPL-005 | 数据隐私合规 | GDPR/个人信息处理不符规范 | P0 |
| CPL-006 | API 破坏性变更无废弃通知 | 公开接口签名变更未标 @deprecated/迁移说明 | P1 |
| CPL-007 | 破坏性变更缺迁移指南 | 大版本升级无 MIGRATION.md 或 CHANGELOG 迁移段 | P1 |

**引用检查**：
- PRJ-010（LICENSE 一致——也是合规问题）

---

## 发现指令

### Skill 目录视角轮换

1. **结构一致性**：检查 frontmatter 字段、name 与目录名、引用文件存在
2. **引用闭环**：module 引用的 check-id 在 catalog 中存在、template 占位符有填充来源
3. **流程完备性**：条件分支闭合、输出格式明确、参数组合冲突有报错

### 通用合规视角

1. **许可证**：依赖链的 license 是否与项目 license 兼容
2. **规范遵守**：项目自定义的 linter/formatter 规则是否被实际遵守

---

## 验证指令

- Skill 检查必须 Glob/Grep 实际验证，不能凭描述推断
- 许可证兼容性需要确认依赖树，不只是直接依赖

---

## 报告侧重

- Skill 合规问题按结构/引用/流程分组
- 许可证问题附依赖链路
