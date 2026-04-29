---
name: xhs
description: 小红书内容分析器 - 解析小红书/xiaohongshu（含 xhslink.com 短链）笔记，支持视频和图文
triggers: xiaohongshu.com, xhslink.com
license: MIT
allowed-tools: Bash Read Write
---

# 小红书内容分析器

解析小红书笔记，自动识别视频/图文，分别走 audio_process / 文本提取。

## 处理流程

### 1. 短链解析（xhslink.com）
小红书短链通过 302 重定向到长链。用 curl 抓 Location 头（必须带 Chrome UA，默认 curl UA 会被拦）：

```bash
curl -s -I -L -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "<短链>" | grep -i "^location:" | tail -1
```

或更简单的 `curl -Ls -o /dev/null -w '%{url_effective}' -A "Mozilla/5.0 ... Chrome/120..." "<短链>"`。

### 2. 抓页面（用 web_fetch，不要用裸 curl）
`web_fetch` 已内置真实 Chrome UA + Accept-Language，绕过基础反爬：

```
web_fetch(url="<长链>", raw=true)
```

`raw=true` 返回原始 HTML，方便正则提视频直链。要纯文本就 `raw=false`（默认）。

### 3. 判断笔记类型
- URL 含 `type=video` → 视频笔记
- URL 含 `type=normal` → 图文笔记
- 都没有 → 看 HTML 里有没有 `https://sns-video-*.xhscdn.com/...`

### 4. 视频笔记 → audio_process
正则提视频直链：

```
https://sns-video-[a-z0-9-]+\.xhscdn\.com/[^\s"'<>]+
```

下载音频（必须带 UA，否则被拦）：

```bash
yt-dlp -x --audio-format mp3 --audio-quality 5 \
  --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -o ~/workspace/_xhs_audio.mp3 "<视频直链>"
```

然后调用 `audio_process(audio_path="~/workspace/_xhs_audio.mp3", prompt="...")`。

**注意**：audio_process 的 prompt 别提「视频/画面」，统一说「音频/内容」，避免模型困惑。

### 5. 图文笔记 → 文本提取
直接把 `web_fetch(url, raw=false)` 的纯文本返给用户。如果用户有自定义 prompt，再调一次 `web_fetch` 让大模型按要求总结。

## 注意

- **反爬关键**：所有出站请求都要带真实 Chrome UA。`web_fetch` 已经内置；裸 curl 必须显式 `-A`；yt-dlp 必须 `--user-agent`
- 短链有时效，过期就报错让用户重新分享
- 视频直链 CDN 不需要登录就能下，但 UA 检查严格
- 处理完清理：`rm -f ~/workspace/_xhs_audio*`
- 如果 web_fetch 返 `HTTP 错误 403/461` → 多半是 UA 被识破或笔记设私密，直接告知用户
- 图文笔记的图片 OCR 暂不支持，仅提文本

## 输出格式

```
📱 笔记信息
标题: xxx
作者: xxx
类型: 视频笔记 / 图文笔记

📝 内容总结
[根据笔记内容生成的详细总结]
```
