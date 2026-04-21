---
name: bili
description: B站视频分析器 - 分析 B站/bilibili（含 b23.tv 短链）视频内容，自动选择画面理解或纯音频方式生成总结
triggers: bilibili.com, b23.tv, BV号
license: MIT
allowed-tools: Bash Read Write
---

# B站视频分析器

分析B站视频内容，支持智能分流处理。

## 处理规则

**短视频（≤15分钟）**：直接调用 `video_process` 工具，传入视频 URL。工具内部会自动下载和处理，不需要手动下载。

**长视频（>15分钟）**：先用 exec 工具下载音频，再调用 `audio_process`：
```bash
yt-dlp -f "worstaudio" -x --audio-format mp3 -o ~/workspace/_bili_audio.mp3 --no-playlist "<视频URL>"
```
然后调用 `audio_process`，`audio_path` 填 `/home/mi/workspace/_bili_audio.mp3`。

## 判断视频时长

如果无法从 URL 判断时长，用 bilibili API 快速查询：
```bash
curl -s "https://api.bilibili.com/x/web-interface/view?bvid=<BV号>" -H "User-Agent: Mozilla/5.0" | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print(f'标题: {d[\"title\"]}, 时长: {d[\"duration\"]}秒, UP主: {d[\"owner\"][\"name\"]}')"
```

如果是 b23.tv 短链，先用 curl 解析 BV 号：`curl -Ls -o /dev/null -w '%{url_effective}' "<短链>"`

**如果不确定时长，直接调用 video_process 尝试即可**，工具会在超限时返回错误提示。

## 注意

- `video_process` 内部自动处理下载，不要手动用 yt-dlp 下载后再传路径
- **如果 video_process 或 audio_process 返回错误（如下载超时），直接告知用户失败原因，不要尝试手动下载视频**
- 处理完成后清理临时文件：`rm -f ~/workspace/_bili_audio*`
