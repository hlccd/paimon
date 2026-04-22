# Module: project-health（项目健康）

## 核心问题

项目基础设施能不能跑？——项目元数据和工程配置的健康度。

## 适用输入模式

| 输入模式 | 激活检查项 |
|---------|-----------|
| code | PRJ-001 ~ PRJ-016 |
| docs | 不适用 |
| code-vs-docs | PRJ-001 ~ PRJ-016（项目侧） |

> SKL-* Skill 合规检查已移至 compliance module。

---

## 检查项

**主检查（PRJ，16 项）**：

| ID | 检查项 | 验证方法 | 默认级别 |
|----|--------|---------|---------|
| PRJ-001 | README 功能描述与代码一致 | Read README + Grep 关键功能 | P1 |
| PRJ-002 | README 安装/运行命令可执行 | 检查依赖存在 + 入口文件存在 | P0 |
| PRJ-003 | 配置示例键名与代码读取一致 | Grep config 键名 vs getenv/get | P0 |
| PRJ-004 | 配置示例默认值与代码 fallback 一致 | 比对示例值 vs 代码默认 | P1 |
| PRJ-005 | 依赖声明与实际 import 一致 | 比对 requirements vs import | P1 |
| PRJ-006 | 入口文件存在且可定位 | Glob main.py/__main__.py 等 | P0 |
| PRJ-007 | 版本号多处声明一致 | Grep version 关键字 | P1 |
| PRJ-008 | .env.example 与 getenv 调用一致 | 比对声明 vs 代码读取 | P1 |
| PRJ-009 | CI 配置引用的脚本/路径存在 | Glob 确认 | P1 |
| PRJ-010 | LICENSE 文件与项目声明一致 | 比对 pyproject.toml / package.json | P2 |
| PRJ-011 | 测试文件非空壳 | Read 检查有实质内容 | P2 |
| PRJ-012 | DB migration 编号连续无冲突 | 列出 migration 文件排序检查 | P1 |
| PRJ-013 | Dockerfile 引用路径/端口与配置一致 | 比对 EXPOSE/COPY vs 实际 | P1 |
| PRJ-014 | 项目内部 import 无循环依赖 | 构建导入图检查环 | P2 |
| PRJ-015 | git 中无敏感文件 | Glob .env/credentials/*.pyc 等 | P0 |
| PRJ-016 | 构建锁文件与依赖声明同步 | lockfile 存在且与 requirements/package.json 一致 | P1 |

---

## 发现指令

### 视角轮换

1. **元数据一致性**：Read README.md，提取功能声明、安装命令、运行命令，Grep 代码验证对应实现
2. **配置 & 依赖**：找配置示例文件，逐键名 Grep 代码读取点；比对 requirements vs import
3. **工程基础设施**：CI 引用的脚本、Dockerfile 路径、测试文件内容、敏感文件

### 专有关注点

1. 多语言项目：同时有 requirements.txt 和 package.json 时分别检查
2. monorepo：子项目有独立 README 时各自独立检查
3. 无 CI 的项目：PRJ-009 标为 N/A
4. 无 Dockerfile 的项目：PRJ-013 标为 N/A

---

## 验证指令

- 必须实际 Grep/Glob 验证——不能只凭 README 描述推断
- import 一致性要考虑动态导入——importlib / __import__ / 条件导入不算遗漏
- 配置示例中注释键名算可选，不检查

---

## 报告侧重

- 每个 finding 用一句话说明"期望 vs 实际"
- 建议修复方案用 diff 或代码片段
