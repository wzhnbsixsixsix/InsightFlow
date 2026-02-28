"""
InsightFlow 配置管理器
文件路径: src/config.py

加载 .env 环境变量和 YAML 配置文件，提供统一的配置访问接口。
"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


class Config:
    """单例配置管理器"""

    _instance = None
    _config: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """加载 .env 和 YAML 配置"""
        # 加载 .env
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        # 加载 YAML 配置
        yaml_path = PROJECT_ROOT / "config" / "insightflow_config.yaml"
        if yaml_path.exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        通过点号路径获取配置值。

        示例:
            config.get("sales_leads.search.max_search_tasks")  -> 8
            config.get("model.temperature")  -> 0.3
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def dashscope_api_key(self) -> str:
        """DashScope API Key"""
        key = os.getenv("DASHSCOPE_API_KEY", "")
        if not key:
            raise ValueError("DASHSCOPE_API_KEY 未设置。请在 .env 文件中配置。")
        return key

    @property
    def search_provider(self) -> str:
        """搜索引擎提供者: duckduckgo | bocha | tavily"""
        return os.getenv("SEARCH_PROVIDER", "duckduckgo").lower()

    @property
    def tavily_api_key(self) -> str:
        """Tavily Search API Key"""
        return os.getenv("TAVILY_API_KEY", "")

    @property
    def bocha_api_key(self) -> str:
        """博查搜索 API Key"""
        return os.getenv("BOCHA_API_KEY", "")

    @property
    def qcc_mcp_key(self) -> str:
        """企查查 MCP Key"""
        return os.getenv("QCC_MCP_KEY", "")

    @property
    def output_dir(self) -> str:
        """销售线索输出目录"""
        return self.get("sales_leads.output.output_dir", "outputs/sales_leads")

    def get_model_name(self, agent_id: str) -> str:
        """获取指定 Agent 的模型名称"""
        return self.get(
            f"sales_leads.models.{agent_id}",
            "unknown-model",
        )

    def get_depth_preset(self, depth: str) -> dict:
        """获取搜索深度预设"""
        return self.get(
            f"sales_leads.depth_presets.{depth}",
            {"search_tasks": 30, "max_leads": 350, "timeout_minutes": 12},
        )
