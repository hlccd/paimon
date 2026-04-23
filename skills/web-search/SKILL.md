---
name: web-search
description: 全网搜索（Bing + 百度双引擎并发，自包含无 daemon 依赖）。用户要"搜一下 / 查最新 / 帮我搜"时触发。
triggers: 搜索, 搜一下, 帮我搜, 查一下, 查最新, 找一下, search, web search
license: MIT
allowed-tools: Bash
---

# web-search: 全网搜索

基于 Bing + 百度的双引擎并发搜索。脚本在本 skill 目录下自包含，不依赖任何外部 daemon。

## 使用方式

本 skill 的主入口是目录内的 `search.py`。下面的示例按 agent harness 常见约定，假设它放在
`skills/web-search/` 下；若放在别处，请相应替换路径。

### 默认搜索（两个引擎并发，按相关度合并去重）

```bash
python3 skills/web-search/search.py "Claude 4.7 新特性" --limit 10
```

### 指定单引擎

```bash
python3 skills/web-search/search.py "小米 SU7 Ultra" --engine baidu --limit 5
python3 skills/web-search/search.py "open source LLM" --engine bing --limit 5
```

### 多引擎显式指定

```bash
python3 skills/web-search/search.py "大模型进展" --engines bing,baidu --limit 10
```

**输出**：JSON 数组到 stdout，字段：`title` / `url` / `description` / `engine`。

## 引擎选择建议

- **中文问题 / 国内信息**：优先 `baidu` 或双引擎并发
- **英文问题 / 技术 / 开源**：优先 `bing`
- **都不确定**：不指定 `--engine`，脚本默认双引擎并发

## 典型流程

1. 用户提一个需要查最新信息的问题
2. 调 `Bash` 跑上述命令，拿到 JSON
3. **只保留前 5-10 条**摘要呈现给用户（防 token 膨胀），格式如：
   - `[engine] 标题` 一行
   - `URL` 一行
   - 一句话描述
4. 如果用户追问某条的具体内容，**再**调抓取：
   ```bash
   python3 skills/web-search/search.py --fetch "<那条 url>"
   ```

## 注意事项

- **依赖未装**：脚本报 `ModuleNotFoundError` 时，**不要反复重试**，直接告知用户：
  ```
  cd skills/web-search && pip install -r requirements.txt
  ```
- **某引擎失败**：脚本会吞异常，另一个引擎仍能返回结果；日志里会说明哪个炸了
- **两引擎都挂**：退出码为 3。可能触发反爬，等一会再重试或切代理；不要反复同一个 query 多次触发
- **不要自己构造 curl 去调百度/Bing**，用脚本（脚本处理了 UA 伪装、编码、去重、URL 规范化）
- **不要**直接用 `Bash` 调 curl 访问搜索页 —— 百度会返回 302 + 机器人验证页
- **结果中的 URL 可能是跳转链接**（尤其百度是 `www.baidu.com/link?url=...`），直接把原始 URL
  返回给用户即可，浏览器会自动 302；不要自己再去跑 curl 展开

## 退出码约定

- `0` 正常结束（包括"所有引擎都成功但恰好没命中任何结果"）
- `2` 参数错误
- `3` 所有引擎都失败（通常是反爬或网络问题）

## 典型失败处理

- Bing 失败且 stderr 有 "captcha/verify" → 已触发反爬，告知用户"当前 Bing 限流，稍后再试或只用百度"
- 百度失败 → 参数可能过期（百度的 `rsv_*` 参数偶尔更新），告知用户"百度搜索暂时失败，用 --engine bing"

## 输出约束

默认只输出 JSON，别的都不输出。JSON 数组可能为空但格式保持合法。
