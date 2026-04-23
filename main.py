import asyncio
import sys
import time

from paimon.bootstrap import create_app
from paimon.config import config
from paimon.log import setup_logging
from paimon.state import state

_MAX_RESTARTS = 5
_RESTART_WINDOW = 300
_RESTART_DELAY = 5


async def main():
    setup_logging(debug=config.debug, log_dir=config.paimon_home)

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
