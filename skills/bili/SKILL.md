---
name: bili
description: B站视频分析器 - 分析 B站/bilibili（含 b23.tv 短链）视频内容，自动选择画面理解或纯音频方式生成总结
triggers: bilibili.com, b23.tv, BV号
license: MIT
allowed-tools: Bash Read Write
---

# B站视频分析器

分析B站视频内容，支持智能分流处理。

## 处理流程

### 1. 规范化 URL
- 完整 URL 直接用
- 单独 BV 号 → `https://www.bilibili.com/video/<BV号>`
- b23.tv 短链先解析：`curl -Ls -o /dev/null -w '%{url_effective}' "<短链>"`

### 2. 抓元信息（决定分流）
用 yt-dlp 拉 title/duration/uploader：
```bash
yt-dlp --print title --print duration --print channel --no-download --no-playlist "<URL>"
```
失败再 fallback 到 bilibili API：
```bash
curl -s "https://api.bilibili.com/x/web-interface/view?bvid=<BV号>" -H "User-Agent: Mozilla/5.0"
```

### 3. 分流决策（参考 fairy handler 的规则）

**用 `video_process`（画面+音频多模态）：**
- 时长 ≤15 分钟，且画面有信息（评测/跑分/演示/教程/操作/PPT/图表/游戏/实拍/VLOG/开箱/对比/展示）
- 时长 ≤3 分钟的短视频默认走视频
- 一般中等视频默认走视频

**用 `audio_process`（纯音频）：**
- 时长 >15 分钟（超 video_process 上限）
- 标题/描述含「播客/对话/访谈/电台」等纯口播关键词
- 分区为「音乐」且为 MV/电台

### 4. 调用工具

**video_process**：直接传 URL，工具内部自动 yt-dlp 下载 + ffmpeg merge：
```
video_process(video_url="<URL>", prompt="<可选自定义>")
```

**audio_process**：先用 exec 工具下载 m4a（B 站音频流体积小），再传文件路径：
```bash
yt-dlp -f "worstaudio[ext=m4a]/worstaudio" -o ~/workspace/_bili_audio.m4a --no-playlist "<URL>"
```
然后调用 `audio_process(audio_path="~/workspace/_bili_audio.m4a")`（绝对路径，~ 会自动展开为用户目录）。

## 注意

- `video_process` 已内置 yt-dlp + ffmpeg merge 逻辑，不要手动下载后再传路径
- 工具内置时长闸门（>15分钟自动报错），优先看元信息别浪费下载流量
- ffmpeg 由 `imageio-ffmpeg` pip 包提供，`pip install -e .` 装好即可，无需系统装
- 处理完成后清理音频临时文件：`rm -f ~/workspace/_bili_audio*`
- 如果工具返错，直接告诉用户失败原因；不要自己用 yt-dlp 反复重试
