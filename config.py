import os
from dataclasses import dataclass, field
from typing import List

CHART_DIR = "temp_charts"
CHART_DIR_ABS = os.path.join(os.path.dirname(os.path.abspath(__file__)), CHART_DIR)


@dataclass
class LLMProvider:
    name: str
    provider_type: str  # "deepseek" or "openai_like"
    default_model: str
    models: List[str]
    base_url: str = ""
    env_key_name: str = ""


PROVIDERS = {
    "DeepSeek": LLMProvider(
        name="DeepSeek",
        provider_type="deepseek",
        default_model="deepseek-chat",
        models=["deepseek-chat", "deepseek-reasoner"],
        base_url="https://api.deepseek.com",
        env_key_name="DEEPSEEK_API_KEY",
    ),
    "Kimi": LLMProvider(
        name="Kimi",
        provider_type="openai_like",
        default_model="moonshot-v1-8k",
        models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        base_url="https://api.moonshot.cn/v1",
        env_key_name="MOONSHOT_API_KEY",
    ),
    "MiniMax": LLMProvider(
        name="MiniMax",
        provider_type="openai_like",
        default_model="MiniMax-M2.5",
        models=["MiniMax-M2.5"],
        base_url="https://api.minimaxi.com/v1",
        env_key_name="MINIMAX_API_KEY",
    ),
}
