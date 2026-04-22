# 地脉

> 隶属：[神圣规划](../aimon.md) / 基础层

**定位**：提瓦特地脉为原型的全局事件总线。

## 核心能力

- **事件总线**：所有模块间的事件交互、任务流转都走地脉
- **消息有序性**：同一 Queue 顺序消费，保证事件不乱序
- **异常日志广播**：以事件形式出地脉，由**独立日志设施**落盘（不入世界树，不归任何神）
- **handler 异常隔离**：单个订阅者异常不影响其他订阅者，异常自动广播到 `error.log` topic

## 技术选型

当前：基于 `asyncio.Queue` 的进程内发布/订阅。未来如需跨进程可替换为 Redis Stream，接口不变。

## 实现

### 数据模型

```python
@dataclass
class Event:
    topic: str          # 事件主题
    payload: dict       # 事件数据
    source: str         # 发布者标识（如 "三月", "死执"）
    timestamp: float    # 发布时间戳
```

### API

| 方法 | 说明 |
|------|------|
| `subscribe(topic, handler)` | 注册订阅，handler 为 `async def handler(event)` |
| `unsubscribe(topic, handler)` | 取消订阅 |
| `publish(topic, payload, source)` | 发布事件，非阻塞入队 |
| `start()` | 启动分发循环（在 `asyncio.gather` 中运行） |
| `stop()` | 停止分发循环 |

### 分发机制

1. `publish()` 将 Event 放入 `asyncio.Queue`（非阻塞）
2. `start()` 持续从 Queue 取事件，按 topic 找到所有已注册 handler
3. 逐个 `await handler(event)`，单个 handler 异常被捕获并广播到 `error.log`
4. 不影响同一事件的其他 handler 或后续事件的处理

## 预定义 Topic

命名约定，不强制。任何模块可发布/订阅任意 topic。

| Topic | 发布者 | 订阅者 | 用途 |
|-------|--------|--------|------|
| `march.ring` | 三月 | 派蒙 | 推送响铃 → 派蒙投递给用户 |
| `march.task_due` | 三月 | 三月内部 | 定时任务到期触发 |
| `shade.authz_update` | 四影 | 派蒙 | 权限变更通知 → 派蒙更新本地缓存 |
| `skill.loaded` | 冰神 | 派蒙 | 新 skill 上线 → 派蒙刷新注册表 |
| `error.log` | 任意模块 | 日志设施 | 异常广播（handler 异常自动触发） |

## 生命周期

- **启动**：`bootstrap.py` 中创建 `Leyline` 实例 → `main.py` 中 `asyncio.gather` 启动分发循环
- **运行**：各模块通过 `state.leyline.subscribe()` 和 `state.leyline.publish()` 交互
- **停止**：`main.py` finally 中 `leyline.stop()`

## 明确不做

- 不做事件持久化（事件是瞬时的）
- 不做事件重放
- 不做跨进程通信（当前单进程，未来需要时换 Redis Stream）
- 不做消息过滤/路由（订阅者自行判断是否处理）

## 代码位置

`paimon/foundation/leyline.py`
