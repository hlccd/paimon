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
_RESTART_DELAY_BASE = 5      # 首次重启等待秒数
_RESTART_DELAY_MAX = 120     # 退避上限（避免崩溃越久重启越久）
_HEALTHY_RUN_SECONDS = 300   # 进程稳定运行 ≥ 此值视作健康，重置 crashes 计数


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
    """三月守护：崩溃自动重启，防止 crash loop。

    REL-014 改进：
    - 指数退避：5s → 10 → 20 → 40 → 80 → 120s 上限，避免反复立即重启耗资源
    - 健康运行重置：进程稳定跑 ≥ _HEALTHY_RUN_SECONDS 视作恢复，crashes 计数清零
      （否则一次零星崩溃后任何后续小问题都会触发"崩溃次数累计"）
    """
    crashes: list[float] = []
    while True:
        run_started_at = time.time()
        try:
            asyncio.run(main())
            break
        except KeyboardInterrupt:
            break
        except SystemExit:
            break
        except Exception as e:
            now = time.time()
            run_duration = now - run_started_at

            # 健康运行重置：本次跑了足够久，前面的崩溃记录视作已恢复
            if run_duration >= _HEALTHY_RUN_SECONDS:
                if crashes:
                    print(
                        f"[三月·守护] 上次运行 {int(run_duration)}s 视作健康，"
                        f"重置 crashes 计数（之前 {len(crashes)} 次）",
                        file=sys.stderr,
                    )
                crashes = []

            # 滑窗清理：只保留 _RESTART_WINDOW 内的崩溃
            crashes = [t for t in crashes if now - t < _RESTART_WINDOW]
            crashes.append(now)

            if len(crashes) >= _MAX_RESTARTS:
                print(
                    f"[三月·守护] {_RESTART_WINDOW}s 内崩溃 {len(crashes)} 次，放弃重启",
                    file=sys.stderr,
                )
                sys.exit(1)

            # 指数退避：5 → 10 → 20 → 40 → 80 → 上限
            delay = min(_RESTART_DELAY_BASE * (2 ** (len(crashes) - 1)), _RESTART_DELAY_MAX)
            print(
                f"[三月·守护] 派蒙崩溃: {e}，{delay}s 后重启 "
                f"({len(crashes)}/{_MAX_RESTARTS}, 本次跑 {int(run_duration)}s)",
                file=sys.stderr,
            )
            time.sleep(delay)


if __name__ == "__main__":
    entry()
