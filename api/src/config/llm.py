from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Driver = Literal["local", "chatgpt", "claude", "gemini", "deepseek"]

class LlmConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="LLM_")

    driver          : Driver = "local"
    timeout         : float  = Field(default=60.0, gt=0, le=600)
    retries         : int    = Field(default=1, ge=0, le=5)
    session_ttl     : float  = Field(default=3600.0, gt=0)
    local_url       : str    = "http://127.0.0.1:11434/v1"
    local_model     : str    = "llama3.2"
    local_key       : str    = ""
    openai_key      : str    = ""
    openai_model    : str    = "gpt-5"
    openai_url      : str    = "https://api.openai.com/v1"
    anthropic_key   : str    = ""
    anthropic_model : str    = "claude-sonnet-5-5"
    anthropic_url   : str    = "https://api.anthropic.com"
    gemini_key      : str    = ""
    gemini_model    : str    = "gemini-2.5-flash"
    gemini_url      : str    = "https://generativelanguage.googleapis.com"
    deepseek_key    : str    = ""
    deepseek_model  : str    = "deepseek-chat"
    deepseek_url    : str    = "https://api.deepseek.com/v1"
