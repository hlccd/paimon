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
    mimo_api_key: str = ""
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_model: str = "mimo-v2-pro"

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
    paimon_home: Path = Path("~/.paimon").expanduser()
    stream_interval: float = 1.0
    max_tokens: int = 64000
    context_window_tokens: int = 128000
    context_compress_threshold_pct: float = 75.0
    context_keep_recent_messages: int = 12

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
