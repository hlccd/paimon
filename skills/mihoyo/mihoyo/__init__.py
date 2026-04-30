"""米游社 API 独立客户端（抄 gsuid_core 核心，去掉 Bot/DB 耦合）。

所有请求函数**无状态**：Cookie/Stoken/Fp/DeviceId 由调用方传入，skill 不存。
paimon 侧水神负责读写世界树 mihoyo_account 表。
"""
from . import actions, api, device, sign, server
