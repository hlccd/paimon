# 红利股评分系统

## 目录结构

```
scorers/
├── __init__.py          # 模块导出
├── base.py              # 行业分类和基础工具
├── universal.py         # 通用评分逻辑（基准版本）
└── README.md            # 本文档
```

## 设计理念

### 分层架构

1. **基础层 (base.py)**: 行业分类、市值要求等通用工具
2. **通用层 (universal.py)**: 适用于所有股票的基准评分逻辑
3. **差异化层 (未来扩展)**: 针对特定行业的优化评分逻辑

### 评分体系 (100分)

| 维度 | 分值 | 说明 |
|------|------|------|
| 股息维度 | 35分 | 当前股息率(22分) + 分红稳定性(13分) |
| 估值维度 | 25分 | 根据行业特征差异化评估 (PB/PE/PEG/PE_ROE/PB_DEBT) |
| 质量维度 | 20分 | 市值规模(10分) + 分红状态(5分) + 分红率(5分) |
| 财务维度 | 10分 | ROE(5分) + 利润增长(3分) + 负债率(2分) **[通用标准]** |
| 成长维度 | 10分 | 分红持续性(6分) + 股息率趋势(4分) |

## 使用方法

### 基本使用

```python
from scorers import classify_stock, UniversalScorer

# 1. 行业分类
classification = classify_stock(stock_name="中国平安", industry="保险")
# 返回：{'industry', 'is_cyclical', 'is_defensive', 'valuation_metric', 'valuation_standard'}

# 2. 评分
stock_data = {
    'code': '601318',
    'name': '中国平安',
    'industry': '保险',
    'dividend_yield': 0.055,
    'payout_ratio': 0.35,
    'history_count': 15,
    'status': '已实施',
    'recent_dividend_count': 2,  # 近12月分红次数
    'pe': 8.5,
    'pb': 0.85,
    'market_cap': 150_000_000_000,
    'price': 42.50,
}

financial_data = {
    'roe': 14.2,                # 净资产收益率 (%)
    'profit_growth': 8.5,       # 净利润增长率 (%)
    'debt_ratio': 45.0,         # 资产负债率 (%)
    'revenue_growth': 7.2,      # 营业收入增长率 (%)
    'report_period': '2025-09-30',
}

# 3. 计算得分
score = UniversalScorer.score_stock(stock_data, classification, financial_data)
# 返回：{'dividend': 32, 'valuation': 19, 'quality': 15, 'financial': 8.5, 'growth': 6}

# 4. 生成评分理由
reasons = UniversalScorer.build_reasons(stock_data, score, classification, financial_data)
# 返回：['[股息 32/35] 高年化股息率 5.5%（近12月2次）...', ...]
```

### 批量评分流程

参考 `tools/fast_scanner.py` 中的完整实现：

1. 获取行情数据（市值、PE、PB等）
2. 并发获取分红数据（股息率、历史分红次数）
3. 并发获取财务数据（ROE、利润增长、负债率）
4. 行业分类 + 评分计算
5. 排序输出报告

## 财务维度评分标准

### ROE (净资产收益率) - 5分

| ROE范围 | 评级 | 得分 | 说明 |
|---------|------|------|------|
| ≥ 15% | 优秀 | 5 | 盈利能力强，股东回报高 |
| 12-15% | 良好 | 4 | 盈利能力较好 |
| 10-12% | 中等 | 3 | 盈利能力一般 |
| 8-10% | 一般 | 2 | 盈利能力偏低 |
| < 8% | 偏低 | 1 | 盈利能力弱 |

### 利润增长率 - 3分

| 增长率范围 | 评级 | 得分 |
|-----------|------|------|
| ≥ 15% | 高增长 | 3 |
| 10-15% | 良好增长 | 2.5 |
| 5-10% | 稳定增长 | 2 |
| 0-5% | 微增长 | 1 |
| < 0% | 负增长 | 0 (不扣分) |

**注**: 周期股负增长常见，不扣分避免误杀

### 负债率 (资产负债率) - 2分

| 负债率范围 | 评级 | 得分 | 风险 |
|-----------|------|------|------|
| < 50% | 低杠杆 | 2 | 财务安全 |
| 50-65% | 中等杠杆 | 1.5 | 风险可控 |
| 65-80% | 较高杠杆 | 1 | 需关注 |
| ≥ 80% | 高杠杆 | 0 | 风险较大 |

## 行业差异化估值

### 估值指标映射

| 行业类型 | 估值指标 | 原因 |
|---------|---------|------|
| 银行 | PB (市净率) | 资产驱动型，账面价值重要 |
| 电力、公用事业 | PE (市盈率) | 现金流稳定，盈利可预测 |
| 消费、医药 | PEG (PE/增长率) | 成长性重要，高PE需增长支撑 |
| 制造业 | PE + ROE | 关注盈利能力和效率 |
| 房地产、周期股 | PB + 负债率 | 破净机会 + 债务风险 |

### 估值评分逻辑

详见 `universal.py` 中的 `score_stock()` 方法，针对不同 `valuation_metric` 有差异化的评分标准。

## 未来扩展

### 行业差异化评分 (计划中)

在充分验证通用基准版本后，可针对特定行业优化财务维度评分标准：

#### 银行业
- 财务维度调整为：ROE(5分) + 不良率(3分) + 资本充足率(2分)
- ROE标准提高：≥18%为优秀（行业平均较高）
- 负债率标准调整：银行负债率天然高，不适用通用标准

#### 电力/公用事业
- 财务维度调整为：ROE(4分) + 现金流(3分) + 负债率(3分)
- 强调现金流稳定性，弱化增长要求

#### 周期股
- 财务维度调整为：ROE(3分) + 周期位置(4分) + 负债率(3分)
- 增加周期位置判断（PB历史分位、行业景气度）

### 扩展步骤

1. 在 `scorers/` 下创建 `industry_specific.py`
2. 定义 `BankScorer`, `UtilityScorer` 等专业评分器
3. 修改 `fast_scanner.py` 根据行业类型选择评分器：
   ```python
   if classification['industry'] == '银行':
       scorer = BankScorer()
   else:
       scorer = UniversalScorer()
   
   score = scorer.score_stock(stock_data, classification, financial_data)
   ```

## 数据来源

- **分红数据**: AkShare `stock_fhps_detail_em()`
- **财务数据**: AkShare `stock_financial_abstract()`
- **行情数据**: AkShare `stock_zh_a_spot_em()`

## 注意事项

1. **缓存机制**: 分红和财务数据变化慢，使用24小时缓存提升性能
2. **并发控制**: 并发度设为10，避免触发API限流
3. **数据质量**: 部分股票财务数据可能缺失，评分时需判空
4. **周期股特殊处理**: 周期股低估时机难判断，估值维度适当扣分提醒风险
5. **历史回测**: 新评分系统上线前，建议用历史数据回测验证有效性

## 维护者

- 初始版本: 2026-04-09
- 最后更新: 2026-04-09
