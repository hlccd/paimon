from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    debug: bool = False

    # ========== LLM Provider 选择 ==========
    # 选项: "claude-xiaomi" | "claude-official" | "openai"
    llm_provider: str = "openai"
    llm_deep_provider: str = ""
    gnosis_shallow_concurrency: int = 5
    gnosis_deep_concurrency: int = 2

    # ========== Claude 小米内网 ==========
    claude_xiaomi_api_key: str = ""
    claude_xiaomi_base_url: str = "http://model.mify.ai.srv/anthropic"
    claude_xiaomi_model: str = "ppio/pa/claude-opus-4-6"

    # ========== Claude 官方 ==========
    claude_official_api_key: str = ""
    claude_official_base_url: str = "https://api.anthropic.com"
    claude_official_model: str = "claude-opus-4-6"

    # ========== OpenAI ==========
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4"

    # ========== MiMo (音视频理解) ==========
    mimo_key: str = ""
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_model: str = "mimo-v2-omni"

    # ========== 渠道配置 ==========
    webui_enabled: bool = True
    webui_host: str = "0.0.0.0"
    webui_port: int = 2975
    webui_access_code: str = ""
    bot_token: str = ""
    owner_id: int = 0
    qq_appid: str = ""
    qq_secret: str = ""
    qq_owner_ids: str = ""

    # ========== 系统配置 ==========
    # 默认锚定仓库根目录下的 .paimon/（code 与 state 同置）
    paimon_home: Path = Path(__file__).resolve().parent.parent / ".paimon"
    stream_interval: float = 1.0
    max_tokens: int = 64000
    context_window_tokens: int = 128000
    context_compress_threshold_pct: float = 75.0
    context_keep_recent_messages: int = 12

    # 天使超时 + 魔女会桥（docs/angels/angels.md §运作方式）
    # 单次 tool call 超时 → 第一次自愈（返错误给模型）、连续 2 次触发魔女会
    # 整体任务超时（仅 skill 路径）→ 直接触发魔女会
    angel_tool_timeout_seconds: int = 30
    angel_total_timeout_seconds: int = 180

    # 冰神 skill 热重载（默认关闭，生产避免意外启用）
    # 开启后：watchdog 监听 skills/*/SKILL.md，create/modify 过死执审查，delete 标孤儿
    skills_hot_reload: bool = False

    # 派蒙入口轻量过滤（docs/paimon/paimon.md §轻量安全校验）
    # 默认开启；设 false 可在调试/误伤排查时临时绕过
    input_filter_enabled: bool = True

    # 四影闭环：草→水→雷多轮迭代上限（水神不通过时生执回炉最多 N 轮）
    # 默认 3；超过上限视为"尽力而为"返回最后一轮产物
    shades_max_rounds: int = 3

    # 时执·生命周期闭环（docs/shades/istaroth.md §核心能力）
    # 三月定时调度时执清扫；各阈值都可在 .env 覆盖
    lifecycle_sweep_enabled: bool = True
    lifecycle_sweep_interval_hours: int = 6      # 清扫频率（建议 [1, 168]）
    # 会话（session）
    session_inactive_hours: int = 6              # 无 updated → 标 archived_at
    session_archived_ttl_days: int = 90          # archived 超时彻底删除
    # 任务（task）—— 对齐 docs "热(30d) → 冷(30-90d) → 过期删除"
    task_running_timeout_hours: int = 1          # status=running 且无更新超时 → 视作卡死标 failed
    task_cold_ttl_days: int = 30                 # cold → archived
    task_archived_ttl_days: int = 60             # archived 超时删除（30+60=90 对齐 docs）

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"), env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("paimon_home", mode="before")
    @classmethod
    def expand_home(cls, v):
        if isinstance(v, str):
            return Path(v).expanduser()
        elif isinstance(v, Path):
            return v.expanduser()
        return v

    @property
    def provider(self) -> str:
        if self.llm_provider in ("claude-xiaomi", "claude-official"):
            return "anthropic"
        elif self.llm_provider == "openai":
            return "openai"
        else:
            raise ValueError(f"未知的 LLM_PROVIDER: {self.llm_provider}")

    @property
    def api_key(self) -> str:
        if self.llm_provider == "claude-xiaomi":
            return self.claude_xiaomi_api_key
        elif self.llm_provider == "claude-official":
            return self.claude_official_api_key
        elif self.llm_provider == "openai":
            return self.openai_api_key
        else:
            raise ValueError(f"未知的 LLM_PROVIDER: {self.llm_provider}")

    @property
    def api_base_url(self) -> str:
        if self.llm_provider == "claude-xiaomi":
            return self.claude_xiaomi_base_url
        elif self.llm_provider == "claude-official":
            return self.claude_official_base_url
        elif self.llm_provider == "openai":
            return self.openai_base_url
        else:
            raise ValueError(f"未知的 LLM_PROVIDER: {self.llm_provider}")

    @property
    def model(self) -> str:
        if self.llm_provider == "claude-xiaomi":
            return self.claude_xiaomi_model
        elif self.llm_provider == "claude-official":
            return self.claude_official_model
        elif self.llm_provider == "openai":
            return self.openai_model
        else:
            raise ValueError(f"未知的 LLM_PROVIDER: {self.llm_provider}")


config = Config()
