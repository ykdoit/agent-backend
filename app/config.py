"""
Application configuration

配置分离：
- .env: 存放敏感密钥
- config.yml: 存放模型配置
- skills_dir: 从环境变量或默认值读取
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional, Dict, Any, List
import yaml


# 配置文件路径
ENV_FILE = Path(__file__).parent.parent / ".env"
CONFIG_FILE = Path(__file__).parent.parent / "config.yml"


def load_yaml_config() -> Dict[str, Any]:
    """加载 YAML 配置文件"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "Enterprise Office Agent"
    debug: bool = False
    
    # API Key (从 .env 读取)
    llm_api_key: Optional[str] = None
    
    # Skills 目录（支持多个目录，用逗号分隔）
    # 示例: /path/to/skills,/another/path/skills
    skills_dir: str = ""
    
    # MCP Server URLs
    oa_mcp_server_url: str = "http://localhost:3001"
    sales_mcp_server_url: str = "http://localhost:3002"
    qj_mcp_server_url: str = "http://localhost:3003"
    
    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    def get_skills_dirs(self) -> List[str]:
        """
        获取 skills 目录列表
        
        优先级：
        1. 环境变量 SKILLS_DIR (.env)
        2. config.yml 中的 skills.dirs
        3. 默认目录 backend/skills
        """
        # 优先级 1: 环境变量
        if self.skills_dir:
            dirs = []
            for d in self.skills_dir.split(","):
                d = d.strip()
                if d:
                    path = Path(d)
                    if not path.is_absolute():
                        path = Path(__file__).parent.parent / path
                    dirs.append(str(path))
            return dirs
        
        # 优先级 2: config.yml
        yaml_config = load_yaml_config()
        skills_config = yaml_config.get("skills", {})
        yaml_dirs = skills_config.get("dirs", "")
        if yaml_dirs:
            dirs = []
            for d in yaml_dirs.split(","):
                d = d.strip()
                if d:
                    path = Path(d)
                    if not path.is_absolute():
                        path = Path(__file__).parent.parent / path
                    dirs.append(str(path))
            return dirs
        
        # 优先级 3: 默认目录
        default_dir = str(Path(__file__).parent.parent / "skills")
        return [default_dir]


# 全局配置实例
_settings: Optional[Settings] = None
_model_config: Optional[Dict[str, Any]] = None
_yaml_config: Optional[Dict[str, Any]] = None


def get_settings() -> Settings:
    """获取配置实例"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_model_config(model_name: str = "default_model") -> Dict[str, Any]:
    """
    获取模型配置
    
    Args:
        model_name: 配置名称，默认为 default_model
    
    Returns:
        模型配置字典，包含 model_name, base_url, generate_args 等
    """
    global _model_config
    if _model_config is None:
        _model_config = load_yaml_config()
    
    config = _model_config.get(model_name, {})
    
    # 如果没有找到配置，返回默认值
    if not config:
        config = {
            "model_name": "gpt-3.5-turbo",
            "base_url": "https://api.openai.com/v1",
            "generate_args": {}
        }
    
    return config


def get_redis_config() -> Dict[str, Any]:
    """
    获取 Redis 配置
    
    Returns:
        Redis 配置字典
    """
    global _yaml_config
    if _yaml_config is None:
        _yaml_config = load_yaml_config()
    
    return _yaml_config.get("redis", {
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "password": None
    })


def get_state_management_config() -> Dict[str, Any]:
    """
    获取状态管理配置
    
    Returns:
        状态管理配置字典
    """
    global _yaml_config
    if _yaml_config is None:
        _yaml_config = load_yaml_config()
    
    return _yaml_config.get("state_management", {
        "session_expire_hours": 24,
        "dialog_history_limit": 100,
        "skill_context_expire_hours": 12,
        "enable_persistence": True
    })


# ============== 新增 AppConfig 类（适配 manager.py）==============

from pydantic import BaseModel


class LLMConfig(BaseModel):
    """LLM 配置"""
    model_name: str = "glm-4.7"
    base_url: str = "https://api.z.ai/api/coding/paas/v4"
    api_key: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2000


class MCPConfig(BaseModel):
    """MCP 配置"""
    oa_server_url: str = "http://localhost:3001"
    sales_server_url: str = "http://localhost:3002"
    qj_server_url: str = "http://localhost:3003"


class AppConfig(BaseModel):
    """应用配置（适配 manager.py）"""
    llm: LLMConfig = LLMConfig()
    mcp: MCPConfig = MCPConfig()
    skills_dir: str = ""
    
    @classmethod
    def from_settings(cls) -> "AppConfig":
        """从 Settings 和 YAML 配置创建 AppConfig"""
        settings = get_settings()
        model_config = get_model_config("default_model")
        yaml_cfg = load_yaml_config()
        
        llm_config = LLMConfig(
            model_name=model_config.get("model_name", "glm-4.7"),
            base_url=model_config.get("base_url", "https://api.z.ai/api/coding/paas/v4"),
            api_key=settings.llm_api_key,
            temperature=model_config.get("generate_args", {}).get("temperature", 0.7),
            max_tokens=model_config.get("generate_args", {}).get("max_tokens", 2000),
        )
        
        mcp_config = MCPConfig(
            oa_server_url=settings.oa_mcp_server_url,
            sales_server_url=settings.sales_mcp_server_url,
            qj_server_url=settings.qj_mcp_server_url,
        )
        
        return cls(
            llm=llm_config,
            mcp=mcp_config,
            skills_dir=settings.get_skills_dirs()[0] if settings.get_skills_dirs() else "",
        )


def get_app_config() -> AppConfig:
    """获取 AppConfig 实例"""
    return AppConfig.from_settings()
