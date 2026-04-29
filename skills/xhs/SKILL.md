---
name: xhs
description: 小红书内容分析器 - 解析小红书/xiaohongshu（含 xhslink.com 短链）笔记，支持视频和图文
triggers: xiaohongshu.com, xhslink.com
license: MIT
allowed-tools: Bash Read Write
---

# 小红书内容分析器

解析小红书笔记。视频走 video_process / audio_process（与 bili 对称），图文走 web_fetch 提正文。

## 处理流程

### 1. 短链解析（仅 xhslink.com）
小红书短链 302 重定向到长链，必须带 Chrome UA 否则被反爬：

```bash
curl -Ls -o /dev/null -w '%{url_effective}' \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  "<短链>"
```

QQ 卡片转过来的已经是带 xsec_token 的长链，直接跳过这步。

### 2. 抓元信息判类型
yt-dlp 原生支持小红书（含 xsec_token 长链），用元信息判视频还是图文：

```bash
yt-dlp --print title --print duration --print uploader --no-download --no-playlist "<长链>"
```

- 命令成功有 `duration` 输出 → **视频笔记**
- 命令报错 `Unsupported URL` 或没 duration → **图文笔记**（fallback 到 web_fetch）

### 3. 视频笔记（走 video_process / audio_process）
和 bili skill 同一套规则：

- **时长 ≤15 分钟** → 直接调 `video_process(video_url="<长链>")`，工具内部用 yt-dlp 下载 + ffmpeg merge + MiMo 多模态理解
- **时长 >15 分钟** → 用 exec 下载音频，再调 audio_process：
  ```bash
  yt-dlp -f "worstaudio" -x --audio-format mp3 -o ~/workspace/_xhs_audio.mp3 --no-playlist "<长链>"
  ```
  然后 `audio_process(audio_path="~/workspace/_xhs_audio.mp3")`。
  audio_process 的 prompt 别提「视频/画面」，统一说「音频/内容」。

### 4. 图文笔记（走 web_fetch）
yt-dlp 不支持的 URL（图文笔记没视频流）→ 直接 `web_fetch(url=<长链>)` 拿纯文本正文返给用户。`web_fetch` 已内置 Chrome UA + Accept-Language，绕过基础反爬。

## 注意

- **入口统一**：xhs skill 是小红书唯一入口；内部分发到 video_process / audio_process / web_fetch，与 bili skill 流程对齐
- **不要自己抓 HTML 正则提视频直链** — yt-dlp 已经做完了这事，再做一遍是冗余且容易出错（shell 引号地狱）
- 处理完清理音频临时文件：`rm -f ~/workspace/_xhs_audio*`
- 工具报错时直接告知用户原因，别反复重试
- 如果 yt-dlp 报「Unsupported URL」→ 大概率是图文笔记，回落到 web_fetch
- 如果 web_fetch 报 403/461 → UA 被识破或笔记设私密，告知用户

## 输出格式

```
📱 笔记信息
标题: xxx
作者: xxx
类型: 视频笔记 / 图文笔记

📝 内容总结
[根据笔记内容生成的详细总结]
```
