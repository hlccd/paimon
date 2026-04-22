import asyncio

from paimon.bootstrap import create_app
from paimon.config import config
from paimon.log import setup_logging
from paimon.state import state


async def main():
    setup_logging(debug=config.debug, log_dir=config.paimon_home)

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

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        pass
    finally:
        if state.leyline:
            await state.leyline.stop()
        if state.irminsul:
            await state.irminsul.close()


def entry():
    asyncio.run(main())


if __name__ == "__main__":
    entry()
