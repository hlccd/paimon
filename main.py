import asyncio

from paimon.bootstrap import create_app
from paimon.config import config
from paimon.log import setup_logging
from paimon.state import state


async def main():
    setup_logging(debug=config.debug, log_dir=config.paimon_home)

    channels = create_app(config)

    if not channels:
        raise RuntimeError(
            "未配置任何频道 (请检查 .env 中的 WEBUI_ENABLED / BOT_TOKEN / QQ_APPID)"
        )

    if state.gnosis:
        state.gnosis.setup_pools()

    if state.primogem:
        await state.primogem.initialize()

    try:
        await asyncio.gather(*(ch.start() for ch in channels))
    except KeyboardInterrupt:
        pass
    finally:
        if state.primogem:
            await state.primogem.close()


def entry():
    asyncio.run(main())


if __name__ == "__main__":
    entry()
