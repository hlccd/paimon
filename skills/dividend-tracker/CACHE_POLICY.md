# 缓存策略文档

## 缓存配置

### 缓存有效期

不同数据类型使用不同的缓存有效期：

```python
CACHE_EXPIRE_HOURS = {
    'dividend': 30 * 24,   # 分红数据：30天（720小时）
    'financial': 30 * 24,  # 财务数据：30天（720小时）
    'price': 7 * 24,       # 股价数据：7天（168小时）
}
```

### 缓存目录

```
~/.fairy/skills/dividend-tracker/cache/
├── {code}.json                # 分红数据（30天）
├── {code}_financial.json      # 财务数据（30天）
└── {code}_price.json          # 股价数据（7天）
```

示例：
```
601398.json                    # 工商银行分红数据
601398_financial.json          # 工商银行财务数据
601398_price.json              # 工商银行股价数据
```

## 缓存机制说明

### 1. 分红数据缓存（30天）

**数据来源**：`ak.stock_fhps_detail_em()`  
**缓存内容**：
- 年化股息率（dividend_yield）
- 分红率（payout_ratio）
- 历史分红次数（history_count）
- 最近12个月分红次数（recent_dividend_count）
- 最新分红状态（status）

**为什么30天？**
- 分红计划通常年度或半年度发布
- 分红数据变化频率低
- 减少API调用压力

### 2. 财务数据缓存（30天）

**数据来源**：`ak.stock_financial_abstract()`  
**缓存内容**：
- ROE（净资产收益率）
- 利润增长率（profit_growth）
- 资产负债率（debt_ratio）
- 营业收入增长率（revenue_growth）
- 其他财务指标

**为什么30天？**
- 财务报告季度发布（3个月）
- 30天内财务指标变化不大
- 平衡数据新鲜度和API负载

### 3. 股价数据缓存（7天）

**数据来源**：`ak.stock_zh_a_spot_em()`  
**缓存内容**：
- 最新价（price）
- 市盈率PE（pe）
- 市净率PB（pb）
- 总市值（market_cap）
- 股票名称（name）
- 所属行业（industry）

**为什么7天？**
- 股价波动频繁，需要相对新鲜的数据
- 估值指标（PE/PB）短期内变化较大
- 7天是合理的新鲜度和缓存命中率平衡点

**获取策略**：
```
优先：尝试从云端获取全市场行情
失败：使用缓存的股价数据（7天有效期）
目的：提高容错性，交易时段API负载高时仍可工作
```

## 缓存过期逻辑

### 读取时检查

```python
cached_time = datetime.fromisoformat(cached['timestamp'])
expire_hours = CACHE_EXPIRE_HOURS.get(data_type, 24)

if datetime.now() - cached_time > timedelta(hours=expire_hours):
    return None  # 过期返回None，触发重新获取
```

### 自动更新

- 当读取缓存发现过期时，返回 `None`
- 触发API调用获取最新数据
- 获取成功后**覆盖**旧缓存文件

### 无自动清理

⚠️ **重要**：缓存文件不会自动删除！

- 过期缓存仍保留在磁盘
- 仅在读取时检查有效期
- 长期运行会积累过期缓存文件

**建议**：定期手动清理
```bash
# 删除30天未修改的缓存
find ~/.fairy/skills/dividend-tracker/cache/ -name "*.json" -mtime +30 -delete
```

## 缓存格式

### 统一JSON格式

```json
{
  "timestamp": "2026-04-10T12:33:47.168938",
  "data": {
    // 具体数据内容
  }
}
```

### 示例：分红数据

```json
{
  "timestamp": "2026-04-10T12:33:47.168938",
  "data": {
    "dividend_yield": 0.038290844098,
    "payout_ratio": 0.016890000000000002,
    "latest_year": "2025-12-31",
    "status": "董事会决议通过",
    "history_count": 22,
    "recent_dividend_count": 2
  }
}
```

### 示例：财务数据

```json
{
  "timestamp": "2026-04-10T12:33:47.842509",
  "data": {
    "roe": 9.45,
    "profit_growth": 0.737707,
    "debt_ratio": 92.011589,
    "revenue_growth": 2.003764,
    "report_period": "20251231"
  }
}
```

### 示例：股价数据

```json
{
  "timestamp": "2026-04-10T12:45:00.000000",
  "data": {
    "price": 5.12,
    "pe": 4.5,
    "pb": 0.52,
    "market_cap": 1950000000000,
    "name": "工商银行",
    "industry": "银行"
  }
}
```

## API调用优化

### 批量获取 + 缓存

当扫描多只股票时：

```python
# 1. 批量获取全市场行情
market_df = ak.stock_zh_a_spot_em()  # 一次API调用

# 2. 逐只保存到价格缓存（7天）
for _, row in market_df.iterrows():
    save_to_cache(code, price_data, data_type='price')

# 3. 批量获取分红数据（并发10线程）
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(fetch_dividend_info, code): code for code in codes}
```

### 缓存命中率提升策略

1. **首次运行**（晚上或周末）
   - API负载低，成功率高
   - 批量获取并缓存数据
   - 建立完整缓存基础

2. **日常查询**
   - 分红/财务数据命中缓存（30天）
   - 股价数据大概率命中（7天）
   - 仅在过期时才调用API

3. **容错降级**
   - 交易时段API失败时
   - 使用缓存数据继续工作
   - 提示用户数据时效性

## 最佳实践

### 推荐运行时间

✅ **最佳时段**：
- 晚上22:00 - 凌晨2:00
- 周末任意时间
- 原因：东方财富API负载低，成功率高

⚠️ **避免时段**：
- 交易时段 9:30 - 15:00
- 原因：API负载高，频繁超时/拒绝连接

### 缓存维护

```bash
# 查看缓存文件数量
ls ~/.fairy/skills/dividend-tracker/cache/*.json | wc -l

# 查看缓存总大小
du -sh ~/.fairy/skills/dividend-tracker/cache/

# 清理过期缓存（>30天未修改）
find ~/.fairy/skills/dividend-tracker/cache/ -name "*.json" -mtime +30 -delete

# 清空所有缓存（重新开始）
rm -rf ~/.fairy/skills/dividend-tracker/cache/
```

## 监控和调试

### 检查缓存状态

```python
import json
from pathlib import Path
from datetime import datetime

cache_file = Path.home() / ".fairy/skills/dividend-tracker/cache/601398.json"
with open(cache_file) as f:
    cached = json.load(f)

timestamp = datetime.fromisoformat(cached['timestamp'])
age_hours = (datetime.now() - timestamp).total_seconds() / 3600

print(f"缓存时间: {timestamp}")
print(f"缓存年龄: {age_hours:.1f} 小时")
print(f"是否过期: {'是' if age_hours > 720 else '否'}")  # 30天=720小时
```

### 缓存统计

```bash
# 统计各类型缓存文件数
echo "分红数据: $(ls ~/.fairy/skills/dividend-tracker/cache/*.json 2>/dev/null | grep -v '_' | wc -l)"
echo "财务数据: $(ls ~/.fairy/skills/dividend-tracker/cache/*_financial.json 2>/dev/null | wc -l)"
echo "股价数据: $(ls ~/.fairy/skills/dividend-tracker/cache/*_price.json 2>/dev/null | wc -l)"
```

## 更新日志

- **2026-04-10**: 初始版本
  - 分红数据：24小时 → 30天
  - 财务数据：24小时 → 30天
  - 股价数据：新增7天缓存机制
  - 实现"优先云端，失败用缓存"的获取策略
