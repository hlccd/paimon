name = "video_process"
description = (
    "视频内容处理工具。输入视频 URL（支持B站/YouTube等 yt-dlp 支持的平台）或本地视频文件路径，"
    "使用 MiMo-V2-Omni 多模态模型对视频内容进行理解，"
    "例如总结视频内容、描述画面细节、提取关键数据等。"
    "模型可同时理解画面和音频，适合有画面信息需要理解的视频。"
    "纯音频/超长内容请用 audio_process。"
)

parameters = {
    "type": "object",
    "properties": {
        "video_url": {
            "type": "string",
            "description": "视频的 URL（支持B站/YouTube等 yt-dlp 支持的平台），或本地视频文件的绝对路径。"
        },
        "prompt": {
            "type": "string",
            "description": "对视频处理的具体要求，例如'用中文总结这段视频的全部内容'、'提取视频中的关键数据'等。不填则默认生成中文摘要。",
            "default": ""
        },
    },
    "required": ["video_url"],
}

DEPS = ["httpx"]

MAX_VIDEO_SECONDS = 900
MAX_VIDEO_FILE_MB = 100

YTDLP_FORMAT = "worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst"


async def _run_cmd_async(cmd: list, timeout: int = 120) -> tuple:
    """异步执行子进程，不阻塞事件循环；超时/取消时 kill 防止孤儿进程。"""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        # 清理子进程，避免 orphan
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        raise
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="replace") if stdout else "",
        stderr.decode("utf-8", errors="replace") if stderr else "",
    )


async def _download_video(url: str) -> str:
    import os, glob
    import subprocess  # 仅用于异常类型

    out_path = os.path.join(os.path.expanduser("~/workspace"), "_video_tmp.mp4")
    cmd = [
        "yt-dlp", "-f", YTDLP_FORMAT,
        "--merge-output-format", "mp4",
        "-o", out_path, "--no-playlist", url,
    ]
    try:
        rc, _, stderr = await _run_cmd_async(cmd, timeout=120)
    except Exception as e:
        raise RuntimeError(f"yt-dlp 下载失败: {e}") from e
    if rc != 0:
        raise RuntimeError(f"yt-dlp 下载失败: {stderr[-500:]}")

    if not os.path.exists(out_path):
        matches = sorted(glob.glob(out_path + "*"))
        if matches:
            out_path = matches[0]
        else:
            raise RuntimeError("下载完成但找不到输出文件")
    return out_path


async def _get_duration(path: str) -> float:
    import json as _json
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
    try:
        rc, stdout, _ = await _run_cmd_async(cmd, timeout=10)
    except Exception:
        return 0
    if rc != 0:
        return 0
    try:
        info = _json.loads(stdout)
    except Exception:
        return 0
    return float(info.get("format", {}).get("duration", 0))


async def _record_to_primogem(component: str, model_name: str, pt: int, ct: int, cost: float) -> None:
    try:
        from paimon.state import state
        if state.primogem:
            await state.primogem.record(
                session_id="", component=component, model_name=model_name,
                input_tokens=pt, output_tokens=ct,
                cost_usd=cost, purpose="音视频分析",
            )
    except Exception:
        pass


async def execute(video_url: str, prompt: str = "", **kwargs) -> str:
    import base64, json, httpx, os

    from paimon.config import config
    mimo_key = config.mimo_key
    if not mimo_key:
        return "❌ MIMO_KEY 未配置，请在 .env 中设置"

    api_url = "https://api.xiaomimimo.com/v1/chat/completions"
    model = "mimo-v2-omni"

    is_remote = video_url.startswith("http://") or video_url.startswith("https://")
    local_file = None

    try:
        if is_remote:
            local_file = await _download_video(video_url)
        else:
            local_file = video_url

        if not os.path.isfile(local_file):
            return f"❌ 文件不存在: {local_file}"

        file_size = os.path.getsize(local_file)
        if file_size > MAX_VIDEO_FILE_MB * 1024 * 1024:
            return f"❌ 视频文件过大 ({file_size / 1024 / 1024:.1f}MB)，超过 {MAX_VIDEO_FILE_MB}MB 上限。请改用 audio_process。"

        duration = await _get_duration(local_file)
        if duration > MAX_VIDEO_SECONDS:
            return (
                f"❌ 视频时长 {duration:.0f}s 超过 {MAX_VIDEO_SECONDS}s 上限。"
                f"请改用 audio_process，或用 ffmpeg 分段后多次调用。"
            )

        # 大文件读 + base64 放到 executor，避免阻塞事件循环（百兆视频约 1~3s CPU）
        import asyncio
        def _read_and_encode(path: str) -> str:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        loop = asyncio.get_running_loop()
        b64 = await loop.run_in_executor(None, _read_and_encode, local_file)
        data_url = f"data:video/mp4;base64,{b64}"

        user_prompt = (
            prompt.strip()
            if prompt.strip()
            else "请用中文对这段视频进行详细总结，包括：\n1. 视频主题和背景\n2. 核心观点和论据\n3. 关键数据、测试结果或案例\n4. 最终结论和建议\n请尽可能详细和全面。"
        )

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "video_url", "video_url": {"url": data_url}},
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
            "max_completion_tokens": 8192,
        }

        headers = {
            "Authorization": f"Bearer {mimo_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(api_url, json=payload, headers=headers)
                resp.raise_for_status()
                result = resp.json()
        except httpx.HTTPStatusError as e:
            return f"❌ API 请求失败 ({e.response.status_code}): {e.response.text[:500]}"
        except httpx.RequestError as e:
            return f"❌ 网络请求异常: {e}"

        try:
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            pt = usage.get("prompt_tokens", 0)
            ct = usage.get("completion_tokens", 0)
            cost = (pt / 1_000_000 * 0.40) + (ct / 1_000_000 * 2.00)

            await _record_to_primogem("video_process", model, pt, ct, cost)

            info = (
                f"\n\n---\n"
                f"📊 Token: 输入 {pt:,} / 输出 {ct:,}\n"
                f"💰 成本: ${cost:.4f}"
            )
            if duration > 0:
                info += f"\n⏱️ 视频时长: {duration:.0f}s"
            return content + info
        except (KeyError, IndexError) as e:
            return f"❌ 解析 API 响应失败: {e}\n原始响应: {json.dumps(result, ensure_ascii=False)[:1000]}"

    finally:
        if is_remote and local_file and os.path.exists(local_file):
            os.remove(local_file)
