# web_search · skill

全网搜索 skill。双引擎并发（Bing + 百度），自包含，直接 httpx GET 搜索页面 + BeautifulSoup 解析，不依赖任何外部 daemon 或服务。

## 装机

```bash
pip install -r requirements.txt
```

依赖：`httpx` / `beautifulsoup4` / `lxml`。

## 手动跑

```bash
# 默认双引擎并发，取前 10 条合并去重
python3 skills/web_search/search.py "Claude 4.7 新特性" --limit 10

# 指定引擎
python3 skills/web_search/search.py "大模型" --engine bing --limit 5
python3 skills/web_search/search.py "小米 SU7" --engine baidu --limit 5

# 抓取单 URL 的正文
python3 skills/web_search/search.py --fetch "https://example.com/article"
```

输出：JSON 数组到 stdout，字段 `title / url / description / engine`。

## 退出码

- `0` 成功（JSON 数组可能为空）
- `2` 参数错误
- `3` 所有引擎都失败（stderr 有错误详情）

## 调试开关

```bash
WEBSEARCH_DEBUG=1 python3 skills/web_search/search.py "..."
```

打印每个引擎的 HTTP 状态、匹配到的结果条数、解析用时。

## 代理（可选）

两个引擎都走 `httpx`，尊重标准环境变量：

```bash
HTTPS_PROXY=http://127.0.0.1:7890 python3 skills/web_search/search.py "..."
```

## 反爬处理

- 默认带浏览器级 UA + `Accept` / `Accept-Language` 头
- 单引擎失败（超时 / 非 200 / captcha 关键词命中）会记 stderr 但不抛；另一个引擎仍能返回
- 如果**两个引擎都挂**（通常是本机 IP 被限流），稍等或切代理

## 不做

- 不做 playwright fallback（太重，skill 场景用不到）
- 不做结果摘要（摘要交给 LLM 在 skill 层面做）
- 不做本地缓存（paimon 的审计/token 统计自然覆盖成本）
