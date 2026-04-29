# 待办

## QQ B站 miniapp 卡片无 URL（2026-04-30）

**现状**：QQ 官方协议下 B 站小程序卡片（`ark_type=miniapp`）只给 source/title/preview，**不给 jump_url**。preview 是 QQ ugcimg.cn 自家 CDN 缩略图，反推不出 BV 号。

**当前行为**：handler 给 LLM 喂结构化提示「无 URL，建议搜反查」。但实测搜反查不可靠：
- bing/baidu 裸 curl 反爬；B 站搜索 API 触发风控（要 cookie + wbi 签名）；yt-dlp `bilisearch:` 也被拦
- 即便能搜到，标题重名概率极高，会拿错视频
- LLM 走完一圈拿不到结果，浪费 4-5 次工具调用 + token

**对比小红书**：xhs 卡片 `ark_type=tuwen` 自带 `jump_url`，已闭环走通。

**待决策方向**：
1. **拍死搜反查**：handler 卡片提示去掉「搜索建议」+ 改写不污染 bili skill trigger（现在 `bilibili.com` 字符串会误命中），直接让派蒙回「QQ 卡片不带 URL，请粘 BV 号」。最干净。
2. **接 B 站搜索 API**：维护 cookie pool + wbi 签名生成。可行但维护重，且重名仍会捞错。
3. **接付费搜索 API**：SerpAPI/Bing API。稳定但要 key。

**临时缓解**：用户遇到 B 站卡片，直接复制视频 URL 重发即可（xhs 卡片不受影响）。
