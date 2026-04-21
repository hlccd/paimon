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


def _download_video(url: str) -> str:
    import subprocess, os, glob

    out_path = os.path.join(os.path.expanduser("~/workspace"), "_video_tmp.mp4")
    cmd = [
        "yt-dlp", "-f", YTDLP_FORMAT,
        "--merge-output-format", "mp4",
        "-o", out_path, "--no-playlist", url,
    ]
    rc, _, stderr = _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"yt-dlp 下载失败: {stderr[-500:]}")

    if not os.path.exists(out_path):
        matches = sorted(glob.glob(out_path + "*"))
        if matches:
            out_path = matches[0]
        else:
            raise RuntimeError("下载完成但找不到输出文件")
    return out_path


def _run_cmd(cmd: list, timeout: int = 120) -> tuple:
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def _get_duration(path: str) -> float:
    import subprocess, json as _json
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
    rc, stdout, _ = _run_cmd(cmd, timeout=10)
    if rc != 0:
        return 0
    info = _json.loads(stdout)
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
            local_file = _download_video(video_url)
        else:
            local_file = video_url

        if not os.path.isfile(local_file):
            return f"❌ 文件不存在: {local_file}"

        file_size = os.path.getsize(local_file)
        if file_size > MAX_VIDEO_FILE_MB * 1024 * 1024:
            return f"❌ 视频文件过大 ({file_size / 1024 / 1024:.1f}MB)，超过 {MAX_VIDEO_FILE_MB}MB 上限。请改用 audio_process。"

        duration = _get_duration(local_file)
        if duration > MAX_VIDEO_SECONDS:
            return (
                f"❌ 视频时长 {duration:.0f}s 超过 {MAX_VIDEO_SECONDS}s 上限。"
                f"请改用 audio_process，或用 ffmpeg 分段后多次调用。"
            )

        with open(local_file, "rb") as f:
            video_bytes = f.read()

        b64 = base64.b64encode(video_bytes).decode("utf-8")
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
