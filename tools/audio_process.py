name = "audio_process"
description = (
    "音频内容处理工具。输入音频文件路径（支持 mp3/wav/m4a/ogg/flac/opus 等常见格式），"
    "使用 Gemini 模型对音频内容进行处理，"
    "例如总结视频时可以提取音频并调用此工具。"
)

parameters = {
    "type": "object",
    "properties": {
        "audio_path": {
            "type": "string",
            "description": "音频文件的绝对路径，支持 mp3/wav/m4a/ogg/flac/opus 等格式"
        },
        "prompt": {
            "type": "string",
            "description": "对音频处理的具体要求，例如'用中文总结这段对话的要点'、'提取这段语音中的关键信息'等。不填则默认生成中文摘要。",
            "default": ""
        },
    },
    "required": ["audio_path"],
}

DEPS = ["httpx"]

MAX_AUDIO_MB = 20


async def _convert_to_wav(audio_path: str) -> str:
    """将音频转换为 16kHz 单声道 WAV（兼容性最佳），异步不阻塞事件循环。"""
    import asyncio

    wav_path = audio_path.rsplit(".", 1)[0] + "_converted.wav"
    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        wav_path
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        raise
    if proc.returncode != 0:
        import subprocess
        raise subprocess.CalledProcessError(
            proc.returncode, cmd,
            output=stdout, stderr=stderr,
        )
    return wav_path


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


async def execute(audio_path: str, prompt: str = "", **kwargs) -> str:
    import base64
    import json
    import httpx
    import subprocess
    import os

    from paimon.config import config
    mimo_key = config.mimo_key
    if not mimo_key:
        return "❌ MIMO_KEY 未配置，请在 .env 中设置"

    api_url = "https://api.xiaomimimo.com/v1/chat/completions"
    model = "mimo-v2-omni"

    if not os.path.isfile(audio_path):
        return f"❌ 文件不存在: {audio_path}"

    file_size = os.path.getsize(audio_path)
    if file_size > MAX_AUDIO_MB * 1024 * 1024:
        return f"❌ 音频文件过大 ({file_size / 1024 / 1024:.1f} MB)，最大支持 {MAX_AUDIO_MB} MB"

    try:
        processed_path = await _convert_to_wav(audio_path)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, (bytes, bytearray)) else str(e.stderr)
        return f"❌ 音频转换失败，ffmpeg 错误: {err}"

    # 读文件 + base64 放 executor，百兆文件 CPU 密集会阻塞事件循环
    import asyncio
    def _read_and_encode(path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    loop = asyncio.get_running_loop()
    audio_data = await loop.run_in_executor(None, _read_and_encode, processed_path)

    try:
        if processed_path != audio_path:
            os.remove(processed_path)
    except OSError:
        pass

    user_prompt = (
        prompt.strip()
        if prompt.strip()
        else "用中文对这段音频内容进行详细总结，包括主要话题、关键要点和重要细节。如果是对话，请区分不同发言者。"
    )

    audio_data_url = f"data:audio/wav;base64,{audio_data}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_data_url
                        }
                    },
                    {
                        "type": "text",
                        "text": user_prompt,
                    }
                ],
            }
        ],
        "max_completion_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {mimo_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
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

        await _record_to_primogem("audio_process", model, pt, ct, cost)

        info = f"\n\n---\n📊 Token 用量: 输入 {pt:,} / 输出 {ct:,}\n💰 成本: ${cost:.4f}"
        return content + info
    except (KeyError, IndexError) as e:
        return f"❌ 解析 API 响应失败: {e}\n原始响应: {json.dumps(result, ensure_ascii=False)[:1000]}"
