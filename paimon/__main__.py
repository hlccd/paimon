import asyncio
import signal
import sys
import time

from paimon.bootstrap import create_app
from paimon.config import config
from paimon.log import setup_logging
from paimon.state import state

_MAX_RESTARTS = 5
_RESTART_WINDOW = 300
_RESTART_DELAY = 5


def _install_signal_handlers() -> None:
    """Windows 下让 CTRL_BREAK_EVENT / SIGTERM 也走 KeyboardInterrupt 路径。

    默认 Python 在 Windows 仅对 CTRL_C 抛 KeyboardInterrupt；
    SIGBREAK / SIGTERM 默认是直接终止进程，**finally 块不会执行**。
    Windows 服务管理器（NSSM / SCM）和子进程包装器通常发 SIGBREAK 来停服务，
    显式注册让 paimon 走完 shutdown_pending + cleanup 路径，避免数据残缺。
    """
    def _raise_kbd(sig, frame):
        raise KeyboardInterrupt()

    # SIGBREAK 仅 Windows 有；SIGTERM 跨平台
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _raise_kbd)
    try:
        signal.signal(signal.SIGTERM, _raise_kbd)
    except (ValueError, OSError):
        # 某些环境下（如已有 handler）会失败，忽略
        pass


async def main():
    setup_logging(debug=config.debug, log_dir=config.paimon_home)
    _install_signal_handlers()

    try:
        channels = await create_app(config)

        if not channels:
            raise RuntimeError(
                "未配置任何频道 (请检查 .env 中的 WEBUI_ENABLED / BOT_TOKEN / QQ_APPID)"
            )

        if state.gnosis:
            state.gnosis.setup_pools()

        tasks = [ch.start() for ch in channels]
        if state.leyline:
            tasks.append(state.leyline.start())
        if state.march:
            tasks.append(state.march.start())

        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        pass
    finally:
        # 先等所有 fire-and-forget 后台任务完成（最多 10s），避免 bg 写库时
        # irminsul.close 截断造成数据残缺。详见 paimon/foundation/bg.py。
        try:
            from paimon.foundation.bg import shutdown_pending
            await shutdown_pending(timeout=10.0)
        except Exception as e:
            print(f"[三月·守护] bg 任务清理异常: {e}", file=sys.stderr)

        for name, cleanup in [
            ("冰神·watcher", lambda: state.skill_hot_loader.stop() if state.skill_hot_loader else None),
            ("三月", lambda: state.march.stop() if state.march else None),
            ("地脉", lambda: state.leyline.stop() if state.leyline else None),
            ("世界树", lambda: state.irminsul.close() if state.irminsul else None),
        ]:
            try:
                coro = cleanup()
                if coro:
                    await coro
            except Exception as e:
                print(f"[三月·守护] {name}关闭异常: {e}", file=sys.stderr)


def entry():
    """三月守护：崩溃自动重启，防止 crash loop。"""
    crashes: list[float] = []
    while True:
        try:
            asyncio.run(main())
            break
        except KeyboardInterrupt:
            break
        except SystemExit:
            break
        except Exception as e:
            now = time.time()
            crashes = [t for t in crashes if now - t < _RESTART_WINDOW]
            crashes.append(now)

            if len(crashes) >= _MAX_RESTARTS:
                print(
                    f"[三月·守护] {_RESTART_WINDOW}s 内崩溃 {len(crashes)} 次，放弃重启",
                    file=sys.stderr,
                )
                sys.exit(1)

            print(
                f"[三月·守护] 派蒙崩溃: {e}，{_RESTART_DELAY}s 后重启 "
                f"({len(crashes)}/{_MAX_RESTARTS})",
                file=sys.stderr,
            )
            time.sleep(_RESTART_DELAY)


if __name__ == "__main__":
    entry()
